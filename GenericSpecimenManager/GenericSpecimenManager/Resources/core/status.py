"""
status.py
=========
Parsing of the specimen status stored in database.csv (the enum itself lives in definitions.py).
"""

from Resources.definitions import SpecimenStatus


def parse_status(text):
    """A database.csv status cell (str/int/None) -> SpecimenStatus; empty or anything unrecognized is UNTOUCHED."""
    try:
        return SpecimenStatus(int(str(text).strip()))
    except (ValueError, TypeError):
        return SpecimenStatus.UNTOUCHED
