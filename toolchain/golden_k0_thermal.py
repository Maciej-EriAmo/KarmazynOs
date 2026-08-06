#!/usr/bin/env python3
"""TB.3 golden: K0 thermal law formulas vs Rust-aligned thresholds.

Does not invoke rustc on .k0 (kcc does that). This checks the *law table*
shared by thermal.k0 and karmazyn_slab (state_for_t / constants).

  python toolchain/golden_k0_thermal.py
"""
from __future__ import annotations

import math
import sys

T_HOT = 70.0
T_WARM = 30.0
T_TOMB = 2.0
T_INIT = 50.0
T_MAX = 100.0
DECAY = 0.92


def clamp_t(t: float) -> float:
    if t < 0.0:
        return 0.0
    if t > T_MAX:
        return T_MAX
    return t


def state_code(t: float) -> int:
    x = clamp_t(t)
    if x >= T_HOT:
        return 3
    if x >= T_WARM:
        return 2
    if x >= T_TOMB:
        return 1
    return 0


def state_for_t(t: float) -> str:
    x = clamp_t(t)
    if x >= T_HOT:
        return "HOT"
    if x >= T_WARM:
        return "WARM"
    if x >= T_TOMB:
        return "COLD"
    return "TOMB"


CODE_NAME = {3: "HOT", 2: "WARM", 1: "COLD", 0: "TOMB"}

SAMPLES = [
    100.0,
    80.0,
    70.0,
    69.999,
    50.0,
    30.0,
    29.999,
    10.0,
    2.0,
    1.999,
    1.0,
    0.0,
    T_INIT,
    T_HOT,
    T_WARM,
    T_TOMB,
]


def main() -> int:
    fails = 0
    for t in SAMPLES:
        c = state_code(t)
        name = state_for_t(t)
        if CODE_NAME[c] != name:
            print(f"FAIL t={t}: code={c} ({CODE_NAME[c]}) vs state_for_t={name}")
            fails += 1
    t1 = clamp_t(50.0 * DECAY)
    if abs(t1 - 46.0) > 1e-9:
        print(f"FAIL tick 50*0.92={t1}")
        fails += 1
    t = T_INIT
    for _ in range(80):
        t = clamp_t(t * DECAY)
    if t >= T_TOMB:
        print(f"FAIL after 80 ticks still alive t={t}")
        fails += 1
    if fails:
        print(f"GOLDEN_K0_FAIL count={fails}")
        return 1
    print("GOLDEN_K0_OK samples=%d" % len(SAMPLES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
