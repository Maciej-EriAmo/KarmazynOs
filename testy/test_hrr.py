#!/usr/bin/env python3
"""
test_hrr.py — unit testy czystych operacji HRR (bind / unbind / bundle)
======================================================================
Maciej Mazur, Warsaw 2026

Czysta matematyka z karmazyn_hrr.py — bez Store/Atom.
Wymaga numpy (jak twarz HRR w kernelu). Bez numpy → skip całego modułu.

Uruchomienie (z roota repo):
    python -m unittest discover -s testy -p "test_hrr.py" -v
    python testy/test_hrr.py
"""

import unittest

import _path  # noqa: F401

try:
    import numpy as np
    from karmazyn_hrr import (
        bind, unbind, bundle, similarity, normalize, random_unit_vector,
    )
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# Mniejszy D niż produkcyjne 2048 — wystarczy do własności, szybsze FFT.
D = 512
# Tolerancja numeryczna FFT / np.real (nie dokładna równość float).
ATOL = 1e-6


@unittest.skipUnless(HAS_NUMPY, "brak numpy — operacje HRR niedostępne")
class TestBind(unittest.TestCase):
    """Splot kołowy: komutatywność, asocjatywność."""

    def setUp(self):
        self.a = random_unit_vector(D, seed=1)
        self.b = random_unit_vector(D, seed=2)
        self.c = random_unit_vector(D, seed=3)

    def test_commutativity(self):
        # bind(a, b) ≈ bind(b, a)  (FFT(a)*FFT(b) = FFT(b)*FFT(a))
        ab = bind(self.a, self.b)
        ba = bind(self.b, self.a)
        self.assertTrue(np.allclose(ab, ba, atol=ATOL))

    def test_associativity(self):
        # bind(bind(a,b), c) ≈ bind(a, bind(b,c))
        left = bind(bind(self.a, self.b), self.c)
        right = bind(self.a, bind(self.b, self.c))
        self.assertTrue(np.allclose(left, right, atol=ATOL))

    def test_shape_preserved(self):
        out = bind(self.a, self.b)
        self.assertEqual(out.shape, (D,))
        self.assertTrue(np.isrealobj(out) or np.allclose(out.imag, 0))


@unittest.skipUnless(HAS_NUMPY, "brak numpy — operacje HRR niedostępne")
class TestUnbind(unittest.TestCase):
    """Korelacja kołowa: round-trip retrieval."""

    def setUp(self):
        self.a = random_unit_vector(D, seed=10)
        self.b = random_unit_vector(D, seed=20)

    def test_roundtrip_retrieval(self):
        # unbind(bind(a,b), a) ≈ b  z sim w okolicy 1/√2 ≈ 0.707 (D skończone)
        s = bind(self.a, self.b)
        r = unbind(s, self.a)
        sim = similarity(r, self.b)
        # Przy D=512 szum jest niski — próg luźniejszy niż średnia teoretyczna.
        self.assertGreater(sim, 0.5, f"retrieval sim={sim:.3f}, oczekiwano >0.5")

    def test_wrong_key_low_similarity(self):
        s = bind(self.a, self.b)
        wrong = random_unit_vector(D, seed=99)
        r = unbind(s, wrong)
        sim = similarity(r, self.b)
        self.assertLess(sim, 0.3, f"zły klucz nie powinien odzyskać b (sim={sim:.3f})")

    def test_mean_retrieval_near_half_sqrt2(self):
        # E[sim] ≈ 1/√2 dla unit vectors — średnia z wielu par (stabilniejsza niż 1 seed).
        sims = []
        for i in range(16):
            a = random_unit_vector(D, seed=100 + i)
            b = random_unit_vector(D, seed=200 + i)
            r = unbind(bind(a, b), a)
            sims.append(similarity(r, b))
        mean = float(np.mean(sims))
        # Okno wokół 0.707 — nie assertEqual, bo skończone D i seed.
        self.assertGreater(mean, 0.55, f"mean sim={mean:.3f}")
        self.assertLess(mean, 0.85, f"mean sim={mean:.3f}")


@unittest.skipUnless(HAS_NUMPY, "brak numpy — operacje HRR niedostępne")
class TestBundle(unittest.TestCase):
    """Superpozycja wektorów."""

    def test_single(self):
        v = random_unit_vector(D, seed=5)
        self.assertTrue(np.allclose(bundle(v), v, atol=ATOL))

    def test_sum_of_two(self):
        a = random_unit_vector(D, seed=6)
        b = random_unit_vector(D, seed=7)
        self.assertTrue(np.allclose(bundle(a, b), a + b, atol=ATOL))

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            bundle()

    def test_unbind_from_bundle_of_bindings(self):
        # Klasyczny HRR: memory = bind(a,x) + bind(b,y); unbind(memory, a) ≈ x
        a = random_unit_vector(D, seed=30)
        b = random_unit_vector(D, seed=31)
        x = random_unit_vector(D, seed=32)
        y = random_unit_vector(D, seed=33)
        mem = bundle(bind(a, x), bind(b, y))
        rx = unbind(mem, a)
        ry = unbind(mem, b)
        self.assertGreater(similarity(rx, x), 0.35)
        self.assertGreater(similarity(ry, y), 0.35)
        # Crosstalk: odzysk x nie powinien wyglądać jak y
        self.assertGreater(similarity(rx, x), similarity(rx, y))


@unittest.skipUnless(HAS_NUMPY, "brak numpy — operacje HRR niedostępne")
class TestSimilarity(unittest.TestCase):
    """Cosine similarity: identyczne, ortogonalne, antyfazowe, zera."""

    def test_identical(self):
        v = random_unit_vector(D, seed=40)
        self.assertAlmostEqual(similarity(v, v), 1.0, places=5)

    def test_orthogonal(self):
        # e0 · e1 = 0 → cosine = 0
        a = np.zeros(D); a[0] = 1.0
        b = np.zeros(D); b[1] = 1.0
        self.assertAlmostEqual(similarity(a, b), 0.0, places=5)

    def test_opposite(self):
        # a i -a → cosine = -1
        v = random_unit_vector(D, seed=42)
        self.assertAlmostEqual(similarity(v, -v), -1.0, places=5)

    def test_scale_invariant(self):
        # cosine nie zależy od długości (o ile obie > 0)
        a = random_unit_vector(D, seed=43)
        b = random_unit_vector(D, seed=44)
        self.assertAlmostEqual(
            similarity(a, b), similarity(3.0 * a, 0.5 * b), places=5
        )

    def test_zero_vector(self):
        z = np.zeros(D)
        v = random_unit_vector(D, seed=41)
        self.assertEqual(similarity(z, v), 0.0)
        self.assertEqual(similarity(v, z), 0.0)
        self.assertEqual(similarity(z, z), 0.0)  # obie normy ~0 → 0.0

    def test_near_zero_norm(self):
        # próg 1e-10 w similarity — wektor poniżej progu jak zero
        tiny = np.full(D, 1e-12)
        v = random_unit_vector(D, seed=45)
        self.assertEqual(similarity(tiny, v), 0.0)

    def test_normalize_unit(self):
        v = np.random.RandomState(42).randn(D)
        n = normalize(v)
        self.assertAlmostEqual(float(np.linalg.norm(n)), 1.0, places=5)


if __name__ == "__main__":
    unittest.main()
