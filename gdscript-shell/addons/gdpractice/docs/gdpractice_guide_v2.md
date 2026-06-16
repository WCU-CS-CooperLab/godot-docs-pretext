# GDPractice Addon Guide

This guide documents the `gdpractice` addon as used in this project: how to author a
practice exercise, how the testing framework (`test.gd`) works, what the in-editor
authoring tools look like, and how everything maps onto the `Shell.gd` / Runestone
web deployment.

Location: `gdscript-shell/addons/gdpractice/docs/gdpractice_guide.md`

---

## 1. Overview & directory structure

GDPractice is built around two parallel trees under `res://`:

- `practice_solutions/<dir>/` — the instructor's complete, working reference:
  scene(s), script(s), a `test.gd`, and optionally a `diff.gd`.
- `practices/<dir>/` — the student-facing starting point. This tree is
  **generated** from `practice_solutions/` by `build.gd`; you should not hand-edit
  it (any hand edits are overwritten the next time the practice is built or reset).

`addons/gdpractice/paths.gd` defines the roots and a few helpers used everywhere
else in the addon:

```gdscript
const RES := "res://"
const PRACTICES_PATH := "res://practices"
const SOLUTIONS_PATH := "res://practice_solutions"

static func to_solution(path: String) -> String:
    return path.replace(PRACTICES_PATH, SOLUTIONS_PATH)

static func to_practice(path: String) -> String:
    return path.replace(SOLUTIONS_PATH, PRACTICES_PATH)

static func get_dir_name(path: String, relative_to := SOLUTIONS_PATH) -> String:
    ...
```

`to_solution()` / `to_practice()` are plain string substitutions between the two
roots — they're how the test panel, the build script, and `Shell.gd` all find "the
other half" of a practice/solution pair given either path. `get_dir_name()` strips
a root prefix and returns just the immediate practice folder name (e.g.
`L1.P2.velocity_comparison`), which is what feeds the naming convention in the next
section.

---

## 2. Naming convention & metadata registration

Every practice lives in a directory named:

```
L<lesson_number>.P<practice_number>[.optional_suffix]
```

e.g. `L1.P1.double_value`, `L1.P2.velocity_comparison`. This is enforced by a regex
in `metadata.gd`'s `PracticeMetadata` class:

```gdscript
var _dir_name_regex := RegEx.create_from_string(r"^L(\d+)\.P(\d+)(\..+)?$")
```

`practice_solutions/metadata.gd` extends the addon's base `Metadata` class and
populates `list: Array[PracticeMetadata]`, one entry per practice:

```gdscript
@tool
extends "res://addons/gdpractice/metadata.gd"

func _init() -> void:
    list.append(PracticeMetadata.new(
        "double_value",       # id — must be unique within the project
        "Double the value",   # title shown in the dock
        preload("res://practice_solutions/L1.P1.double_value/practice.tscn"),
        []                    # scripts_to_open (optional, see below)
    ))
```

`PracticeMetadata._init()` takes `(id, title, packed_scene, scripts_to_open := [])`.
It derives the directory name from `packed_scene.resource_path` (via
`Paths.get_dir_name()`), runs it through the regex above, and computes:

- `lesson_number`, `practice_number` — parsed integers
- `item` — `"L1.P1"` style label shown in the dock
- `full_title` — `"L1.P1 Double the value"`

**Important gotcha:** if the directory name doesn't match the regex, `regex_match`
is `null` and the very next line (`regex_match.strings[1].to_int()`) is a
null-reference error — registering a `PracticeMetadata` for a non-conforming
directory name will hard-error in the editor, not just print a warning.

Each Godot project starts its own numbering at `L1.P1` — there's no shared registry
between projects, so there's no risk of collision.

### Why this matters even though Shell.gd doesn't read it

`Shell.gd` (the Runestone/web deployment path, see §7) never touches `Metadata`,
`PracticeMetadata`, or the progress database — it gets everything it needs (scene
paths, test source) directly from the JS payload. The naming convention and
metadata registration exist purely for the **in-editor authoring workflow** (§5):
the GDQuest dock, the live test panel, and progress tracking are all driven by
`metadata.list`. Keeping this registration unlocks the live SplitLayout test panel
while you're writing `test.gd`, which is well worth the small overhead.

`id` feeds `db/progress.gd`'s `state` dictionary (`{completion, tries}` per id) and
must be unique within the project. `scripts_to_open` lets you specify which
script(s) should open automatically when a student selects this practice in the
dock — if left empty, the dock opens the practice scene's root node's script.

---

## 3. The build pipeline (`build.gd`)

`build.gd` converts `practice_solutions/<dir>/` into `practices/<dir>/`. It's run
via:

```
godot --headless --script addons/gdpractice/build.gd -- --generate-practices
```

It's also triggered for a single practice by the dock's per-practice **Reset**
button (see §5).

For every file in a solution directory except `test.gd` and `diff.gd`, the file is
copied to the parallel `practices/` path. `.gd` and `.tscn` files get additional
processing.

### Comment-based stub syntax (`.gd` files)

`build.gd` looks for a trailing `#` comment on each non-comment-only line and
rewrites the line based on what follows the `#`:

| Solution line | Resulting practice line | Effect |
|---|---|---|
| `position += velocity * delta # position` | `position` | Code replaced by the comment text, same indentation |
| `@export var speed := 200.0 # @export var speed := 0.0` | `@export var speed := 0.0` | Any valid GDScript can be the replacement — useful for changing export defaults without `diff.gd` |
| `for column in range(columns): #` | *(line deleted)* | Empty trailing comment deletes the line entirely |
| `var cell := Vector2(column, row) # << var cell := Vector2(0, 0)` | `var cell := Vector2(0, 0)` *(dedented 2 levels)* | `<`/`>` each shift indentation by one level (`<` = outdent, `>` = indent) before substituting the rest |
| `    # explain something` *(pure comment, nothing before `#`)* | unchanged | Lines with no code before `#` are copied verbatim — these are the instructional comments students read |

This is how a fully-working solution script becomes a starter script with
fill-in-the-blank gaps, while keeping the solution itself fully readable and
runnable.

> **Gotcha — single `#` only:** the build regex matches the *last* `#` on a line.
> A line like `## Some doc comment` has `#` as the "code" part and `Some doc comment`
> as the "replacement" — the generated practice line becomes the bare text
> `Some doc comment`, which is almost certainly not what you want. **Use single `#`
> for all comments in `practice.gd`** (and any other `.gd` file that goes through
> the build pipeline). `test.gd` and `diff.gd` are never processed by `build.gd`
> and can use `##` doc comments freely.

> **Gotcha — return-type parse errors:** Godot 4 enforces that all code paths in a
> typed function return a value at parse time, not just at runtime. A stub that
> leaves a typed function body empty (e.g. replacing the only `return` line with
> `pass`) will produce a parse error when the generated practice script loads.
> Make sure every stub for a non-`void` function still contains a valid typed
> return statement — e.g. `return value` instead of `pass` for a function that
> returns `int`.

### `diff.gd` — structural differences for `.tscn` files

If `practice_solutions/<dir>/diff.gd` exists and defines a static function whose
name exactly matches a `.tscn` file's basename (e.g. a function named `practice`
for `practice.tscn`), `build.gd` instantiates the **solution** scene, calls that
function on it, and packs the *mutated* result as the practice scene.

Use `diff.gd` only when you need to make a **structural** change to the scene that
can't be expressed as a script-line substitution — for example, removing a node the
student is meant to add, or changing a node's type. For simple property changes
(export defaults, initial values), the comment-stub syntax is cleaner:

```gdscript
# In practice.gd (solution side):
@export var speed := 200.0 # @export var speed := 0.0
# Generated practice has: @export var speed := 0.0
# No diff.gd needed.
```

A minimal `diff.gd` looks like:

```gdscript
static func practice(scene: Node) -> void:
    scene.get_node("NodeToRemove").queue_free()
```

If no matching function exists for a given `.tscn`, that scene is copied unchanged
(a `[SKIP]` line is printed in the Output panel).

### Project-level `diff.gd`

Separately, `practice_solutions/diff.gd` (at the root, not per-practice) can define
`edit_project_configuration()`, called once via `--do-project-diff` when building
the whole workbook project. In this repo it strips all non-`ui_*` input actions from
`project.godot` — a project-wide cleanup step, unrelated to per-practice `diff.gd`.

### `.file_checksums.json`

After building a practice, `build.gd` writes
`practices/<dir>/.file_checksums.json` — an MD5 checksum per generated file
(skipping `.uid` files). This is read by `test.gd`'s default
`_add_file_modified_requirement()` (§4) to detect whether the student has actually
edited anything.

---

## 4. Writing `test.gd`

Each `practice_solutions/<dir>/test.gd` extends
`res://addons/gdpractice/tester/test.gd` (`class_name PracticeTest`). It's
instantiated and driven through the same lifecycle by both the editor's test panel
(`ui_test_panel.gd`) and `Shell.gd`:

```
setup(practice, solution)
  → setup_requirements() → _build_requirements()
  → [run requirements; abort here if any fail]
  → setup_checks() → _setup_state() → _setup_populate_test_space() → _build_checks()
  → run() → each Check.run()
  → get_completion()  # 1 if every top-level check is PASS, else 0
```

### `setup(practice, solution)`

Waits one frame (so the practice scene has had time to enter `_ready`), stores
`_practice` / `_solution`, and — if the practice node has a script — preprocesses
its source into `_practice_code: Array[String]` for use with
`_is_code_line_match()`. The preprocessing strips **all whitespace** (including
internal spaces) and drops empty/comment-only lines, so patterns for
`_is_code_line_match()` should not contain spaces.

### Requirements

A `Requirement` has a `description` and an async `checker: Callable -> String`
(empty string = passes; non-empty = a hint shown to the student, and **checks are
not run at all** if any requirement fails). The base class's `_build_requirements()`
always calls:

- `_add_file_modified_requirement()` — reads `.file_checksums.json` next to the
  practice scene, MD5-compares each listed file (ignoring the scene file itself,
  since Godot rewrites it on save/run), and if *nothing* changed, returns a hint
  suggesting the student check they're working in the right file/scene.

Override `_build_requirements()` (calling `super()` first) to add more:

- `_add_actions_requirement(actions: Array)` — fails if any named `InputMap`
  action doesn't exist in the project. Also activates the directional arrow overlay
  in the input feedback UI (§5) for the four standard movement actions.
- `_add_properties_requirement(properties: Array[String], object := _practice)` —
  fails if `object` is missing any listed property (e.g. the student deleted an
  exported variable).
- `_add_callable_requirement(description, checker, params := [])` — generic
  wrapper for any custom `String`-returning checker; this is also how you wire in
  the structural guardrails from `requirements.gd` (§6).

### Checks

A `Check` has `description`, `hint`, `status` (`DISABLED` / `PASS` / `FAIL`), a
`checker: Callable -> String`, optional `dependencies: Array[Check]` (a check is
`DISABLED` if any dependency hasn't passed), and optional `subchecks: Array[Check]`
(a check only runs its subchecks if its own `checker` passes; the check's result is
the last subcheck's result, with early exit on first failure).

`_add_simple_check(description, checker) -> Check` creates a `Check`, appends it to
`checks`, and returns it so you can attach `dependencies`/`subchecks`.

### State setup & the `_test_space` pattern

Two virtual hooks called once per test run before `_build_checks()`:

- **`_setup_state()`** — synchronise starting conditions between practice and
  solution before sampling begins. Always reset both nodes' positions (and any other
  relevant state) to a known value here, even if they started at `Vector2.ZERO` in
  the scene — both nodes begin receiving `_physics_process` calls as soon as they're
  added to the tree (before `_setup_state()` runs), so without an explicit reset,
  one or both nodes may have already moved by the time sampling starts.

```gdscript
func _setup_state() -> void:
    _practice.position = Vector2.ZERO   # reset before sampling
    _solution.position = Vector2.ZERO
    _solution.velocity = _practice.velocity  # mirror practice state onto solution
```

- **`_setup_populate_test_space()`** — gather samples into `_test_space: Array`
  over time, typically via `_connect_timed`:

```gdscript
func _setup_populate_test_space() -> void:
    await _connect_timed(1.0, get_tree().physics_frame, _sample_test_space)

func _sample_test_space() -> void:
    _test_space.append({
        practice_position = _practice.position,
        solution_position = _solution.position,
        delta = get_physics_process_delta_time(),
    })
```

> **Timing gotcha — `physics_frame` fires after `_physics_process`:** the signal
> fires *after* each physics frame has already run, so the first sample in
> `_test_space` reflects positions that have already been updated once since the
> reset in `_setup_state()`. This means:
>
> - Per-frame displacement comparisons between consecutive samples are reliable.
> - Comparisons that accumulate expected displacement from `_test_space` deltas
>   (e.g. summing `velocity * delta` across all samples and comparing to total
>   displacement) will be off by one frame and should be avoided.
> - Direct practice-vs-solution position comparisons are reliable as long as both
>   nodes are reset to the same starting position in `_setup_state()` — the one-frame
>   head-start affects both equally.

### Helper method reference

| Method | Purpose |
|---|---|
| `_call_all(method, arg_array := []) -> Dictionary` | Calls `method` on both `_practice` and `_solution`, returns `{practice: ..., solution: ...}`. Good for comparing function return values without needing `_test_space` at all. |
| `_set_all(property_path: NodePath, value)` | Sets the same property on both `_practice` and `_solution` via `set_indexed`. |
| `_is_sliding_window_pass(predicate: Callable) -> bool` | Walks consecutive pairs `(x, y)` in `_test_space`. Returns `true` only if `predicate(x, y)` is `true` for every consecutive pair. Write predicates that mean "this pair is good" — the function returns `true` only when *all* pairs are good. |
| `_is_code_line_match(target_lines: Array) -> bool` | `true` if any line in `_practice_code` matches (via `String.match`, glob-style) any pattern in `target_lines`. Remember `_practice_code` has all whitespace stripped. |
| `_connect_timed(time, sig, callback)` | Connects `callback` to `sig`, waits `time` seconds, then disconnects. Used in `_setup_populate_test_space()` to sample state over a fixed window. |
| `_load(pattern, is_practice := true) -> Resource` | Loads the single resource matching `pattern` under the test script's directory (practice or solution side), asserting exactly one match. |

> **Type inference in lambdas:** GDScript can't always infer the type of a variable
> assigned from a `Dictionary` value inside a lambda. Prefer explicit types where
> needed to avoid runtime errors — e.g. `var displacement: Vector2 = y.position - x.position`
> rather than `var displacement := y.position - x.position`.

---

## 5. The in-editor authoring & testing workflow

None of this section applies to the deployed Shell.gd/Runestone exercise — it's the
experience you get while developing a practice in the Godot editor, made possible
by the `metadata.gd` registration from §2.

### Finding the GDQuest dock

The practices dock is in the **GDQuest** tab in the right-hand dock area — the same
panel group as the Inspector/Node/History tabs (upper-right of the editor, alongside
the 3D/2D viewport). The plugin adds it via `add_control_to_dock(DOCK_SLOT_RIGHT_UL,
ui_practice_dock)` and the tab is labelled "GDQuest" with a "PRACTICES" header
inside. If you don't see it, check **Project → Project Settings → Plugins** and
confirm "GDQuest Practices" is enabled; also check the Output panel for any errors
from `gdpractice.gd` or `metadata.gd` that may have prevented the dock from loading.

### Practices dock (`ui_practice_dock` / `ui_selectable_practice`)

The dock lists every registered `PracticeMetadata` entry. Each entry shows:

- The `item` label (e.g. "L1.P1") and `title`.
- A checkbox reflecting `db/progress.gd` completion state for that `id`.
- A **Reset** button — re-runs `build_practice(dir_name, true)` for that practice,
  regenerating `practices/<dir>/` from the current solution (and `diff.gd` if
  present) and updating `.file_checksums.json`. The Reset button is visible when no
  generated practice scene exists yet (i.e. before the first build), and after a
  reset confirmation.
- When selected: opens the **practice** scene and calls `open_practice_scripts()`,
  which opens either the scripts listed in `scripts_to_open`, or — by default —
  the root node's script.
- A **Run** button (visible only when selected), which runs the current scene.

> **First-run progress error:** on the very first run, `db.gd` may fail to write
> `user://progress_v2.tres` with a "Can't open" error, because the `user://`
> directory doesn't exist until the game has been run at least once. This is
> non-fatal — the dock shows unchecked checkboxes and resolves itself the first time
> you run a practice scene.

> **Exclusive window conflict:** when Reset completes, it shows a confirmation
> `AcceptDialog`. If the script editor is simultaneously showing a "file changed on
> disk, reload?" dialog (triggered because Reset just regenerated `practice.gd`),
> Godot may log a "child window exclusive" error. This is cosmetic — dismiss
> whichever dialog is visible and both will clear.

### Test panel (`ui_test_panel`)

When you run a practice scene (and it's recognized as a practice — i.e. its path is
under `practices/` and matches a registered `PracticeMetadata`), this panel
appears. It instantiates the solution scene alongside the practice (via
`SplitLayout`), loads `practice_solutions/<dir>/test.gd`, and runs the full
lifecycle from §4. While running, the report label cycles through fixed phase
strings (`REPORT_PHASES`):

- `"Setting up the test..."`
- `"Verifying your practice tasks..."` (requirements phase)
- `"Test setup failed."` (for both setup and requirements failures)
- `"Looks like you've got some things to fix."` (completion 0)
- `"Congratulations! You aced this practice."` (completion 1)

These strings are shared across **all** practices — only `Check.description` /
`Check.hint` and `Requirement.description` / hint are per-practice text. The **x5**
button in the panel speeds up `Engine.time_scale` by 5× while the test runs,
useful for practices with long sample windows.

### SplitLayout — the graphical comparison

`tester/split_layout/split_layout.tscn` puts the practice and solution scenes into
two side-by-side `SubViewport`s inside an `HBoxContainer`. The solution's viewport
has a translucent overlay and a "Reference" label so it's visually distinguishable.
Both viewports use `own_world_3d = true` (so 3D physics/collisions don't interact
between practice and solution) and `render_target_update_mode = UPDATE_ALWAYS`.
This is "free" for any practice with a visual scene — no extra wiring needed in
`test.gd`. §8 describes porting this same idea into `Shell.gd`.

### Log entries (`log_entry`)

Each `Check`/`Requirement` result is rendered as a `log_entry` instance, and the
**variation** chosen determines what the student actually sees:

- A top-level `Check` with **no subchecks**: `check_no_subchecks_pass/fail` — shows
  an icon, `description`, and `hint` (on fail).
- A top-level `Check` **with subchecks**: `check_pass/fail` — shows icon and
  `description` only (no hint); each **subcheck** gets `subcheck_pass/fail` (hint
  shown only on fail).
- A failed `Requirement`: `requirement` variation — always shows its `hint`.

This matters for authoring: whether you structure something as a flat check vs. a
check-with-subchecks changes which hint text the student sees and when.

### Input feedback overlay (`input_panel_container` / `input_feedback_ui`)

During a test run, a banner is shown via `input_panel_container`:

- `.warn()` while the test is actively running ("don't touch inputs").
- `.note()` / `.safe()` after completion 0 / 1.
- `.off()` if requirements failed before checks ran.

Nested inside is `input_feedback_ui`, which visualizes live key/mouse input. Its
directional arrow indicators are **hardcoded** to check for
`InputMap.has_action("move_left"/"move_right"/"move_up"/"move_down")` — the arrows
only appear if your practice registers exactly those four action names (via
`_add_actions_requirement`). Any other key press shows a generic key-label
indicator; mouse clicks show a generic mouse indicator.

### Solution warning banner (`ui_solution_warning`)

If you open a scene under `practice_solutions/` directly in the editor, a banner
appears identifying which practice scene you should be working with instead, with a
clickable link to open it. Purely a navigation aid while authoring.

---

## 6. Structural guardrails (`tester/requirements.gd`)

`Requirements` is a static utility, separate from the `Requirement` class in
`test.gd`. Its public `check()` method is currently stubbed to always return `true`,
but the underlying `_check_*` functions are real and usable.

`Requirements.setup(practice_base_path)` scans `practice_base_path` for `*.gd` and
`*.tscn`, pairs each with its solution counterpart via `Paths.to_solution()`
(dropping any without a solution), and loads both sides into `_list.scripts` /
`_list.scenes` as `{practice, solution}` pairs.

| Function | What it compares | Notes / caveats |
|---|---|---|
| `_check_methods()` | `get_script_method_list()`, sorted by name, argument **names** stripped | Catches added/removed/renamed functions or changed argument types/return type. Renaming a parameter is allowed. |
| `_check_properties()` | `get_script_property_list()` (filtering out the script-name and `"metadata"` pseudo-properties) | Strict dictionary equality including export hints/usage flags — even a cosmetic export-hint change would fail this. |
| `_check_signals()` | `get_script_signal_list()`, sorted, argument names stripped | Same idea as methods, for custom signals. |
| `_check_constants()` | `get_script_constant_map()`, strict `==` | Every constant **and its value** must match — the strictest of the set. |
| `_check_nodes()` | Scene-tree shape: per node-path, the set of `{type, script_path}` | **Caveat (flagged as TODO in source):** keys are node paths derived from node *names*. If a practice asks the student to rename a node, this check will incorrectly fail. Good for "did you keep the same node types/scripts in the same places", not for naming/reorganization exercises. |

These are not wired into any `test.gd` by default. To use one, wrap it in a
`_add_callable_requirement`:

```gdscript
const Requirements := preload("res://addons/gdpractice/tester/requirements.gd")

func _build_requirements() -> void:
    super()
    Requirements.setup(_practice_base_path)
    _add_callable_requirement(
        "Function signatures must not change",
        func() -> String:
            return "" if Requirements._check_methods() \
                else "Don't change the function's parameters or return type — only fill in the body."
    )
```

> **Static-state caution:** `Requirements` stores its scanned file list in
> module-level `static var`s. `setup()` must be called again immediately before
> each `_check_*()` call if there's any chance multiple practices' requirements
> could be evaluated in the same process — otherwise a later practice could see an
> earlier practice's `_list`.

---

## 7. The `Shell.gd` / Runestone integration

`Shell.gd` is the entry point for the web-exported build used by Runestone. It
exposes `window.godotShell.loadExercise(payload)` to the host page's JS.

### Incoming payload

```jsonc
{
  "pck":    "ch01_p1.pck",   // optional — per-exercise resource pack to mount
  "scene":  "res://practices/L1.P1.double_value/practice.tscn",
  "code":   "...student GDScript source...",
  "test":   "...test.gd source, as a string...",
  "origin": "https://runestone.example"  // for postMessage targeting
}
```

`_load_exercise()`:

1. Optionally fetches and mounts `pck` via `ProjectSettings.load_resource_pack()`.
2. Tears down any previous exercise (`_teardown()` frees `_test`/`_solution`/`_practice`).
3. Loads & instantiates the **practice** scene at `scene` (CACHE_MODE_IGNORE).
4. Compiles `code` as a fresh `GDScript`, `.reload()`s it (syntax errors are
   reported back immediately without proceeding), and `set_script()`s it onto the
   practice scene's root — **replacing whatever starter script was in the scene**.
5. Loads & instantiates the **solution** scene at `Paths.to_solution(scene)`,
   `visible = false` if it's a `CanvasItem`, added as a hidden sibling.
6. Compiles `test` as a fresh `GDScript` the same way, instantiates it as `_test`.
7. Runs `_run_checks()`.

### `_run_checks()` / outgoing result

Mirrors the editor lifecycle: `_test.setup()` → requirements (abort+report on
failure) → `setup_checks()` → `await check.run()` for each top-level check → post:

```jsonc
{
  "type":   "result",
  "passed": true,
  "score":  1.0,           // 1.0 or 0.0
  "checks": [
    {
      "description": "...",
      "hint": "...",
      "status": "pass",    // "pass" | "fail" | "disabled" | "unknown"
      "passed": true,
      "subchecks": [ /* same shape */ ]
    }
  ]
}
```

A requirement failure instead posts `{type:"result", passed:false, score:0.0,
checks:[], requirements:[{description, hint}, ...]}`. A syntax error in student
code or test code, or a missing scene, posts `{type:"error", message}`.

Messages get `source: "godot-activecode"` and `subject: "runestone"` added and are
sent via `window.parent.postMessage(...)`. On non-Web platforms, `_post_to_runestone`
just prints the JSON — useful for local testing by calling `_load_exercise()`
directly from the debugger, per the comment at the top of `Shell.gd`.

### What's different from the editor flow

- `Metadata`/`PracticeMetadata`/`db/progress.gd` are **never consulted**. Progress
  tracking is owned by Runestone via the posted result.
- `test.gd`'s **source is sent as a string** and compiled at runtime — it does not
  need to exist as a file relative to the scene the way the editor's
  `ui_test_panel.gd` expects. Whatever packages exercises for Runestone needs to
  read each practice's `practice_solutions/<dir>/test.gd` and embed its source into
  the payload — that packaging step lives outside this addon.
- The solution scene is added **hidden**, purely for `test.gd`'s state
  comparisons — there is no SplitLayout-style visual comparison. §8 covers how to
  add one.

---

## 8. Recipe: visual practice/solution comparison in `Shell.gd`

This is a recipe, not an implemented change — it ports the editor's `SplitLayout`
idea into the web export.

**1. Scene tree (`Shell.tscn`).** Currently `Shell.tscn` is a bare `Node`. Add (or
wrap the root in) a `Control` covering the viewport, containing an `HBoxContainer`
with two `SubViewportContainer` → `SubViewport` pairs — structurally the same as
`tester/split_layout/split_layout.tscn` (`PracticeSubViewport`,
`SolutionSubViewport`). For 3D scenes, set `own_world_3d = true` on both
`SubViewport`s so practice/solution physics don't interact; set
`render_target_update_mode = SubViewport.UPDATE_ALWAYS` on both so they render
continuously rather than only-when-visible.

**2. `_load_exercise()` changes.** Instead of:

```gdscript
add_child(_practice)
...
if _solution is CanvasItem:
    _solution.visible = false
add_child(_solution)
```

do:

```gdscript
practice_sub_viewport.add_child(_practice)
...
solution_sub_viewport.add_child(_solution)
```

Parent each scene into its own `SubViewport` and drop the `visible = false` branch
entirely — visibility is controlled by whether the solution viewport/container is
shown, not by hiding the node.

**3. Timing is already correct.** Both `_practice` and `_solution` are live nodes
in the tree and receive `_process`/`_physics_process` regardless of visibility.
Making the solution visible in its own viewport is purely a rendering change; no
changes to the test-pipeline timing or `_setup_state()` position-reset pattern (§4)
are needed.

**4. Input routing.** Set `handle_input_locally = false` on the practice
`SubViewport` so keyboard/mouse input continues to flow from the main viewport into
it and reach the student's script as today. The solution scene has no student script
attached, so it generally needs no special input handling — but strip any
`CanvasLayer`/UI nodes from the solution scene before adding it to the viewport, or
keep solution scenes free of such nodes, since they'd now be visible to the student.

**5. Resizing.** `export_presets.cfg` currently relies on adaptive canvas resize for
a single full-viewport scene (`html/canvas_resize_policy = 2`). With a split
layout, connect to the root `Control`'s `resized` signal and explicitly set
`practice_sub_viewport.size` / `solution_sub_viewport.size` (e.g. half the
available size each) — `SubViewportContainer.stretch = true` scales the *display*,
but `SubViewport.size` (the actual render target resolution) needs updating
separately for crispness.

**6. Optional toggle / payload flag.** Most exercises won't need this view. Add an
optional `showComparison: bool` field to the payload (default `false`); when
`false`, hide the solution `SubViewportContainer` and let the practice viewport take
the full width (no `postMessage` contract changes needed). You could also mirror the
editor's `ToggleShowButton` so students can expand/collapse the reference panel
themselves regardless of the payload flag — useful at small embedded sizes where a
permanent 50/50 split would be cramped. A picture-in-picture inset (a `SubViewport`
rendered as a `TextureRect` overlay in a corner) is a lighter-weight alternative.

---

## 9. Worked examples

Three example practices, registered as `L1.P1`–`L1.P3`, each demonstrating a
different tier of the framework. All files live under `practice_solutions/`; run
**Reset** from the GDQuest dock (§5) to generate the corresponding `practices/`
directory for each one.

### L1.P1.double_value — simple

Demonstrates: `_call_all()` for direct function-return comparison; a
`Requirements._check_methods()` structural guardrail; comment-stub syntax with a
typed return value.

The solution script:

```gdscript
# Returns double `value`.
func get_double(value: int) -> int:
    return value * 2 # return value
```

generates a practice where `get_double` returns `value` unchanged (valid `int`,
passes Godot's parse-time return-type check, but gives wrong answers). The student
fills in `* 2`.

`test.gd` uses `_call_all("get_double", [n])` across several test values and
compares practice vs. solution return values. If the student changes the function's
signature instead of its body, the `_check_methods()` requirement fires first and
blocks the value checks entirely.

### L1.P2.velocity_comparison — medium

Demonstrates: `_setup_state()` position reset; `_setup_populate_test_space()` with
`_connect_timed`; `_is_sliding_window_pass()` for per-frame displacement checks;
direct practice-vs-solution position comparison; `_add_properties_requirement`.

The solution script:

```gdscript
@export var velocity := Vector2(120.0, 0.0)

func _physics_process(delta: float) -> void:
    position += velocity * delta # position
```

generates a practice where the body is replaced by `position` (a no-op expression
statement). The student fills in the integration. `_setup_state()` resets both
nodes' positions to `Vector2.ZERO` and mirrors `_practice.velocity` onto
`_solution` before sampling so both simulations start from identical conditions.

### L1.P3.visual_velocity_comparison — graphical

Demonstrates: input-driven motion; `Input.action_press()`/`action_release()` to
simulate held input during the sample window; comment-stub syntax for changing an
export default; `_add_actions_requirement`; the SplitLayout visual comparison (both
panels react to the same simulated input simultaneously).

The solution script:

```gdscript
@export var speed := 200.0 # @export var speed := 0.0

func _physics_process(delta: float) -> void:
    var direction := Input.get_axis("move_left", "move_right") # var direction := 0.0
    velocity = Vector2(direction * speed, 0.0) # velocity = Vector2.ZERO
    position += velocity * delta # position
```

generates a practice with `speed = 0.0` and three no-op stub lines. The student
must set a speed value *and* implement all three lines to pass. `test.gd` presses
`move_right` via `Input.action_press()` for the sample window so both practice and
solution receive identical simulated input, then compares per-frame displacements
and absolute positions. No `diff.gd` is needed — the export default change is
handled entirely by the comment-stub syntax.
