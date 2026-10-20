"""
naming.py
=========
Turn identifiers into display text: Slicer's CamelCase names and database.csv column names.
"""

import re


def camel_to_snake(text):
    """'InsideAllSegments' -> 'inside_all_segments' (the form used for a config value)."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()


def camel_to_label(text):
    """'InsideAllSegments' -> 'Inside all segments' (first word capitalised, rest lower case - the wording of Slicer's own GUI)."""
    words = camel_to_snake(text).replace("_", " ")
    return words[:1].upper() + words[1:]


def column_label(name):
    """A database.csv column name as a readable table header: 'batch_id' -> 'Batch id', 'specimenID' -> 'Specimen ID', 'ID' -> 'ID', 'sampleName' -> 'Sample name'. Words are split at '_' / '-' / spaces and at lower-to-UPPER case changes; ALL-CAPS words (IDs, acronyms) stay as they are, other words are lower case, and the first letter of the whole label is capitalised."""
    parts = re.split(r"[_\-\s]+|(?<=[a-z0-9])(?=[A-Z])", name.strip())
    words = [p if (p.isupper() and len(p) > 1) else p.lower() for p in parts if p]
    label = " ".join(words)
    return label[:1].upper() + label[1:]
