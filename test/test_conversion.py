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
        self.assertEqual(_parse_value_table("0xFF:N/A"), {0xFF: "N/A"})

    def test_multiple_entries(self):
        self.assertEqual(
            _parse_value_table("0xFE:Invalid;0xFF:N/A"),
            {0xFE: "Invalid", 0xFF: "N/A"},
        )

    def test_two_byte_keys(self):
        self.assertEqual(
            _parse_value_table("0xFFFE:Invalid;0xFFFF:N/A"),
            {0xFFFE: "Invalid", 0xFFFF: "N/A"},
        )

    def test_label_with_spaces(self):
        # The "See last byte" idiom used for VIN padding.
        self.assertEqual(
            _parse_value_table("0xFF:See last byte"),
            {0xFF: "See last byte"},
        )

    def test_no_table_passthrough(self):
        self.assertEqual(_parse_value_table("N/A"), {})
        self.assertEqual(_parse_value_table("Subsequent byte"), {})
        self.assertEqual(_parse_value_table(""), {})

    def test_unparsable_entries_skipped(self):
        # Bad hex key is silently skipped; valid entries still come through.
        self.assertEqual(
            _parse_value_table("0xZZ:Bad;0xFF:N/A"),
            {0xFF: "N/A"},
        )


class ParseLinearTest(unittest.TestCase):
    """Verify the linear-formula parser handles every form found in format/*.csv."""

    def test_identity(self):
        self.assertEqual(_parse_linear("E=N"), (1.0, 0.0))

    def test_offset_only_negative(self):
        self.assertEqual(_parse_linear("E=N-127"), (1.0, -127.0))

    def test_offset_only_positive(self):
        self.assertEqual(_parse_linear("E=N+10"), (1.0, 10.0))

    def test_scale_only(self):
        # Forms found in format/*.csv: E=N*100, E=N*0.1, E=N*2.5, E=N*5
        self.assertEqual(_parse_linear("E=N*100"), (100.0, 0.0))
        self.assertEqual(_parse_linear("E=N*0.1"), (0.1, 0.0))

    def test_scale_and_offset(self):
        # Forms found in format/*.csv: E=N*0.1-300, E=N*5-780
        self.assertEqual(_parse_linear("E=N*0.1-300"), (0.1, -300.0))
        self.assertEqual(_parse_linear("E=N*5-780"), (5.0, -780.0))

    def test_unicode_multiply_sign(self):
        # CSV uses '*'; '×' accepted for forward compatibility.
        self.assertEqual(_parse_linear("E=N×5"), (5.0, 0.0))

    def test_whitespace_tolerated(self):
        self.assertEqual(_parse_linear(" E = N - 127 "), (1.0, -127.0))

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            _parse_linear("Ascii")
        with self.assertRaises(ValueError):
            _parse_linear("Not defined")
        with self.assertRaises(ValueError):
            _parse_linear("E=N**2")  # exponent: outside linear scope


class ConvertTest(unittest.TestCase):
    """Verify the integrated converter applies value_table before formula."""

    def test_value_table_takes_priority(self):
        # 0xFF matches the value table even though E=N-127 is a valid formula.
        self.assertEqual(_convert(0xFF, "0xFE:Invalid;0xFF:N/A", "E=N-127"), "N/A")

    def test_value_table_miss_falls_through_to_formula(self):
        # Raw 130 is not in the value table -> apply E=N-127.
        self.assertEqual(_convert(130, "0xFE:Invalid;0xFF:N/A", "E=N-127"), "3")

    def test_identity_formula(self):
        self.assertEqual(_convert(42, "N/A", "E=N"), "42")

    def test_scale_and_offset_formula(self):
        # 200 * 0.1 - 300 = -280
        self.assertEqual(_convert(200, "N/A", "E=N*0.1-300"), "-280")

    def test_ascii_printable(self):
        self.assertEqual(_convert(0x41, "N/A", "Ascii"), "A")

    def test_ascii_non_printable_hex_fallback(self):
        self.assertEqual(_convert(0x00, "N/A", "Ascii"), "0x00")
        self.assertEqual(_convert(0xFF, "N/A", "Ascii"), "0xFF")

    def test_not_defined_returns_empty(self):
        # Only the value_table can produce output; raw 0x05 isn't in the table.
        self.assertEqual(_convert(0x05, "0x00:Off;0x01:On", "Not defined"), "")

    def test_not_defined_with_table_match(self):
        self.assertEqual(_convert(0x01, "0x00:Off;0x01:On", "Not defined"), "On")

    def test_multi_byte_table_match(self):
        # Aggregated 2-byte value 0xFFFF should hit the table.
        self.assertEqual(
            _convert(0xFFFF, "0xFFFE:Invalid;0xFFFF:N/A", "E=N"),
            "N/A",
        )

    def test_subsequent_byte_marker_returns_empty(self):
        # Defensive: continuation rows should never be passed to _convert in
        # practice, but if they are, they yield an empty string.
        self.assertEqual(_convert(0x00, "Subsequent byte", "Subsequent byte"), "")


if __name__ == "__main__":
    unittest.main()
