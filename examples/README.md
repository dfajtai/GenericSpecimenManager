# Examples

## `config/`

Study configs to start from. **They contain example paths from the machines they were made on** - open one in the
Config Editor and point its CSV paths at your own data before using it.

| file | what it shows |
|---|---|
| `config_example_pig.json` | a minimal, annotated starting point: two images, a handful of segments, batch export |
| `config_example_rabbit.json` | a markups file per specimen, volume rendering, window/level, markup export in batch export |
| `pig_config.json`, `rabbit_config.json`, `deer_config.json`, `kamilla_config.json` | full configs of real studies |

The module remembers the folder of the last config you used, so browsing starts there next time.
