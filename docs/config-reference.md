# Config reference

The complete `config.json` schema (1:1 with `core/config_model.py`) and a key reference table: every named parameter, where to set it, what it does.

## Config schema (complete, 1:1 with `core/config_model.py`)

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

    // B) an image that is NOT a preseg column: just a name. Its file is found with
    //    defaults.image.path_pattern (e.g. "{ID}/{name}.nii.gz"), so a study can list
    //    additional images by hand without touching the CSVs.
    { "name": "t2", "role": "foreground", "opacity": 0.4 }
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
               "template_path": "template.mrk.json", "writable": true, "color": [1,1,0],
               "size": 3,                       // point size: Slicer's Markups display "Scale" ...
               "size_absolute": false,          // ... or millimetres if true (a real-world size)
               "glyph_type": "Sphere3D" },      // point shape; Sphere3D = a 3D ball visible on several slices; all optional

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
3. If neither resolves, the image is skipped with a warning - or, if it is
   `required`, loading the specimen fails.

Only the images listed in `images[]` are ever loaded - extra columns in the preseg
CSV are ignored. To add an image the CSV doesn't have, list it by name (no
`csv_column`) and let `defaults.image.path_pattern` find its file.

**`{column}` patterns work the same way everywhere** - image, segment and markups
paths, `output_dir_pattern`, and the batch export patterns: a `{name}` is replaced by
that column's value for the specimen being processed. So a study whose files are
not stored per-specimen-folder needs no path column at all. A flat folder with
everything in it, or any other layout, is just a pattern over your columns:

| layout | pattern (`defaults.image.path_pattern` unless noted) |
|---|---|
| everything in one folder, `<ID>_<measurement>_<image>.nii.gz` | `{ID}_{measurement}_{name}.nii.gz` |
| one folder per specimen | `{ID}/{measurement}/{name}.nii.gz` |
| grouped by a database column (e.g. `batch`) | `{batch}/{ID}/{name}.nii.gz` |
| any two columns | `{col1}/{col2}.nii.gz` |

Things worth knowing:

- Set the common pattern once in `defaults.image.path_pattern`; each `images[]` row then
  only needs its `name` (which `{name}` inserts) - or its own `csv_column` when one image
  is stored somewhere unusual.
- The path is relative to `study_dir` unless it is absolute. The pattern only *builds* the
  path - whether the file exists is found out when the specimen loads (an optional image
  is skipped with a warning, a `required` one is an error).
- Initialize Study checks every `{column}` against the real CSV headers first: an unknown
  column in `output_dir_pattern` stops it with a message, in the other patterns it is logged
  as a warning. At load time a pattern naming a column the specimen lacks reports the pattern,
  the column and the available columns.


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
