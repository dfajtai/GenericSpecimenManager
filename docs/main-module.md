# The main module

The module GUI, specimen status, filtering, reset, and how errors are handled.

## Main module layout, specimen status, filter and reset

The module is collapsible blocks in the Slicer style, top to bottom: a collapsed **Help** block (three buttons: *Workflow help...* and *Config Editor help...* open the two cheat sheets, *Project page on GitHub* opens the repository in the browser), **Advanced Study Settings**
(collapsed; the config and CSV paths, and - once a study is initialized and the config enables it - the **Batch export**
button), then the **Initialize Study** button (pastel green until a study is initialized; **Save database CSV** - hidden
with `auto_save_database` - appears under it once it is) and the **Specimen browser** (Group and Status filters in one row, the
table, Load / Reset / Save / Close). A progress bar appears at the very bottom while a specimen loads or a batch export runs.

**Initialize Study** always re-reads the config file, so a config edited and saved meanwhile takes effect. If a specimen is
open, any action that would invalidate it (initializing again, loading another config, running Batch export) says so and offers
*Save and close* / *Close without saving* / *Cancel*. **Load selected specimen** opens the images with the first `foreground`
image (lowest index) as the shown foreground and as the Segment Editor's active (source) image, and puts the crosshair at the
centre of the scan; switching the source volume in the Segment Editor keeps the background and moves the foreground along.

Each specimen has a status, stored in the `status_column` of `database.csv` as an integer
(`0` untouched, `1` in progress, `2` to review, `3` finished; values live in `definitions.py`).
Column headers are shown as readable labels (`batch_id` -> `Batch id`, `specimenID` -> `Specimen ID`; the real `database.csv` name is in the header's tooltip), every column is as wide as its content, and the spare width goes to the free-text columns that have empty cells (e.g. notes), or to the last free-text column if there is none. The table always shows the status as its last column, headed `Status`, as a dropdown that also colors the
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

## When something goes wrong

The module checks its inputs before it touches Slicer, and says in plain words what to fix:

- **The path fields** show their state live: a red border means the path does not exist, yellow means it is a folder
  and not a file, green means it is fine.
- **Initialize Study** first checks that the config and both CSVs can be read, that the key columns exist in both CSVs,
  and that every `{column}` in a path pattern matches a real column. A pattern that certainly cannot work stops it
  with a message; one that only *may* fail is logged as a warning.
- **Config Editor...** with no valid config path offers *Browse for config.json...*, *Open clean Config Editor* or
  *Cancel*, instead of an error.
- With a specimen open, anything that would invalidate it (initializing again, loading another config, running Batch
  export) asks whether to save and close it first.

How these checks are built: [Error handling](dev/error-handling.md).
