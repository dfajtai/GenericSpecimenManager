# Batch export

Turns every *finished* specimen into analysable files in one pass. Everything is set on the Config Editor's **Batch
export** tab (or under `batch_export` in the config - see the [Config reference](config-reference.md)).

## Running it

The **Batch export** button is inside the collapsible *Advanced Study Settings* block. It appears once a study is
initialized and the config enables batch export. It asks for confirmation first (how many finished specimens, what
will be produced - it can take long) and shows a progress bar at the bottom of the module while it runs. If a
specimen is open, it offers to save and close it first.

Only specimens with the status *finished* are processed, whatever the Status filter shows. With none finished, it
stops at once and lists the status counts.

## What it produces

Any combination of the following, in one pass:

- **Segments** (`export_segments`) - each segment as its own label map file. Overlapping segments are handled
  correctly, because every segment is exported separately. `segments_filter` limits which segments are exported.
- **Segment statistics** (`compute_stats`) - one CSV with a row per specimen and segment: volume, min, max, mean,
  median, std and/or `percentile_<N>` (`stats_metrics`; empty = the default set). `stats_reference_images` are the
  volumes the intensities are sampled from; each gets its own row per segment, so a multi-sequence study gets one row
  per sequence. `stats_segments_filter` selects the segments independently of `segments_filter`: a segment can be
  exported without being in the statistics, or the other way round.
- **Markups** (`export_markups`) - each specimen's `.mrk.json`, plus a per-specimen CSV (`label`, `x`, `y`, `z`).
- **Markup summary** (`markups_report`, needs `export_markups`) - every specimen's points combined into one or more
  CSVs. `markups_coordinate_system` is `RAS` (default, Slicer's own) or `LPS` (for ITK/DICOM-based pipelines); it
  applies to the CSV columns only, not to the `.mrk.json`.

## Where the files go

| setting | meaning |
|---|---|
| `output_dir` | the root everything is anchored to; unset = `study_dir`, relative = under `study_dir` |
| `output_dir_pattern` | per-specimen subfolder under that root, for the segment and markup **files** (e.g. `{batch}/{ID}`) |
| `stats_output_path` | the statistics CSV, directly under the root (default `report.csv`) |
| `markups_output_path` | the markup summary CSV, directly under the root (default `markups_report.csv`) |

Patterns use `{column}` - any key, `database.csv` or `preseg.csv` column of the specimen. The two CSV patterns also take:

- `{date}`, `{time}`, `{datetime}` - the current date / time (`YYYY-MM-DD` / `HH-MM-SS` / both).
- `{index}` - a two-digit counter (`_01`, `_02`, ...) before the extension, taking the lowest one not on disk yet, so
  `report_{index}.csv` never overwrites a previous run. Without `{index}` an existing file is overwritten.

Whether specimens share a file is decided by the pattern: those that resolve to the same path end up in one CSV; a
pattern with a differing column (e.g. `{batch}/report.csv`) gives one CSV per value. There is no separate switch.

The *Group specimens by key* option of the main module only changes what the table shows; it has no effect on the
export (a pattern can still use the same column by name).

How it works inside: [Batch export internals](dev/batch-export-internals.md).
