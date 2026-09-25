# Config Editor

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
status" in [the main module page](main-module.md)); **Auto-save database**; **Filtering** - "Group specimens by
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
an `{index}` placeholder (see [Batch mode & batch export](batch-export.md)
for exactly how these resolve, group, and what `{index}` does).

**Images** - a **Quick add from preseg columns...** popup (column name + Add + Labelmap checkbox); the main
table (name, csv_column, type, role, required, **Preset**
dropdown populated live from the Presets JSON, **Color table** dropdown -
curated + freely editable, opacity); "Edit advanced..." popup (path_pattern/window_level/
threshold/interpolate); a live **Effective settings** preview for the
selected row. A **Default path pattern** field above the table
(`defaults.image.path_pattern`) finds the file of every image whose CSV column is
empty or not set - so an image that is not in the preseg CSV can be added as a
name-only row.

**Segmentation** - enabled, reference_image, path_pattern, output_filename; a
segments table (name, source, csv_column, path_pattern, color picker).

**Markups** - enabled, csv_column, path_pattern, template_path, writable,
color (a picker - *Set color...* / *Clear*, same as the segments' colors), size (point scale, or millimetres with *in mm*) and shape (e.g. *Sphere3D*, a 3D ball that shows across several slices).

**Workspace** - (also: optional **Specimen annotation** - `workspace.specimen_annotation` - yellow top-left text in the Red/Yellow/Green/3D views showing the loaded specimen's ID, a rule, one `column: value` line per remaining Table column, a rule, and the status; live-updated on table edits; its font size/color/background are constants in `definitions.py`); blanket window/level; slice rotation (Red/Yellow/Green,
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
(source: [`Resources/Html/config_editor_help_cheatsheet.html`](../GenericSpecimenManager/GenericSpecimenManager/Resources/Html/config_editor_help_cheatsheet.html);
scrollable, copyable, with a section-jump combo and a search bar - not a wall of
plain text), one section per tab (in the same order as the tabs), with concrete
examples (e.g. the Segment Editor section includes a real node-attribute dump plus
step-by-step instructions for finding the exact attribute name on your own Slicer
version). The same popup (`gui/help_dialog.py`) shows the main module's own cheat sheet,
[`module_help_cheatsheet.html`](../GenericSpecimenManager/GenericSpecimenManager/Resources/Html/module_help_cheatsheet.html),
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

## Content you can extend without touching code

Two of the Config Editor's content sources are deliberately **externalized
from [the Config Editor code](../GenericSpecimenManager/GenericSpecimenManager/Resources/gui/config_editor)**, so they can be
extended later without any Python knowledge:

- **[`Resources/Html/config_editor_help_cheatsheet.html`](../GenericSpecimenManager/GenericSpecimenManager/Resources/Html/config_editor_help_cheatsheet.html)**
  - the full content behind the "Help" button. Plain editable HTML/CSS (Qt's
  rich-text subset - don't expect full browser compatibility, but the usual
  `<h2>/<ul>/<li>/<table>/<pre>/<code>` all work). A new section is just a
  new `<h2>...</h2>` block - nothing to change in the `.py` file.
- **[`Resources/Html/example_presets_template.html`](../GenericSpecimenManager/GenericSpecimenManager/Resources/Html/example_presets_template.html)**
  - the static frame/style for the "Show example presets..." popup, with a
  `{{CONTENT}}` placeholder that the code fills in at runtime (since that
  part is itself data-driven - see below). If you just want to tweak the
  popup's look (colors, font size, layout), this is the file.
- **[`Resources/Presets/example_presets.json`](../GenericSpecimenManager/GenericSpecimenManager/Resources/Presets/example_presets.json)**
  - the actual preset catalogue data:
  `{"<name>": {"description": "...", "preset": {...ImageConfig fields...}}}`.
  Adding a preset = adding a JSON entry, **no code required**. This one file
  feeds the "Show example presets..." popup, the "Insert ALL" button, AND
  the two starter presets (`ct_soft_tissue`, `ct_bone`) a brand-new config
  gets by default - all three read the same file via
  `ConfigEditorDialog._loadExamplePresets()` (cached after the first
  read) and `_presetResourceDir()` for the folder path.

All three loaders are **defensive**: a missing/broken file doesn't crash
anything - it just returns an empty catalogue
(`Presets/example_presets.json`) or a short inline error message
(`config_editor_help_cheatsheet.html` / `example_presets_template.html`). See
`_loadExamplePresets()` / `_loadHtmlResource()`.
