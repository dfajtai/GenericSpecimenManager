"""Tests for Resources/core/numbers.py (pure Python - no Slicer needed). Run: python -m unittest discover -s tests"""

import math
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "GenericSpecimenManager", "GenericSpecimenManager"))
from Resources.core.numbers import round_stat, valid_decimals, valid_precision  # noqa: E402


class RoundStatTest(unittest.TestCase):
    """round_stat hides float noise: decimals round, the absolute precision snaps near-whole values."""

    def test_binary_rounding_noise_is_removed(self):
        """0.1 + 0.2 and a float32 0.1 print as the clean number."""
        self.assertEqual(round_stat(0.1 + 0.2, 4, 1e-6), 0.3)
        self.assertEqual(repr(round_stat(0.50000000000001, 4, 1e-6)), "0.5")
        float32_value = struct.unpack("f", struct.pack("f", 0.1))[0]   # 0.10000000149011612
        self.assertEqual(repr(round_stat(float32_value, 4, 1e-6)), "0.1")

    def test_decimals_are_honoured(self):
        """The number of places is the caller's choice; rounding onto a whole number gives an integer."""
        self.assertEqual(round_stat(1.23456789, 3, 1e-6), 1.235)
        self.assertEqual(repr(round_stat(2.6, 0, 1e-6)), "3")
        self.assertEqual(repr(round_stat(2.4, 0, 1e-6)), "2")

    def test_whole_numbers_stay_whole(self):
        """5.0 becomes the int 5 whatever the decimals."""
        for decimals in (0, 2, 4, 9):
            self.assertEqual(repr(round_stat(5.0, decimals, 1e-6)), "5")

    def test_precision_snaps_near_whole_values(self):
        """Within the absolute precision of a whole number (zero included) the value is that integer, even with many decimals."""
        self.assertEqual(repr(round_stat(255.0000004, 9, 1e-6)), "255")
        self.assertEqual(repr(round_stat(3e-7, 9, 1e-6)), "0")
        self.assertEqual(repr(round_stat(2.0000015, 9, 1e-6)), "2.0000015")   # further away than the precision: a real fraction

    def test_small_values_keep_digits_down_to_the_precision(self):
        """Below what the decimals can show a value is not erased: it is rounded at the precision's resolution; below the precision it is 0."""
        self.assertEqual(repr(round_stat(3e-5, 4, 1e-6)), "3e-05")
        self.assertEqual(repr(round_stat(1.23456e-5, 4, 1e-6)), "1.2e-05")
        self.assertEqual(repr(round_stat(-3e-5, 4, 1e-6)), "-3e-05")
        self.assertEqual(repr(round_stat(5e-7, 4, 1e-6)), "0")           # below the precision
        self.assertEqual(repr(round_stat(3e-5, 4, 1e-4)), "0")           # a coarser precision erases more
        self.assertEqual(repr(round_stat(0.00012345, 4, 1e-6)), "0.0001")   # not "small": the normal decimals apply

    def test_precision_is_the_callers_choice(self):
        """A coarser precision snaps more, a finer one keeps small values."""
        self.assertEqual(repr(round_stat(0.9996, 6, 1e-3)), "1")
        self.assertEqual(repr(round_stat(3e-7, 9, 1e-12)), "3e-07")
        self.assertEqual(repr(round_stat(3.4e-7, 4, 1e-9)), "3.4e-07")   # a fine precision lets a small value keep its digits

    def test_special_values_are_kept(self):
        """NaN (empty ROI) and infinity pass through."""
        self.assertTrue(math.isnan(round_stat(float("nan"), 4, 1e-6)))
        self.assertEqual(round_stat(float("inf"), 4, 1e-6), float("inf"))

    def test_negative_values(self):
        """Negative zero becomes 0, negative fractions are rounded."""
        self.assertEqual(repr(round_stat(-0.0000000001, 4, 1e-6)), "0")
        self.assertEqual(repr(round_stat(-1.23456, 4, 1e-6)), "-1.2346")

    def test_huge_values_stay_floats(self):
        """Too large to print as a digit string, so not converted to an int."""
        self.assertIsInstance(round_stat(1e20, 4, 1e-6), float)

    def test_non_floats_are_returned_as_they_are(self):
        """Text and ints are not statistics values and stay untouched."""
        self.assertEqual(round_stat("abc", 4, 1e-6), "abc")
        self.assertEqual(round_stat(3, 4, 1e-6), 3)


class ValidSettingsTest(unittest.TestCase):
    """valid_decimals / valid_precision fall back for anything unusable."""

    def test_valid_decimals(self):
        """0 and positive ints are used."""
        self.assertEqual(valid_decimals(0, 4), 0)
        self.assertEqual(valid_decimals(6, 4), 6)

    def test_invalid_decimals_fall_back(self):
        """None, negative numbers, strings, floats and booleans give the default."""
        for bad in (None, -1, "4", 2.5, True):
            self.assertEqual(valid_decimals(bad, 4), 4, bad)

    def test_valid_precision(self):
        """Positive ints and floats are used, as floats."""
        self.assertEqual(valid_precision(1e-9, 1e-6), 1e-9)
        self.assertEqual(valid_precision(1, 1e-6), 1.0)

    def test_invalid_precision_falls_back(self):
        """None, zero, negatives, NaN, infinity, strings and booleans give the default."""
        for bad in (None, 0, -1e-6, float("nan"), float("inf"), "1e-6", True):
            self.assertEqual(valid_precision(bad, 1e-6), 1e-6, bad)


if __name__ == "__main__":
    unittest.main()
