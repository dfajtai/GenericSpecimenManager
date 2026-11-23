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


def first_free_indexed_path(template, token, exists=os.path.exists):
    """Return `template` with every `token` replaced by the lowest two-digit counter ("01", "02", ...) for which the resulting path does not exist yet, so a report from an earlier run is never overwritten. The counter takes exactly the place of the token and brings no separator of its own: "report_{token}.csv" gives "report_01.csv". `exists` is only for tests."""
    index = 1
    while True:
        candidate = template.replace(token, f"{index:02d}")
        if not exists(candidate):
            return candidate
        index += 1
