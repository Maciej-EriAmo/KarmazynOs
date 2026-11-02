#!/usr/bin/env python3
"""Szew open_store. Prawo jest w native/karmazyn_substrate, nie w porównaniu backendów.

    python testy/test_substrate_compat.py -v
"""

from __future__ import annotations

import os
import unittest

import _path  # noqa: F401

from karmazyn_backend import native_available, open_store


class TestOpenStoreIsSubstrate(unittest.TestCase):
    def test_python_backend_refused(self):
        with self.assertRaises(RuntimeError) as ctx:
            open_store(backend="python")
        self.assertIn("native/karmazyn_substrate", str(ctx.exception))

    def test_env_python_refused(self):
        old = os.environ.get("KARMAZYN_SUBSTRATE")
        os.environ["KARMAZYN_SUBSTRATE"] = "python"
        try:
            with self.assertRaises(RuntimeError):
                open_store()
        finally:
            if old is None:
                os.environ.pop("KARMAZYN_SUBSTRATE", None)
            else:
                os.environ["KARMAZYN_SUBSTRATE"] = old

    def test_open_store_is_native(self):
        if not native_available():
            self.skipTest("brak mostu native")
        s = open_store(thermal=True)
        try:
            self.assertTrue(hasattr(s, "native_backend"))
            a = s.atom_new("t", "e")
            aid = a.id if hasattr(a, "id") else a
            self.assertTrue(s.has_atom(aid))
        finally:
            close = getattr(s, "close", None)
            if close:
                close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
