"""Tests for Resources/core/numbers.py (pure Python - no Slicer needed). Run: python -m unittest discover -s tests"""

import math
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "GenericSpecimenManager", "GenericSpecimenManager"))
from Resources.core.numbers import round_stat, valid_decimals  # noqa: E402


class RoundStatTest(unittest.TestCase):
    """round_stat hides float noise without touching special values."""

    def test_binary_rounding_noise_is_removed(self):
        """0.1 + 0.2 and a float32 0.5 neighbour print as the clean number."""
        self.assertEqual(round_stat(0.1 + 0.2, 6), 0.3)
        self.assertEqual(repr(round_stat(0.50000000000001, 6)), "0.5")
        float32_value = struct.unpack("f", struct.pack("f", 0.1))[0]   # 0.10000000149011612
        self.assertEqual(repr(round_stat(float32_value, 6)), "0.1")

    def test_decimals_are_honoured(self):
        """The number of places is the caller's choice, 0 gives a whole number."""
        self.assertEqual(round_stat(1.23456789, 3), 1.235)
        self.assertEqual(round_stat(2.6, 0), 3)
        self.assertEqual(repr(round_stat(2.4, 0)), "2")

    def test_small_values_follow_the_decimals(self):
        """Near zero nothing is snapped to 0: the value is rounded to the chosen decimals like any other."""
        self.assertEqual(repr(round_stat(5e-7, 9)), "5e-07")
        self.assertEqual(repr(round_stat(0.0000004, 9)), "4e-07")
        self.assertEqual(repr(round_stat(5e-7, 6)), "0")   # rounds to zero only because 6 decimals cannot show it
        self.assertEqual(repr(round_stat(0.0000026, 6)), "3e-06")

    def test_special_values_are_kept(self):
        """NaN (empty ROI) and infinity pass through; negative zero becomes zero."""
        self.assertTrue(math.isnan(round_stat(float("nan"), 6)))
        self.assertEqual(round_stat(float("inf"), 6), float("inf"))
        self.assertEqual(repr(round_stat(-0.0000000001, 6)), "0")

    def test_whole_numbers_stay_whole(self):
        """5.0 becomes the int 5 whatever the precision; a fraction keeps its decimals."""
        for decimals in (0, 2, 6, 9):
            self.assertEqual(repr(round_stat(5.0, decimals)), "5")
        self.assertEqual(repr(round_stat(255.0000004, 9)), "255")   # within 1e-6 of a whole number, even with many decimals
        self.assertEqual(repr(round_stat(2.0000015, 9)), "2.0000015")   # further away: a real fraction
        self.assertEqual(repr(round_stat(0.5, 6)), "0.5")
        self.assertIsInstance(round_stat(1e20, 6), float)   # too large to print as a digit string

    def test_non_floats_are_returned_as_they_are(self):
        """Text and ints are not statistics values and stay untouched."""
        self.assertEqual(round_stat("abc", 6), "abc")
        self.assertEqual(round_stat(3, 6), 3)


class ValidDecimalsTest(unittest.TestCase):
    """valid_decimals falls back for anything that is not a whole number >= 0."""

    def test_valid_values(self):
        """0 and positive ints are used."""
        self.assertEqual(valid_decimals(0, 6), 0)
        self.assertEqual(valid_decimals(4, 6), 4)

    def test_invalid_values_fall_back(self):
        """None, negative numbers, strings, floats and booleans give the default."""
        for bad in (None, -1, "4", 2.5, True):
            self.assertEqual(valid_decimals(bad, 6), 6, bad)


if __name__ == "__main__":
    unittest.main()
