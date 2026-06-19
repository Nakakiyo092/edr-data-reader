#!/usr/bin/env python3

"""Unit tests for the raw-to-physical conversion helpers in reader.py.

License:
    MIT License.
    See the accompanying LICENSE file for full terms.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reader import _convert, _parse_linear, _parse_value_table


class ParseValueTableTest(unittest.TestCase):
    """Verify the semicolon-separated value-table parser."""

    def test_single_entry(self):
        """A lone '0xH:Label' entry parses into a single-key dict."""
        self.assertEqual(_parse_value_table("0xFF:N/A"), {0xFF: "N/A"})

    def test_multiple_entries(self):
        """Entries separated by ';' parse into one dict entry each."""
        self.assertEqual(
            _parse_value_table("0xFE:Invalid;0xFF:N/A"),
            {0xFE: "Invalid", 0xFF: "N/A"},
        )

    def test_two_byte_keys(self):
        """Hex keys wider than one byte are honored for multi-byte signals."""
        self.assertEqual(
            _parse_value_table("0xFFFE:Invalid;0xFFFF:N/A"),
            {0xFFFE: "Invalid", 0xFFFF: "N/A"},
        )

    def test_label_with_spaces(self):
        """Labels may contain spaces (e.g., the VIN 'See last byte' idiom)."""
        self.assertEqual(
            _parse_value_table("0xFF:See last byte"),
            {0xFF: "See last byte"},
        )

    def test_no_table_passthrough(self):
        """Sentinel cells ('N/A', 'Subsequent byte', empty) yield no entries."""
        self.assertEqual(_parse_value_table("N/A"), {})
        self.assertEqual(_parse_value_table("Subsequent byte"), {})
        self.assertEqual(_parse_value_table(""), {})

    def test_unparsable_entries_skipped(self):
        """A bad hex key is silently dropped while valid neighbors come through."""
        self.assertEqual(
            _parse_value_table("0xZZ:Bad;0xFF:N/A"),
            {0xFF: "N/A"},
        )


class ParseLinearTest(unittest.TestCase):
    """Verify the linear-formula parser handles every form found in format/*.csv."""

    def test_identity(self):
        """'E=N' parses as scale=1, offset=0."""
        self.assertEqual(_parse_linear("E=N"), (1.0, 0.0))

    def test_offset_only_negative(self):
        """'E=N-K' captures the negative offset."""
        self.assertEqual(_parse_linear("E=N-127"), (1.0, -127.0))

    def test_offset_only_positive(self):
        """'E=N+K' captures the positive offset."""
        self.assertEqual(_parse_linear("E=N+10"), (1.0, 10.0))

    def test_scale_only(self):
        """'E=N*K' captures the scale; covers all CSV-occurring scales."""
        self.assertEqual(_parse_linear("E=N*100"), (100.0, 0.0))
        self.assertEqual(_parse_linear("E=N*0.1"), (0.1, 0.0))

    def test_scale_and_offset(self):
        """'E=N*K+/-K' captures both scale and offset; covers all CSV forms."""
        self.assertEqual(_parse_linear("E=N*0.1-300"), (0.1, -300.0))
        self.assertEqual(_parse_linear("E=N*5-780"), (5.0, -780.0))

    def test_unicode_multiply_sign(self):
        """'×' is accepted as a synonym for '*' for forward compatibility."""
        self.assertEqual(_parse_linear("E=N×5"), (5.0, 0.0))

    def test_whitespace_tolerated(self):
        """Whitespace around tokens does not break parsing."""
        self.assertEqual(_parse_linear(" E = N - 127 "), (1.0, -127.0))

    def test_invalid_raises(self):
        """Non-linear strings ('Ascii', 'Not defined', exponents) raise ValueError."""
        with self.assertRaises(ValueError):
            _parse_linear("Ascii")
        with self.assertRaises(ValueError):
            _parse_linear("Not defined")
        with self.assertRaises(ValueError):
            _parse_linear("E=N**2")


class ConvertTest(unittest.TestCase):
    """Verify the integrated converter applies value_table before formula."""

    def test_value_table_takes_priority(self):
        """A value_table hit returns the label even when the formula is valid."""
        self.assertEqual(_convert(0xFF, "0xFE:Invalid;0xFF:N/A", "E=N-127"), "N/A")

    def test_value_table_miss_falls_through_to_formula(self):
        """When the raw value is not in the table, the formula is applied."""
        self.assertEqual(_convert(130, "0xFE:Invalid;0xFF:N/A", "E=N-127"), "3")

    def test_identity_formula(self):
        """'E=N' returns the raw value as a string."""
        self.assertEqual(_convert(42, "N/A", "E=N"), "42")

    def test_scale_and_offset_formula(self):
        """'E=N*K+/-K' applies the affine transform and stringifies the result."""
        # 200 * 0.1 - 300 = -280
        self.assertEqual(_convert(200, "N/A", "E=N*0.1-300"), "-280")

    def test_ascii_printable(self):
        """A printable byte under the Ascii rule becomes the character."""
        self.assertEqual(_convert(0x41, "N/A", "Ascii"), "A")

    def test_ascii_non_printable_hex_fallback(self):
        """A non-printable byte under the Ascii rule falls back to '0xHH'."""
        self.assertEqual(_convert(0x00, "N/A", "Ascii"), "0x00")
        self.assertEqual(_convert(0xFF, "N/A", "Ascii"), "0xFF")

    def test_not_defined_returns_empty(self):
        """A 'Not defined' formula plus a value_table miss yields an empty string."""
        self.assertEqual(_convert(0x05, "0x00:Off;0x01:On", "Not defined"), "")

    def test_not_defined_with_table_match(self):
        """A 'Not defined' formula plus a value_table hit returns the label."""
        self.assertEqual(_convert(0x01, "0x00:Off;0x01:On", "Not defined"), "On")

    def test_multi_byte_table_match(self):
        """A multi-byte aggregated raw value matches a multi-byte key in the table."""
        self.assertEqual(
            _convert(0xFFFF, "0xFFFE:Invalid;0xFFFF:N/A", "E=N"),
            "N/A",
        )

    def test_subsequent_byte_marker_returns_empty(self):
        """Defensive: continuation markers passed to _convert yield an empty string."""
        self.assertEqual(_convert(0x00, "Subsequent byte", "Subsequent byte"), "")


if __name__ == "__main__":
    unittest.main()
