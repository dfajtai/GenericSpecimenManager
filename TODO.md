# TODO

## Done

- [x] Hide Reload & Test, Help & Acknowledgement
- [x] Volume rendering preset offset (min/max rescale + fixed offset, both supported) (https://gist.github.com/cpinter/8a1f71c7eb3ef0ebcaa6c1be6e1c9d4a#file-setpresetoffest-py)
- [x] Update main README.md (examples, tree structure, links)
- [x] Volume rendering column width adjust
- [x] Slice rotation config (Red/Yellow/Green in-plane rotation)
- [x] Workspace tab (window/level, slice rotation, crosshair, ruler, orientation marker)

## Dropped

- [x] ~~Windowed mode~~ - already works natively (drag the module panel's title bar), no code needed
- [x] ~~Rewrite ConfigEditor - Easier to extend, every tab affects a list of Config classes, no overlaps between functionality or resopnsibility (but keep hierarhycal overrides).~~ [2026-09-17]

## Open

- [ ] Colored logging
- [ ] Update README.md

* [ ] **Examples/ folder: real configs + README**

  - one small, real config.json per example species (pig/rabbit/deer), matching what's already used in production
  - Examples/README.md explaining each one, and how to adapt for a new species

* [ ] **Dataset-prep example script(s)** - the missing link before Examples/ is actually useful: a
      script that turns raw scan data into what this module consumes (a `database.csv` + `preseg.csv`
      pair, with files organized/renamed as needed). Needs two input modes:

  - **BIDS-formatted input** -> parse the BIDS structure (subject/session/modality) into rows
  - **flat file dump input** -> regex/pattern-match filenames into subject/measurement/image-type,
    no assumed structure
  - Tech stack: `pathlib` for paths, `shutil` for copy/move into the study's layout, `re` for
    filename parsing, `pandas` to build/write the two CSVs, `SimpleITK` to read a volume when a
    check (dimensions, orientation, spacing) is needed before trusting a file
  - Should be runnable standalone (no Slicer import needed) - it's a data-prep step, not a module feature

* [ ] Extension packaging (`.s4ext`) so it's installable via Extension Manager, not just git clone
* [ ] Screenshot(s)/short demo in the main README
* [ ] Verify the curated Slicer enum lists (crosshair mode/behavior, ruler type, orientation
      marker) against a couple of different Slicer versions - they're editable-but-curated
      guesses, not confirmed
