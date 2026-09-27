#!/usr/bin/env python3

"""
Unit tests for the per-run result folder of the EDR data reader.

License:
    MIT License.
    See the accompanying LICENSE file for full terms.
"""

import contextlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reader import _new_result_dir, _output_data  # pylint: disable=wrong-import-position

_FORMAT_DIR = Path(__file__).resolve().parents[1] / "format"


class OutputTestCase(unittest.TestCase):
    """Tests for where and when the reader writes its result files."""

    def setUp(self):
        # Run in a scratch copy of the repo layout: format/ in, result/ out
        tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(tmp.cleanup)
        shutil.copytree(_FORMAT_DIR, os.path.join(tmp.name, "format"))
        self.enterContext(contextlib.chdir(tmp.name))

    def test_new_result_dir_is_timestamped(self):
        """The folder is named after the run's start time under result/."""
        with mock.patch("reader.time.strftime", return_value="20260101_000000"):
            self.assertEqual(_new_result_dir(), "result/20260101_000000")

    def test_new_result_dir_avoids_existing(self):
        """A second run within the same second gets a suffixed folder."""
        with mock.patch("reader.time.strftime", return_value="20260101_000000"):
            os.makedirs("result/20260101_000000")
            self.assertEqual(_new_result_dir(), "result/20260101_000000_2")
            os.makedirs("result/20260101_000000_2")
            self.assertEqual(_new_result_dir(), "result/20260101_000000_3")

    def test_new_result_dir_is_not_created(self):
        """Choosing the path alone leaves no folder behind."""
        path = _new_result_dir()
        self.assertFalse(os.path.exists(path))

    def test_output_creates_folder_on_data(self):
        """The first successful read creates the folder and writes its CSV."""
        payload = bytes([0x62, 0xFA, 0x13]) + bytes(8)
        _output_data(payload, "result/run1")
        self.assertTrue(os.path.isfile("result/run1/did_fa13.csv"))

    def test_output_without_data_creates_nothing(self):
        """A failed read (no payload) does not create the folder."""
        _output_data(None, "result/run1")
        self.assertFalse(os.path.exists("result/run1"))

    def test_runs_do_not_mix(self):
        """A partial second run leaves the first run's files untouched."""
        first = bytes([0x62, 0xFA, 0x13]) + bytes([0x11] * 8)
        _output_data(first, "result/run1")
        _output_data(bytes([0x62, 0xFA, 0x14]) + bytes(8), "result/run1")
        before = Path("result/run1/did_fa13.csv").read_bytes()

        # The second run only gets DID 0xFA13, with different content
        _output_data(bytes([0x62, 0xFA, 0x13]) + bytes([0x22] * 8), "result/run2")

        self.assertEqual(Path("result/run1/did_fa13.csv").read_bytes(), before)
        self.assertEqual(sorted(os.listdir("result/run2")), ["did_fa13.csv"])


if __name__ == "__main__":
    unittest.main()
