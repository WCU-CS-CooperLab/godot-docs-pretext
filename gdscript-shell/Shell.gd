# Shell.gd
# Attach to the root Node of your base web export scene (Shell.tscn).
#
# This is the entry point for the Runestone/Godot integration. It:
#   1. Registers window.godotShell.loadExercise() for Runestone's JS bridge to call.
#   2. Loads a per-exercise .pck file on demand.
#   3. Instantiates both the practice and solution scenes from the .pck.
#   4. Injects the student's code string into the practice scene's root script.
#   5. Runs GDPractice's test.gd pipeline against both scenes.
#   6. Posts results back to the Runestone host page via postMessage.
#   7. Forwards print() output to the Runestone host page via postMessage,
#      so it appears in the activecode output area rather than the console.

extends Node

const Paths := preload("res://addons/gdpractice/paths.gd")
const Test  := preload("res://addons/gdpractice/tester/test.gd")

# Holds the currently running practice and solution so we can free them on reset.
var _practice: Node = null
var _solution: Node = null
var _test: PracticeTest = null
var _parent_origin: String = "*"


# Keeps the JavaScriptBridge callback alive for the lifetime of this node.
# If this is not stored, it gets garbage collected and stops working.
var _js_callback: JavaScriptObject = null


func _ready() -> void:
	if OS.get_name() != "Web":
		push_warning("Shell: not running as a web export; JavaScriptBridge is inactive.")
		return

	_js_callback = JavaScriptBridge.create_callback(_on_js_message)
	
	# Get the iframe's own global window object
	var window = JavaScriptBridge.get_interface("window")
	window.godotLoadExerciseCallback = _js_callback
	
	# Register a JavaScript message event listener inside the iframe context
	JavaScriptBridge.eval("""
		if (typeof window.hostOrigin === 'undefined') {
		    window.hostOrigin = null;
	    }

		window.addEventListener('message', (event) => {
			if (!window.hostOrigin && event.data && event.data.type === 'loadExercise') {
				window.hostOrigin = event.origin;
			}
			
			if (event.origin !== window.hostOrigin) return;
			
			if (event.data && event.data.type === 'loadExercise') {
				if (window.godotLoadExerciseCallback) {
					window.godotLoadExerciseCallback(event.data.payload);
				}
			}
		});
	""", true)

	# Expose a single callable on window.godotShell so activecode.js can call it.
	# activecode.js calls:
	# window.godotShell.loadExercise({ pck, scene, code, test })
	#_js_callback = JavaScriptBridge.create_callback(_on_js_message)
	#JavaScriptBridge.eval("window.godotShell = {};", true)
	#var godot_shell = JavaScriptBridge.get_interface("godotShell")
	#godot_shell.loadExercise = _js_callback

	# Connect console.log inside this iframe so that Godot's print()
	# output (which the web export routes to console.log) is forwarded to
	# the Runestone host page as a { type: "print" } postMessage, in addition
	# to still appearing in the browser console.
	# activecode_gdscript.js handles these messages and appends each line to
	# the activecode output area so students can see their print() output.
	JavaScriptBridge.eval("""
		(function() {
			var _origLog = console.log.bind(console);
			console.log = function() {
				_origLog.apply(console, arguments);
				var text = Array.prototype.join.call(arguments, ' ');
				
				var target = window.hostOrigin || '*';
				
				window.parent.postMessage({
					source:  'godot-activecode',
					subject: 'runestone',
					type:    'print',
					text:    text
				}, target);
			};
		})();
	""", true)

	# Tell the host page we're ready to receive exercises.
	_post_to_runestone({ "type": "ready" })


# ------------------------------------------------------------
# Receives the JS payload and dispatches to _load_exercise().
# JavaScriptBridge passes JS arguments as an Array; args[0] is the payload object.
# ------------------------------------------------------------
func _on_js_message(args: Array) -> void:
	if args.is_empty():
		push_error("Shell: received empty message from JS.")
		return

	var raw = args[0]
	var payload := {
		"pck":   str(raw.pck)   if "pck"   in raw else "",
		"scene": str(raw.scene) if "scene" in raw else "",
		"code":  str(raw.code)  if "code"  in raw else "",
		"test":  str(raw.test)  if "test"  in raw else "",
		"origin": str(raw.origin) if "origin" in raw else "*",
	}
	_parent_origin = payload["origin"]
	_load_exercise(payload)


# ------------------------------------------------------------
# Main entry point. Loads the .pck, instantiates scenes,
# injects student code, and runs the GDPractice check pipeline.
#
# payload keys:
#   pck   — relative URL of the .pck file, e.g. "ch01_p1.pck"
#            (empty string means the scene is already in the base export)
#   scene — res:// path of the practice scene inside the .pck,
#            e.g. "res://practices/L1.P1.example/practice.tscn"
#   code  — the student's GDScript source as a plain string
#   test  — the instructor's GDScript test source as a plain string
# ------------------------------------------------------------
func _load_exercise(payload: Dictionary) -> void:
	var pck_path: String    = payload.get("pck", "")
	var scene_path: String  = payload.get("scene", "")
	var student_code: String = payload.get("code", "")
	var test_code: String =    payload.get("test", "")

	if scene_path.is_empty():
		_post_error("No scene path provided.")
		return

	# ── Step 1: load the per-exercise .pck if one was specified ───────────────
	# On web, the path is a URL relative to the directory containing index.html.
	if not pck_path.is_empty():
		var http := HTTPRequest.new()
		add_child(http)
		http.request(pck_path)
		var response = await http.request_completed
		http.queue_free()

		var result_code  = response[0]
		var http_code    = response[1]
		var body: PackedByteArray = response[3]

		if result_code != HTTPRequest.RESULT_SUCCESS or http_code != 200:
			_post_error("Could not fetch exercise pack: %s (HTTP %d)" % [pck_path, http_code])
			return
		
		# Write bytes to a temporary path in Godot's virtual filesystem,
		# then load from there.
		var tmp_path := "user://tmp_exercise.pck"
		var file := FileAccess.open(tmp_path, FileAccess.WRITE)
		file.store_buffer(body)
		file.close()

		var ok := ProjectSettings.load_resource_pack(tmp_path)
		if not ok:
			_post_error("Could not mount exercise pack: " + pck_path)
			return

	# ── Step 2: tear down any previously running exercise ─────────────────────
	_teardown()
	# Wait one frame to let queue_free() fully process before adding new nodes.
	await get_tree().process_frame

	# ── Step 3: verify the practice scene exists ──────────────────────────────
	if not ResourceLoader.exists(scene_path):
		_post_error("Practice scene not found: " + scene_path)
		return

	# ── Step 4: instantiate the practice scene and inject the student's code ──
	var practice_packed: PackedScene = ResourceLoader.load(scene_path, "", ResourceLoader.CACHE_MODE_IGNORE)
	_practice = practice_packed.instantiate()

	# Create a GDScript resource from the student's code string and attach it
	# to the practice scene root. This replaces whatever starter script was
	# in the scene with the student's live submission.
	var student_script := GDScript.new()
	student_script.source_code = student_code
	var reload_err := student_script.reload()

	if reload_err != OK:
		# Syntax error — report back without crashing. Don't add the scene yet.
		_post_error("Syntax error in your code. Check for typos and indentation.")
		return

	_practice.set_script(student_script)
	add_child(_practice)

	# ── Step 5: instantiate the solution scene ────────────────────────────────
	# GDPractice requires both scenes for its comparison-based check system.
	# The solution scene lives at the parallel path under practice_solutions/.
	var solution_path: String = Paths.to_solution(scene_path)
	if not ResourceLoader.exists(solution_path):
		_post_error("Solution scene not found: " + solution_path)
		return

	var solution_packed: PackedScene = ResourceLoader.load(solution_path, "", ResourceLoader.CACHE_MODE_IGNORE)
	_solution = solution_packed.instantiate()
	# Add solution as a child but hide it — it only exists for state comparison.
	if _solution is CanvasItem:
		_solution.visible = false
	add_child(_solution)

	# ── Step 6: 
	# Create a GDScript resource from the testing code string and attach it
	# to the practice scene root. 
	var test_script : Script = GDScript.new()
	test_script.source_code = test_code
	var test_reload_err := test_script.reload()

	if test_reload_err != OK:
		# Syntax error — report back without crashing. Don't add the scene yet.
		_post_error("Syntax error in testing code. Check for typos and indentation.")
		return

	_test = test_script.new()
	add_child(_test)

	# Run the full GDPractice check pipeline.
	await _run_checks()


# ------------------------------------------------------------
# Runs the GDPractice check pipeline and posts results back
# to Runestone. Mirrors the sequence in ui_test_panel.gd.
# ------------------------------------------------------------
func _run_checks() -> void:
	# setup() waits one frame internally, then reads the practice script
	# and populates _practice_code for use by _is_code_line_match() etc.
	await _test.setup(_practice, _solution)

	# Requirements are preconditions (e.g. "did the student modify the file?",
	# "are required input actions present?"). A failed requirement aborts checks.
	_test.setup_requirements()
	var requirements_passed := await _check_requirements()
	if not requirements_passed:
		return

	# setup_checks() runs _setup_state() and _setup_populate_test_space(),
	# then _build_checks() — this is where the exercise-specific test.gd
	# populates the checks array.
	await _test.setup_checks()

	# Run each check individually with await so we respect any async checks
	# (e.g. checks that simulate input events over multiple frames).
	# Note: test.run() does NOT await internally, so we do it here instead.
	for check in _test.checks:
		await check.run()

	# ── Build and post the result payload ────────────────────────────────────
	var completion: int = _test.get_completion()  # 1 = all passed, 0 = any failed
	var passed: bool = completion == 1
	var score: float = 0
	var total: float = 0

	var check_results: Array = []
	for check in _test.checks:
		var check_data := {
			"description": check.description,
			"hint":        check.hint,
			"status":      _status_to_string(check.status),
			"passed":      check.status == Test.Status.PASS,
		}
		score += 1 if check.status == Test.Status.PASS else 0
		total += 1
		# Include subchecks so Runestone can show granular feedback.
		var subchecks: Array = []
		for subcheck in check.subchecks:
			subchecks.append({
				"description": subcheck.description,
				"hint":        subcheck.hint,
				"status":      _status_to_string(subcheck.status),
				"passed":      subcheck.status == Test.Status.PASS,
			})
			score += 1 if check.status == Test.Status.PASS else 0
			total += 1
		
		check_data["subchecks"] = subchecks
		check_results.append(check_data)

	_post_to_runestone({
		"type":    "result",
		"passed":  passed,
		"score":   0.0 if total == 0.0 else score/total,
		"checks":  check_results,
	})


# ------------------------------------------------------------
# Runs requirements and returns false if any fail.
# Posts a result message describing which requirements failed.
# ------------------------------------------------------------
func _check_requirements() -> bool:
	var all_passed := true
	var failed_requirements: Array = []

	for requirement in _test.requirements:
		var hint: String = await requirement.check()
		if not hint.is_empty():
			all_passed = false
			failed_requirements.append({
				"description": requirement.description,
				"hint":        hint,
			})

	if not all_passed:
		_post_to_runestone({
			"type":         "result",
			"passed":       false,
			"score":        0.0,
			"checks":       [],
			"requirements": failed_requirements,
		})

	return all_passed


# ------------------------------------------------------------
# Frees the practice scene, solution scene, and test node
# from the previous exercise run.
# ------------------------------------------------------------
func _teardown() -> void:
	if _test != null:
		_test.queue_free()
		_test = null
	if _solution != null:
		_solution.queue_free()
		_solution = null
	if _practice != null:
		_practice.queue_free()
		_practice = null


# ------------------------------------------------------------
# Converts a Test.Status enum value to a plain string for JSON.
# ------------------------------------------------------------
func _status_to_string(status: int) -> String:
	match status:
		Test.Status.PASS:     return "pass"
		Test.Status.FAIL:     return "fail"
		Test.Status.DISABLED: return "disabled"
		_:                    return "unknown"


# ------------------------------------------------------------
# Posts a structured error message back to Runestone.
# ------------------------------------------------------------
func _post_error(message: String) -> void:
	push_error("Shell: " + message)
	_post_to_runestone({ "type": "error", "message": message })


# ------------------------------------------------------------
# Sends any Dictionary payload to the Runestone host page.
# activecode.js listens for window message events where
# event.data.source === "godot-activecode".
#
# Uses window.parent so this works whether Godot is in an
# <iframe> (production) or the top-level window (testing).
# ------------------------------------------------------------
func _post_to_runestone(data: Dictionary) -> void:
	if OS.get_name() != "Web":
		print("Shell (non-web postMessage): ", JSON.stringify(data))
		return

	data["source"] = "godot-activecode"
	data["subject"] = "runestone"  # satisfies SpliceWrapper
	
	var json := JSON.stringify(data)
	JavaScriptBridge.eval(
		"window.parent.postMessage(%s, '%s');" % [json, _parent_origin],
		true
	)
