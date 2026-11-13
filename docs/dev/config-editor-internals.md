# Config Editor internals

Code: [`gui/config_editor/`](../../GenericSpecimenManager/GenericSpecimenManager/Resources/gui/config_editor).
`dialog.py` holds `ConfigEditorDialog` (load / save / dirty tracking); each tab is one mixin
(`general_tab.py` ... `manual_tab.py`) with the same four steps: `_build...Tab`, `_populate...`, `_collect...`,
`_clear...`. Adding a config key means touching those four in the key's tab (see `CLAUDE.md`, "Common changes").

## Dirty tracking and closing

Every field is watched for changes (a `_dirty` flag); the title bar shows a trailing `*`. Closing (the button or the
window's X) prompts Save / Discard / Cancel. That prompt is wrapped defensively: if the save-prompt logic itself
throws, the window still closes rather than staying stuck open.

## Saving

Save always builds from the tabs, through the same logic as *Manual edit config -> Refresh from form*, so stray text
in a field cannot be saved silently. The write goes through `core/safe_io.py` (atomic, previous version kept as
`config.json.prev`). After a successful save from a dialog opened by the main module, it offers to push the config
into the active scene, the same as *Select .json file* there. `Ctrl+S` saves quietly while the editor window is active,
and the main module's specimen save steps aside then.

## Relative paths

A relative Study dir / preseg CSV / database CSV is resolved against the config file's folder. With a relative preseg
path and no Study dir, `study_dir` is not written, and the module uses the config's folder.

## Content you can extend without touching code

Three data files feed the editor; all are plain files under `Resources/`:

- [`Html/config_editor_help_cheatsheet.html`](../../GenericSpecimenManager/GenericSpecimenManager/Resources/Html/config_editor_help_cheatsheet.html)
  - the content behind the *Help* button, rendered by a `QTextBrowser` (Qt's rich-text subset: `<h2>`, `<ul>`, `<li>`,
  `<table>`, `<pre>`, `<code>` work). A new section is a new `<h2>` block; the section-jump combo is built from them.
  The main module's own sheet, [`Html/module_help_cheatsheet.html`](../../GenericSpecimenManager/GenericSpecimenManager/Resources/Html/module_help_cheatsheet.html),
  uses the same popup (`gui/help_dialog.py`); its anchors are listed in `MODULE_HELP_SECTIONS` in `gui/main_widget.py`.
- [`Html/example_presets_template.html`](../../GenericSpecimenManager/GenericSpecimenManager/Resources/Html/example_presets_template.html)
  - the frame and style of the *Show example presets...* popup, with a `{{CONTENT}}` placeholder filled at runtime.
- [`Presets/example_presets.json`](../../GenericSpecimenManager/GenericSpecimenManager/Resources/Presets/example_presets.json)
  - the preset catalogue, `{"<name>": {"description": "...", "preset": {...ImageConfig fields...}}}`. One file feeds the
  popup, the *Insert ALL* button and the two starter presets (`ct_soft_tissue`, `ct_bone`) of a new config, via
  `ConfigEditorDialog._loadExamplePresets()` (cached) and `_presetResourceDir()`.

The loaders are defensive: a missing or broken file gives an empty catalogue (presets) or a short inline message (HTML),
never a crash (`_loadExamplePresets()`, `_loadHtmlResource()`).
