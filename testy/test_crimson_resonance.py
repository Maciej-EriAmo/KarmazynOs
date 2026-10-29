# -*- coding: utf-8 -*-
"""Rezonans obcego węzła: ten sam _p2s otwiera crimson_handshake, inny milczy.

Próg zostaje 0.8. Test woła jądro z archiwum/karmazyn.py bez gniazda
i bez known_nodes.json. Macierz phi_space zostaje słownikiem (lambd 0.1).
"""
from __future__ import annotations

import importlib.util
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCH = ROOT / "archiwum"
K = b"K" * 32


def _load_kernel():
    arch = str(ARCH)
    sys.path.insert(0, arch)
    try:
        name = "karmazyn_arch_kernel"
        spec = importlib.util.spec_from_file_location(name, ARCH / "karmazyn.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("brak archiwum/karmazyn.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        while arch in sys.path:
            sys.path.remove(arch)


def _node(kernel, blob: bytes):
    real = os.urandom

    def fake(n: int) -> bytes:
        if n == 32:
            return blob
        return real(n)

    os.urandom = fake
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            return kernel.KarmazynOS()
    finally:
        os.urandom = real


def _blinded(node, tag: str) -> bytes:
    dim = 128
    vec = node.get_phi2_vector(dim)
    blind = node._get_blinding(K, tag, dim)
    return (vec + blind).tobytes()


class CrimsonResonanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = _load_kernel()

    def test_threshold_stays_0_8(self):
        src = (ARCH / "karmazyn.py").read_text(encoding="utf-8")
        self.assertIn("if rez >= 0.8:", src)

    def test_same_p2s_opens_channel(self):
        blob = b"\x11" * 32
        a = _node(self.kernel, blob)
        b = _node(self.kernel, blob)
        self.assertEqual(a.phi._p2s, b.phi._p2s)
        ok_a, confirm = a.crimson_handshake(
            _blinded(b, "blind-B"), True, K, b.phi.phi2_bytes().hex()
        )
        ok_b, _ = b.crimson_handshake(
            _blinded(a, "blind-A"), False, K, a.phi.phi2_bytes().hex()
        )
        self.assertTrue(ok_a)
        self.assertTrue(ok_b)
        self.assertIsInstance(confirm, bytes)
        self.assertGreater(len(confirm), 0)
        self.assertEqual(a.crimson_key, b.crimson_key)
        self.assertEqual(len(a.crimson_key), 32)

    def test_foreign_p2s_stays_silent(self):
        a = _node(self.kernel, b"\x11" * 32)
        b = _node(self.kernel, b"\x22" * 32)
        self.assertNotEqual(a.phi._p2s, b.phi._p2s)
        dim = 128
        va = a.get_phi2_vector(dim)
        vb = b.get_phi2_vector(dim)
        rez = float((va * vb).sum())
        self.assertLess(rez, 0.8)
        ok, confirm = a.crimson_handshake(
            _blinded(b, "blind-B"), True, K, b.phi.phi2_bytes().hex()
        )
        self.assertFalse(ok)
        self.assertIsNone(confirm)
        self.assertIsNone(a.crimson_key)


class PhiMatrixBoundaryTests(unittest.TestCase):
    def test_dictionary_decay_stays_phi_space_law(self):
        mod = sys.modules.get("hss_karmazyn_matrix")
        if mod is None:
            _load_kernel()
            mod = sys.modules["hss_karmazyn_matrix"]
        matrix = mod.HSSKarmazynMatrix(lambd=0.1)
        matrix.add_atom_vector("a", vector=[0.0] * matrix.dim, init_T=1.0)
        matrix.step()
        atom = matrix.get_atom("a")
        self.assertIsNotNone(atom)
        self.assertAlmostEqual(atom["T"], 0.9)
        self.assertFalse(hasattr(matrix, "has_atom"))
        self.assertFalse(hasattr(matrix, "create_atom"))
        self.assertFalse(hasattr(matrix, "tick"))
        src = (ARCH / "hss_karmazyn_matrix.py").read_text(encoding="utf-8")
        self.assertIn("1.0 - self.lambd", src)
        self.assertIn("lambd: float = 0.1", src)


if __name__ == "__main__":
    unittest.main()
