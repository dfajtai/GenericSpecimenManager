# GenericSpecimenManager

A single, JSON-configured Slicer module. No per-species Python module - one
`config.json` describes a study (which images, which segments, which
landmarks, batch export, how the Segment Editor should behave, ...), and the
module loads and executes it.

This README lives at the **repo root**, one level above the actual Slicer
module (a common CMake-extension layout: the outer folder is the repo/
extension, the inner one is the module CMake registers by name).

```
GenericSpecimenManager/                          <- repo root (this README, top CMakeLists.txt, LICENSE, TODO.md)
├── CMakeLists.txt                                <- extension-level CMake (adds the module subdirectory)
├── LICENSE
├── TODO.md
└── GenericSpecimenManager/                       <- the actual Slicer module
    ├── CMakeLists.txt                            <- module-level CMake (scripted module boilerplate)
    ├── GenericSpecimenManager.py                 <- the Slicer module (title/icon, Widget/Logic wiring)
    ├── Config/                                   <- study configs, e.g. pig_config.json, rabbit_config.json,
    │                                                 deer_config.json, kamilla_config.json, plus a few
    │                                                 config_example_*.json used as minimal, annotated starting points
    ├── Examples/                                 <- reference/documentation-only, NOT registered wrapper examples
    │   ├── DeerSegmentor.py / PigChunker.py / RabbitVertCount.py
    ├── Resources/
    │   ├── ConfigModel.py                        <- dataclasses: StudyConfig and the rest of the schema
    │   ├── GenericSpecimenEngine.py               <- the actual logic (Logic, GenericSpecimen, Widget base)
    │   ├── BatchProcessor.py                     <- batch export/statistics, run against every 'done' specimen
    │   ├── ConfigEditor.py                       <- the dialog behind the "Config Editor..." button
    │   ├── Definitions.py                        <- every hardcoded toggle/curated choice list, in ONE place
    │   ├── LoggingSetup.py                       <- shared logger, optional log-to-file
    │   ├── Presets/example_presets.json          <- Config Editor's preset catalogue - extensible without code
    │   ├── Html/                                 <- Config Editor Help / example-presets HTML content - extensible without code
    │   │   ├── help_cheatsheet.html
    │   │   └── example_presets_template.html
    │   ├── Icons/GenericSpecimenManager.png / .svg
    │   └── UI/GenericSpecimenManager.ui
    └── Testing/
        ├── CMakeLists.txt
        └── Python/CMakeLists.txt
```

[`GenericSpecimenManager/GenericSpecimenManager.py`](GenericSpecimenManager/GenericSpecimenManager.py)
puts `Resources` on `sys.path` and reaches the logic via
`from Resources.GenericSpecimenEngine import GenericSpecimenManagerWidgetBase`.
Each file's responsibility:

| file | responsibility |
|---|---|
| [`GenericSpecimenManager.py`](GenericSpecimenManager/GenericSpecimenManager.py) | Slicer module registration (title, icon, `CONFIG_PATH`) - ~60 lines, no business logic |
| [`Resources/ConfigModel.py`](GenericSpecimenManager/Resources/ConfigModel.py) | the typed, attribute-accessed representation of `config.json` (dataclasses) |
| [`Resources/GenericSpecimenEngine.py`](GenericSpecimenManager/Resources/GenericSpecimenEngine.py) | `Logic`, `GenericSpecimen` (load/save/close one specimen), the Widget base class |
| [`Resources/BatchProcessor.py`](GenericSpecimenManager/Resources/BatchProcessor.py) | `BatchProcessor` - segment/markup export and/or custom statistics for every `done` specimen, one combined CSV |
| [`Resources/ConfigEditor.py`](GenericSpecimenManager/Resources/ConfigEditor.py) | GUI for building/editing `config.json` without hand-writing JSON |
| [`Resources/Definitions.py`](GenericSpecimenManager/Resources/Definitions.py) | every hardcoded toggle (e.g. `HIDE_HELP_AND_ACKNOWLEDGEMENT`) and curated dropdown-choice list, in one findable place |
| [`Resources/LoggingSetup.py`](GenericSpecimenManager/Resources/LoggingSetup.py) | the shared `logger` every other file uses instead of `print()`, with an optional log-to-file toggle |
| [`Resources/Presets/example_presets.json`](GenericSpecimenManager/Resources/Presets/example_presets.json) | Config Editor's preset catalogue - **data, not code**, freely extensible |
| [`Resources/Html/*.html`](GenericSpecimenManager/Resources/Html) | Config Editor's Help + example-presets popup content - **data, not code**, freely extensible |

All Python files are **100% docstring-covered** (classes, methods,
nested helper functions too) - VS Code's Outline panel / hover tooltips give
useful context with zero digging. For the trickier parts (Segment Editor
node handling, VTK transfer-function remapping, path resolution) there are
also inline tech comments beyond the docstrings, explaining *why* something
is done a certain way, not just *what* it does.

## ConfigModel - typed config, not a `.get()` chain

Instead of `cfg["segmentation"].get("segments", [])`, you write
`cfg.segmentation.segments`. Dataclasses in
[`ConfigModel.py`](GenericSpecimenManager/Resources/ConfigModel.py) fall into two groups:

- **Section dataclasses** (`StudyConfig`, `SegmentationConfig`,
  `LandmarksConfig`, `GlobalWindowLevelConfig`, `BatchExportConfig`,
  `BatchModeConfig`, `SegmentEditorConfig`, `BrushConfig`,
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

## Config schema (complete, 1:1 with `ConfigModel.py`)

```jsonc
{
  "study_dir": "...", "database_csv_path": "...", "preseg_csv_path": "...",
  "key_columns": ["ID"],                       // composite key, present in BOTH csvs
  "done_column": "done",
  "table_columns": ["ID", "comment", "done"],  // ANY database.csv column can be shown/edited
  "output_dir_pattern": "{ID}",                 // curly-brace format string, builds each specimen's output folder

  "defaults": {
    "image":   { /* ImageConfig fields - see below - applied to every images[] row */ },
    "segment": { /* SegmentConfig fields - applied to every segments[] row */ }
  },
  "presets": {
    "ct_default": { "window_level": {"min": -150, "max": 700}, "color_table": "Grey" }
  },

  "images": [
    // A) explicit image: defaults.image -> presets.<preset> -> this dict, in that order
    { "name": "background", "csv_column": "background", "role": "background",
      "path_pattern": "{ID}/{name}.nii.gz",     // only used if csv_column resolves to nothing
      "preset": "ct_default", "type": "volume", "required": true,
      "opacity": 1.0, "color_table": "Grey", "interpolate": true,
      "window_level": {"min":-150,"max":700},   // OR {"auto":true} OR {"window":..,"level":..}
      "threshold": {"min":1,"max":300,"apply":true} },

    // B) dynamic image: opens one per preseg.csv column that matches the regex AND
    //    is non-empty FOR THAT specimen. Name = the column's name (prefix/suffix strippable).
    { "pattern": "^seq_.*$", "strip_prefix": "seq_", "preset": "ct_default" }
  ],

  "segmentation": {
    "enabled": true,
    "reference_image": "mask",
    "path_pattern": "{ID}/{segment_name}.nii.gz",   // default naming, overridable per segment
    "segments": [
      { "name": "liver", "csv_column": "liver_path", "color": [0.8,0.1,0.1] },  // source: "file" (default)
      { "name": "tumor", "source": "empty", "color": [1,1,0] }                   // never tries a file
    ],
    "output_filename": "segment.seg.nrrd", "opacity": 0.5
  },

  "landmarks": { "enabled": true, "csv_column": "markups_path", "path_pattern": "{label}-markups.mrk.json",
                 "template_path": "template.mrk.json", "writable": true, "color": [1,1,0] },

  "volume_rendering": [
    // LIST - one entry per image, any/all of them can be enabled at once
    { "image": "t1", "enabled": true, "preset": "CT-Chest-Contrast-Enhanced",
      "window_level": {"min": -200, "max": 800} }     // optional shift, OR {"window":..,"level":..}
  ],

  "window_level": { "enabled": false, "min": -150, "max": 700 },  // GLOBAL, applied to every loaded volume

  "batch_mode": { "enabled": true, "column": "batch" },

  "batch_export": {
    "enabled": true, "export_segments": true, "export_markups": true,
    "reference_image": "mask", "segments_filter": ["liver", "tumor"],
    "output_dir": "results", "per_batch_subfolder": true   // only with batch_mode enabled
  },

  "segment_editor": {
    "overwrite_mode": "none",     // "none" = allow overlap (default) | "all_segments" | "visible_segments"
    "brush": { "shape": "sphere", "diameter_mm": 5, "relative": false },
    "active_effect": "Paint",
    "attributes": { "BrushSphere": "1" }    // escape hatch, see the key format note below
  }
}
```

### Path resolution (images, segments, markups - all the same rule)

1. If `csv_column` is set and non-empty for this specimen → use its value
   (resolved relative to `study_dir` unless already absolute).
2. Otherwise `path_pattern.format(...)`, available keys: every `key_columns`
   value, every column of that specimen's `database.csv`/`preseg.csv` row,
   plus `{name}` for images or `{segment_name}` for segments.
3. A dynamic (`pattern`) image has no `path_pattern` fallback - if the
   matching column is empty for a given row, that image is simply skipped
   (so one specimen might end up with 3 images and another with 5, from the
   same config).

## Config Editor

A "Config Editor..." button lives in every module GUI. It's a standalone,
non-modal window that **automatically opens pre-loaded with whatever config
is currently active in the main module** (if any). Nearly the whole schema
is editable tab-by-tab, without hand-writing JSON. Tabs are ordered as a
data-flow story: what to load, in what order it's used, then how the
workspace/tools around it behave:

| tab | in a sentence |
|---|---|
| General | paths, key/table/output-dir columns, batch export |
| Images | the images[] table + live merge preview |
| Segmentation | segments[] table + reference/path pattern |
| Landmarks | markups file/template config |
| Workspace | window/level, slice rotation, crosshair, ruler, 3D marker |
| Segment editor | brush/overwrite-mode/active-effect defaults |
| Volume rendering | per-image VR table (enable/preset/shift) |
| Defaults / Presets | the `defaults`/`presets` JSON + example catalogue |
| Manual edit config | raw-JSON preview and round-trip |

**General** - Study dir first (set it before browsing the two CSVs below - they
display relative to whatever it already contains); key/table/output-dir
columns; "Show CSV columns..." (both CSVs' headers + the columns common to
both = likely key-column candidates); **Batch export** fields at the bottom
(enabled, export_segments/markups, reference_image, segments_filter,
output_dir, per_batch_subfolder).

**Images** - quick-add table (column name + Add + Labelmap checkbox); the main
table (name, csv_column, pattern/strip, type, role, required, **Preset**
dropdown populated live from the Presets JSON, **Color table** dropdown -
curated + freely editable, opacity); "Edit advanced..." popup (window_level/
threshold/interpolate); a live **Effective settings** preview for the
selected row.

**Segmentation** - enabled, reference_image, path_pattern, output_filename; a
segments table (name, source, csv_column, path_pattern, color picker).

**Landmarks** - enabled, csv_column, path_pattern, template_path, writable,
color.

**Workspace** - blanket window/level; slice rotation (Red/Yellow/Green,
degrees); crosshair mode/behavior/thickness; ruler and 3D orientation
marker - all applied once per specimen load. Every field defaults to
`(unset)` (leave Slicer's own default alone) except the three crosshair
fields, which fall back to this module's long-standing defaults.

**Segment editor** - overwrite_mode; brush (shape/diameter/"Use absolute size
(mm)" checkbox); active_effect; raw attributes (JSON).

**Volume rendering** - a table, one row per Images-tab image: Image / Enable /
Preset (dropdown) / Min / Max / Offset. Any number of images can be enabled
at once; "Refresh image list" keeps it in sync as the Images tab changes.

**Defaults / Presets** - `defaults.image`, `defaults.segment`, `presets` as
JSON fields, with a worked example of the merge order; "Insert example..."
(defaults.image) and "Show example presets..." (13 ready-made CT/MRI/PET/
overlay presets, HTML card view, "Insert ALL" button).

**Manual edit config** - a live preview of the actual JSON that would be
written ("Refresh from form") and loading hand-edited JSON back into the
tabs ("Apply to form"). Save always builds from the tabs, so hand edits
here need Apply first or they won't be saved.

**Help**: a "Help" button opens a `QTextBrowser`-rendered HTML cheat sheet
(source: [`Resources/Html/help_cheatsheet.html`](GenericSpecimenManager/Resources/Html/help_cheatsheet.html);
scrollable, copyable - not a wall of plain text), one section per tab (in
the same order as the tabs), with concrete examples (e.g. the Segment
Editor section includes a real node-attribute dump plus step-by-step
instructions for finding the exact attribute name on your own Slicer
version).

**New / Load from file / Reload from disk**: New and Load from file both
prompt Save/Discard/Cancel first if the form has unsaved changes. Reload
from disk re-reads the CURRENTLY open file - handy after hand-editing it
outside the dialog, without having to browse again.

**Save -> reload in the active module**: right after a successful Save, if
the dialog was opened from the main module (not standalone), it offers to
push the just-saved config straight into the active scene - the same as
clicking "Select .json file" there again, without having to re-browse.

**Workflow safety**: every field is watched for changes (a `_dirty` flag),
the title bar shows a trailing `*` while dirty; closing (button or window
"X") also prompts Save/Discard/Cancel, **defensively wrapped** - if anything in that

save-prompt logic itself throws, the window still closes rather than
getting stuck open (see below for why that mattered in practice).

### Content you can extend without touching code

Two of the Config Editor's content sources are deliberately **externalized
from [`ConfigEditor.py`](GenericSpecimenManager/Resources/ConfigEditor.py)**, so they can be
extended later without any Python knowledge:

- **[`Resources/Html/help_cheatsheet.html`](GenericSpecimenManager/Resources/Html/help_cheatsheet.html)**
  - the full content behind the "Help" button. Plain editable HTML/CSS (Qt's
  rich-text subset - don't expect full browser compatibility, but the usual
  `<h2>/<ul>/<li>/<table>/<pre>/<code>` all work). A new section is just a
  new `<h2>...</h2>` block - nothing to change in the `.py` file.
- **[`Resources/Html/example_presets_template.html`](GenericSpecimenManager/Resources/Html/example_presets_template.html)**
  - the static frame/style for the "Show example presets..." popup, with a
  `{{CONTENT}}` placeholder that the code fills in at runtime (since that
  part is itself data-driven - see below). If you just want to tweak the
  popup's look (colors, font size, layout), this is the file.
- **[`Resources/Presets/example_presets.json`](GenericSpecimenManager/Resources/Presets/example_presets.json)**
  - the actual preset catalogue data:
  `{"<name>": {"description": "...", "preset": {...ImageConfig fields...}}}`.
  Adding a preset = adding a JSON entry, **no code required**. This one file
  feeds the "Show example presets..." popup, the "Insert ALL" button, AND
  the two starter presets (`ct_soft_tissue`, `ct_bone`) a brand-new config
  gets by default - all three read the same file via
  `ConfigEditorDialog._load_example_presets()` (cached after the first
  read) and `_preset_resource_dir()` for the folder path.

All three loaders are **defensive**: a missing/broken file doesn't crash
anything - it just returns an empty catalogue
(`Presets/example_presets.json`) or a short inline error message
(`help_cheatsheet.html` / `example_presets_template.html`). See
`_load_example_presets()` / `_load_html_resource()`.

## Segment Editor integration - the full story

This section is deliberately detailed because **it broke across several
iterations**, and the final, working solution isn't obvious. If this ever
needs touching again, re-read this first.

### Bug 1: wrong attribute-key format

The brush parameters (`BrushSphere`, `BrushAbsoluteDiameter`,
`BrushRelativeDiameter`, `BrushDiameterIsRelative`) are **common
(effect-independent) attributes** on `vtkMRMLSegmentEditorNode` - they have
**no effect prefix**. Only effect-specific settings use an
`EffectName.ParamName` form (e.g. `Paint.ColorSmudge`, a literal **dot**,
not a comma). A real node's attribute dump:

```
BrushAbsoluteDiameter: 25
BrushDiameterIsRelative: 1
BrushSphere: 0
Paint.ColorSmudge: 0
Threshold.MinimumThreshold: 69.75
```

For a while the code wrote `"Paint,BrushSphere"` / `"Paint.BrushSphere"` -
neither of which ever existed, so the config **had zero effect** on
anything, completely silently.

### Bug 2: `active_effect` on a "bare" (context-less) node

An earlier version registered the `vtkMRMLSegmentEditorNode` as a
class-level DEFAULT/template node (`AddDefaultNode`), and also set
`active_effect` on it. That node has no attached segmentation and no source
volume. When the real Segment Editor widget clones this template and tries
to immediately activate the effect with no context - **several effects
crash natively (no Python traceback at all)**. This caused a full Slicer
crash on module switch.

**Fix**: `active_effect` is **never** set on the bare default/template
node. It's only applied once the node actually has a segmentation attached
(`node.GetSegmentationNode() is not None`) - i.e. it's genuinely in use.

### Bug 3: redundant duplicate write → GUI freeze

An intermediate version called `effect.setParameter(...)` and
`effect.updateGUIFromMRML()` by hand, AFTER the node-attribute write, "just
to be safe". `SetAttribute()` ALREADY triggers the widget's own automatic
MRML→GUI sync (via the Modified event) - the extra manual call caused a
**nested, double GUI update** that, on an exception between a
`blockSignals(True)`/`(False)` pair, **permanently left the widget's
signals blocked** → every brush control froze in the GUI.

**Fix**: only ONE write path - `SetAttribute()` on the node, no manual
poking at the effect object.

### Bug 4: ordering - brush written BEFORE activation, not after

`SetActiveEffectName(...)` can itself run something like a
`setMRMLDefaults()` routine that **overwrites** the brush attributes with
its own factory defaults (e.g. a 3% relative brush size) - if the brush
write happened before this call, our config was immediately clobbered.

**Fix**: activate first, write brush attributes after - ours needs to be
the last (winning) write.

### The final, two-layer solution

1. **Once, at Study Init**
   (`GenericSpecimenManagerLogic._configure_segment_editor_defaults`):
   applies safe defaults - to the default/template node AND to any
   already-existing live node, but only sets `active_effect` if that live
   node already has a segmentation attached.
2. **Per specimen, on load**
   (`GenericSpecimen._activate_segment_editor`): via the Segment Editor
   widget, **first** set the segmentation + source volume (real context),
   **then** write brush attributes, **then** activate the effect (now
   safe), and **finally** switch to that module - so it appears
   automatically, already configured, every time a specimen loads.

## Volume Rendering - a per-image list + the correct VTK API

`volume_rendering` is a **list**, not a single object - any number of
images can be `enabled` at once, each with its own preset and an optional
min/max (or window/level) shift.

For the shift, **I searched before coding** - my first attempt would have
used a nonexistent `vtkPiecewiseFunction.AdjustRange()` /
`vtkColorTransferFunction.AdjustRange()` method (a plausible-sounding but
invented API). A real, community-verified Slicer script (the
"shiftVolumeRendering" gist) shows the actual, documented pattern:

```python
volProp = volumePropertyNode.GetVolumeProperty()
scalarOpacity = volProp.GetScalarOpacity()   # vtkPiecewiseFunction
# per control point: GetNodeValue() -> modify x -> RemoveAllPoints() + AddPoint()
```

`GenericSpecimen._remap_transfer_function()` does the same thing, but
instead of a fixed offset (like the original gist), it linearly rescales
the control points into an **arbitrary target range** (preserving shape and
color/opacity values, only moving the x-position) - this works for both the
opacity (`vtkPiecewiseFunction`) and color (`vtkColorTransferFunction`)
transfer functions (the latter's write-back method is `AddRGBPoint`, with a
6-value node `[x,r,g,b,midpoint,sharpness]`, versus opacity's 4-value node
`[x,y,midpoint,sharpness]`).

Verified with a mocked test: control points originally spanning
`[-450..1000]` correctly shift/rescale into a new `[-200..800]` range, with
relative positions (fractions) and y/RGB values left unchanged.

Each entry also supports a plain `offset` (a fixed shift, no rescale - the
gist's original technique, via `_offset_transfer_function()`) as an
alternative to `window_level`; if both are set, `offset` wins. Note: this
shifts the actual render correctly, but Slicer's own Volume Rendering
module's "Shift" slider won't reflect it - cosmetic only.

## Error handling in the main module

**Live, continuous validation** (not just a popup on click): the
Config/DB/Preseg path fields constantly show their state - red border =
doesn't exist, yellow = it's a folder (not a file), green = OK. See
`GenericSpecimenManagerWidgetBase._validatePathField`.

**Pure-Python preflight check** (`_preflight_check`), run before Initialize
Study, **before** any Slicer/VTK call happens:
1. Does the config path exist, and is it a file (not a folder - the
   `Config/` folder is pre-filled by default as a browse starting point,
   which was easy to accidentally try to open as a file, raising an
   `IsADirectoryError`)?
2. Can the database/preseg CSV be read with plain Python's `csv` module (not
   Slicer's `loadTable` - which can throw a native, scary error dialog on an
   empty/broken path that a Python `try/except` can't cleanly catch)?
3. Do the config's `key_columns` **actually appear** in both CSVs' headers -
   if not, a specific message (the missing column names plus the CSVs' real
   headers), not a vague downstream error.

Every "fix your input" message uses `warningDisplay` (instead of
`errorDisplay`) - a less alarming style for a simple user mistake; actual
exceptions (JSON parse errors, an `initializeStudy` crash) still use
`errorDisplay`.

**Re-init protection**: if a specimen is active and you click Initialize
Study, a Save/Discard/Cancel prompt appears first - re-initializing the
study could lose, or misattribute, the open specimen's unsaved work.

## Batch mode & batch export

With `batch_mode.enabled`, the GUI shows a batch-select combo (`cmbBatch`)
after Initialize Study, populated with the unique values of
`batch_mode.column` ("(all)" plus every value). Switching re-filters the
table. **Switching is blocked while a specimen is active** - it must be
closed first, or export/save could get attributed to the wrong row.

A single **Batch Export** button runs
[`BatchProcessor`](GenericSpecimenManager/Resources/BatchProcessor.py)
against every `done` specimen, driven entirely by `cfg.batch_export`. In
one pass, any combination of:

- **export_segments** - each segment exported to its own labelmap file via
  Slicer's native `ExportSegmentsToLabelmapNode` (handles overlapping
  segments correctly - each segment gets its own independently-exported
  mask, never a shared multi-label array to misinterpret)
- **export_markups** - the markups file
- **compute_stats** - custom per-segment statistics (volume, min, max,
  mean, median, std, and/or `percentile_<N>`), computed from the same
  per-segment labelmap export + `slicer.util.arrayFromVolume()` + plain
  numpy (no pandas, no third-party segmentation-file reader).
  `stats_reference_images` (comma-separated in the Config Editor, or "Use
  all loaded images") is one or more sample volumes - each gets its OWN
  row per segment (an `image` column joins the key/segment columns), so
  multi-sequence studies (e.g. native/arterial/portal-phase MR) get one
  stats row per phase per segment. All sample images must share the
  segmentation's geometry. Every specimen's rows are concatenated into
  **one combined CSV** (`stats_output_path`, plain and study_dir-relative
  unless absolute, `{date}` substituted if present - defaults to
  `report.csv`), ordered by key columns, then image, then segment name.
  `stats_metrics` is comma-separated in the Config Editor; leave it unset
  to use
  [`Definitions.DEFAULT_STATS_METRICS`](GenericSpecimenManager/Resources/Definitions.py).

Each specimen is loaded through the **lean**
`GenericSpecimen.load_for_batch()` path - only the segmentation plus at
most one reference/"master" volume (never the full configured image set),
skipping workspace settings, volume rendering, and Segment Editor
activation entirely, since none of that is needed for a headless batch
run. Per-batch export: with `batch_export.per_batch_subfolder: true`,
exports go into `<out_dir>/<batch_value>/...` folders instead of one flat
folder.

## Logging & feedback

Every file uses the shared `logger` from
[`Resources/LoggingSetup.py`](GenericSpecimenManager/Resources/LoggingSetup.py)
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
[`Resources/Definitions.py`](GenericSpecimenManager/Resources/Definitions.py) -
one file to check when looking for a knob to turn, instead of hunting
through class bodies.

A specimen load always switches the layout to the standard Four-Up view
(Red/Yellow/Green/3D) - hardcoded, no config option, since there wasn't a
good reason to make this configurable.

## Development notes

- **Testing without a live Slicer**: every non-trivial change was verified
  with a mocked-`qt`/`vtk`/`slicer` smoke test (fake widget classes
  implementing only what that particular test needs). This doesn't replace
  testing in a real Slicer session, but it does catch syntax errors, wrong
  call order, and missing parameters.
- **Don't guess Slicer/VTK APIs** - see the Volume Rendering section above:
  a plausible-sounding but nonexistent method name (`AdjustRange`) would
  have sailed through code review, only failing in a live session. When an
  API is uncertain, search for it, or at least flag explicitly in the
  code/docstring that it isn't 100% confirmed.
- **Dataclass, not a `.get()` chain** - if a new top-level config section is
  needed, always introduce it in [`ConfigModel.py`](GenericSpecimenManager/Resources/ConfigModel.py)
  as a dataclass (with a `from_dict` classmethod); don't let a raw dict leak
  into the engine.
- **Backward compatibility is not a goal** - the schema has changed shape
  more than once (e.g. `volume_rendering` from a single object to a list),
  and this was deliberately NOT handled backward-compatibly. The goal is a
  fast, clear adaptation to the NEXT problem, not eternal support for old
  configs.

## Adding a new study/species

1. Write `Config/<species>_config.json` per the schema above - or start from
   the Config Editor (New → browse the CSVs → "Show CSV columns..." for the
   key columns → Images tab quick-add → Save).
2. In the GUI, `Select .json file` → "Initialize Study".
3. Once it's final, optionally add a short, reference-style wrapper to
   [`Examples/`](GenericSpecimenManager/Examples) (not required - the files there aren't registered
   in CMake, they just document what a dedicated, named/iconed module would
   look like if one were ever needed).
