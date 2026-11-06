"""
paths.py
========
Path text from the CSVs / config -> the running platform's separator. Pure Python.
"""

import os


def platform_path(path, sep=None):
    """Return `path` with the separators of this platform: studies are written with "/" (CSV cells, path patterns), which is turned into "\\" on Windows; a "\\"-separated path coming from a Windows-made CSV is turned into "/" elsewhere. A relative path stays relative (it is resolved against the study folder later); `sep` is only for tests."""
    sep = sep or os.sep
    other = "/" if sep == "\\" else "\\"
    return str(path).replace(other, sep)
