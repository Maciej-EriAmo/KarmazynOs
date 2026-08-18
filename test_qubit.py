#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy cienkiej warstwy kubitów — nie Store, nie klon Qiskit."""
from __future__ import annotations

import math
import random
import unittest

from karmazyn_qubit import Reg, bell, ket0, ket1, plus


class TestQubitOps(unittest.TestCase):
    def test_x_flips_zero(self):
        r = ket0().x(0)
        self.assertAlmostEqual(abs(r.amp[1]), 1.0, places=12)
        self.assertAlmostEqual(abs(r.amp[0]), 0.0, places=12)

    def test_h_twice_is_i(self):
        r = ket0().h(0).h(0)
        self.assertAlmostEqual(abs(r.amp[0]), 1.0, places=12)

    def test_plus_equal_probs(self):
        r = plus()
        self.assertAlmostEqual(r.probs()[0], 0.5, places=12)
        self.assertAlmostEqual(r.probs()[1], 0.5, places=12)

    def test_z_on_plus_is_minus(self):
        r = plus().z(0)
        self.assertAlmostEqual(r.amp[0].real, 1 / math.sqrt(2), places=10)
        self.assertAlmostEqual(r.amp[1].real, -1 / math.sqrt(2), places=10)

    def test_hh_x_on_two_wires(self):
        r = Reg(2).x(1)
        self.assertAlmostEqual(abs(r.amp[2]), 1.0, places=12)

    def test_cnot_computational(self):
        r = Reg(2).x(0).cnot(0, 1)
        self.assertAlmostEqual(abs(r.amp[3]), 1.0, places=12)

    def test_bell_probs(self):
        r = bell()
        p = r.probs()
        self.assertAlmostEqual(p[0], 0.5, places=12)
        self.assertAlmostEqual(p[3], 0.5, places=12)
        self.assertAlmostEqual(p[1] + p[2], 0.0, places=12)

    def test_bell_entropy_ln2(self):
        r = bell()
        self.assertAlmostEqual(r.entropy((0,)), math.log(2.0), places=10)
        self.assertAlmostEqual(r.entropy((1,)), math.log(2.0), places=10)

    def test_product_entropy_zero(self):
        r = Reg(2).h(0)
        self.assertAlmostEqual(r.entropy((1,)), 0.0, places=12)

    def test_measure_collapses(self):
        r = ket1()
        self.assertEqual(r.measure(0), 1)
        self.assertAlmostEqual(abs(r.amp[1]), 1.0, places=12)

    def test_measure_all_bell_correlated(self):
        rng = random.Random(0)
        hits = {0: 0, 3: 0}
        for _ in range(200):
            r = bell()
            r.rng = rng
            m = r.measure_all()
            hits[m] = hits.get(m, 0) + 1
        self.assertGreater(hits[0], 40)
        self.assertGreater(hits[3], 40)
        self.assertEqual(hits.get(1, 0) + hits.get(2, 0), 0)

    def test_bloch_z(self):
        x, y, z = ket0().bloch()
        self.assertAlmostEqual(z, 1.0, places=12)
        x, y, z = ket1().bloch()
        self.assertAlmostEqual(z, -1.0, places=12)

    def test_swap(self):
        r = Reg(2).x(0).swap(0, 1)
        self.assertAlmostEqual(abs(r.amp[2]), 1.0, places=12)

    def test_n_limit(self):
        with self.assertRaises(ValueError):
            Reg(9)


if __name__ == "__main__":
    unittest.main()
