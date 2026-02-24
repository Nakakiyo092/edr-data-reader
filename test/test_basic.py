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

        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True
        )

        # Verity the output (No device error)
        self.assertIn("FileNotFoundError", result.stdout)


if __name__ == "__main__":
    unittest.main()
