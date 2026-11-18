"""
numbers.py
==========
Number formatting for the files the module writes. Pure Python.
"""

import math


def valid_decimals(value, default):
    """Return `value` if it is a usable number of decimal places (an int, not a bool, from 0 up), else `default`. The config is hand-editable, so a stray `"4"`, `-1` or `true` falls back instead of breaking the export."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return default


def valid_precision(value, default):
    """Return `value` if it is a usable absolute precision (a finite number above 0, not a bool), else `default`."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
        return float(value)
    return default


def round_stat(value, decimals, precision):
    """Prepare a statistic for the CSV. `precision` is an absolute epsilon: a value within it of a whole number (zero included, so anything below `precision` becomes 0) is written as that integer, whatever `decimals` is (255.0000004 -> 255, 3e-7 -> 0, never 255.0000). Any other value is rounded to `decimals` places, so the CSV shows 0.5 and not 0.5000000298 (float32 image data, or a voxel volume such as 3 * 0.1, leave binary rounding noise behind). A value too small for that (below 10**-decimals, but above `precision`) is not erased: it keeps as many digits as `precision` resolves (3e-5 with 4 decimals and 1e-6 -> 3e-05). A rounded whole number is an integer too. NaN and infinity are returned unchanged."""
    if not isinstance(value, float) or math.isnan(value) or math.isinf(value):
        return value
    nearest = round(value)
    if abs(nearest) < 1e15 and abs(value - nearest) <= precision:   # beyond 1e15 an int would only print a long digit string
        return int(nearest)
    if abs(value) < 10.0 ** -decimals:   # smaller than `decimals` can show: go as deep as the precision allows
        decimals = max(decimals, math.ceil(-math.log10(precision)))
    rounded = round(value, decimals) + 0.0   # + 0.0: -0.0 becomes 0.0
    if rounded.is_integer() and abs(rounded) < 1e15:   # e.g. 2.4 with 0 decimals
        return int(rounded)
    return rounded
