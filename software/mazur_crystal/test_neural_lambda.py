"""U2 — λ_neural OFF nie rusza toru; ON + ckpt PhiMost działa bez psucia GC."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Testy z włączoną flagą potrzebują PHIMOST_ROOT (katalog PhiMost z checkpointem).
_PHIMOST_ENV = os.environ.get("PHIMOST_ROOT", "").strip()
PHIMOST = Path(_PHIMOST_ENV) if _PHIMOST_ENV else None


def _ckpt():
    if PHIMOST is None:
        return None
    ckpt = PHIMOST / "checkpoints" / "most_dump_recall.pt"
    return ckpt if ckpt.is_file() else None
for p in (
    ROOT,
    ROOT / "archiwum" / "kernel_python",
    ROOT / "software",
    ROOT / "native",
):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

os.environ.setdefault("KARMAZYN_SUBSTRATE", "python")
os.environ["KARMAZYN_MAZUR"] = "1"


class TestNeuralLambda(unittest.TestCase):
    def setUp(self):
        os.environ["PHIMOST_NEURAL_LAMBDA"] = "0"
        if PHIMOST is not None:
            os.environ["PHIMOST_ROOT"] = str(PHIMOST)
        else:
            os.environ.pop("PHIMOST_ROOT", None)

    def tearDown(self):
        os.environ["PHIMOST_NEURAL_LAMBDA"] = "0"

    def _store(self):
        from karmazyn_substrate import Store
        from mazur_crystal import Tracer, attach_lorentz_bridge

        s = attach_lorentz_bridge(Store(thermal=True), mrc=True)
        s.create_atom(
            "ctx", "c", "shared motif text pulse", T=100.0, tracer=Tracer(energy=1.0)
        )
        root = s.bubble_new("root")
        s.set_root(root)
        root.bind("c", s.get_atom("ctx"))
        s.set_context("ctx")
        s.create_atom(
            "hot", "m", "shared motif text memory", T=50.0, tracer=Tracer(energy=1.0)
        )
        s.create_atom(
            "cold", "m", "orthogonal noise", T=50.0, tracer=Tracer(energy=9.0)
        )
        return s

    def test_flag_off_neural_none(self):
        from mazur_crystal.neural_lambda import neural_N, neural_lambda_enabled

        self.assertFalse(neural_lambda_enabled())
        s = self._store()
        self.assertIsNone(neural_N(s.get_atom("hot"), s.get_atom("ctx")))

    def test_flag_on_loads_ckpt_or_skips(self):
        if _ckpt() is None:
            self.skipTest("brak PHIMOST_ROOT z checkpointem — uruchom smoke_checkpoint.py")
        os.environ["PHIMOST_NEURAL_LAMBDA"] = "1"
        # reset mazur_neural autoload state
        sys.path.insert(0, str(PHIMOST))
        import mazur_neural as mn

        mn.reset_encoder()
        from mazur_crystal.neural_lambda import neural_N, neural_lambda_enabled

        self.assertTrue(neural_lambda_enabled())
        s = self._store()
        n = neural_N(s.get_atom("hot"), s.get_atom("ctx"))
        self.assertIsNotNone(n)
        self.assertGreaterEqual(float(n), 0.0)
        self.assertLessEqual(float(n), 1.0)

    def test_relevance_on_does_not_break_find(self):
        if _ckpt() is None:
            self.skipTest("brak PHIMOST_ROOT z checkpointem")
        os.environ["PHIMOST_NEURAL_LAMBDA"] = "1"
        sys.path.insert(0, str(PHIMOST))
        import mazur_neural as mn

        mn.reset_encoder()
        s = self._store()
        hits = s.find_resonating(limit=5)
        ids = [a.id for a in hits]
        self.assertIn("hot", ids)
        # cold może spaść w rankingu — nie wymagamy NotIn przy neural
        r_hot = s.relevance(s.get_atom("hot"))
        r_cold = s.relevance(s.get_atom("cold"))
        self.assertTrue(r_hot == r_hot and r_cold == r_cold)  # finite

    def test_gc_still_works_with_flag_on(self):
        # GC musi działać z flagą także bez PhiMost (N = None)
        os.environ["PHIMOST_NEURAL_LAMBDA"] = "1"
        if PHIMOST is not None:
            sys.path.insert(0, str(PHIMOST))
        try:
            import mazur_neural as mn

            mn.reset_encoder()
        except Exception:
            pass
        from mazur_crystal import Tracer, attach_lorentz_bridge
        from karmazyn_substrate import Store

        s = attach_lorentz_bridge(Store(thermal=True), mrc=False)
        s.create_atom(
            "ctx", "c", "shared motif text", T=100.0, tracer=Tracer(energy=1.0)
        )
        root = s.bubble_new("root")
        s.set_root(root)
        root.bind("c", s.get_atom("ctx"))
        s.set_context("ctx")
        s.create_atom(
            "keep", "m", "shared motif text", T=1.5, tracer=Tracer(energy=1.0)
        )
        s.create_atom("drop", "m", "nope", T=1.5, tracer=Tracer(energy=8.0))
        s.tick()
        self.assertTrue(s.has_atom("keep"))
        self.assertFalse(s.has_atom("drop"))


if __name__ == "__main__":
    raise SystemExit(not unittest.main(verbosity=2))
