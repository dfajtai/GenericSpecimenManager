# Error handling in the main module

How the main module validates its inputs and reports problems. The user-facing summary is in [The main module](../main-module.md#when-something-goes-wrong).

**Live, continuous validation** (not just a popup on click): the
config/DB/preseg path fields constantly show their state - red border =
doesn't exist, yellow = it's a folder (not a file), green = OK. See
`GenericSpecimenManagerWidgetBase._validatePathField`.

**Pure-Python preflight check** (`_preflightCheck`), run before Initialize
Study, **before** any Slicer/VTK call happens:
1. Does the config path exist, and is it a file (not a folder - the
   folder config browsing starts in - the last used one, else
   `examples/config` - is pre-filled into the field, which was easy to
   accidentally try to open as a file, raising an `IsADirectoryError`)?
2. Can the database/preseg CSV be read with plain Python's `csv` module (not
   Slicer's `loadTable` - which can throw a native, scary error dialog on an
   empty/broken path that a Python `try/except` can't cleanly catch)?
3. Do the config's `key_columns` **actually appear** in both CSVs' headers -
   if not, a specific message (the missing column names plus the CSVs' real
   headers), not a vague downstream error.
4. **Pattern check** (`core/pattern_check.py`): every `{column}` pattern is checked
   against the real CSV headers. Unbalanced braces or an unknown column in
   `output_dir_pattern` blocks Initialize Study with a plain message; anything
   that only *may* fail (an unknown column in an image/segment/markups path
   pattern, an image name listed twice, a `csv_column` that isn't in the preseg
   CSV and has no path pattern to fall back to) is logged as a warning. At load time, a pattern
   naming a column a specimen lacks reports the pattern, the column and the
   available columns - not a bare `KeyError`.

Every "fix your input" message uses `warningDisplay` (instead of
`errorDisplay`) - a less alarming style for a simple user mistake; actual
exceptions (JSON parse errors, an `initializeStudy` crash) still use
`errorDisplay`.

**Re-init protection**: if a specimen is active and you click Initialize
Study, a Save/Discard/Cancel prompt appears first - re-initializing the
study could lose, or misattribute, the open specimen's unsaved work.

**Config Editor with no valid config path**: clicking "Config Editor..."
while the config path field isn't an actual file - empty, still pointing
at a folder (the pre-filled browse starting folder mentioned above),
or a file that no longer exists - no longer fails with a raw error dialog
(or, for empty, silently opens blank with no explanation) - `onBtnConfigEditor`
checks `os.path.isfile` first and, if it's not one, asks instead: **Browse
for config.json...** (identical to clicking "Select .json file" - loads
the picked file into the active scene, then opens the Config Editor on
it), **Open clean Config Editor** (starts blank, same as New), or
**Cancel** (closes the prompt, opens nothing).
