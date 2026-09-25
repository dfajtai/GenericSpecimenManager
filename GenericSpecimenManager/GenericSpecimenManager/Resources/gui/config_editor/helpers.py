"""
helpers.py
==========
Small helpers shared by the Config Editor's tabs (CSV headers, list/float parsing, optional dropdowns).
"""

import csv

from Resources.definitions import UNSET


DEFAULT_SEGMENT_COLOR = (0.9, 0.9, 0.2)


def read_csv_header(path):
    """Read just the header row of a CSV as a list of column names; returns [] on any read error (missing file, not a CSV, etc.) rather than raising."""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return [h.strip() for h in next(csv.reader(f)) if h.strip()]
    except Exception:
        return []


def guess_key_columns(header):
    """Best-effort guess at which header column(s) are the specimen key: anything named like id/sid/specimen/specimenid (case-insensitive), falling back to just the first column."""
    guesses = [h for h in header if h.strip().lower() in ("id", "sid", "specimen", "specimenid")]
    return guesses or (header[:1] if header else [])


def csv_list(text):
    """Split a comma-separated GUI field into a clean list of non-empty, stripped strings."""
    return [c.strip() for c in text.split(",") if c.strip()]


def to_float(text):
    """Parse a GUI field's text as a float, or None if it's empty/unparseable - used everywhere a numeric field is optional (opacity, min/max, diameter, ...)."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def combo_value(combo):
    """The text of an optional dropdown as a config value: the '(unset)' entry (or nothing typed) -> ''."""
    text = (combo.currentText or "").strip()
    return "" if text == UNSET else text


def set_combo_value(combo, value):
    """Select `value` in an optional dropdown; an empty value selects the '(unset)' entry instead of leaving a blank."""
    combo.currentText = value or UNSET
