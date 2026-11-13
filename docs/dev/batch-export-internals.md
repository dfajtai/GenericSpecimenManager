# Batch export internals

How `BatchProcessor` ([`study/batch_processor.py`](../../GenericSpecimenManager/GenericSpecimenManager/Resources/study/batch_processor.py))
does what [Batch export](../batch-export.md) describes.

## Flow

`BatchProcessor` is driven entirely by `cfg.batch_export`. It reuses the already-initialized specimen list (it does
not re-initialize the study) and runs against every specimen with status `finished`. Each specimen is loaded through
the lean `GenericSpecimen.load_for_batch()` path: only the segmentation plus at most one reference volume, with no
workspace settings, volume rendering or Segment Editor activation, since a headless run needs none of that.

## Segments

Each segment goes through Slicer's native `ExportSegmentsToLabelmapNode`, one segment at a time. Overlapping segments
therefore come out as independent masks, never as a shared multi-label array that could be misread.

## Statistics

Computed from the same per-segment label map export, with `slicer.util.arrayFromVolume()` and plain numpy (no pandas,
no third-party segmentation reader). All sample images must share the segmentation's geometry. The default metrics
are `definitions.DEFAULT_STATS_METRICS`.

## Markups

The per-specimen CSV is written from the live markups node (`GetNthControlPointLabel()` /
`GetNthControlPointPositionWorld()`), not by re-parsing the `.mrk.json`. In Slicer's markups schema `position` is
already the point's full world coordinate; `orientation` is a separate, mostly display-only axis frame (at the file
level, just the LPS/RAS sign convention) and is not a per-point transform to apply on top of `position`.

`LPS` flips x and y relative to RAS (`LPS = -x, -y, z`). Only the CSV columns change; the `.mrk.json` keeps Slicer's
own handling.

## Output paths

- `output_dir` + `output_dir_pattern` govern the segment and markup files. The pattern is resolved per specimen with
  the same `{column}` mechanism as the top-level `output_dir_pattern`.
- `stats_output_path` and `markups_output_path` are anchored to the same root but are **never nested through
  `output_dir_pattern`**. They group and overwrite independently of each other and can even resolve to the same file.
- Grouping into one file or several is emergent from the resolved path; there is no flag for it.
