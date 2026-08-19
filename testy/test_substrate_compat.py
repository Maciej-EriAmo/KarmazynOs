#!/usr/bin/env python3
"""
test_substrate_compat.py — zgodność prawa reach-GC: Python Store ↔ Rust native
==============================================================================

Uruchomienie (z roota repo):
    python testy/test_substrate_compat.py -v
    python testy/test_substrate_compat.py --substrate both

Wymaga: cargo build --release w native/karmazyn_substrate (dla native).
Gdy DLL brak: testy native → skip, python i tak biegną.

Pokrycie (to samo prawo co test_substrate prawo T×reach):
  orphan dies, root retains TOMB, unset_root reaps, heat resurrection,
  env_of closure, extra_reach, parent chain lookup (native/python).
"""

from __future__ import annotations

import os
import sys
import unittest

import _path  # noqa: F401

# CLI flags before imports that read env
from karmazyn_backend import (
    apply_cli_substrate_flags,
    backend_info,
    native_available,
    open_store,
    substrate_backend,
)

apply_cli_substrate_flags()

COOL = 80  # margin: T_INIT*0.92^n < T_TOMB (native i python ten sam decay)


class _Clo:
    def __init__(self, env):
        self.env = env


def _env_of_clo(v):
    return v.env if isinstance(v, _Clo) else None


def _aid(a):
    return a.id if hasattr(a, "id") else a


def _backends_to_run():
    """Lista backendów do przebiegnięcia w tym procesie."""
    mode = substrate_backend()
    if mode == "both":
        out = ["python"]
        if native_available():
            out.append("native")
        return out
    if mode == "native" and not native_available():
        return []  # caller skips
    return [mode]


class CompatLawBase:
    """Scenariusze — podklasy ustawiają BACKEND."""

    BACKEND = "python"

    def setUp(self):
        if self.BACKEND == "native" and not native_available():
            self.skipTest("native DLL missing (cargo build --release)")
        self.s = open_store(thermal=True, backend=self.BACKEND)

    def tearDown(self):
        close = getattr(self.s, "close", None)
        if close:
            try:
                close()
            except Exception:
                pass

    def test_orphan_dies(self):
        a = self.s.atom_new("var", "orphan")
        self.s.settle(COOL)
        self.assertFalse(self.s.has_atom(_aid(a)))
        self.assertGreaterEqual(self.s.stats()["reaped"], 1)

    def test_root_retains_tomb(self):
        root = self.s.bubble_new("root")
        self.s.set_root(root)
        a = self.s.atom_new("var", "keep")
        root.bind("keep", a)
        self.s.settle(COOL)
        self.assertTrue(self.s.has_atom(_aid(a)))
        self.assertTrue(a.is_dead())
        self.assertEqual(self.s.stats()["retained_tomb"], 1)

    def test_unset_root_then_reap(self):
        root = self.s.bubble_new("root")
        self.s.set_root(root)
        a = self.s.atom_new("var", "x")
        root.bind("x", a)
        self.s.settle(COOL)
        self.assertTrue(self.s.has_atom(_aid(a)))
        self.s.unset_root(root)
        self.s.settle(2)
        self.assertFalse(self.s.has_atom(_aid(a)))

    def test_heat_resurrection(self):
        root = self.s.bubble_new("root")
        self.s.set_root(root)
        a = self.s.atom_new("var", "z")
        root.bind("z", a)
        self.s.settle(COOL)
        self.assertEqual(self.s.stats()["retained_tomb"], 1)
        for _ in range(12):
            self.s.heat(a)
        self.s.tick()
        self.assertFalse(a.is_dead())
        self.assertEqual(self.s.stats()["retained_tomb"], 0)

    def test_env_of_closure_survives(self):
        s = open_store(thermal=True, backend=self.BACKEND, env_of=_env_of_clo)
        self.addCleanup(lambda: getattr(s, "close", lambda: None)())
        root = s.bubble_new("root")
        s.set_root(root)
        inner = s.bubble_new("inner")
        n = s.atom_new("var", "n", value=0)
        inner.bind("n", n)
        clo = s.atom_new("var", "clo", value=_Clo(inner))
        root.bind("clo", clo)
        s.settle(100)
        self.assertTrue(s.has_atom(_aid(n)))
        self.assertIsNotNone(inner.lookup("n"))

    def test_extra_reach_protects(self):
        held = set()

        def extra():
            return list(held)

        s = open_store(thermal=True, backend=self.BACKEND, extra_reach=extra)
        self.addCleanup(lambda: getattr(s, "close", lambda: None)())
        a = s.atom_new("var", "flat")
        held.add(_aid(a))
        s.settle(COOL)
        self.assertTrue(s.has_atom(_aid(a)))
        held.clear()
        s.settle(2)
        self.assertFalse(s.has_atom(_aid(a)))


class TestLawPython(CompatLawBase, unittest.TestCase):
    BACKEND = "python"


class TestLawNative(CompatLawBase, unittest.TestCase):
    BACKEND = "native"


class TestCrossAgreement(unittest.TestCase):
    """Te same scenariusze na obu — porównaj kluczowe liczby w stats."""

    @classmethod
    def setUpClass(cls):
        if not native_available():
            raise unittest.SkipTest("native DLL missing")

    def _run_orphan(self, backend):
        s = open_store(thermal=True, backend=backend)
        try:
            s.atom_new("var", "orphan")
            s.settle(COOL)
            return s.stats()
        finally:
            getattr(s, "close", lambda: None)()

    def _run_retain(self, backend):
        s = open_store(thermal=True, backend=backend)
        try:
            root = s.bubble_new("root")
            s.set_root(root)
            a = s.atom_new("var", "keep")
            root.bind("keep", a)
            s.settle(COOL)
            st = s.stats()
            st["_has"] = s.has_atom(_aid(a))
            st["_dead"] = a.is_dead()
            return st
        finally:
            getattr(s, "close", lambda: None)()

    def test_orphan_stats_agree(self):
        py = self._run_orphan("python")
        nt = self._run_orphan("native")
        self.assertEqual(py["reaped"], nt["reaped"])
        self.assertEqual(py["total"], nt["total"])
        self.assertEqual(py["alive"], nt["alive"])

    def test_retain_stats_agree(self):
        py = self._run_retain("python")
        nt = self._run_retain("native")
        self.assertTrue(py["_has"] and nt["_has"])
        self.assertTrue(py["_dead"] and nt["_dead"])
        self.assertEqual(py["retained_tomb"], nt["retained_tomb"])
        self.assertEqual(py["reaped"], nt["reaped"])


class TestBackendSwitch(unittest.TestCase):
    def test_backend_info(self):
        info = backend_info()
        self.assertIn(info["backend"], ("python", "native", "both"))
        self.assertIn("native_available", info)

    def test_open_store_python(self):
        s = open_store(backend="python")
        a = s.atom_new("t", "e")
        self.assertTrue(s.has_atom(_aid(a)))

    def test_open_store_native_or_skip(self):
        if not native_available():
            self.skipTest("no native")
        s = open_store(backend="native")
        try:
            a = s.atom_new("t", "e")
            self.assertTrue(s.has_atom(_aid(a)))
        finally:
            s.close()

    def test_env_switch(self):
        old = os.environ.get("KARMAZYN_SUBSTRATE")
        try:
            os.environ["KARMAZYN_SUBSTRATE"] = "python"
            self.assertEqual(substrate_backend(), "python")
            if native_available():
                os.environ["KARMAZYN_SUBSTRATE"] = "native"
                self.assertEqual(substrate_backend(), "native")
        finally:
            if old is None:
                os.environ.pop("KARMAZYN_SUBSTRATE", None)
            else:
                os.environ["KARMAZYN_SUBSTRATE"] = old


def main():
    # default for this module: both (when no env set)
    if "KARMAZYN_SUBSTRATE" not in os.environ and "--substrate" not in sys.argv:
        os.environ["KARMAZYN_SUBSTRATE"] = "both"
    apply_cli_substrate_flags()
    info = backend_info()
    print("compat backends:", info)
    unittest.main(verbosity=2, argv=[sys.argv[0]] + [
        a for a in sys.argv[1:]
        if a not in ("--native", "--python", "--substrate")
        and not (len(sys.argv) > sys.argv.index(a) and a == sys.argv[sys.argv.index(a)] and False)
    ] if False else _unittest_argv())


def _unittest_argv():
    """Strip our flags so unittest does not see them as test names."""
    out = [sys.argv[0]]
    skip_next = False
    for i, a in enumerate(sys.argv[1:], 1):
        if skip_next:
            skip_next = False
            continue
        if a in ("--native", "--python"):
            continue
        if a == "--substrate":
            skip_next = True
            continue
        out.append(a)
    return out


if __name__ == "__main__":
    if "KARMAZYN_SUBSTRATE" not in os.environ:
        os.environ.setdefault("KARMAZYN_SUBSTRATE", "both")
    apply_cli_substrate_flags()
    print("compat:", backend_info())
    unittest.main(verbosity=2, argv=_unittest_argv())
