# GenericSpecimenManager

A single, JSON-configured Slicer module. No per-species Python module - one
`config.json` describes a study (which images, which segments, which
markups, batch export, how the Segment Editor should behave, ...), and the
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
    │   ├── BatchProcessor.py                     <- batch export/statistics, run against every 'finished' specimen
    │   ├── ConfigEditor.py                       <- the dialog behind the "Config Editor..." button
    │   ├── Definitions.py                        <- every hardcoded toggle/curated choice list, in ONE place
    │   ├── HelpDialog.py                         <- the shared cheat-sheet popup (section jump + search) used by both Help buttons
    │   ├── LoggingSetup.py                       <- shared logger, optional log-to-file
    │   ├── Presets/example_presets.json          <- Config Editor's preset catalogue - extensible without code
    │   ├── Html/                                 <- Help / example-presets HTML content - extensible without code
    │   │   ├── config_editor_help_cheatsheet.html
    │   │   ├── module_help_cheatsheet.html       <- the main module's own cheat sheet (the collapsed Help block at the bottom of the module)
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
| [`Resources/BatchProcessor.py`](GenericSpecimenManager/Resources/BatchProcessor.py) | `BatchProcessor` - segment/markup export and/or custom statistics for every `finished` specimen, one combined CSV |
| [`Resources/ConfigEditor.py`](GenericSpecimenManager/Resources/ConfigEditor.py) | GUI for building/editing `config.json` without hand-writing JSON |
| [`Resources/Definitions.py`](GenericSpecimenManager/Resources/Definitions.py) | every hardcoded toggle (e.g. `HIDE_HELP_AND_ACKNOWLEDGEMENT`) and curated dropdown-choice list, in one findable place |
| [`Resources/HelpDialog.py`](GenericSpecimenManager/Resources/HelpDialog.py) | the shared cheat-sheet popup (section-jump combo + search bar) behind both Help buttons |
| [`Resources/LoggingSetup.py`](GenericSpecimenManager/Resources/LoggingSetup.py) | the shared `logger` every other file uses instead of `print()`, with an optional log-to-file toggle |
| [`Resources/Presets/example_presets.json`](GenericSpecimenManager/Resources/Presets/example_presets.json) | Config Editor's preset catalogue - **data, not code**, freely extensible |
| [`Resources/Html/*.html`](GenericSpecimenManager/Resources/Html) | the two cheat sheets (Config Editor's and the main module's) + example-presets popup content - **data, not code**, freely extensible |

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

## Config schema (complete, 1:1 with `ConfigModel.py`)

```jsonc
{
  "study_dir": "...", "database_csv_path": "...", "preseg_csv_path": "...",
  "key_columns": ["ID"],                       // composite key, present in BOTH csvs
  "status_column": "status",
  "table_columns": ["ID", "comment", "status"],  // ANY database.csv column can be shown/edited
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

  "markups": { "enabled": true, "csv_column": "markups_path", "path_pattern": "{label}-markups.mrk.json",
               "template_path": "template.mrk.json", "writable": true, "color": [1,1,0] },

  "volume_rendering": [
    // LIST - one entry per image, any/all of them can be enabled at once
    { "image": "t1", "enabled": true, "preset": "CT-Chest-Contrast-Enhanced",
      "window_level": {"min": -200, "max": 800} }     // optional shift, OR {"window":..,"level":..}
  ],

  "window_level": { "enabled": false, "min": -150, "max": 700 },  // GLOBAL, applied to every loaded volume

  "auto_save_database": false,   // write database.csv after every table edit (default false; hides "Save database CSV")
  "group_by_key": { "enabled": true, "column": "batch" },
  "status_filter": { "enabled": true },        // optional; on by default - the main module's Status filter checklist

  "factor_columns": [
    // Renders as a checkbox (binary) or a level dropdown (multilevel) in the main module's
    // specimen table instead of free text. Only shows up if the column is ALSO in table_columns.
    { "column": "sex", "type": "binary" },
    { "column": "treatment", "type": "multilevel", "levels": ["control", "low", "high"] }
  ],

  "batch_export": {
    "enabled": true, "export_segments": true, "export_markups": true,
    "reference_image": "mask", "segments_filter": ["liver", "tumor"],       // export_segments only
    "stats_segments_filter": ["liver"],                                    // compute_stats only, independent of segments_filter
    "output_dir": "results", "output_dir_pattern": "{batch}/{ID}",  // per-specimen, {column} mechanism
    "stats_output_path": "{batch}/report_{index}.csv",              // {index} = 01-based, avoids overwriting a previous run
    "markups_report": true, "markups_output_path": "{batch}/markups_{index}.csv"
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
| General | paths, key/table/output-dir columns, Filtering ("Group specimens by key", "Filter by status"), factor columns |
| Batch export | headless batch run: what to produce, where it goes, and the segment/markup reports |
| Images | the images[] table + live merge preview |
| Segmentation | segments[] table + reference/path pattern |
| Markups | markups file/template config |
| Workspace | window/level, slice rotation, crosshair, ruler, 3D marker |
| Segment editor | brush/overwrite-mode/active-effect defaults |
| Volume rendering | per-image VR table (enable/preset/shift) |
| Defaults / Presets | the `defaults`/`presets` JSON + example catalogue |
| Manual edit config | raw-JSON preview and round-trip |

**General** - Study dir first (set it before browsing the two CSVs below - they
display relative to whatever it already contains); key/table/output-dir
columns; "Show CSV columns..." (both CSVs' headers + the columns common to
both = likely key-column candidates); **Status column** (the `database.csv`
column holding each specimen's status - any name, e.g. `done`; see "Specimen
status" below); **Auto-save database**; **Filtering** - "Group specimens by
key" (with its key column on the same row) and "Filter by status", both
main-module-only viewing conveniences (a group-select combo / a status
checklist above the table), with zero effect on the Batch export tab. **Factor columns** - a
small table (Add/Remove) turning any `database.csv` column into a checkbox
("binary") or a level dropdown ("multilevel", with its own comma-separated
Levels field) in the main module's specimen table, instead of free-text
editing - a level is always written to the CSV as its exact text, never a
numeric index. Independent of Table columns: a factor column only actually
renders as a checkbox/dropdown if it's ALSO listed there.

**Batch export** - its own tab (it outgrew a group box inside General).
"Enable batch export" is the master switch; below it, **Batch export root
dir** is the base folder everything else on this tab is anchored to. Then
**Batch operations** (check any combination, in this order) - export_segments,
Custom segment statistics, then (on their own row) export_markups (also
writes a per-specimen markups CSV automatically - label/x/y/z, read
straight from the live markups node, not re-derived from the .mrk.json
file's "orientation" field, which is a display-only local axis frame, not
a per-point transform to apply on top of position) and Markup summary
(combines every specimen's markup points into one or more CSVs).
**Segment export settings** (reference_image, segments_filter,
output_dir_pattern) govern segment file export only. **Segment statistics
settings** has its own, independent segments filter (a segment can be
exported without being in the statistics, or vice versa), plus metrics and
the report pattern. **Markup summary settings** has its own pattern.
Both the statistics report pattern and the markup summary pattern support
an `{index}` placeholder (see the "Batch mode & batch export" section below
for exactly how these resolve, group, and what `{index}` does).

**Images** - quick-add table (column name + Add + Labelmap checkbox); the main
table (name, csv_column, pattern/strip, type, role, required, **Preset**
dropdown populated live from the Presets JSON, **Color table** dropdown -
curated + freely editable, opacity); "Edit advanced..." popup (window_level/
threshold/interpolate); a live **Effective settings** preview for the
selected row.

**Segmentation** - enabled, reference_image, path_pattern, output_filename; a
segments table (name, source, csv_column, path_pattern, color picker).

**Markups** - enabled, csv_column, path_pattern, template_path, writable,
color (a picker - *Set color...* / *Clear*, same as the segments' colors).

**Workspace** - (also: optional **Specimen annotation** - `workspace.specimen_annotation` - yellow top-left text in the Red/Yellow/Green/3D views showing the loaded specimen's ID, a rule, one `column: value` line per remaining Table column, a rule, and the status; live-updated on table edits; its font size/color/background are constants in `Definitions.py`); blanket window/level; slice rotation (Red/Yellow/Green,
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
(source: [`Resources/Html/config_editor_help_cheatsheet.html`](GenericSpecimenManager/Resources/Html/config_editor_help_cheatsheet.html);
scrollable, copyable, with a section-jump combo and a search bar - not a wall of
plain text), one section per tab (in the same order as the tabs), with concrete
examples (e.g. the Segment Editor section includes a real node-attribute dump plus
step-by-step instructions for finding the exact attribute name on your own Slicer
version). The same popup (`HelpDialog.py`) shows the main module's own cheat sheet,
[`module_help_cheatsheet.html`](GenericSpecimenManager/Resources/Html/module_help_cheatsheet.html),
from the collapsed **Help** block at the bottom of the module.

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

- **[`Resources/Html/config_editor_help_cheatsheet.html`](GenericSpecimenManager/Resources/Html/config_editor_help_cheatsheet.html)**
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
(`config_editor_help_cheatsheet.html` / `example_presets_template.html`). See
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

## Main module layout, specimen status, filter and reset

The module is three collapsible blocks in the Slicer style: **Advanced Study Settings** (collapsed; the
config and CSV paths), then the **Initialize Study** button (pastel green until a study is initialized;
**Save database CSV** - hidden with `auto_save_database` - and **Batch export** - only if the config
enables it - appear under it once it is), the **Specimen browser** (Group and Status filters in one row, the
table, Load / Reset / Save / Close) and a collapsed **Help** block.

Each specimen has a status, stored in the `status_column` of `database.csv` as an integer
(`0` untouched, `1` in progress, `2` to review, `3` finished; values live in `Definitions.py`).
The table always shows it as its last column, headed `Status`, as a dropdown that also colors the
row (white / light blue / pale yellow / darker green).

- **Automatic:** a specimen goes `0` → `1` when it loads from its own saved file or is saved. This
  never downgrades `2`/`3`. Closing without changes leaves the status alone.
- **Saving:** *Save progress for active specimen*, or **Ctrl+S** from any module while a specimen is loaded (Slicer's own Save scene shortcut is untouched when none is loaded).
- **Manual:** the table dropdown, or the Close active specimen dialog (*Yes, mark to review* /
  *Yes, mark finished*).
- **Status filter:** a checklist above the table (all ticked by default) shows only the specimens in
  the ticked statuses; it can be switched off with `status_filter.enabled` (Config Editor: General → Filtering → *Filter by status*). Batch export always processes `finished` specimens only, whatever the filter says.
- **Reset selected specimen...** (pastel-red button under *Load selected specimen*; works on the
  selected row, no need to load it): **permanently deletes** the specimen's saved segmentation and
  markups files and sets its status back to `untouched`. The confirmation dialog shows the specimen ID and the exact
  files, and the button only enables after typing `RESET`. If the specimen is currently loaded it
  is closed too (unsaved work is discarded). Source images are never touched.

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

**Config Editor with no valid config path**: clicking "Config Editor..."
while the config path field isn't an actual file - empty, still pointing
at a folder (the same default `Config/` browse starting point as above),
or a file that no longer exists - no longer fails with a raw error dialog
(or, for empty, silently opens blank with no explanation) - `onBtnConfigEditor`
checks `os.path.isfile` first and, if it's not one, asks instead: **Browse
for config.json...** (identical to clicking "Select .json file" - loads
the picked file into the active scene, then opens the Config Editor on
it), **Open clean Config Editor** (starts blank, same as New), or
**Cancel** (closes the prompt, opens nothing).

## Batch mode & batch export

With `group_by_key.enabled`, the GUI shows a group-select combo (`cmbGroupByKey`,
labeled "Group specimens by key" in the Config Editor's General tab) after
Initialize Study, populated with the unique values of `group_by_key.column`
("(all)" plus every value). Switching re-filters the table. **Switching is
blocked while a specimen is active** - it must be closed first, or
export/save could get attributed to the wrong row. This toggle is a
**main-module viewing convenience only** - `batch_export` never depends on
it; its own `output_dir_pattern`/`stats_output_path`/`markups_output_path`
can reference any database.csv column directly (including this one, by
name).

A single **Batch Export** button (under Initialize Study, shown once a study is initialized and the config enables batch export) runs
[`BatchProcessor`](GenericSpecimenManager/Resources/BatchProcessor.py)
against every `finished` specimen (it reuses the already-initialized specimen list - it doesn't re-initialize the study - and stops with a message listing the status counts if none is `finished`), driven entirely by `cfg.batch_export` -
configured on its own **Batch export** Config Editor tab (it outgrew a
group box inside General). In one pass, any combination of:

- **export_segments** - each segment exported to its own labelmap file via
  Slicer's native `ExportSegmentsToLabelmapNode` (handles overlapping
  segments correctly - each segment gets its own independently-exported
  mask, never a shared multi-label array to misinterpret). `segments_filter`
  (Config Editor: Segment export settings' "Segments filter") limits which
  segments get exported - independent of `stats_segments_filter` below.
- **compute_stats** - custom per-segment statistics (volume, min, max,
  mean, median, std, and/or `percentile_<N>`), computed from the same
  per-segment labelmap export + `slicer.util.arrayFromVolume()` + plain
  numpy (no pandas, no third-party segmentation-file reader).
  `stats_reference_images` (comma-separated in the Config Editor, or "Use
  all loaded images") is one or more sample volumes - each gets its OWN
  row per segment (an `image` column joins the key/segment columns), so
  multi-sequence studies (e.g. native/arterial/portal-phase MR) get one
  stats row per phase per segment. All sample images must share the
  segmentation's geometry. `stats_segments_filter` (Config Editor: Segment
  statistics settings' own "Segments filter") independently limits which
  segments get a statistics row - a segment can be included here without
  being exported to a file, or vice versa; `stats_metrics` is
  comma-separated in the Config Editor; leave it unset to use
  [`Definitions.DEFAULT_STATS_METRICS`](GenericSpecimenManager/Resources/Definitions.py).
- **export_markups** - the markups `.mrk.json` file, plus a per-specimen
  markups CSV (`label`, `x`, `y`, `z`) written automatically alongside it,
  read straight from the live markups node via
  `GetNthControlPointLabel()`/`GetNthControlPointPositionWorld()`. This is
  deliberately *not* re-parsing the raw `.mrk.json` file and multiplying
  its `orientation` field into `position` - in Slicer's markups schema,
  `position` is already the point's full world coordinate, and
  `orientation` is a separate, mostly-display-only local axis frame (or,
  at the file level, just the LPS/RAS sign convention) - it is not a
  per-point pose transform to apply on top of `position`. `x`/`y`/`z` are
  written in whatever convention `markups_coordinate_system` (Config
  Editor label: "Markup CSV coordinate encoding") says - `"RAS"` (default,
  Slicer's own world coordinate, written as-is) or `"LPS"` (flips x and y:
  `LPS = -x, -y, z` relative to RAS - useful when the CSV feeds an
  ITK/DICOM-based pipeline that expects LPS). This only affects the CSV
  columns; the `.mrk.json` file itself keeps Slicer's own coordinate
  handling untouched.
  `markups_report` (Config Editor label: "Markup summary" - needs
  `export_markups` also on) additionally combines every specimen's
  markup points into one or more CSVs via `markups_output_path` (Config
  Editor label: "Markup summary pattern") - same `{column}` pattern,
  root-anchoring, and emergent grouping-by-resolved-path as
  `stats_output_path` below, and the same coordinate encoding.

`output_dir` (optional root: unset -> `study_dir`; relative -> resolved
under `study_dir`; absolute -> used as-is) + `output_dir_pattern` (a
curly-brace pattern resolved **per specimen**, joined onto that root -
the exact same `{column}` mechanism as the top-level `output_dir_pattern`,
any key/database.csv/preseg.csv column; unset defaults the same way too,
joining the key columns) together govern **segment and markup export
only**. There's no separate on/off flag for "split by batch" - a database
column that varies per specimen (e.g. `{batch}/{ID}`) naturally routes
different specimens into different subfolders just by being referenced in
the pattern.

`stats_output_path` (Config Editor label: "Report pattern") and
`markups_output_path` (Config Editor label: "Markup summary pattern") are
each a curly-brace pattern, resolved per specimen, anchored directly to
the SAME shared root (`output_dir` if set, else `study_dir` directly)
segment/markup files use - but, unlike those, **never nested through
`output_dir_pattern`**; each is its own separate path right under that
root. They default to `report.csv` and `markups_report.csv` respectively,
and each groups/overwrites independently of the other - they can even
resolve to the same file if you point them there. Placeholders in both:

- `{column}` - any key/database.csv/preseg.csv column value
- `{date}` / `{time}` / `{datetime}` - the current date/time
  (`YYYY-MM-DD` / `HH-MM-SS` / combined)
- `{index}` - only if present in the pattern: the lowest-available
  two-digit `_NN` suffix (starting at `_01`) appended before the
  extension, based on what already exists on disk - e.g.
  `report_{index}.csv` -> `report_01.csv`, then `report_02.csv` on the
  next run, so a previous run's file is never clobbered. Without
  `{index}`, a pre-existing file at the resolved path is silently
  overwritten, exactly as before.

Grouping into one file or several is entirely emergent: specimens that
resolve to the same final path share one CSV; specimens that resolve to
different paths (the pattern references a column whose value differs,
e.g. `{batch}/report.csv`) end up in separate files instead - no separate
flag needed for that.

Each specimen is loaded through the **lean**
`GenericSpecimen.load_for_batch()` path - only the segmentation plus at
most one reference/"master" volume (never the full configured image set),
skipping workspace settings, volume rendering, and Segment Editor
activation entirely, since none of that is needed for a headless batch
run.

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

## Key reference

Every named constant/parameter used above, in one place - what it's called,
where you set it (config.json key and/or Config Editor field), and what it
actually does.

| Name | Where | Function |
|---|---|---|
| `study_dir` | General → Study dir | Root every relative path in the config resolves against. Empty → the preseg CSV's own folder. |
| `key_columns` | General → Key columns | Composite specimen ID (e.g. `ID` or `ID,measurement`) - must exist, with matching values, in both `database.csv` and `preseg.csv`. |
| `status_column` | General → Status column | `database.csv` column holding each specimen's status as an integer: `0` untouched, `1` in progress, `2` to review, `3` finished (created if missing). The column can have any name (e.g. `done`); the table always shows it as the last column, headed `Status`, as a dropdown that colors the row (not optional, no need to list it in `table_columns`). Batch Export processes only `3`. `1` is set automatically when a specimen loads from its own saved file or is saved; `2`/`3` are set manually (dropdown or the Close dialog). |
| `table_columns` | General → Table columns | Which `database.csv` columns are shown/editable in the main module's specimen table. |
| `output_dir_pattern` (top-level) | General → Output dir pattern | Per-specimen output folder for **interactive** work (segmentation/markups/saved images). Independent of `batch_export`'s own root dir/patterns below. |
| `group_by_key.column` | General → Group specimens by key | Database column used to populate the main module's group-select combo. Viewing convenience only - has no effect on Batch export. |
| `status_filter.enabled` | General → Filtering → Filter by status | Show the main module's Status filter (a checklist of the four statuses above the table). On by default. Viewing convenience only - Batch export ignores it. |
| `auto_save_database` | General → Auto-save database | On = `database.csv` is written to disk after every table edit, and the manual "Save database CSV" button is hidden. Default off. |
| `factor_columns` | General → Factor columns | Which `database.csv` columns render as a checkbox (`binary`) or a level dropdown (`multilevel`) in the main module's specimen table, instead of free text. Only takes effect for columns also listed in `table_columns`. |
| `batch_export.output_dir` | Batch export → Batch export root dir | The root every batch pattern below is anchored to (segment/markup files, and any relative Segment export/Report/Markup summary pattern). Empty → `study_dir`. |
| `batch_export.output_dir_pattern` | Batch export → Segment export pattern | Per-specimen subfolder, joined onto the batch root dir - governs segment + markup **file** export only. |
| `batch_export.segments_filter` | Segment export settings → Segments filter | Which segments get exported to a labelmap file. Independent of `stats_segments_filter`. |
| `batch_export.stats_segments_filter` | Segment statistics settings → Segments filter | Which segments get a statistics row. Independent of `segments_filter` - a segment can be in one, both, or neither. |
| `batch_export.stats_output_path` | Segment statistics settings → Report pattern | Statistics CSV path, anchored directly to the batch root dir (never nested through the Segment export pattern). Defaults to `report.csv`. |
| `batch_export.markups_output_path` | Markup summary settings → Markup summary pattern | Combined markup-summary CSV path, same anchoring rule as the Report pattern. Defaults to `markups_report.csv`. |
| `batch_export.markups_coordinate_system` | Markup summary settings → Markup CSV coordinate encoding | `RAS` (default) or `LPS` - which convention the x/y/z values in the per-specimen markups CSV and the combined summary CSV use. Does not affect the `.mrk.json` file itself. |
| `{column}` | Any path-pattern field | Any key/`database.csv`/`preseg.csv` column name in curly braces - substituted with that specimen's value. |
| `{date}` / `{time}` / `{datetime}` | Report pattern, Markup summary pattern | Current date/time, substituted once per batch run (`YYYY-MM-DD` / `HH-MM-SS` / combined). |
| `{index}` | Report pattern, Markup summary pattern | Only when present: a two-digit, `_01`-based counter inserted before the file extension, picking the lowest suffix not already on disk - so a previous run's file is never overwritten. Absent → existing file is overwritten as usual. |
