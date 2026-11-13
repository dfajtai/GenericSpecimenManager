# GenericSpecimenManager

**Repetitive segmentation and annotation of pre-processed images in 3D Slicer, with file naming, progress tracking
and export handled for you - ending in data that is safe to analyse automatically.**

GenericSpecimenManager builds on Slicer's Segment Editor and takes the bookkeeping of a manual image-annotation study
off your hands: which files belong to which specimen, what a segment or a file is called, where results are saved,
which specimen is finished. You describe the study once in a JSON config; from then on every specimen is loaded,
saved and exported the same way, every time, so you can concentrate on the segmentation itself.

## What it does

- **One config describes a whole study** - images, segments, markups, workspace, batch export. No per-species
  module to write. A guided **Config Editor** builds the JSON for you.
- **Consistent file and segment names** - paths and names are generated from your CSV columns by patterns
  such as `{ID}/{measurement}/{name}.nii.gz`. Nobody types or picks a path by hand.
- **Start from an automatic segmentation** - a segment can be initialised from an existing label map (for example the
  output of an automatic or model-based segmentation, found through a CSV column or a path pattern) instead of an
  empty one, so the manual work becomes review and correction rather than drawing from scratch.
- **Progress is tracked per specimen** - untouched → in progress → to review → finished, stored in
  your `database.csv`, colour-coded in the specimen browser, filterable.
- **Consistent, analysable output** - a batch export turns every *finished* specimen into per-segment label maps,
  a combined segment-statistics CSV and a markup-summary CSV (RAS or LPS coordinates), with anti-overwrite
  filename patterns.
- **Your data stays intact** - saves are atomic, `database.csv` is backed up and checked before it is replaced, a save that would overwrite someone else's change asks first, and a lock file warns when a study is open elsewhere ([data safety](docs/data-safety.md)).
- **Comfortable to work in** - one-click load/save/close, `Ctrl+S` while a specimen is loaded, a factory-style
  *reset* for a specimen that has to start over, optional on-screen specimen annotation, and built-in cheat
  sheets with search.

## Implemented scenarios

Everything below is set per study in the config (or through the Config Editor), so each project gets its own setup.

- **Project-level setup** - one config per study with `defaults` and named `presets` that layer onto each image or
  segment; any file layout, from one folder per specimen to a flat dump, through `{column}` patterns.
- **Workspace customisation** - crosshair, slice-view ruler, orientation markers (3D and/or slice views),
  radiological or neurological view convention, a fixed in-plane slice rotation, a global window/level, and an
  on-screen specimen annotation.
- **Image display** - per-image window/level, colour table (including `gnuplot2` / `inferno`), display threshold,
  opacity and volume rendering, several background and foreground images per specimen.
- **Segment Editor defaults** - overwrite mode, editable area, brush, active effect, editable intensity range per
  effect, a Threshold range per image, and which volume follows into the slice views' foreground.
- **Segmentation** - segments created empty, or pre-filled from existing label maps (automatic segmentations);
  per-segment colour and initial visibility; segmentation opacity.
- **Markups** - point lists from a template or a file, with size, glyph and colour set in the config.
- **Review workflows** - four statuses per specimen, filter by status, group by a column, checkbox and dropdown
  columns for your own metadata, optional auto-save of `database.csv`.
- **Batch export** - per-segment label maps, segment statistics (several metrics, several reference images) and a
  markup summary, for finished specimens only.

Ready-made configs for several of these are in [`examples/config/`](examples/config).

## How it fits together

| # | step | what happens | status |
|---|---|---|---|
| 1 | **Pre-processing** | raw scans (any layout, or a BIDS dataset) become two CSVs: `preseg.csv` (which files belong to which specimen) and `database.csv` (what to track per specimen) | planned - for now the CSVs are made by hand ([roadmap](docs/roadmap.md)) |
| 2 | **Annotation** | in the Slicer module, each specimen is loaded - with its segments empty or pre-filled from earlier automatic segmentations - then segmented / annotated and saved; names, paths and status are handled by the config, not by hand | **this repository** |
| 3 | **Batch export** | every *finished* specimen becomes per-segment label maps, a segment-statistics CSV and a markup-summary CSV | **this repository** |
| 4 | **Analysis** | the exported CSVs are analysed automatically | planned ([roadmap](docs/roadmap.md)) |

## Repository map

| folder | what is in it |
|---|---|
| [`GenericSpecimenManager/`](GenericSpecimenManager) | the Slicer extension - start with its [README](GenericSpecimenManager/README.md) |
| [`docs/`](docs) | user reference: config schema, Config Editor, main module, batch export, data safety; [`docs/dev/`](docs/dev) holds the developer docs |
| [`howto/`](howto) | step-by-step guides, e.g. [your first study](howto/first-study.md) |
| [`examples/config/`](examples/config) | ready-made study configs to start from |

## Quick start

Developed against 3D Slicer 5.10. Until it is available through the Extension Manager, add the module by hand:

1. Clone this repository.
2. In Slicer: *Edit → Application Settings → Modules → Additional module paths*, add
   `<clone>/GenericSpecimenManager/GenericSpecimenManager`, restart Slicer.
3. Open *Segmentation → Generic Specimen Manager*, pick a config (for example one from
   [`examples/config/`](examples/config) - adjust its CSV paths to your data), press **Initialize Study**.

Full walk-through: [Your first study](howto/first-study.md).

## Documentation

### For users

| I want to... | read |
|---|---|
| set up my first study, step by step | [Your first study](howto/first-study.md) |
| start a new study or species | [Setting up a new study](howto/new-study.md) |
| build a config with the guided editor | [Config Editor](docs/config-editor.md) |
| look up a config key | [Config reference](docs/config-reference.md) |
| understand the module window: specimens, statuses, filters, reset | [The main module](docs/main-module.md) |
| export segments, statistics and markups | [Batch export](docs/batch-export.md) |

### For developers

| I want to... | read |
|---|---|
| find my way around the code, run the tests | [Architecture](docs/dev/architecture.md) |
| know how the study's files are protected | [Data safety](docs/data-safety.md) |
| see why the Segment Editor integration looks the way it does | [Segment Editor design notes](docs/dev/segment-editor-design-notes.md) |
| see how the volume rendering shift works | [Volume rendering notes](docs/dev/volume-rendering.md) |
| see what is planned, or what changed | [Roadmap](docs/roadmap.md), [Changelog](CHANGELOG.md) |

## License

GNU General Public License v3.0 - see [LICENSE](LICENSE).
