"""
numbers.py
==========
Number formatting for the files the module writes. Pure Python.
"""

import math

# A statistic this close to a non-zero whole number is written as that integer (absolute, like numpy.isclose(..., rtol=0, atol=1e-6)).
WHOLE_TOLERANCE = 1e-6


def valid_decimals(value, default):
    """Return `value` if it is a usable number of decimal places (an int, not a bool, from 0 up), else `default`. The config is hand-editable, so a stray `"6"`, `-1` or `true` falls back instead of breaking the export."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return default


def round_stat(value, decimals, whole_tolerance=WHOLE_TOLERANCE):
    """Round a statistic to `decimals` places so the CSV shows 0.5 and not 0.5000000298 (float32 image data, or a voxel volume such as 3 * 0.1, leave binary rounding noise behind). A value within `whole_tolerance` of a non-zero whole number is written as that integer (255.0000004 -> 255, never 255.00), whatever `decimals` is. Values near zero are NOT snapped to 0: a small value is rounded to `decimals` like any other (5e-7 stays 5e-07 with 9 decimals, becomes 0 with 6). NaN and infinity are returned unchanged."""
    if not isinstance(value, float) or math.isnan(value) or math.isinf(value):
        return value
    nearest = round(value)
    if nearest != 0 and abs(nearest) < 1e15 and math.isclose(value, nearest, rel_tol=0.0, abs_tol=whole_tolerance):   # beyond 1e15 an int would only print a long digit string
        return int(nearest)
    rounded = round(value, decimals) + 0.0   # + 0.0: -0.0 becomes 0.0
    if rounded.is_integer() and abs(rounded) < 1e15:   # e.g. 2.4 with 0 decimals
        return int(rounded)
    return rounded
