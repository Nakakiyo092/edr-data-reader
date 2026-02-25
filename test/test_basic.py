#!/usr/bin/env python3

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
        # Get absolute path to reader.py
        script_path = Path(__file__).resolve().parents[1] / "reader" / "reader.py"

        # Run the script with an invalid device name
        result = subprocess.run(
            [sys.executable, str(script_path), "NULL"],
            capture_output=True,
            text=True
        )

        # Verity the output (No device error)
        self.assertIn("could not open port", result.stdout)
        self.assertIn("", result.stderr)

    def test_no_response(self):
        # Get absolute path to reader.py
        script_path = Path(__file__).resolve().parents[1] / "reader" / "reader.py"

        # Run the script with a virtual CAN interface
        result = subprocess.run(
            [sys.executable, str(script_path), "virtual"],
            capture_output=True,
            text=True
        )

        # Verity the output (Time out error)
        self.assertIn("Time out", result.stdout)


if __name__ == "__main__":
    unittest.main()
