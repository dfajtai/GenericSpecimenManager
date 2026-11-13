# Config reference

The complete `config.json` schema (1:1 with `core/config_model.py`), and how paths are resolved. The per-key reference is in the Config Editor's Help (see *Key reference* at the end).

**Paths** in the CSVs, the path patterns and `batch_export.output_dir` are written with `/`; the module converts them to the running platform's separator (`\` on Windows). Relative paths stay relative to `study_dir`.

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
      "opacity": 1.0, "color_table": "Grey", "interpolate": true,   // color_table: a Slicer table name/ID, or the built-in "gnuplot2" / "inferno" (matplotlib maps, black at the low end; values outside "threshold" stay transparent)
      "window_level": {"min":-150,"max":700},   // OR {"auto":true} OR {"window":..,"level":..}
      "threshold": {"min":1,"max":300,"apply":true},   // DISPLAY threshold of the slice views
      "segment_editor_threshold": {"min":200,"max":1500} },   // the Segment Editor's Threshold effect starts with this range whenever this image is the editor's source volume (either end may be left out; images without it leave the range as it is)

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
      { "name": "tumor", "source": "empty", "color": [1,1,0], "visible": false }  // never tries a file; "visible": false = hidden when the segmentation is first built (omit = Slicer's default, shown); a saved segmentation is not touched
    ],
    "output_filename": "segment.seg.nrrd",
    "opacity": 0.5                                 // whole-segmentation display opacity 0-1; omit = 1
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
    "overwrite_mode": "none",     // omit = leave Slicer's setting alone | "none" = allow overlap | "all_segments" | "visible_segments"
    "editable_area": "everywhere", // omit = leave Slicer's setting alone (it is "everywhere") | "inside_all_segments" | "inside_visible_segments" | "outside_all_segments" | "outside_visible_segments"
    "brush": { "shape": "sphere", "diameter_mm": 5, "relative": false },
    "active_effect": "Paint",
    "source_volume_to_foreground": true,          // default true: the Segment Editor's source volume is shown as the slice views' foreground and the reference image stays background. false = the module leaves the layers alone (Slicer's own behaviour: source volume -> background, foreground cleared)
    "editable_intensity_range": {                 // Editable intensity range, set when the effect becomes active (Slicer has ONE range for all effects, so it is rewritten on every switch; other effects keep the last one)
      "Paint": {"min": -50, "max": 100},          // an end left out = the source volume's own end
      "Erase": {"min": -1024, "max": -60} },
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

What every key does, where it is set in the Config Editor and which values it takes is in the **Key reference** section of
the Config Editor's cheat sheet (Config Editor window -> **Help** -> *Key reference*; the source is
[`config_editor_help_cheatsheet.html`](../GenericSpecimenManager/GenericSpecimenManager/Resources/Html/config_editor_help_cheatsheet.html)).
It is kept in one place only, so it cannot drift from this page.
