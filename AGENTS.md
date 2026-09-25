# GenericSpecimenManager - notes for AI assistants

A JSON-configured 3D Slicer module for repetitive specimen-by-specimen segmentation/annotation. One `config.json`
per study; two CSVs (`preseg.csv`, `database.csv`); a status per specimen; batch export of finished specimens.
It is the middle of a small ecosystem, not a standalone tool: pre-processed images and two CSVs go in, reliable,
machine-analysable data comes out.

    raw scans -> pre-processing (planned) -> preseg.csv + database.csv -> THIS module -> batch export CSVs -> analysis (planned)

Guiding idea: people make mistakes, code doesn't. Take the error-prone parts (file/segment names, paths, where results
go, which specimen is done) out of human hands, and never put the data at risk. So: generate names and paths from CSV
columns via patterns, validate up front, write files safely, keep the UI surface small (the maintainer keeps pruning
options nobody would use). The two CSVs and the exported files are the contract between the pieces - treat their
format as an interface (see `docs/roadmap.md` for the planned pre-processing/analysis steps).
Human docs: `README.md`, `docs/` (reference), `howto/` (guides). Full code map: `docs/architecture.md`.
The maintainer talks to you in Hungarian - answer in the user's language, keep code, docs and commits in English.

## Where things are
Module root: `GenericSpecimenManager/GenericSpecimenManager/` (a thin `GenericSpecimenManager.py` + `Resources/`).

    Resources/core/    pure Python, NO Slicer/Qt/VTK: config_model, pattern_check, safe_io, status, logging_setup
    Resources/utils/   plain functions that manipulate Slicer itself: workspace, volume_rendering, segment_editor, slicer_ui
    Resources/study/   domain: specimen (GenericSpecimen), logic, batch_processor
    Resources/gui/     Qt: main_widget + mixins, help_dialog, config_editor/ (dialog + one mixin per tab)
    Resources/definitions.py   every tweakable constant / dropdown choice list (one place)
    Resources/UI, Html, Presets, Icons   data - do not move (Slicer packaging)

Layer rule (enforced by a test): core <- utils <- study <- gui. Never import upward.

## Common changes
- **New config key**: `core/config_model.py` (dataclass field) -> its tab in `gui/config_editor/*_tab.py`
  (`_build...Tab`, `_populate...`, `_collect...`, `_clear...`) -> `docs/config-reference.md` and the Config Editor
  cheat sheet (`Resources/Html/config_editor_help_cheatsheet.html`) -> `CHANGELOG.md`.
- **New constant / dropdown list**: `Resources/definitions.py`. Optional dropdowns show `UNSET` ("(unset)"), never a blank entry.
- **Anything that writes a file the study depends on**: go through `core/safe_io.py` (atomic write, backups, lock).
- **A new file under `Resources/`**: list it in `MODULE_PYTHON_RESOURCES` in `GenericSpecimenManager/GenericSpecimenManager/CMakeLists.txt`.

## Conventions
- `gui/` methods are camelCase (Slicer style, e.g. `_populateGeneral`); `core/`, `utils/`, `study/` are snake_case.
- Every function/method has a docstring; explain WHY for Slicer/VTK quirks. Don't guess Slicer APIs - flag uncertainty.
- Unknown config keys are ignored silently; no backward-compatibility shims (the schema may change).
- Keep docs in step with the code: `docs/`, the cheat sheets and `CHANGELOG.md`.

## Check your work (no Slicer needed)
    python -m unittest discover -s tests          # imports (Slicer stubbed), layers, packaging, safe_io, utils
    python -m pyflakes GenericSpecimenManager/GenericSpecimenManager/Resources   # undefined names after a refactor
Slicer-bound behaviour cannot be run here - say so instead of claiming it works.

## Slicer/PythonQt gotchas
- No-arg Qt getters are often properties WITHOUT parens (`rowCount`, `height`, `defaultSectionSize`); methods that
  return objects need parens (`verticalHeader()`, `viewport()`).
- `slicer`, `qt`, `vtk`, `ctk` don't import outside Slicer; the tests stub them (`tests/test_imports.py`).
- Slicer's Reload button reloads only the main script, not `Resources/*`.
- Status values are the integers 0-3 (`SpecimenStatus` in `definitions.py`); Batch export processes only 3 (finished).
