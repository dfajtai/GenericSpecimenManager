# Changelog

Newest first. Planned work is in the [roadmap](docs/roadmap.md).

## 2026-09-25

- **Repository restructured** for a public release: the docs live in `docs/` (config reference, Config Editor, main module, batch export, volume rendering, architecture, design notes, roadmap), step-by-step guides in `howto/`, study configs in `examples/config/`. The root README is now a landing page; the extension has its own README. `UPDATES.md` became this `CHANGELOG.md`; `TODO.md` became `docs/roadmap.md`. The unused `Examples/` wrapper modules were removed.
- **Images tab simplified**: the `pattern` (regex) / `strip_prefix` / `strip_suffix` options are gone from the UI, the config schema and the code (old keys in a config are ignored silently; the dynamic-images example config was removed). Only the images listed in the table are loaded. New **Default path pattern** field above the table (`defaults.image.path_pattern`): an image whose CSV column is empty - or that has no CSV column at all - is found with it, so extra images can be added by hand as name-only rows.
- **Images tab**: *Quick add* is now a modal popup (button *Quick add from preseg columns...*), so the images table has the whole tab; the *Edit advanced* popup was redesigned with grouped sections.
- **Reference image** (Segmentation and Batch export tabs) is now a dropdown filled from the Images tab and kept in sync with it; the *Suggest* button is gone.
- **Images tab**: the *Effective settings* box is compact (its height is `IMAGES_PREVIEW_VISIBLE_LINES` in `Definitions.py`, the effective result is its first line) and the images table takes the remaining space.
- **Config Editor dropdowns** no longer offer a blank entry for "nothing chosen": the image *Preset* and *Color table*, the Volume rendering *Preset* and the window/level mode show `(unset)` (`UNSET` in `Definitions.py`); the Reference image dropdowns show it as placeholder text. Nothing is written to the config for `(unset)`.
- **`CLAUDE.md` / `AGENTS.md`** (identical): a short map of the repo for AI assistants - layers, where common changes go, conventions, how to check work, Slicer/PythonQt gotchas. `tests/test_agent_notes.py` keeps it from rotting (every file it names must exist).
- **Refactor**: a new `utils/` layer for everything that manipulates Slicer itself, as plain functions (no specimen state): the workspace setup (`workspace.py`), volume rendering (`volume_rendering.py`), the Segment Editor defaults and hand-off (`segment_editor.py` - the brush/overwrite attribute logic that was duplicated in two places is now shared), the Help section and Ctrl+S shortcut (`slicer_ui.py`, `SaveShortcut`) and `config_location.py`. `GenericSpecimen` shrank from 960 to 535 lines. All methods in `gui/` now use Slicer's camelCase (`_populateGeneral`, `showSpecimenTable`, `_preflightCheck` ...); `core/`, `utils/` and `study/` stay snake_case. New `tests/test_utils.py`.
- **Segment editor tab**: *Active effect* is an (editable) dropdown of Slicer's effects (`SEGMENT_EDITOR_EFFECT_CHOICES` in `definitions.py`); the raw attributes box fills the rest of the tab.
- **Code reorganised into packages** under `Resources/` (the data folders `UI/`, `Html/`, `Presets/`, `Icons/` stay where they were): `core/` (pure Python: config model, pattern check, safe IO, status, logging), `study/` (specimen, logic, batch processor, config location), `gui/` (module widget split into mixins - specimen table, study setup, specimen actions, annotation - and the Config Editor with one mixin per tab). Behaviour is unchanged; the old 2700- and 2500-line files are gone, modules are `snake_case`. The module's `CMakeLists.txt` now lists every resource file (before, the Python files under `Resources/` were not listed and would not have been installed). New tests: `tests/test_imports.py` (every module imports, with Slicer stubbed) and `tests/test_packaging.py` (CMake list matches the files).
- **Data safety** (`SafeIO.py`, [docs/data-safety.md](docs/data-safety.md)): `database.csv` is written atomically and checked before it replaces the old file, backed up into `.backups/` (throttled, newest 10 kept), and a save that would overwrite a version changed on disk in the meantime asks first. A lock file warns when a study is open in another session. Segmentation and markups are written atomically and keep the previous save as `<file>.prev` (Reset removes it too); the Config Editor saves configs atomically. First automated tests: `tests/test_safeio.py` (`python -m unittest discover -s tests`).
- **Markups**: new optional `markups.size` (point scale, Slicer's Markups display *Scale*; in millimetres with `size_absolute`) and `markups.glyph_type` (point shape - `Sphere3D` is a 3D ball that shows across several neighbouring slices), set in the Config Editor's Markups tab under Color.
- **Pattern validation**: new `PatternCheck.py` checks every `{column}` pattern and images[] `pattern` regex against the CSV headers at Initialize Study (errors block, possible problems are logged); patterns that fail at load time now say which pattern and column. Duplicate image names are skipped with a warning (they used to overwrite each other and leave an orphan node). A top-level `output_dir_pattern` given as a list of columns (`["ID", "measurement"]`, as in five of the example configs) is accepted again and the examples were converted to the string form.
- **Config Editor: an image row's own `path_pattern`** is now editable (Images → *Edit advanced...* → Path pattern) and no longer silently dropped when a config that has one is loaded and saved.
- **Config browsing remembers the last used config folder** (in Slicer's settings) and starts there; without one it starts in `examples/config` (git checkout) or the dialog default. Applies to *Select .json file*, the Config Editor's Load / Save as, and the Browse choice of the Initialize Study / Config Editor prompts.

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
