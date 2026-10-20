# GenericSpecimenManager (Slicer extension)

A single, JSON-configured 3D Slicer module for repetitive specimen-by-specimen segmentation and annotation. One
`config.json` describes a study; the module loads and executes it. The bigger picture and motivation are in the
[repository README](../README.md).

## Layout

```
GenericSpecimenManager/                 <- this folder: the Slicer extension
├── CMakeLists.txt                      <- extension-level CMake
├── README.md                           <- this file
└── GenericSpecimenManager/             <- the module Slicer loads (add THIS folder as an additional module path)
    ├── GenericSpecimenManager.py
    └── Resources/
        ├── core/                       <- config model, safe file IO, pattern check (pure Python)
        ├── utils/                      <- everything that manipulates Slicer itself (workspace, volume rendering, Segment Editor)
        ├── study/                      <- specimens, database, batch export
        ├── gui/                        <- the module widget and the Config Editor
        └── UI/, Html/, Presets/, Icons/   <- data
```

Code structure in detail: [Architecture](../docs/architecture.md).

## Using the module

The module window has these blocks, top to bottom: a collapsed **Help** block (the workflow cheat sheet, the Config Editor cheat sheet and a link to the project page on GitHub), then

1. **Advanced Study Settings** (collapsed) - the config file and the two CSV paths, and the **Batch export** button
   (shown once a study is initialized and the config enables it).
2. **Initialize Study** - loads the config and both CSVs and builds the specimen list. It is pastel green until a
   study is initialized. Below it appears **Save database CSV**, when the config wants it.
3. **Specimen browser** - Group and Status filters, the specimen table, and the buttons to *Load*, *Reset*,
   *Save* and *Close* a specimen.

The **Config Editor...** button builds and edits `config.json` without hand-writing JSON (`Ctrl+S` saves the config
while that window is active). A progress bar at the bottom of the module shows loading a specimen and the batch export.
*Initialize Study* re-reads the config, so edits take effect; when a specimen is open, anything that would invalidate it
asks first whether to save and close it.

Typical session: select a config → *Initialize Study* → select a specimen → *Load selected specimen* → segment and
place markups → *Save progress* (or `Ctrl+S`) → *Close active specimen* (optionally marking it *to review* or
*finished*) → later, *Batch export* the finished specimens.

## The inputs

A study is two CSVs plus a config:

- **`preseg.csv`** - one row per specimen: its key columns and the paths (or path parts) of its images.
- **`database.csv`** - one row per specimen: its key columns and whatever you want to record (comments, measurements,
  factors) plus the **status** column the module maintains.
- **`config.json`** - which columns identify a specimen, which images/segments/markups to load, where results go,
  how batch export behaves. Start from [`examples/config/`](../examples/config).

## Where to read next

| topic | page |
|---|---|
| your first study, step by step | [howto/first-study.md](../howto/first-study.md) |
| the specimen browser, status, filters, reset | [docs/main-module.md](../docs/main-module.md) |
| every config key | [docs/config-reference.md](../docs/config-reference.md) |
| the Config Editor tab by tab | [docs/config-editor.md](../docs/config-editor.md) |
| batch export | [docs/batch-export.md](../docs/batch-export.md) |
