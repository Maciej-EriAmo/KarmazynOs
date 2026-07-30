#!/usr/bin/env python3
"""
bench_substrate.py — testy wydajnościowe substratu (Python ref vs Rust)

Użycie:
  python bench_substrate.py
  python bench_substrate.py --scale 3          # 3× więcej operacji
  python bench_substrate.py --backends python,pyo3,ctypes
  python bench_substrate.py --json out.json
  python bench_substrate.py --skip-lua

Mierzy: atom_new, has/get, bind/lookup, tick, GC settle, mixed workload,
        snapshot/restore, opcjonalnie Lua eval na NativeStore/PythonStore.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_REPO = os.path.dirname(os.path.abspath(__file__))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
_NATIVE = os.path.join(_REPO, "native")
if _NATIVE not in sys.path:
    sys.path.insert(0, _NATIVE)


# ── timing ───────────────────────────────────────────────────────────────────


def _median(xs: Sequence[float]) -> float:
    return float(statistics.median(xs)) if xs else float("nan")


def _mean(xs: Sequence[float]) -> float:
    return float(statistics.fmean(xs)) if xs else float("nan")


def bench(
    fn: Callable[[], Any],
    *,
    rounds: int = 5,
    warmup: int = 1,
) -> Tuple[float, List[float]]:
    """Zwraca (median_sec, all_secs)."""
    for _ in range(max(0, warmup)):
        fn()
    times: List[float] = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return _median(times), times


@dataclass
class Row:
    backend: str
    case: str
    n: int
    median_ms: float
    mean_ms: float
    ops_per_s: float
    samples: List[float] = field(default_factory=list)

    def speedup_vs(self, baseline_ops: float) -> Optional[float]:
        if baseline_ops <= 0 or self.ops_per_s <= 0:
            return None
        return self.ops_per_s / baseline_ops


# ── store factories ──────────────────────────────────────────────────────────


def _make_python(thermal: bool = True):
    from karmazyn_substrate import Store

    return Store(thermal=thermal)


def _make_native(thermal: bool = True, bridge: str = "pyo3"):
    # force bridge via env before import path uses it
    prev = os.environ.get("KARMAZYN_NATIVE_BRIDGE")
    if bridge == "pyo3":
        os.environ["KARMAZYN_NATIVE_BRIDGE"] = "pyo3"
    elif bridge == "ctypes":
        os.environ["KARMAZYN_NATIVE_BRIDGE"] = "ctypes"
    try:
        # re-open after env — NativeStore reads env at _open_core time
        from karmazyn_substrate_native import NativeStore, native_available, native_bridge

        if not native_available():
            raise RuntimeError("native unavailable")
        s = NativeStore(thermal=thermal)
        actual = getattr(s, "native_backend", native_bridge())
        if bridge == "ctypes" and actual != "ctypes":
            raise RuntimeError(f"chciano ctypes, jest {actual}")
        if bridge == "pyo3" and actual != "pyo3":
            raise RuntimeError(f"chciano pyo3, jest {actual}")
        return s
    finally:
        if prev is None:
            os.environ.pop("KARMAZYN_NATIVE_BRIDGE", None)
        else:
            os.environ["KARMAZYN_NATIVE_BRIDGE"] = prev


def available_backends() -> List[str]:
    out = ["python"]
    try:
        from karmazyn_substrate_native import native_available, native_bridge

        if not native_available():
            return out
        # probe pyo3
        try:
            s = _make_native(bridge="pyo3")
            if hasattr(s, "close"):
                s.close()
            out.append("pyo3")
        except Exception:
            pass
        try:
            s = _make_native(bridge="ctypes")
            if hasattr(s, "close"):
                s.close()
            out.append("ctypes")
        except Exception:
            pass
    except Exception:
        pass
    return out


def make_store(backend: str, thermal: bool = True):
    if backend == "python":
        return _make_python(thermal=thermal)
    if backend in ("pyo3", "native"):
        return _make_native(thermal=thermal, bridge="pyo3")
    if backend == "ctypes":
        return _make_native(thermal=thermal, bridge="ctypes")
    raise ValueError(backend)


# ── cases ────────────────────────────────────────────────────────────────────


def case_atom_new(store, n: int) -> None:
    for i in range(n):
        store.atom_new("var", f"a{i}", value=i)


def case_has_get(store, n: int) -> None:
    # pre: need atoms — caller prepares; here just operate on 0..n-1
    for i in range(n):
        store.has_atom(i)
        store.get_atom(i)


def case_bind_lookup(store, n: int) -> None:
    root = store.bubble_new("bench_root")
    store.set_root(root)
    atoms = [store.atom_new("var", f"b{i}", value=i) for i in range(n)]
    for i, a in enumerate(atoms):
        root.bind(f"k{i}", a)
    for i in range(n):
        root.lookup(f"k{i}")


def case_tick_hot(store, n: int) -> None:
    """n rooted atoms, 20 ticks (no GC of them)."""
    root = store.bubble_new("hot")
    store.set_root(root)
    for i in range(n):
        a = store.atom_new("var", f"h{i}", value=i)
        root.bind(f"h{i}", a)
    for _ in range(20):
        store.tick()


def case_gc_orphans(store, n: int) -> None:
    """Create n orphans and settle until vacuum (80 ticks)."""
    for i in range(n):
        store.atom_new("var", f"o{i}", value=i)
    store.settle(80)


def case_mixed(store, n: int) -> None:
    """Create n, bind n//2, delete some, tick, stats, snapshot restore."""
    root = store.bubble_new("mix")
    store.set_root(root)
    atoms = []
    for i in range(n):
        a = store.atom_new("var", f"m{i}", value=i)
        atoms.append(a)
        if i % 2 == 0:
            root.bind(f"m{i}", a)
    for i in range(0, n, 5):
        store.has_atom(atoms[i].id)
    store.settle(10)
    st = store.stats()
    _ = st.get("total")
    snap = store.snapshot_atoms()
    temps = {k: getattr(v, "T", 50.0) for k, v in snap.items()}
    # add noise then restore
    store.atom_new("var", "noise", value=-1)
    store.restore_atoms(snap, temps)


def case_lua_eval(store, n: int) -> None:
    lua_root = os.path.join(_REPO, "LUA")
    if lua_root not in sys.path:
        sys.path.insert(0, lua_root)
    from _paths import ensure_kernel_on_path, ensure_lua_package

    ensure_kernel_on_path(lua_root)
    ensure_lua_package(lua_root)
    from karmazyn_lua.lib import mount

    ev = mount(store)
    for i in range(n):
        ev.eval_line(f"return {i} + {i}")


# ── runner ───────────────────────────────────────────────────────────────────


def run_case(
    backend: str,
    name: str,
    n: int,
    setup_thermal: bool,
    body: Callable,
    *,
    rounds: int,
    prepare: Optional[Callable] = None,
    ops: Optional[int] = None,
) -> Row:
    """body(store) runs the measured work. prepare(store) optional pre-work untimed."""

    def once():
        s = make_store(backend, thermal=setup_thermal)
        try:
            if prepare is not None:
                prepare(s)
            body(s)
        finally:
            if hasattr(s, "close"):
                try:
                    s.close()
                except Exception:
                    pass

    med, samples = bench(once, rounds=rounds, warmup=1)
    op_count = ops if ops is not None else n
    ops_s = (op_count / med) if med > 0 else float("inf")
    return Row(
        backend=backend,
        case=name,
        n=n,
        median_ms=med * 1000.0,
        mean_ms=_mean(samples) * 1000.0,
        ops_per_s=ops_s,
        samples=[x * 1000.0 for x in samples],
    )


def scale_n(base: int, scale: float) -> int:
    return max(1, int(base * scale))


def run_all(
    backends: Sequence[str],
    scale: float,
    rounds: int,
    skip_lua: bool,
) -> List[Row]:
    rows: List[Row] = []

    cases = [
        # name, base_n, thermal, body, ops_factor (ops = n * factor or None = n)
        ("atom_new", 20_000, False, case_atom_new, 1.0),
        ("bind_lookup", 5_000, True, case_bind_lookup, 2.0),  # bind+lookup
        ("tick_hot_x20", 2_000, True, case_tick_hot, 20.0),  # 20 ticks × n atoms-ish
        ("gc_orphans_settle80", 5_000, True, case_gc_orphans, 1.0),
        ("mixed_workload", 3_000, True, case_mixed, 1.0),
    ]

    # has_get needs pre-created atoms
    def prep_atoms(n: int):
        def _p(s):
            for i in range(n):
                s.atom_new("var", f"p{i}", value=i)

        return _p

    n_has = scale_n(20_000, scale)
    for be in backends:
        rows.append(
            run_case(
                be,
                "has_get",
                n_has,
                False,
                lambda s, nn=n_has: case_has_get(s, nn),
                rounds=rounds,
                prepare=prep_atoms(n_has),
                ops=n_has * 2,
            )
        )

    for name, base_n, thermal, body, op_f in cases:
        n = scale_n(base_n, scale)
        for be in backends:
            rows.append(
                run_case(
                    be,
                    name,
                    n,
                    thermal,
                    lambda s, b=body, nn=n: b(s, nn),
                    rounds=rounds,
                    ops=int(n * op_f),
                )
            )

    if not skip_lua:
        n_lua = scale_n(500, scale)
        for be in backends:
            try:
                rows.append(
                    run_case(
                        be,
                        "lua_eval",
                        n_lua,
                        True,
                        lambda s, nn=n_lua: case_lua_eval(s, nn),
                        rounds=max(3, rounds - 1),
                        ops=n_lua,
                    )
                )
            except Exception as e:
                print(f"  [skip] lua_eval/{be}: {e}")

    return rows


def print_table(rows: List[Row]) -> None:
    # group by case
    cases = []
    for r in rows:
        if r.case not in cases:
            cases.append(r.case)

    # baseline = python ops if present
    print()
    print(f"{'case':<22} {'backend':<8} {'n':>8} {'med_ms':>10} {'ops/s':>12} {'×python':>8}")
    print("-" * 72)
    for case in cases:
        group = [r for r in rows if r.case == case]
        base = next((r for r in group if r.backend == "python"), None)
        base_ops = base.ops_per_s if base else 0.0
        for r in group:
            sp = r.speedup_vs(base_ops) if base and r.backend != "python" else None
            sp_s = f"{sp:7.2f}×" if sp is not None else ("   1.00×" if r.backend == "python" else "      —")
            print(
                f"{r.case:<22} {r.backend:<8} {r.n:>8} {r.median_ms:>10.2f} "
                f"{r.ops_per_s:>12,.0f} {sp_s}"
            )
        print("-" * 72)


def summarize(rows: List[Row]) -> Dict[str, Any]:
    cases = sorted({r.case for r in rows})
    summary = {"cases": {}, "backends": sorted({r.backend for r in rows})}
    for case in cases:
        group = [r for r in rows if r.case == case]
        base = next((r for r in group if r.backend == "python"), None)
        entry = {}
        for r in group:
            entry[r.backend] = {
                "median_ms": round(r.median_ms, 3),
                "ops_per_s": round(r.ops_per_s, 1),
                "n": r.n,
                "speedup_vs_python": (
                    round(r.speedup_vs(base.ops_per_s), 3)
                    if base and r.backend != "python"
                    else (1.0 if r.backend == "python" else None)
                ),
            }
        summary["cases"][case] = entry
    # geometric-ish average speedup for pyo3 vs python across cases
    speedups = []
    for case in cases:
        g = summary["cases"][case]
        if "python" in g and "pyo3" in g and g["pyo3"]["speedup_vs_python"]:
            speedups.append(g["pyo3"]["speedup_vs_python"])
    if speedups:
        summary["pyo3_avg_speedup_vs_python"] = round(statistics.fmean(speedups), 3)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Benchmark Karmazyn substrate")
    ap.add_argument("--scale", type=float, default=1.0, help="mnożnik rozmiaru (default 1)")
    ap.add_argument("--rounds", type=int, default=5, help="powtórzeń na case")
    ap.add_argument(
        "--backends",
        default="auto",
        help="comma list: python,pyo3,ctypes or auto",
    )
    ap.add_argument("--skip-lua", action="store_true")
    ap.add_argument("--json", dest="json_path", default=None, help="zapisz wynik JSON")
    ap.add_argument("--quick", action="store_true", help="scale=0.25 rounds=3")
    args = ap.parse_args(argv)

    if args.quick:
        args.scale = 0.25
        args.rounds = 3

    if args.backends.strip().lower() == "auto":
        backends = available_backends()
    else:
        backends = [b.strip() for b in args.backends.split(",") if b.strip()]

    print("=" * 72)
    print("  KarmazynOS — benchmark substratu (Python vs Rust)")
    print("=" * 72)
    print(f"  backends: {backends}")
    print(f"  scale={args.scale}  rounds={args.rounds}  skip_lua={args.skip_lua}")

    if "python" not in backends:
        print("  [warn] brak 'python' w backends — brak bazy do speedup")

    t0 = time.perf_counter()
    rows = run_all(backends, args.scale, args.rounds, args.skip_lua)
    elapsed = time.perf_counter() - t0

    print_table(rows)
    summary = summarize(rows)
    if "pyo3_avg_speedup_vs_python" in summary:
        print(f"  średni speedup pyo3 vs python: {summary['pyo3_avg_speedup_vs_python']:.2f}×")
    print(f"  czas całego biegu: {elapsed:.1f}s")

    if args.json_path:
        payload = {
            "summary": summary,
            "rows": [asdict(r) for r in rows],
            "meta": {
                "scale": args.scale,
                "rounds": args.rounds,
                "backends": list(backends),
                "elapsed_s": elapsed,
            },
        }
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"  JSON → {args.json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
