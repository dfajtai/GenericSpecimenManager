# Roadmap

What is planned. What has been done is in the [changelog](../CHANGELOG.md).

## Ecosystem

The Slicer module is the middle of a three-step pipeline; the other two steps are still missing.

- **Dataset-prep scripts (before the module)** - turn raw scan data into what the module consumes: a `database.csv` +
  `preseg.csv` pair, with files organised or renamed as needed. Two input modes:
  - **BIDS-formatted input** - parse the BIDS structure (subject/session/modality) into rows.
  - **flat file dump input** - regex/pattern-match file names into subject/measurement/image type, no assumed
    structure.
  - Stack: `pathlib`, `shutil` (copy/move into the study layout), `re` (file-name parsing), `pandas` (write the two
    CSVs), `SimpleITK` (read a volume when a check of dimensions, orientation or spacing is needed).
  - Runnable standalone - no Slicer import; it is a data-prep step, not a module feature.
- **Analysis scripts (after the module)** - working with the batch-export CSVs (segment statistics, markup summaries):
  loading, joining with the study metadata, and simple example analyses.

## Module and packaging

- Extension packaging (`.s4ext`) so it is installable from the Extension Manager, not only via git clone.
- Screenshot(s) / a short demo in the README.
- Verify the curated Slicer enum lists (crosshair mode/behavior, ruler type, orientation marker) against a couple of
  different Slicer versions - they are editable-but-curated guesses, not confirmed.
