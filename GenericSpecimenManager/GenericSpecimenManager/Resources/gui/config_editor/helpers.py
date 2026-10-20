"""
helpers.py
==========
Small helpers shared by the Config Editor's tabs (CSV headers, list/float parsing, optional dropdowns).
"""

import csv

import qt

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


def fill_labeled_combo(combo, labels):
    """Fill an optional dropdown with '(unset)' followed by the display labels of a {config value: label} dict."""
    combo.addItems([UNSET] + list(labels.values()))


def set_labeled_combo(combo, labels, value):
    """Select the entry for config `value` (its display label); empty/unknown selects '(unset)'."""
    combo.currentText = labels.get(value or "", UNSET)


def labeled_combo_value(combo, labels):
    """The config value behind the selected display label of a labeled dropdown; '(unset)' -> ''."""
    text = combo.currentText
    for value, label in labels.items():
        if label == text:
            return value
    return ""


def fill_grouped_combo(combo, groups):
    """Fill a dropdown with '(unset)' followed by `groups` ([(heading, [names]), ...]): each group gets a separator line and a greyed-out, unselectable heading, then its names. The names are the items' text, so combo_value()/set_combo_value() keep working."""
    combo.addItem(UNSET)
    for heading, names in groups:
        combo.insertSeparator(combo.count)
        combo.addItem(f"-- {heading} --")
        header = combo.model().item(combo.count - 1)
        if header is not None:
            header.setFlags(qt.Qt.NoItemFlags)   # shown, but cannot be picked
        combo.addItems(names)


def move_target(row, delta, count):
    """Row index a row would move to when shifted by `delta` (-1 = up, +1 = down) in a table of `count` rows, or None when it cannot move (nothing selected, or already first/last) - also tells the Move buttons whether to be enabled."""
    if row is None or row < 0 or row >= count:
        return None
    target = row + delta
    return target if 0 <= target < count else None


def update_move_buttons(table, upBtn, downBtn):
    """Enable Move up/down for the table's selected row only when it has room to move that way (disabled for the first/last row, or when nothing is selected)."""
    row = table.currentRow() if table.selectedIndexes() else -1
    count = table.rowCount
    upBtn.enabled = move_target(row, -1, count) is not None
    downBtn.enabled = move_target(row, +1, count) is not None
