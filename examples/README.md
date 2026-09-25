# Examples

## `config/`

Study configs to start from - open one in the Config Editor and point its paths at your own data. The `example_*`
files use relative paths; the four configs of real studies (last row) still contain the paths of the machines they were
made on.

| file | what it shows |
|---|---|
| `example_minimal.json` | the smallest working config: two images, one empty segment - a starting point |
| `example_flat_folder.json` | no path columns at all: every image found by one `{ID}_{name}` pattern in a flat folder (an extra image only needs a name), segments pre-filled from automatic segmentation files |
| `example_review_workflow.json` | reviewing automatic segmentations: status workflow, a binary and a multilevel factor column, group by site, auto-save, specimen annotation, Segment Editor brush defaults |
| `example_batch_and_markups.json` | markups (template file, a 4 mm `Sphere3D` point that shows across slices), workspace views, and a full batch export: label maps, statistics and a markup summary with `{date}` / `{index}` file names and LPS coordinates |
| `pig_config.json`, `rabbit_config.json`, `deer_config.json`, `kamilla_config.json` | configs of real studies, as used (they still contain the paths of the machines they were made on) |

To try an `example_*` config, put a `preseg.csv` and a `database.csv` next to it (with the key columns named in the
config), or point its paths at your own files.

The module remembers the folder of the last config you used, so browsing starts there next time.
