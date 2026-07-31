# -*- coding: utf-8 -*-
"""SF/SR: kentry markers present in source (and ELF when built)."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KENTRY = ROOT / "boot" / "kentry"
MARKER = b"KARMAZYN_KENTRY_OK"
SLAB_OK = b"SLAB_OK"
SLAB_FAIL = b"SLAB_FAIL"
SLAB_VACUUM = b"SLAB_VACUUM_OK"


class KentryMarkerTests(unittest.TestCase):
    def test_marker_in_source(self):
        src = (KENTRY / "src" / "main.rs").read_bytes()
        self.assertIn(MARKER, src)

    def test_r5_slab_markers_in_source(self):
        src = (KENTRY / "src" / "main.rs").read_bytes()
        self.assertIn(SLAB_OK, src)
        self.assertIn(SLAB_VACUUM, src)
        self.assertIn(SLAB_FAIL, src)
        # must depend on karmazyn_slab, not hand-rolled store
        self.assertIn(b"karmazyn_slab", src)
        self.assertIn(b"SlabStore", src)

    def test_header_size_const(self):
        src = (KENTRY / "src" / "main.rs").read_text(encoding="utf-8")
        self.assertIn("MB2_HEADER_LEN: u32 = 24", src)
        self.assertIn("size_of::<Multiboot2Header>() == 24", src)

    def test_cargo_depends_on_slab(self):
        toml = (KENTRY / "Cargo.toml").read_text(encoding="utf-8")
        self.assertIn("karmazyn_slab", toml)
        self.assertIn("native/karmazyn_slab", toml.replace("\\", "/"))

    def test_elf_markers_if_built(self):
        elf = KENTRY / "target" / "x86_64-unknown-none" / "release" / "karmazyn_kentry"
        if not elf.is_file():
            self.skipTest("kentry ELF not built (run cargo build --target x86_64-unknown-none)")
        data = elf.read_bytes()
        self.assertIn(MARKER, data, "marker missing from ELF")
        self.assertIn(SLAB_OK, data, "SLAB_OK missing from ELF (R5)")
        self.assertIn(SLAB_VACUUM, data, "SLAB_VACUUM_OK missing from ELF")


if __name__ == "__main__":
    unittest.main()
