# -*- coding: utf-8 -*-
"""Smoke: Studio SDL (bez okna — --check)."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "software"), os.path.join(ROOT, "kernel"),
                os.path.join(ROOT, "native")]
os.environ["KARMAZYN_SUBSTRATE"] = "python"


class StudioSdlSmoke(unittest.TestCase):
    def test_sdl_available_or_skip(self):
        from karmazyn_io_sdl import sdl_available
        if not sdl_available():
            self.skipTest("pygame not installed")
        self.assertTrue(sdl_available())

    def test_studio_check(self):
        from karmazyn_io_sdl import sdl_available
        if not sdl_available():
            self.skipTest("pygame not installed")
        from karmazyn_studio import main
        code = main(["--python", "--check"])
        self.assertEqual(code, 0)

    def test_color_for_T(self):
        from karmazyn_io_sdl import _color_for_T
        self.assertEqual(_color_for_T(0), (50, 50, 60))  # tomb-ish
        hot = _color_for_T(90)
        self.assertGreater(hot[0], 200)  # red-ish


if __name__ == "__main__":
    unittest.main()
