# The main module

The module GUI, specimen status, filtering, reset, and how errors are handled.

## Main module layout, specimen status, filter and reset

The module is three collapsible blocks in the Slicer style: **Advanced Study Settings** (collapsed; the
config and CSV paths), then the **Initialize Study** button (pastel green until a study is initialized;
**Save database CSV** - hidden with `auto_save_database` - and **Batch export** - only if the config
enables it - appear under it once it is), the **Specimen browser** (Group and Status filters in one row, the
table, Load / Reset / Save / Close) and a collapsed **Help** block.

Each specimen has a status, stored in the `status_column` of `database.csv` as an integer
(`0` untouched, `1` in progress, `2` to review, `3` finished; values live in `definitions.py`).
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
config/DB/preseg path fields constantly show their state - red border =
doesn't exist, yellow = it's a folder (not a file), green = OK. See
`GenericSpecimenManagerWidgetBase._validatePathField`.

**Pure-Python preflight check** (`_preflightCheck`), run before Initialize
Study, **before** any Slicer/VTK call happens:
1. Does the config path exist, and is it a file (not a folder - the
   folder config browsing starts in - the last used one, else
   `examples/config` - is pre-filled into the field, which was easy to
   accidentally try to open as a file, raising an `IsADirectoryError`)?
2. Can the database/preseg CSV be read with plain Python's `csv` module (not
   Slicer's `loadTable` - which can throw a native, scary error dialog on an
   empty/broken path that a Python `try/except` can't cleanly catch)?
3. Do the config's `key_columns` **actually appear** in both CSVs' headers -
   if not, a specific message (the missing column names plus the CSVs' real
   headers), not a vague downstream error.
4. **Pattern check** (`core/pattern_check.py`): every `{column}` pattern is checked
   against the real CSV headers. Unbalanced braces or an unknown column in
   `output_dir_pattern` blocks Initialize Study with a plain message; anything
   that only *may* fail (an unknown column in an image/segment/markups path
   pattern, an image name listed twice, a `csv_column` that isn't in the preseg
   CSV and has no path pattern to fall back to) is logged as a warning. At load time, a pattern
   naming a column a specimen lacks reports the pattern, the column and the
   available columns - not a bare `KeyError`.

Every "fix your input" message uses `warningDisplay` (instead of
`errorDisplay`) - a less alarming style for a simple user mistake; actual
exceptions (JSON parse errors, an `initializeStudy` crash) still use
`errorDisplay`.

**Re-init protection**: if a specimen is active and you click Initialize
Study, a Save/Discard/Cancel prompt appears first - re-initializing the
study could lose, or misattribute, the open specimen's unsaved work.

**Config Editor with no valid config path**: clicking "Config Editor..."
while the config path field isn't an actual file - empty, still pointing
at a folder (the pre-filled browse starting folder mentioned above),
or a file that no longer exists - no longer fails with a raw error dialog
(or, for empty, silently opens blank with no explanation) - `onBtnConfigEditor`
checks `os.path.isfile` first and, if it's not one, asks instead: **Browse
for config.json...** (identical to clicking "Select .json file" - loads
the picked file into the active scene, then opens the Config Editor on
it), **Open clean Config Editor** (starts blank, same as New), or
**Cancel** (closes the prompt, opens nothing).
