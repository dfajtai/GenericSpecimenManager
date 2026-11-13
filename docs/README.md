# Documentation

Reference documentation for GenericSpecimenManager. New here? Start with the
[repository README](../README.md) and [Your first study](../howto/first-study.md).

## For users

| page | what it covers |
|---|---|
| [Config reference](config-reference.md) | the complete `config.json` schema, path resolution, and a key reference table |
| [Config Editor](config-editor.md) | the guided editor: how it works and what each tab is for |
| [The main module](main-module.md) | the module layout, specimen status, filters, reset, what happens when something is wrong |
| [Batch export](batch-export.md) | segment export, statistics, markup summary, filename patterns |
| [Data safety](data-safety.md) | atomic writes, backups, change detection and the study lock |
| [Roadmap](roadmap.md) | what is planned |

Step-by-step guides live in [`../howto/`](../howto).

## For developers

| page | what it covers |
|---|---|
| [Architecture](dev/architecture.md) | repository layout, layers, file responsibilities, config model, logging, tests, development rules |
| [Error handling](dev/error-handling.md) | how the main module validates its inputs before Initialize Study |
| [Batch export internals](dev/batch-export-internals.md) | how the batch export loads, exports and writes |
| [Config Editor internals](dev/config-editor-internals.md) | dirty tracking, saving, and the help / preset content that can be extended without code |
| [Segment Editor design notes](dev/segment-editor-design-notes.md) | why the Segment Editor integration looks the way it does |
| [Volume rendering notes](dev/volume-rendering.md) | how the preset shift/remap works and why |

The day-by-day development log is in [`../changelog/`](../changelog).
