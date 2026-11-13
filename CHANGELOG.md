# Changelog

Newest first, one line per change. The day-by-day development log with the reasoning is in [`changelog/`](changelog) (the detailed entries up to 2026-11-09:
[archive](changelog/archive-2026-09-to-11-09.md));
planned work is in the [roadmap](docs/roadmap.md).

## 2026-11-09

- Fix: text typed into a table cell (e.g. a comment) was saved as `0`.
- New: `segment_editor.source_volume_to_foreground: false` stops the module from moving the source volume into the foreground.
- New: `segment_editor.editable_intensity_range` - the Editable intensity range per brush effect (Paint / Erase).
- New: `visible: false` on a segment hides it when a specimen's segmentation is first built (Config Editor: *Visible* column).
- Fix: relative `study_dir`, preseg and database paths are resolved against the config file's folder, in the module and in the Config Editor.
- The Config Editor re-reads the preseg CSV when the Study dir changes, and *Quick add* reads its header itself.

## 2026-11-06

- Paths in CSVs, patterns and the batch export folder may use `/` on every platform; they are converted to the running platform's separator.
- A relative `study_dir` is relative to the config file, not to Slicer's current directory.

## 2026-11-05

- New: a per-image Segment Editor Threshold range (`segment_editor_threshold`).
- Fix: the status dot turns green again after a save.
- *Close active specimen* warns first about unsaved changes.

## 2026-10-20

- New: built-in colour maps `gnuplot2` and `inferno`; the Color table dropdown is grouped like Slicer's Colors module.
- New: batch export asks for confirmation, offers to close an open specimen, and shows a progress bar.
- Initialize Study re-reads the config file, so saved edits take effect.
- The first `foreground` image is the one shown and the Segment Editor's source volume after a specimen opens; the crosshair jumps to the centre of the scan.
- The specimen table shows readable column headers and uses the full width.
- `Ctrl+S` saves the config in the Config Editor.
- Main module: the *Help* block moved to the top with separate workflow / Config Editor buttons and a GitHub link; *Batch export* moved into *Advanced Study Settings*.
- Closing an open specimen is always asked about explicitly (save and close / close without saving / cancel).

## 2026-10-16

- New: `segment_editor.editable_area`; `segmentation.opacity` now takes effect.
- New: *Move up* / *Move down* on the Images and Segmentation tabs.
- Fix: `overwrite_mode: none` (allow overlap) is saved; the dropdown has `(unset)`.
- Fix: the Images *Edit advanced...* popup's buttons could be off-screen.
- Fix: 3D display of float label images; switching the Segment Editor's source volume no longer replaces the slice views' background.

## 2026-09-25

- Repository restructured: documentation in `docs/` and `howto/`, example configs in `examples/config/`, code split into `core/`, `utils/`, `study/` and `gui/`; automated tests added.
- New: data safety - atomic writes, `database.csv` backups and change detection, a study lock, `.prev` copies of specimen files ([Data safety](docs/data-safety.md)).
- New: `{column}` pattern validation at Initialize Study.
- New: `markups.size` and `markups.glyph_type`.
- New: *Default path pattern* on the Images tab lets an image be added by name only; the `pattern` / `strip_prefix` / `strip_suffix` options were removed.
- Config Editor: *Quick add* is a popup, dropdowns show `(unset)` instead of a blank, the reference image is a dropdown, an image's own `path_pattern` is editable.
- Config browsing remembers the last used folder.
- Four new portable example configs.

## 2026-09-24

- New: specimen status `0`-`3` (replaces the `done` column), row colours, status filter. Existing configs need `done_column` renamed to `status_column`.
- New: *Reset selected specimen*, `factor_columns` (checkbox / dropdown columns), optional on-screen specimen annotation, `Ctrl+S` saves the active specimen.
- New: the main module's own cheat sheet; the module window rebuilt as collapsible blocks.
- Batch export: operations split into segment export, statistics and markup summary, each with its own filter and pattern; `{index}` placeholder; `landmarks` renamed to `markups`.
- Batch export no longer re-initializes the study and stops with a clear message when no specimen is finished.

## 2026-09-23 and earlier

- Batch export rework; segment statistics CSV; segment export handles overlaps; coloured logging.
- Radiological / neurological view convention, slice rotation, Workspace tab (window/level, crosshair, ruler, orientation marker).
- Volume rendering preset shift (range rescale or fixed offset).
