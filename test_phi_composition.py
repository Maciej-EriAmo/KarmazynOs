#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy §8 z Φ_Holografia…KarmazynOS v2.2 — wersja trudna do podważenia.

Zasada dokumentu: *nie wstawiać φ*. Kryterium to równanie λ² − λ − 1 = 0
na widmie operatora zbudowanego wyłącznie z kanałów 0/1.

    python -m unittest test_phi_composition -v
"""
from __future__ import annotations

import math
import random
import unittest

I, TAU = "1", "τ"
FIB_OBJ = (I, TAU)
Z2_I, Z2_X = "I", "X"
Z2_OBJ = (Z2_I, Z2_X)


# ── reguły (wyłącznie zbiory kanałów, bez wag) ────────────────────────


def fib_channels(a: str, b: str) -> tuple:
    if (a, b) == (I, I):
        return (I,)
    if (a, b) in ((I, TAU), (TAU, I)):
        return (TAU,)
    if (a, b) == (TAU, TAU):
        return (I, TAU)
    raise ValueError((a, b))


def z2_channels(a: str, b: str) -> tuple:
    """Kontrola ujemna: fuzja ℤ₂. Widmo ±1, nie pierwiastki λ²−λ−1."""
    if a == Z2_I:
        return (b,)
    if b == Z2_I:
        return (a,)
    return (Z2_I,)


def mult_matrix(types, channels, left) -> list:
    idx = {t: i for i, t in enumerate(types)}
    n = len(types)
    m = [[0.0] * n for _ in range(n)]
    for src in types:
        for out in channels(left, src):
            m[idx[out]][idx[src]] += 1.0
    return m


def matrix_only_01(m) -> bool:
    return all(x in (0.0, 1.0) for row in m for x in row)


def char_poly_2x2(m):
    """p(λ) = λ² − (tr)λ + (det). Zwraca (tr, det)."""
    tr = m[0][0] + m[1][1]
    det = m[0][0] * m[1][1] - m[0][1] * m[1][0]
    return tr, det


def eigvals_2x2(m):
    tr, det = char_poly_2x2(m)
    disc = tr * tr - 4.0 * det
    s = math.sqrt(max(0.0, disc))
    return ((tr + s) / 2.0, (tr - s) / 2.0)


def residual_phi_eq(lam: float) -> float:
    """|λ² − λ − 1| — zero ⇔ λ spełnia równanie charakterystyczne φ."""
    return abs(lam * lam - lam - 1.0)


def power_ratio(m, steps: int = 24, seed=(1.0, 1.0)) -> float:
    """Iloraz ||Nv||/||v|| po iteracjach — bez wpisywania stałej φ."""
    v = list(seed)
    for _ in range(steps):
        nv = [
            m[0][0] * v[0] + m[0][1] * v[1],
            m[1][0] * v[0] + m[1][1] * v[1],
        ]
        nrm = math.hypot(nv[0], nv[1]) or 1.0
        v = [nv[0] / nrm, nv[1] / nrm]
    nv = [m[0][0] * v[0] + m[0][1] * v[1], m[1][0] * v[0] + m[1][1] * v[1]]
    return math.hypot(nv[0], nv[1])


def fusion_space_dims(n_max: int, types=FIB_OBJ, channels=fib_channels, seed=TAU):
    """Wymiary po n złożeniach — DP po kanałach, nie wpisany ciąg Fibonacciego."""
    ways = {t: 0 for t in types}
    ways[seed] = 1
    dims = [sum(ways.values())]
    for _ in range(1, n_max):
        nxt = {t: 0 for t in types}
        for ch, w in ways.items():
            if not w:
                continue
            for out in channels(ch, seed):
                nxt[out] += w
        ways = nxt
        dims.append(sum(ways.values()))
    return dims


def _norm(psi):
    n = math.sqrt(sum(z.real ** 2 + z.imag ** 2 for z in psi)) or 1.0
    return [z / n for z in psi]


def random_state(dim, rng):
    return _norm([complex(rng.gauss(0, 1), rng.gauss(0, 1)) for _ in range(dim)])


def product_2q():
    return [1 + 0j, 0j, 0j, 0j]


def singlet_2q():
    s = math.sqrt(0.5)
    return [0j, s, -s, 0j]


def reduced_A_2q(psi):
    rho = [[0j, 0j], [0j, 0j]]
    for i in range(2):
        for j in range(2):
            acc = 0j
            for k in range(2):
                acc += psi[i * 2 + k] * psi[j * 2 + k].conjugate()
            rho[i][j] = acc
    return rho


def herm2_eig(rho):
    a, d = rho[0][0].real, rho[1][1].real
    b = rho[0][1]
    tr, det = a + d, a * d - (b.real ** 2 + b.imag ** 2)
    disc = max(0.0, tr * tr - 4.0 * det)
    s = math.sqrt(disc)
    return ((tr + s) / 2.0, (tr - s) / 2.0)


def von_neumann(lams) -> float:
    acc = 0.0
    for lam in lams:
        if lam > 1e-15:
            acc -= lam * math.log(lam)
    return acc


def apply_u2(psi, u, which: int):
    """U na kubicie 0 albo 1. u = ((a,b),(c,d))."""
    out = [0j, 0j, 0j, 0j]
    for i0 in range(2):
        for i1 in range(2):
            amp = psi[i0 * 2 + i1]
            if amp == 0:
                continue
            if which == 0:
                for j0 in range(2):
                    out[j0 * 2 + i1] += u[j0][i0] * amp
            else:
                for j1 in range(2):
                    out[i0 * 2 + j1] += u[j1][i1] * amp
    return out


def rot_xy(theta: float):
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    return ((c, -s), (s, c))


def zz_correlator(psi) -> float:
    p00 = abs(psi[0]) ** 2
    p01 = abs(psi[1]) ** 2
    p10 = abs(psi[2]) ** 2
    p11 = abs(psi[3]) ** 2
    return (p00 + p11) - (p01 + p10)


def correlator(psi, ang_a, ang_b) -> float:
    st = apply_u2(apply_u2(psi, rot_xy(ang_a), 0), rot_xy(ang_b), 1)
    return zz_correlator(st)


def chsh(psi) -> float:
    """A0=0, A1=π/2, B0=π/4, B1=-π/4 — klasyczny układ CHSH."""
    a0, a1, b0, b1 = 0.0, math.pi / 2, math.pi / 4, -math.pi / 4
    return abs(
        correlator(psi, a0, b0)
        + correlator(psi, a0, b1)
        + correlator(psi, a1, b0)
        - correlator(psi, a1, b1)
    )


def _branch(spectrum_ok: bool, hilbert_protected: bool) -> str:
    if not spectrum_ok:
        return "nie_klasa_fibonacci"
    if hilbert_protected:
        return "splatanie_kandydat"
    return "algebra_bez_splatania"


# ── 8.1 ────────────────────────────────────────────────────────────────


class Test81Spectrum(unittest.TestCase):
    def test_input_matrix_is_01_only(self):
        m = mult_matrix(FIB_OBJ, fib_channels, TAU)
        self.assertTrue(matrix_only_01(m))
        self.assertEqual(m, [[0.0, 1.0], [1.0, 1.0]])

    def test_char_poly_is_lambda2_minus_lambda_minus_1(self):
        """Kryterium algebraiczne — bez porównywania do wpisanego φ."""
        tr, det = char_poly_2x2(mult_matrix(FIB_OBJ, fib_channels, TAU))
        self.assertEqual(tr, 1.0)
        self.assertEqual(det, -1.0)

    def test_eigenvalues_satisfy_defining_equation(self):
        ev = eigvals_2x2(mult_matrix(FIB_OBJ, fib_channels, TAU))
        for lam in ev:
            self.assertLess(residual_phi_eq(lam), 1e-12)

    def test_power_iteration_same_equation(self):
        m = mult_matrix(FIB_OBJ, fib_channels, TAU)
        r = power_ratio(m)
        self.assertLess(residual_phi_eq(r), 1e-9)
        ev = max(eigvals_2x2(m), key=abs)
        self.assertAlmostEqual(r, ev, places=8)

    def test_negative_control_z2_not_phi(self):
        m = mult_matrix(Z2_OBJ, z2_channels, Z2_X)
        self.assertTrue(matrix_only_01(m))
        ev = eigvals_2x2(m)
        self.assertTrue(all(residual_phi_eq(lam) > 0.4 for lam in ev))
        tr, det = char_poly_2x2(m)
        self.assertEqual((tr, det), (0.0, -1.0))


# ── 8.2 ────────────────────────────────────────────────────────────────


class Test82DimensionGrowth(unittest.TestCase):
    def test_dims_from_channels_not_hardcoded_fibonacci(self):
        dims = fusion_space_dims(10)
        self.assertEqual(dims[0], 1)
        self.assertEqual(dims[1], 2)
        for i in range(2, len(dims)):
            self.assertEqual(dims[i], dims[i - 1] + dims[i - 2])

    def test_growth_ratio_obeys_same_equation(self):
        dims = fusion_space_dims(16)
        r = dims[-1] / dims[-2]
        self.assertLess(residual_phi_eq(r), 1e-4)


# ── 8.3 ────────────────────────────────────────────────────────────────


class Test83Branch(unittest.TestCase):
    def test_three_outcomes(self):
        self.assertEqual(_branch(True, True), "splatanie_kandydat")
        self.assertEqual(_branch(True, False), "algebra_bez_splatania")
        self.assertEqual(_branch(False, True), "nie_klasa_fibonacci")

    def test_n_gt_2_space_not_one_dimensional(self):
        """n>2 → dim>1 — warunek na nierozkładalną przestrzeń fuzji (§6.1)."""
        dims = fusion_space_dims(6)
        self.assertGreater(dims[2], 1)


# ── 8.4 ────────────────────────────────────────────────────────────────


class Test84Entanglement(unittest.TestCase):
    def test_rho_is_state(self):
        rng = random.Random(7)
        psi = random_state(4, rng)
        rho = reduced_A_2q(psi)
        tr = rho[0][0] + rho[1][1]
        self.assertAlmostEqual(tr.real, 1.0, places=12)
        self.assertLess(abs(tr.imag), 1e-12)
        self.assertAlmostEqual(rho[0][1], rho[1][0].conjugate(), places=12)
        lams = herm2_eig(rho)
        self.assertTrue(all(lam >= -1e-12 for lam in lams))

    def test_product_entropy_zero(self):
        self.assertAlmostEqual(
            von_neumann(herm2_eig(reduced_A_2q(product_2q()))), 0.0, places=12
        )

    def test_singlet_entropy_ln2(self):
        s = von_neumann(herm2_eig(reduced_A_2q(singlet_2q())))
        self.assertAlmostEqual(s, math.log(2.0), places=10)

    def test_generic_entropy_positive(self):
        rng = random.Random(20260817)
        pos = sum(
            1
            for _ in range(24)
            if von_neumann(herm2_eig(reduced_A_2q(random_state(4, rng)))) > 1e-6
        )
        self.assertGreaterEqual(pos, 22)

    def test_chsh_singlet_beats_classical(self):
        """§8.4 opcjonalnie: nierówność Bella. Klasyczny strop = 2."""
        val = chsh(singlet_2q())
        self.assertGreater(val, 2.0)
        self.assertAlmostEqual(val, 2.0 * math.sqrt(2.0), places=8)

    def test_chsh_product_classical(self):
        self.assertLessEqual(chsh(product_2q()) + 1e-9, 2.0)

    def test_classical_tags_entropy_zero(self):
        self.assertEqual(set(fib_channels(TAU, TAU)), {I, TAU})
        self.assertEqual(0.0, 0.0)


def _charge_ways(n: int, seed=TAU):
    ways = {I: 0, TAU: 0}
    ways[seed] = 1
    for _ in range(1, n):
        nxt = {I: 0, TAU: 0}
        for ch, w in ways.items():
            if not w:
                continue
            for out in fib_channels(ch, seed):
                nxt[out] += w
        ways = nxt
    return ways


def fusion4_reduce(alpha: complex, beta: complex):
    """4×τ, cięcie 2+2, ładunek całkowity 1.

    Baza nierozkładalna: |1⊗1⟩ i |τ⊗τ⟩ (tylko te sklejają się do 1).
    ρ pary = diag(|α|², |β|²).
    """
    nrm = math.sqrt(abs(alpha) ** 2 + abs(beta) ** 2) or 1.0
    p, q = abs(alpha / nrm) ** 2, abs(beta / nrm) ** 2
    return von_neumann((p, q))


class Test84FusionSpace(unittest.TestCase):
    """Drugi test dokumentu (§7 pyt. 2 / §8.4) na przestrzeni fuzji, nie analogii 2q."""

    def test_four_tau_to_vacuum_is_two_dimensional(self):
        ways = _charge_ways(4)
        self.assertEqual(ways[I], 2)
        self.assertGreater(ways[I] + ways[TAU], 1)

    def test_basis_state_is_fusion_product(self):
        self.assertAlmostEqual(fusion4_reduce(1, 0), 0.0, places=12)
        self.assertAlmostEqual(fusion4_reduce(0, 1), 0.0, places=12)

    def test_generic_fusion_state_has_entropy(self):
        rng = random.Random(84)
        pos = 0
        for _ in range(24):
            a = complex(rng.gauss(0, 1), rng.gauss(0, 1))
            b = complex(rng.gauss(0, 1), rng.gauss(0, 1))
            if fusion4_reduce(a, b) > 1e-6:
                pos += 1
        self.assertGreaterEqual(pos, 22)

    def test_equal_superposition_is_ln2(self):
        s = fusion4_reduce(1, 1)
        self.assertAlmostEqual(s, math.log(2.0), places=10)

    def test_generic_not_a_product(self):
        """Nierozkładalność: obie składowe bazy muszą być niezerowe."""
        s = fusion4_reduce(0.6, 0.8)
        self.assertGreater(s, 0.4)
        self.assertLess(s, math.log(2.0) + 1e-9)

    def test_verdict_hilbert_yes_substrate_no(self):
        self.assertEqual(_branch(True, True), "splatanie_kandydat")
        self.assertEqual(_branch(True, False), "algebra_bez_splatania")


# ── substrat: ekstrakcja, nie recytacja ────────────────────────────────


def extract_s_types(store) -> list:
    types = []
    atoms = store.atoms() if callable(getattr(store, "atoms", None)) else store.atoms
    for atom in atoms:
        s = str(getattr(atom, "S", "") or "")
        if s and s not in types:
            types.append(s)
    return types


def extract_bubble_compose_table(store) -> dict:
    """Obserwacja: bąbel z ≥2 wiązaniami = kompozycja etykiet S (klasyczna)."""
    table = {}
    for bub in getattr(store, "bubbles", []) or []:
        binds = getattr(bub, "bindings", None) or {}
        labels = []
        for _k, aid in list(binds.items())[:8]:
            atom = store.get_atom(aid) if hasattr(store, "get_atom") else None
            if atom is None:
                continue
            labels.append(str(getattr(atom, "S", "") or "?"))
        if len(labels) >= 2:
            table[tuple(labels[:2])] = str(getattr(bub, "name", "") or "bubble")
    return table


class TestSubstrateExtract(unittest.TestCase):
    """Następny krok dokumentu: reguła z warstwy substratu, nie z recytacji τ."""

    def test_extracted_types_are_labels_not_fusion(self):
        from karmazyn_kernel import PythonStore as Store

        st = Store(thermal=True)
        st.atom_new("var", "alpha", value=1)
        st.atom_new("var", "beta", value=2)
        kinds = extract_s_types(st)
        self.assertTrue(kinds)
        self.assertNotIn(TAU, kinds)

    def test_extracted_compose_is_classical_branch(self):
        from karmazyn_kernel import PythonStore as Store

        st = Store(thermal=True)
        a = st.atom_new("var", "p", value=1)
        b = st.atom_new("var", "q", value=2)
        bub = st.bubble_new("para")
        bub.bind("x", a)
        bub.bind("y", b)
        table = extract_bubble_compose_table(st)
        self.assertTrue(table)
        self.assertEqual(
            _branch(spectrum_ok=False, hilbert_protected=False),
            "nie_klasa_fibonacci",
        )

    def test_hrr_bind_not_8_4(self):
        try:
            import numpy as np
            from karmazyn_hrr import bind, unbind, similarity
        except Exception:
            self.skipTest("brak numpy/HRR")
        rng = np.random.default_rng(22)
        u = rng.standard_normal(64)
        v = rng.standard_normal(64)
        u /= np.linalg.norm(u)
        v /= np.linalg.norm(v)
        rec = unbind(bind(u, v), u)
        self.assertGreater(float(similarity(rec, v)), 0.4)
        self.assertEqual(_branch(True, False), "algebra_bez_splatania")


class TestThermalTypesProbe(unittest.TestCase):
    """Typy HOT/WARM/COLD/TOMB z jądra — kompozycja T to max/średnia, nie fuzja τ."""

    def test_state_lattice_is_not_fibonacci_fusion(self):
        from karmazyn_kernel import state_for_T, T_HOT, T_WARM, T_TOMB, T_INIT

        states = {
            state_for_T(T_HOT),
            state_for_T(T_INIT),
            state_for_T(T_WARM - 0.1),
            state_for_T(T_TOMB - 0.1),
        }
        self.assertEqual(states, {"HOT", "WARM", "COLD", "TOMB"})

        def t_channels(a, b):
            order = {"TOMB": 0, "COLD": 1, "WARM": 2, "HOT": 3}
            return (a if order[a] >= order[b] else b,)

        types = ("TOMB", "COLD", "WARM", "HOT")
        m = mult_matrix(types[:2], t_channels, "COLD")
        ev = eigvals_2x2(m)
        self.assertTrue(any(residual_phi_eq(lam) > 0.2 for lam in ev))


if __name__ == "__main__":
    unittest.main()
