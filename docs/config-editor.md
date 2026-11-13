# Config Editor

The **Config Editor...** button opens a window for building and editing `config.json` without writing JSON by hand.
It opens pre-loaded with the config that is active in the main module (if any). Every field has a tooltip, and its
**Help** button opens a searchable cheat sheet with a section per tab - that is the per-field reference; this page is
the overview.

## Working with it

- **New / Load from file / Reload from disk** - New and Load ask first if the form has unsaved changes; Reload
  re-reads the open file, handy after editing it elsewhere.
- **Save** writes the config built from the tabs and offers to load it into the module right away. `Ctrl+S` saves
  too, while the editor window is active. The previous version is kept as `config.json.prev`.
- The title bar shows a `*` while there are unsaved changes; closing asks whether to save them.

## The tabs

The tabs follow the data flow: what to load, then how the workspace and tools around it behave.

| tab | what you set there |
|---|---|
| General | the study folder, CSV paths, key columns, table columns, status column, group/status filters, auto-save, factor columns (checkbox or dropdown columns) |
| Batch export | what the batch export produces and where it goes - see [Batch export](batch-export.md) |
| Images | one row per image (*Quick add from preseg columns...* fills it from the CSV), with a preview of the effective settings after `defaults` and presets are merged |
| Segmentation | the segments, reference image, path pattern, opacity, per-segment colour and initial visibility |
| Markups | the markups template and file, point colour, size and shape |
| Workspace | window/level, slice rotation, crosshair, ruler, orientation markers, view convention, on-screen specimen annotation |
| Segment editor | the Segment Editor defaults: editable area, overwrite mode, brush, active effect, editable intensity range, source volume in the foreground |
| Volume rendering | per image: enable, preset, optional range shift |
| Defaults / Presets | `defaults` and named `presets` as JSON, with a worked example and a catalogue of ready-made CT/MRI/PET presets to insert |
| Manual edit config | the JSON the form would write, and loading hand-edited JSON back into the tabs |

The merge order for an image is `defaults.image` -> the named preset -> the row's own fields (the last one wins);
see the [Config reference](config-reference.md).

The **Manual edit config** tab is a view of the form: *Save* always builds from the tabs, so hand edits made there
need **Apply to form** first.

How the editor is built, and how its help and preset content can be extended without code:
[Config Editor internals](dev/config-editor-internals.md).
