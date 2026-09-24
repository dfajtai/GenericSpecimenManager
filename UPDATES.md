# Updates

Newest first. Built from the Done list in [TODO.md](TODO.md).

## 2026-09-24

- **Config Editor / Batch Export tab refinement**
  - Batch operations reordered (export segments, custom segment statistics / export markups, markup summary), laid out as a 2x2 grid.
  - `landmarks` renamed to `markups` everywhere (config keys, code, Config Editor, Help, README).
  - Settings split into Segment export settings, Segment statistics settings (own segments filter) and Markup summary settings.
  - `{index}` placeholder: adds a two-digit `_01`-based counter before the extension so an existing report is never overwritten.
- **Specimen status** (replaces the 0/1 `done` column): `done_column` -> `status_column` (default `status`), integer enum `0` untouched / `1` in progress / `2` to review / `3` finished (defined in `Definitions.py`). Table row colors: white / light blue / pale yellow / darker green. `1` is set automatically when a specimen loads from its own saved file or is saved (never downgrades `2`/`3`); Batch export processes only `3`. A Status filter checklist (`status_filter.enabled`, on by default; Config Editor: General → Filtering) shows only the ticked statuses. Existing configs/CSVs need the column renamed and `1` values reviewed.
- **Reset selected specimen**: a pastel-red button under Load (works on the selected row, no need to load it) that deletes the specimen's saved segmentation and markups files and sets its status to `untouched`. The confirmation lists the files and requires typing RESET; a loaded specimen is closed too. Save and Close now sit in their own full-width rows.
- **Cheat sheets**: `help_cheatsheet.html` renamed to `config_editor_help_cheatsheet.html`; the main module got its own `module_help_cheatsheet.html` (workflow, study settings, specimen table, status, load/save/close, reset, batch export) behind a collapsed **Help** block at the bottom of the module. Both open in the same popup (`HelpDialog.py`) with a section-jump combo and a search bar that wraps around.
- **Main module GUI**: three Slicer-style collapsible blocks (like the Markups module) - **Advanced Study Settings** (collapsed; config/CSV paths), **Specimen browser** (Group + Status filters side by side in one row, table, buttons) and a collapsed **Help**, with the **Initialize Study** button between the first two (pastel green until a study is initialized; **Save database CSV** and **Batch export** appear under it once it is, if the config wants them). Config Editor General tab: *Grouping* is now **Filtering**, *Group specimens by key* and its key column share one row (1:3), plus a *Filter by status* checkbox.
- **Batch export** no longer re-initializes the study on every run, and with no `finished` specimen it stops at once with a clear message (status counts + how to fix it).
- **Ctrl+S** saves the active specimen (same as *Save progress*, quietly with a status-bar note) from any Slicer module while a specimen is loaded; without one, Slicer's own Save scene shortcut works as usual.
- Columns created through the *missing columns* dialog at Initialize Study are written to `database.csv` right away.
- **Main module**
  - Specimen table: whole-row selection, height fits the row count (capped, never makes the whole module scroll), the status column is a dropdown and binary factor columns render as checkboxes.
  - Status dot next to the selected/active specimen (gray / green / orange for unsaved changes).
  - Buttons that need an initialized study start disabled; Close active specimen offers "Yes, mark to review" / "Yes, mark finished".
  - Auto-save database is set only by `auto_save_database` in the config (the main module's checkbox is gone); the Save database CSV button is hidden while it is on.
  - Factor columns (`factor_columns`): checkbox or level dropdown for any `database.csv` column; missing columns are offered for creation at Initialize Study.
  - Optional specimen annotation (`workspace.specimen_annotation`): the loaded specimen's database row as yellow text in the views.
  - Initialize Study / Config Editor offer Browse / Open clean Config Editor / Cancel instead of error popups when the config path is not a file.

## 2026-09-23

- Batch export rework with additional features (segment statistics, markup summary, and so on).

## 2026-09-22

- Batch mode custom "segment statistics" reporting to a CSV file.
- Batch export fixes (export segmentations to masks, segment by segment, handling overlap).

## 2026-09-18

- Colored logging.
- Radiologist / Neurologist view convention.

## Earlier (undated)

- Hide Reload & Test, Help & Acknowledgement.
- Volume rendering preset offset (min/max rescale plus fixed offset, both supported).
- Main README updated (examples, tree structure, links).
- Volume rendering column width adjust.
- Slice rotation config (Red/Yellow/Green in-plane rotation).
- Workspace tab (window/level, slice rotation, crosshair, ruler, orientation marker).
