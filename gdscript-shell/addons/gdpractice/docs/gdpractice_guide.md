# GDPractice Addon Guide

This guide documents the `gdpractice` addon as used in this project: how to author a
practice exercise, how the testing framework (`test.gd`) works, what the in-editor
authoring tools look like, and how everything maps onto the `Shell.gd` / Runestone
web deployment.

Suggested location: `gdscript-shell/addons/gdpractice/docs/gdpractice_guide.md`.

---

## 1. Overview & directory structure

GDPractice is built around two parallel trees under `res://`:

- `practice_solutions/<dir>/` — the instructor's complete, working reference:
  scene(s), script(s), a `test.gd`, and optionally a `diff.gd`.
- `practices/<dir>/` — the student-facing starting point. This tree is
  **generated** from `practice_solutions/` by `build.gd`; you should not hand-edit
  it (any hand edits are overwritten the next time the practice is built/reset).

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
        "double_value",                                  # id — must be unique
        "Double the value",                              # title
        preload("res://practice_solutions/L1.P1.double_value/solution.tscn"),
        []                                                # scripts_to_open (optional)
    ))
```

`PracticeMetadata._init()` takes `(id, title, packed_scene, scripts_to_open := [])`.
It derives the directory name from `packed_scene.resource_path` (via
`Paths.get_dir_name()`), runs it through the regex above, and computes:

- `lesson_number`, `practice_number` — parsed integers
- `item` — `"L1.P1"` style label
- `full_title` — `"L1.P1 Double the value"`

**Important gotcha:** if the directory name doesn't match the regex, `regex_match`
is `null` and the very next line (`regex_match.strings[1].to_int()`) is a
null-reference error — registering a `PracticeMetadata` for a non-conforming
directory name will hard-error in the editor, not just print a warning.

### Why this matters even though Shell.gd doesn't read it

`Shell.gd` (the Runestone/web deployment path, see §7) never touches `Metadata`,
`PracticeMetadata`, or the progress database — it gets everything it needs (scene
paths, test source) directly from the JS payload. The naming convention and
metadata registration exist purely for the **in-editor authoring workflow** (§5):
the practices dock, the live test panel, and progress tracking are all driven by
`metadata.list`. Since each Godot project can start its own numbering at `L1.P1`
without colliding with anything else, there's no real cost to keeping this — and it
unlocks the live SplitLayout test panel while you're writing `test.gd`.

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

(also triggered, for a single practice, by the dock's per-practice **Reset**
button — see §5).

For every file in a solution directory except `test.gd` and `diff.gd`, the file is
copied to the parallel `practices/` path. `.gd` and `.tscn` files get additional
processing.

### Comment-based stub syntax (`.gd` files)

`build.gd` looks for a trailing `# ...` comment on each non-comment-only line and
rewrites the line based on what follows the `#`:

| Solution line | Resulting practice line | Effect |
|---|---|---|
| `position += delta * velocity # position` | `position` | Code replaced by the comment text, same indentation |
| `for column in range(columns): #` | *(line deleted)* | Empty trailing comment deletes the line entirely |
| `var cell := Vector2(column, row) # << var cell := Vector2(0, 0)` | `var cell := Vector2(0, 0)` *(dedented by 2 levels)* | `<`/`>` runs shift indentation by one level per character (`<` = outdent, `>` = indent) before substituting the rest of the comment as the new line |
| `    # explain something` *(a pure comment line, nothing before `#`)* | unchanged | Lines with no code before `#` are copied verbatim — these are the instructional comments students read |

This is how a fully-working solution script becomes a starter script with
fill-in-the-blank gaps, while keeping the solution itself fully readable and
runnable.

### `diff.gd` — structural differences for `.tscn` files

If `practice_solutions/<dir>/diff.gd` exists and defines a static function whose
name exactly matches a `.tscn` file's basename (e.g. a function named `practice`
for `practice.tscn`), `build.gd` instantiates the **solution** scene, calls that
function on it (`solution_diff.call(diff_func_name, solution_scene)`), and packs
the *mutated* result as the practice scene. This is how you make the student's
starting scene structurally different from the solution — e.g. removing a node the
student is meant to add, or changing a starting property — without touching the
`.gd` comment-stub mechanism at all. If no matching function exists, the scene is
copied through unchanged (and a `[SKIP]` line is printed).

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

Override `_build_requirements()` (calling `super()` first, usually) to add more:

- `_add_actions_requirement(actions: Array)` — fails if any named `InputMap`
  action doesn't exist in the project. Useful for input-driven practices.
- `_add_properties_requirement(properties: Array[String], object := _practice)` —
  fails if `object` is missing any listed property (e.g. the student deleted an
  exported variable).
- `_add_callable_requirement(description, checker, params := [])` — generic
  wrapper for any custom `String`-returning checker; this is also how you'd wire in
  the structural guardrails from `requirements.gd` (§6).

### Checks

A `Check` has `description`, `hint`, `status` (`DISABLED` / `PASS` / `FAIL`), a
`checker: Callable -> String`, optional `dependencies: Array[Check]` (a check is
`DISABLED` if any dependency hasn't passed), and optional `subchecks: Array[Check]`
(a check only runs its subchecks if its own `checker` passes; the check's overall
result is the *last* subcheck's result, evaluated in order with early exit on
first failure).

`_add_simple_check(description, checker) -> Check` creates a `Check`, appends it to
`checks`, and returns it so you can attach `dependencies`/`subchecks`.

### State setup & the `_test_space` pattern

Two virtual hooks, called once per test run before `_build_checks()`:

- **`_setup_state()`** — copy relevant initial state from `_practice` to
  `_solution` so both start from the same conditions (e.g. copy the student's
  chosen velocity onto the solution node, so the solution moves the way it *should*
  given the student's inputs, not from some hardcoded default).
- **`_setup_populate_test_space()`** — gather samples into `_test_space: Array` over
  time, typically via:

```gdscript
func _connect_timed(time: float, sig: Signal, callback: Callable) -> void:
    sig.connect(callback)
    await get_tree().create_timer(time).timeout
    sig.disconnect(callback)
```

  e.g. `await _connect_timed(1.0, get_tree().process_frame, _populate_test_space)`
  where `_populate_test_space()` appends a dictionary of
  `{practice_position, solution_position, delta}` each frame for one second.

### Helper method reference

| Method | Purpose |
|---|---|
| `_call_all(method, arg_array := []) -> Dictionary` | Calls `method` on both `_practice` and `_solution`, returns `{practice: ..., solution: ...}`. Good for "does my function return the right value" checks without needing `_test_space` at all. |
| `_set_all(property_path: NodePath, value)` | Sets the same property on both `_practice` and `_solution` via `set_indexed`. |
| `_is_sliding_window_pass(predicate: Callable) -> bool` | Walks consecutive pairs `(x, y)` in `_test_space`. Returns `true` only if `predicate(x, y)` is `true` for **every** consecutive pair; stops and returns `false` at the first pair where it isn't. |
| `_is_code_line_match(target_lines: Array) -> bool` | `true` if any line in `_practice_code` matches (via `String.match`, glob-style — `*`/`?`) any pattern in `target_lines`. Remember `_practice_code` has all whitespace stripped. |
| `_load(pattern, is_practice := true) -> Resource` | Loads the single resource matching `pattern` under the test script's directory (practice or solution side), asserting exactly one match exists. |

> **Gotcha with `_is_sliding_window_pass`:** because it returns `true` only when the
> predicate holds for *every* pair, a predicate that means "this pair is bad" will
> make the function return `true` only when the *entire* test space is uniformly
> "bad" — and `false` as soon as *any* single pair is "good". If you want "fails if
> any pair is bad", write a predicate that means "this pair is good" and check
> `_is_sliding_window_pass(good_predicate)` is `true`. The shipped
> `script_templates/Test/default.gd` template uses a `fail_predicate`-style naming
> with this function — trace through a concrete `_test_space` by hand (or add a
> `print()`) before relying on the polarity, since it's easy to get backwards.

---

## 5. The in-editor authoring & testing workflow

None of this section applies to the deployed Shell.gd/Runestone exercise — it's the
experience you get while developing a practice in the Godot editor, made possible
by the `metadata.gd` registration from §2.

### Practices dock (`ui_practice_dock` / `ui_selectable_practice`)

A dock panel lists every registered `PracticeMetadata` (grouped/labeled using
`item`/`title`). Each entry has:

- A checkbox reflecting `db/progress.gd` completion state for that `id`.
- A **Reset** button — re-runs `build_practice(dir_name, true)` for that practice,
  regenerating `practices/<dir>/` from the current solution (+ `diff.gd`) and
  updating `.file_checksums.json`.
- When selected: opens the **practice** scene and calls `open_practice_scripts()`,
  which opens either the scripts listed in `scripts_to_open`, or — by default —
  the root node's script.
- A **Run** button (visible only when selected), which runs the current scene.

### Test panel (`ui_test_panel`)

When you run a practice scene (and it's recognized as a practice — i.e. its path is
under `practices/` and matches a registered `PracticeMetadata`), this panel
appears. It instantiates the solution scene alongside the practice (see
`SplitLayout` below), loads `practice_solutions/<dir>/test.gd`, and runs the full
lifecycle from §4. While running, the report label cycles through fixed phase
strings (`REPORT_PHASES`):

- `"Setting up the test..."`
- `"Verifying your practice tasks..."` (requirements)
- `"Test setup failed."` (shown for both setup and requirements failures)
- `"Looks like you've got some things to fix."` (completion 0)
- `"Congratulations! You aced this practice."` (completion 1)

These strings are shared across **all** practices — they're not something you
customize per-practice; only `Check.description`/`Check.hint` and
`Requirement.description`/hint are per-practice text.

### SplitLayout — the graphical comparison

`tester/split_layout/split_layout.tscn` puts the practice and solution scenes into
two side-by-side `SubViewport`s inside an `HBoxContainer`. The solution's viewport
has a translucent overlay + a "Reference" label so it's visually distinguishable.
Both viewports use `own_world_3d = true` (so 3D physics/collisions don't interact
between practice and solution) and `render_target_update_mode = UPDATE_ALWAYS`.
This is "free" for any practice with a visual scene — no extra wiring needed in
`test.gd`. §8 describes porting this same idea into `Shell.gd`.

### Log entries (`log_entry`)

Each `Check`/`Requirement` result is rendered as a `log_entry` instance, and the
**variation** chosen determines what the student actually sees:

- A top-level `Check` with **no subchecks**: `check_no_subchecks_pass/fail` — shows
  an icon **and** `description` (and `hint` on fail).
- A top-level `Check` **with subchecks**: the check itself gets
  `check_pass/fail` (icon + `description` only, no `hint` shown), and **each
  subcheck** gets `subcheck_pass/fail` (icon + `description`, with `hint` shown
  only on fail).
- A failed `Requirement` gets the `requirement` variation — always shows its
  `hint`.

This matters for authoring: whether you structure something as a flat check vs. a
check-with-subchecks changes which hint text the student sees and when.

### Input feedback overlay (`input_panel_container` / `input_feedback_ui`)

During a test run, a banner is shown via `input_panel_container`:

- `.warn()` while the test is actively running ("don't touch inputs").
- `.note()` / `.safe()` after completion 0 / 1.
- `.off()` if requirements failed before checks ran.

Nested inside is `input_feedback_ui`, which visualizes live key/mouse input. Its
directional arrow indicators are **hardcoded** to
`InputMap.has_action("move_left"/"move_right"/"move_up"/"move_down")` — this overlay
is only meaningful (for direction indicators) if your practice uses exactly those
four action names. Any other key press shows a generic key-label indicator; mouse
clicks show a generic mouse indicator.

### Solution warning banner (`ui_solution_warning`)

If you (the instructor) open a scene under `practice_solutions/` directly in the
editor, a banner appears identifying which practice scene you should be working
with instead, with a clickable link to open it. Purely a navigation aid while
authoring — not part of the deployed exercise.

---

## 6. Structural guardrails (`tester/requirements.gd`)

`Requirements` is a static utility, separate from the `Requirement` class in
`test.gd`. Its public entry point `check()` is currently stubbed to always return
`true`, but the underlying `_check_*` functions are real and usable.

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
| `_check_nodes()` | Scene-tree shape via `_get_scene_tree_proxy()`: per node-path, the set of `{type, script_path}` | **Caveat (flagged as a TODO in the source):** keys are node paths derived from node *names*. If a practice intentionally asks the student to rename a node, this check will incorrectly fail. Good for "did you keep the same node types/scripts in the same places", not for naming/reorganization exercises. |

These are not wired into any `test.gd` by default. To use one, wrap it in
`_add_callable_requirement` (which expects a `String`-returning checker):

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
> module-level `static var`s. `setup()` must be called (again) immediately before
> each `_check_*()` call within a given test run if there's any chance multiple
> practices' requirements could be evaluated in the same process — otherwise a
> later practice could see an earlier practice's `_list`.

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
directly from the debugger, per the docstring in `Shell.gd`.

### What's different from the editor flow

- `Metadata`/`PracticeMetadata`/`db/progress.gd` are **never consulted**. Progress
  tracking is presumably owned by Runestone via the posted result, not by this
  addon.
- `test.gd`'s **source is sent as a string** and compiled at runtime — it does not
  need to exist as a file relative to the scene the way the editor's
  `ui_test_panel.gd` expects (`Paths.to_solution(base_path).path_join("test.gd")`).
  Whatever packages exercises for Runestone needs to read each practice's
  `practice_solutions/<dir>/test.gd` and embed its source into the payload — that
  packaging step lives outside this addon and isn't covered here.
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

— i.e. parent each scene into its own `SubViewport` and drop the
`visible = false` branch entirely; visibility is now controlled by whether the
solution viewport/container is shown at all, not by hiding the node.

**3. Timing is already correct.** Both `_practice` and `_solution` are live nodes
in the tree and receive `_process`/`_physics_process` regardless of visibility —
during `_test.setup_checks()`'s `_connect_timed(...)` sampling window (§4), the
solution is *already* running its motion every frame. Making it visible in its own
viewport is purely a rendering change; no changes to the test-pipeline timing are
needed. The student will see both react in real time during that sampling window.

**4. Input routing.** Set `handle_input_locally = false` on the practice
`SubViewport` so keyboard/mouse input continues to flow from the main viewport down
into it and reach the student's script as today. The solution scene has no student
script attached, so it generally needs no special input handling — but if the
solution scene contains its own `CanvasLayer`/UI (debug overlays, etc.), strip those
before adding it to the viewport, or keep solution scenes free of such nodes,
since they'd now be visible to the student.

**5. Resizing.** `export_presets.cfg` currently relies on adaptive canvas resize for
a single full-viewport scene (`html/canvas_resize_policy = 2`). With a split
layout, connect to the root `Control`'s `resized` signal and explicitly set
`practice_sub_viewport.size` / `solution_sub_viewport.size` (e.g. half the
available size each) — `SubViewportContainer.stretch = true` scales the *display*,
but `SubViewport.size` (the actual render target resolution) needs updating
separately for crispness/performance.

**6. Optional toggle / payload flag.** Most exercises won't need this view. Add an
optional `showComparison: bool` field to the payload (default `false`); when
`false`, hide the solution `SubViewportContainer` and let the practice viewport take
the full width (no `postMessage` contract changes needed — this is purely
client-side rendering). You could also mirror the editor's `ToggleShowButton` so
students can expand/collapse the reference panel themselves regardless of the
payload flag — useful at small embedded sizes where a permanent 50/50 split would
be cramped. A smaller picture-in-picture inset (a third `SubViewport` rendered as a
`TextureRect` overlay in a corner) is a lighter-weight alternative to a true 50/50
split if screen real estate is tight.

---

## 9. Worked examples

Three example practices, registered as `L1.P1`–`L1.P3`, each demonstrating a
different tier of the framework:

- **`L1.P1.double_value`** (simple) — a single-script practice with no movement.
  `test.gd` uses `_call_all()` to compare a practice function's return value
  against the solution's across several inputs (§4), with a structural-guardrail
  requirement wired via `Requirements._check_methods()` (§6).
- **`L1.P2.velocity_comparison`** (medium) — the `_setup_state` /
  `_setup_populate_test_space` / `_test_space` / `_is_sliding_window_pass` pipeline
  (§4) comparing practice vs. solution motion over one second, plus an
  `_add_actions_requirement` for the relevant input actions.
- **`L1.P3.visual_velocity_comparison`** (graphical) — the same pipeline as `P2`,
  with a more visual scene and a `diff.gd` that structurally diverges the
  practice's starting scene from the solution (§3). This is the example the §8
  Shell.gd split-view recipe is written against.

*(Implementations live under `practice_solutions/L1.P1.double_value/`,
`practice_solutions/L1.P2.velocity_comparison/`, and
`practice_solutions/L1.P3.visual_velocity_comparison/`.)*
