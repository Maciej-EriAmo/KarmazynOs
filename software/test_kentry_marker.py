# -*- coding: utf-8 -*-
"""SF/SR: kentry marker present in source (and ELF when built)."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KENTRY = ROOT / "boot" / "kentry"
MARKER = b"KARMAZYN_KENTRY_OK"


class KentryMarkerTests(unittest.TestCase):
    def test_marker_in_source(self):
        src = (KENTRY / "src" / "main.rs").read_bytes()
        self.assertIn(MARKER, src)

    def test_header_size_const(self):
        src = (KENTRY / "src" / "main.rs").read_text(encoding="utf-8")
        self.assertIn("MB2_HEADER_LEN: u32 = 24", src)
        self.assertIn("size_of::<Multiboot2Header>() == 24", src)

    def test_elf_marker_if_built(self):
        elf = KENTRY / "target" / "x86_64-unknown-none" / "release" / "karmazyn_kentry"
        if not elf.is_file():
            self.skipTest("kentry ELF not built (run cargo build --target x86_64-unknown-none)")
        data = elf.read_bytes()
        self.assertIn(MARKER, data, "marker missing from ELF")


if __name__ == "__main__":
    unittest.main()
