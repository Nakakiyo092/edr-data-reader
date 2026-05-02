#!/usr/bin/env python3

"""
A Python script to test the basic functionality of the EDR data reader.

License:
    MIT License.
    See the accompanying LICENSE file for full terms.
"""

import unittest
import subprocess
import sys
from pathlib import Path


class BasicTestCase(unittest.TestCase):

    print_on: bool

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_no_device(self):
        """Test the behavior when no valid device is specified."""

        # Get absolute path to reader.py
        script_path = Path(__file__).resolve().parents[1] / "src" / "reader.py"

        # Run the script with an invalid device name
        result = subprocess.run(
            [sys.executable, str(script_path), "NULL"],
            capture_output=True,
            text=True
        )

        # Verity the output (No device error)
        self.assertIn("Could not access CAN nework", result.stdout)
        self.assertIn("", result.stderr)

    def test_no_response(self):
        """Test the behavior when no response is received on CAN bus."""

        # Get absolute path to reader.py
        script_path = Path(__file__).resolve().parents[1] / "src" / "reader.py"

        # Run the script with a virtual CAN interface
        result = subprocess.run(
            [sys.executable, str(script_path), "virtual"],
            capture_output=True,
            text=True
        )

        # Verity the output (Time out for all did)
        self.assertIn("Time out", result.stdout)
        self.assertIn("", result.stderr)


if __name__ == "__main__":
    unittest.main()
