# Batch mode & batch export

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
[`BatchProcessor`](../GenericSpecimenManager/GenericSpecimenManager/Resources/study/batch_processor.py)
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
  [`definitions.DEFAULT_STATS_METRICS`](../GenericSpecimenManager/GenericSpecimenManager/Resources/definitions.py).
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
