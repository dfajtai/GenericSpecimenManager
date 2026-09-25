# Architecture

How the code is organised: which file does what, how the config is modelled, how logging works, and the rules new code should follow.

## Repository layout

```
<repo root>/                                     <- README.md, CHANGELOG.md, LICENSE, .gitignore
├── docs/                                         <- reference documentation (you are here)
├── howto/                                        <- step-by-step guides
├── examples/config/                              <- ready-made study configs to start from
└── GenericSpecimenManager/                       <- the Slicer extension
    ├── CMakeLists.txt                            <- extension-level CMake (adds the module subdirectory)
    ├── README.md                                 <- the module's own readme (usage)
    └── GenericSpecimenManager/                   <- the actual Slicer module
        ├── CMakeLists.txt                            <- module-level CMake (scripted module boilerplate)
        ├── GenericSpecimenManager.py                 <- the Slicer module (title/icon, Widget/Logic wiring)
        ├── Resources/
        │   ├── definitions.py                        <- every hardcoded toggle/curated choice list, in ONE place
        │   ├── paths.py                              <- where the bundled data (Html/, Presets/, examples/config) lives
        │   ├── core/                                 <- pure Python - no Slicer, unit-testable anywhere
        │   │   ├── config_model.py                   <- dataclasses: StudyConfig and the rest of the schema
        │   │   ├── pattern_check.py                  <- validates {column} patterns against the CSV headers
        │   │   ├── safe_io.py                        <- atomic writes, backups, change detection, study lock
        │   │   ├── status.py                         <- parsing of the status stored in database.csv
        │   │   └── logging_setup.py                  <- shared logger, optional log-to-file
        │   ├── utils/                                <- manipulates Slicer itself - functions, no specimen state
        │   │   ├── workspace.py                      <- layout, crosshair, window/level, slice rotation, markers, view convention
        │   │   ├── volume_rendering.py               <- volume rendering: presets, transfer-function remap and shift
        │   │   ├── segment_editor.py                 <- Segment Editor defaults (study init) and hand-off of a loaded specimen
        │   │   ├── slicer_ui.py                      <- the module panel's Help section, the Ctrl+S shortcut
        │   │   └── config_location.py                <- where config browse dialogs start (last used folder, Slicer settings)
        │   ├── study/                                <- the domain layer: specimens, database, batch - no GUI
        │   │   ├── specimen.py                       <- GenericSpecimen: image/segmentation/markups loading, save, close
        │   │   ├── logic.py                          <- Logic: config, database/preseg tables, specimens, safe database saving
        │   │   └── batch_processor.py                <- batch export/statistics, run against every 'finished' specimen
        │   ├── gui/                                  <- Qt
        │   │   ├── main_widget.py                    <- the module widget: setup, enter/exit, parameter node, scene events
        │   │   ├── specimen_table.py                 <- specimen table: rendering, status dropdown, filters, selection
        │   │   ├── study_setup.py                    <- config/CSV picking, prompts, pre-flight checks, Initialize Study
        │   │   ├── specimen_actions.py               <- load / save / close / reset, Ctrl+S, saving the database
        │   │   ├── annotation.py                     <- the on-screen specimen annotation
        │   │   ├── help_dialog.py                    <- the shared cheat-sheet popup (section jump + search)
        │   │   └── config_editor/                    <- the "Config Editor..." dialog
        │   │       ├── dialog.py                     <- ConfigEditorDialog: load / save / dirty tracking
        │   │       ├── general_tab.py ... manual_tab.py   <- one mixin per tab: build + populate + collect + clear
        │   │       ├── helpers.py, popups.py
        │   ├── Presets/example_presets.json          <- Config Editor's preset catalogue - extensible without code
        │   ├── Html/                                 <- Help / example-presets HTML content - extensible without code
        │   │   ├── config_editor_help_cheatsheet.html
        │   │   ├── module_help_cheatsheet.html       <- the main module's own cheat sheet (collapsed Help block)
        │   │   └── example_presets_template.html
        │   ├── Icons/GenericSpecimenManager.png / .svg
        │   └── UI/GenericSpecimenManager.ui
        └── Testing/
            ├── CMakeLists.txt
            └── Python/CMakeLists.txt
```

## Layers

```
core/    pure Python, no Slicer                         <- unit-tested anywhere
utils/   Slicer API calls, no domain state              <- functions that take config sections / nodes as arguments
study/   specimens, database, batch                     <- the domain; uses core/ and utils/
gui/     Qt widgets and dialogs                         <- uses everything below
```

A layer only imports from the layers listed before it: `core` <- `utils` <- `study` <- `gui` (`definitions.py` and `paths.py` sit beside them and may be imported by any layer).

## Files and their responsibilities

```

[`GenericSpecimenManager/GenericSpecimenManager/GenericSpecimenManager.py`](../GenericSpecimenManager/GenericSpecimenManager/GenericSpecimenManager.py)
puts `Resources` on `sys.path` and reaches the logic via
`from Resources.gui.main_widget import GenericSpecimenManagerWidgetBase`.
Each file's responsibility:

| file | responsibility |
|---|---|
| [`GenericSpecimenManager.py`](../GenericSpecimenManager/GenericSpecimenManager/GenericSpecimenManager.py) | Slicer module registration (title, icon, `CONFIG_PATH`) - ~60 lines, no business logic |
| [`Resources/definitions.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/definitions.py) | every hardcoded toggle (e.g. `HIDE_HELP_AND_ACKNOWLEDGEMENT`) and curated dropdown-choice list, in one findable place |
| [`Resources/paths.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/paths.py) | where the bundled data folders live, resolved from one place |
| [`Resources/core/config_model.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/core/config_model.py) | the typed, attribute-accessed representation of `config.json` (dataclasses) |
| [`Resources/core/pattern_check.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/core/pattern_check.py) | checks every `{column}` pattern of a config against the CSV headers at Initialize Study |
| [`Resources/core/safe_io.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/core/safe_io.py) | atomic writes, backups, change detection and the study lock - see [Data safety](data-safety.md) |
| [`Resources/core/status.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/core/status.py) | parsing of a `database.csv` status cell |
| [`Resources/core/logging_setup.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/core/logging_setup.py) | the shared `logger` every other file uses instead of `print()`, with an optional log-to-file toggle |
| [`Resources/utils/workspace.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/utils/workspace.py) | the 3D Slicer workspace of a loaded specimen: layout, crosshair, window/level, slice rotation, ruler, markers, view convention |
| [`Resources/utils/volume_rendering.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/utils/volume_rendering.py) | volume rendering: presets, min/max remap, fixed shift |
| [`Resources/utils/segment_editor.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/utils/segment_editor.py) | Segment Editor defaults at Initialize Study, and the hand-off of a loaded specimen's segmentation |
| [`Resources/utils/slicer_ui.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/utils/slicer_ui.py) | bits of Slicer's own UI this module bends: the Help section, the `Ctrl+S` shortcut |
| [`Resources/utils/config_location.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/utils/config_location.py) | where the config browse dialogs start: the last used config folder (kept in Slicer's settings), else `examples/config` |
| [`Resources/study/specimen.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/study/specimen.py) | `GenericSpecimen` - loading its images/segmentation/markups, saving, closing; calls the `utils/` functions for the workspace, volume rendering and Segment Editor |
| [`Resources/study/logic.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/study/logic.py) | `GenericSpecimenManagerLogic` - config, tables, specimens, safe database saving, study lock |
| [`Resources/study/batch_processor.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/study/batch_processor.py) | `BatchProcessor` - segment/markup export and/or custom statistics for every `finished` specimen, one combined CSV |
| [`Resources/gui/main_widget.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/gui/main_widget.py) | the module widget; the specimen table, study setup, specimen actions and annotation behaviour are mixins next to it |
| [`Resources/gui/config_editor/`](../GenericSpecimenManager/GenericSpecimenManager/Resources/gui/config_editor) | GUI for building/editing `config.json` without hand-writing JSON - one mixin per tab, plus `dialog.py` |
| [`Resources/gui/help_dialog.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/gui/help_dialog.py) | the shared cheat-sheet popup (section-jump combo + search bar) behind both Help buttons |
| [`Resources/Presets/example_presets.json`](../GenericSpecimenManager/GenericSpecimenManager/Resources/Presets/example_presets.json) | Config Editor's preset catalogue - **data, not code**, freely extensible |
| [`Resources/Html/*.html`](../GenericSpecimenManager/GenericSpecimenManager/Resources/Html) | the two cheat sheets (Config Editor's and the main module's) + example-presets popup content - **data, not code**, freely extensible |

All Python files are **100% docstring-covered** (classes, methods,
nested helper functions too) - VS Code's Outline panel / hover tooltips give
useful context with zero digging. For the trickier parts (Segment Editor
node handling, VTK transfer-function remapping, path resolution) there are
also inline tech comments beyond the docstrings, explaining *why* something
is done a certain way, not just *what* it does.

## The config model - typed config, not a `.get()` chain

Instead of `cfg["segmentation"].get("segments", [])`, you write
`cfg.segmentation.segments`. Dataclasses in
[`config_model.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/core/config_model.py) fall into two groups:

- **Section dataclasses** (`StudyConfig`, `SegmentationConfig`,
  `MarkupsConfig`, `GlobalWindowLevelConfig`, `BatchExportConfig`,
  `GroupByKeyConfig`, `SegmentEditorConfig`, `BrushConfig`,
  `DefaultsConfig`) - one meaning, one place in the schema, built once from
  the raw dict (`ClassName.from_dict(...)`).
- **Override dataclasses** (`ImageConfig`, `SegmentConfig`,
  `VolumeRenderingEntry`, `WindowLevel`, `Threshold`) - every field is
  `Optional`, defaulting to `None` ("not specified"). The SAME shape is used
  for `defaults.image`, `presets[name]`, AND a concrete `images[]` entry;
  `merge_image_overrides()` / `merge_segment_overrides()` layer them
  (defaults → preset → the entry's own fields, last non-`None` value wins).
  Semantic defaults only apply at the point of use
  (`img_cfg.type or "volume"`), so merging never confuses "field wasn't set"
  with "field was set to the dataclass's own default".

`load_config(path) -> StudyConfig` loads and parses the JSON.

## Logging & feedback

Every file uses the shared `logger` from
[`Resources/core/logging_setup.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/core/logging_setup.py)
instead of bare `print()`. Terminal output looks exactly like plain
`print()` did before (just the message, no extra noise); flip
`DEBUG_LOG_TO_FILE = True` in that file to ALSO write every line to
`~/GenericSpecimenManager.log`, timestamped, alongside the terminal -
useful when troubleshooting something after the fact or a crash that
scrolled the terminal away.

**Itemized load/save summaries**: `GenericSpecimen.load()`/`.save()` print
an aligned ASCII table (`_print_table()`, pure stdlib) of every item
touched - image name/type/role, segmentation, markups - with its status
(loaded/skipped/written) and resolved path. A save also announces the
specimen's output folder in the table title.

**"Save progress" / "Save database CSV" popups** are pretty-printed,
key-value style, and name the actual folder/path written - not just a bare
tuple of key values.

Every hardcoded toggle and curated dropdown-choice list (e.g.
`HIDE_HELP_AND_ACKNOWLEDGEMENT`, the Workspace tab's crosshair/ruler/marker
choices) lives in
[`Resources/definitions.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/definitions.py) -
one file to check when looking for a knob to turn, instead of hunting
through class bodies.

A specimen load always switches the layout to the standard Four-Up view
(Red/Yellow/Green/3D) - hardcoded, no config option, since there wasn't a
good reason to make this configurable.

## Tests

Automated tests need no Slicer: `python -m unittest discover -s tests` from the repo root.

- `test_safeio.py` - atomic writes, backups, change detection, the study lock.
- `test_imports.py` - every module imports (Slicer/Qt/VTK are stubbed): catches broken imports, cycles and
  top-level errors after moving code around.
- `test_utils.py` - the pure logic inside `utils/` (Segment Editor attributes, transfer-function shift/remap), with Slicer stubbed.
- `test_layers.py` - the layer rule above holds (no upward imports; `core/` imports no Slicer/Qt/VTK).
- `test_agent_notes.py` - the files `CLAUDE.md` mentions exist, and `AGENTS.md` is an identical copy of it.
- `test_example_configs.py` - every config in `examples/config` parses and uses only keys the schema knows.
- `test_packaging.py` - every file under `Resources/` is listed in the module's `CMakeLists.txt`.

`core/` is pure Python on purpose, so new logic that doesn't need Slicer belongs there, where it can be tested.
Everything Slicer-bound (`study/`, `gui/`) is checked by hand in Slicer; `python -m pyflakes` over
`Resources/` is a cheap check for undefined names after a refactor.

Slicer's *Reload* button reloads only the main script - after changing a file under `Resources/`, restart Slicer
(or reload the module by hand) to be sure the change is picked up.

## Development notes

- **Testing without a live Slicer**: every non-trivial change was verified
  with a mocked-`qt`/`vtk`/`slicer` smoke test (fake widget classes
  implementing only what that particular test needs). This doesn't replace
  testing in a real Slicer session, but it does catch syntax errors, wrong
  call order, and missing parameters.
- **Don't guess Slicer/VTK APIs** - see [Volume rendering](volume-rendering.md):
  a plausible-sounding but nonexistent method name (`AdjustRange`) would
  have sailed through code review, only failing in a live session. When an
  API is uncertain, search for it, or at least flag explicitly in the
  code/docstring that it isn't 100% confirmed.
- **Dataclass, not a `.get()` chain** - if a new top-level config section is
  needed, always introduce it in [`config_model.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/core/config_model.py)
  as a dataclass (with a `from_dict` classmethod); don't let a raw dict leak
  into the engine.
- **Backward compatibility is not a goal** - the schema has changed shape
  more than once (e.g. `volume_rendering` from a single object to a list),
  and this was deliberately NOT handled backward-compatibly. The goal is a
  fast, clear adaptation to the NEXT problem, not eternal support for old
  configs.
