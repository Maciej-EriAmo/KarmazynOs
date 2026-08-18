#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""karmazyn_qubit — proste kubity w KarmazynOS.

Minister, nie król. Amplitudy żyją tutaj, nie w Store.
To nie jest Qiskit / Cirq / IBM — własna, cienka warstwa:
  Reg(n) · H X Y Z S T · CNOT SWAP · pomiar · entropia podukładu.

Limit: n ≤ 8 (256 amplitud). Na więcej trzeba osobnego backendu.

    from karmazyn_qubit import Reg
    r = Reg(2)
    r.h(0).cnot(0, 1)   # para Bella
    print(r.probs())
    print(r.measure_all())
"""
from __future__ import annotations

import cmath
import math
import random
from typing import Iterable, List, Optional, Sequence, Tuple

N_MAX = 8
_SQRT2 = math.sqrt(2.0)

I2 = ((1 + 0j, 0j), (0j, 1 + 0j))
X = ((0j, 1 + 0j), (1 + 0j, 0j))
Y = ((0j, -1j), (1j, 0j))
Z = ((1 + 0j, 0j), (0j, -1 + 0j))
H = (
    (1 / _SQRT2 + 0j, 1 / _SQRT2 + 0j),
    (1 / _SQRT2 + 0j, -1 / _SQRT2 + 0j),
)
S = ((1 + 0j, 0j), (0j, 1j))
Tgate = ((1 + 0j, 0j), (0j, cmath.exp(1j * math.pi / 4)))


def _norm2(z: complex) -> float:
    return z.real * z.real + z.imag * z.imag


def _normalize(amp: List[complex]) -> List[complex]:
    s = math.sqrt(sum(_norm2(z) for z in amp)) or 1.0
    return [z / s for z in amp]


class Reg:
    """Rejestr n kubitów. Wire 0 = najmniej znaczący bit stanu."""

    def __init__(self, n: int = 1, *, rng: Optional[random.Random] = None):
        if n < 1 or n > N_MAX:
            raise ValueError(f"n w 1..{N_MAX}, jest {n}")
        self.n = int(n)
        self.amp: List[complex] = [0j] * (1 << self.n)
        self.amp[0] = 1 + 0j
        self.rng = rng or random.Random()

    def reset(self) -> "Reg":
        self.amp = [0j] * (1 << self.n)
        self.amp[0] = 1 + 0j
        return self

    def copy(self) -> "Reg":
        o = Reg(self.n, rng=self.rng)
        o.amp = list(self.amp)
        return o

    def _apply1(self, wire: int, u) -> None:
        if not (0 <= wire < self.n):
            raise IndexError(wire)
        bit = 1 << wire
        out = [0j] * len(self.amp)
        for i in range(len(self.amp)):
            if i & bit:
                continue
            j = i | bit
            a0, a1 = self.amp[i], self.amp[j]
            out[i] = u[0][0] * a0 + u[0][1] * a1
            out[j] = u[1][0] * a0 + u[1][1] * a1
        self.amp = out

    def h(self, w: int = 0) -> "Reg":
        self._apply1(w, H)
        return self

    def x(self, w: int = 0) -> "Reg":
        self._apply1(w, X)
        return self

    def y(self, w: int = 0) -> "Reg":
        self._apply1(w, Y)
        return self

    def z(self, w: int = 0) -> "Reg":
        self._apply1(w, Z)
        return self

    def s(self, w: int = 0) -> "Reg":
        self._apply1(w, S)
        return self

    def t(self, w: int = 0) -> "Reg":
        self._apply1(w, Tgate)
        return self

    def phase(self, w: int, theta: float) -> "Reg":
        u = ((1 + 0j, 0j), (0j, cmath.exp(1j * theta)))
        self._apply1(w, u)
        return self

    def cnot(self, control: int, target: int) -> "Reg":
        if control == target:
            raise ValueError("CNOT: control == target")
        if not (0 <= control < self.n and 0 <= target < self.n):
            raise IndexError((control, target))
        out = [0j] * len(self.amp)
        cbit, tbit = 1 << control, 1 << target
        for i, a in enumerate(self.amp):
            j = i ^ tbit if (i & cbit) else i
            out[j] += a
        self.amp = out
        return self

    def swap(self, a: int, b: int) -> "Reg":
        if a == b:
            return self
        return self.cnot(a, b).cnot(b, a).cnot(a, b)

    def probs(self) -> List[float]:
        return [_norm2(z) for z in self.amp]

    def prob(self, wire: int, bit: int = 1) -> float:
        mask, want = 1 << wire, (1 << wire) if bit else 0
        return sum(_norm2(self.amp[i]) for i in range(len(self.amp)) if (i & mask) == want)

    def measure(self, wire: int) -> int:
        p1 = self.prob(wire, 1)
        bit = 1 if self.rng.random() < p1 else 0
        mask, keep = 1 << wire, (1 << wire) if bit else 0
        for i in range(len(self.amp)):
            if (i & mask) != keep:
                self.amp[i] = 0j
        self.amp = _normalize(self.amp)
        return bit

    def measure_all(self) -> int:
        ps = self.probs()
        x = self.rng.random()
        acc = 0.0
        hit = len(ps) - 1
        for i, p in enumerate(ps):
            acc += p
            if x <= acc:
                hit = i
                break
        self.amp = [0j] * len(self.amp)
        self.amp[hit] = 1 + 0j
        return hit

    def bloch(self) -> Tuple[float, float, float]:
        """<X>, <Y>, <Z> — tylko n=1."""
        if self.n != 1:
            raise ValueError("bloch tylko dla 1 kubitu")
        a, b = self.amp[0], self.amp[1]
        x = 2 * (a.conjugate() * b).real
        y = 2 * (a.conjugate() * b).imag
        z = _norm2(a) - _norm2(b)
        return (x, y, z)

    def entropy(self, wires: Sequence[int]) -> float:
        """Entropia von Neumanna podukładu (dokładny ślad, n≤8)."""
        ws = tuple(sorted(set(int(w) for w in wires)))
        if not ws or any(w < 0 or w >= self.n for w in ws):
            raise IndexError(ws)
        k = len(ws)
        dim_a = 1 << k
        rho = [[0j] * dim_a for _ in range(dim_a)]
        others = [w for w in range(self.n) if w not in ws]
        for i, ai in enumerate(self.amp):
            if ai == 0:
                continue
            ia = 0
            for t, w in enumerate(ws):
                if (i >> w) & 1:
                    ia |= 1 << t
            rest = 0
            for t, w in enumerate(others):
                if (i >> w) & 1:
                    rest |= 1 << t
            for j, aj in enumerate(self.amp):
                if aj == 0:
                    continue
                rest_j = 0
                for t, w in enumerate(others):
                    if (j >> w) & 1:
                        rest_j |= 1 << t
                if rest_j != rest:
                    continue
                ja = 0
                for t, w in enumerate(ws):
                    if (j >> w) & 1:
                        ja |= 1 << t
                rho[ia][ja] += ai * aj.conjugate()
        return _vn_from_rho(rho)

    def ket_str(self, eps: float = 1e-9) -> str:
        parts = []
        for i, a in enumerate(self.amp):
            if _norm2(a) < eps:
                continue
            bits = format(i, f"0{self.n}b")
            parts.append(f"({a.real:+.3f}{a.imag:+.3f}j)|{bits}>")
        return " + ".join(parts) or "0"

    def __repr__(self) -> str:
        return f"Reg({self.n}) {self.ket_str()}"


def _vn_from_rho(rho: List[List[complex]]) -> float:
    # hermitowska, ślad 1 — wartości własne przez numpy jeśli jest, inaczej 2×2
    n = len(rho)
    if n == 1:
        lam = rho[0][0].real
        return 0.0 if lam <= 1e-15 else -lam * math.log(lam)
    if n == 2:
        a, d = rho[0][0].real, rho[1][1].real
        b = rho[0][1]
        tr, det = a + d, a * d - (b.real ** 2 + b.imag ** 2)
        disc = max(0.0, tr * tr - 4.0 * det)
        s = math.sqrt(disc)
        return _vn_lams(((tr + s) / 2.0, (tr - s) / 2.0))
    try:
        import numpy as np

        w = np.linalg.eigvalsh(np.array(rho, dtype=complex))
        return _vn_lams(float(x) for x in w)
    except Exception:
        # ślad potęgi — słabe przybliżenie; lepiej wymagać numpy dla n>2
        raise RuntimeError("entropia podukładu >1 kubita wymaga numpy")


def _vn_lams(lams: Iterable[float]) -> float:
    acc = 0.0
    for lam in lams:
        if lam > 1e-15:
            acc -= lam * math.log(lam)
    return acc


def ket0() -> Reg:
    return Reg(1)


def ket1() -> Reg:
    return Reg(1).x(0)


def plus() -> Reg:
    return Reg(1).h(0)


def bell() -> Reg:
    return Reg(2).h(0).cnot(0, 1)


def demo() -> None:
    print("karmazyn_qubit — minister amplitud")
    r = bell()
    print("Bell:", r.ket_str())
    print("P:", [round(p, 4) for p in r.probs()])
    print("S(q0):", round(r.entropy((0,)), 6), "  (ln2=", round(math.log(2), 6), ")")
    m = r.copy().measure_all()
    print("pomiar:", format(m, "02b"))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="KarmazynOS kubity")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    if args.demo:
        demo()
    else:
        demo()
