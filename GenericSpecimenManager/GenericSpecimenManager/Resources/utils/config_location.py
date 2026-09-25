"""
config_location.py
=================
Where the config file browse dialogs start: the folder of the config used LAST (kept in Slicer's
own settings, so it survives restarts), else the repo's examples/config folder when running from
a git checkout, else nothing (the dialog's own default). Shared by the main module and the
Config Editor.
"""

import os

import slicer

from Resources.definitions import LAST_CONFIG_DIR_SETTING
from Resources.paths import EXAMPLES_CONFIG_DIR


def _examples_config_dir():
    """<repo root>/examples/config if this runs from a git checkout, else ''."""
    return EXAMPLES_CONFIG_DIR if os.path.isdir(EXAMPLES_CONFIG_DIR) else ""


def default_config_dir():
    """Folder config browse dialogs should start in: the last used config folder if it still exists, else examples/config, else ''."""
    try:
        last = str(slicer.app.settings().value(LAST_CONFIG_DIR_SETTING) or "")
    except Exception:
        last = ""
    return last if last and os.path.isdir(last) else _examples_config_dir()


def remember_config_path(path):
    """Remember the folder of `path` (a config file just loaded/saved) as the next browse starting folder. Best effort - never raises."""
    try:
        folder = os.path.dirname(os.path.abspath(str(path)))
        if os.path.isdir(folder):
            slicer.app.settings().setValue(LAST_CONFIG_DIR_SETTING, folder)
    except Exception:
        pass
