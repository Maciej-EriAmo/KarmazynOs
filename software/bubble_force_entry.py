#!/usr/bin/env python3
"""
bubble_force_entry.py — doświadczenie: siłowe wejście do bąbla
==============================================================
Świat A: host na tym samym Store (API jądra).
Świat B: gość Lua na projekcji (isolate) vs shared.

  python software/bubble_force_entry.py
  python software/bubble_force_entry.py --json out/bubble_force_report.json
  python software/bubble_force_entry.py --no-lua

Jakość informacji 0–4:
  0 nic/szum · 1 etykieta/id · 2 meta (n, T, state) · 3 częściowa treść · 4 exact GOLDEN
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "kernel"))
sys.path.insert(0, str(ROOT / "software"))

os.environ.setdefault("KARMAZYN_SUBSTRATE", "python")

from karmazyn_kernel import T_HOT, T_INIT, open_store  # noqa: E402

GOLDEN = "GOLDEN_PAYLOAD_v1"
GOLDEN_ID = "sec_vault_1"
GOLDEN_S = "secret:doc"

PUBLIC_NOTE = "hello public"
DECOY_NOTE = "not golden"
ORPHAN_NOTE = "lonely orphan"

# Etykiety „atakującego” — hard mode: nie zna poprawnej nazwy vault
BRUTE_LABELS = (
    "vault",
    "secret",
    "secrets",
    "private",
    "secure",
    "bag",
    "root",
    "main",
    "hidden",
    "gold",
    "treasure",
    "decoy",
    "public",
    "admin",
    "system",
)


@dataclass
class AttackResult:
    world: str  # A | B
    phase: str  # discovery | penetrate
    name: str
    found_label: bool = False
    found_id: bool = False
    quality: int = 0
    exact_golden: bool = False
    dirty: bool = False  # mutował store / zostawił ślad
    detail: str = ""
    elapsed_ms: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _quality_from_payloads(
    *,
    labels: Sequence[str] = (),
    ids: Sequence[str] = (),
    partial_e: Sequence[str] = (),
    exact: bool = False,
    has_count_or_t: bool = False,
) -> int:
    if exact:
        return 4
    if any(GOLDEN in (p or "") for p in partial_e) or any(
        GOLDEN_S in (p or "") for p in partial_e
    ):
        return 3
    if has_count_or_t or ids:
        # id bez treści = co najwyżej 2 jeśli wiemy że to vault atom
        if GOLDEN_ID in ids or any("sec" in str(i) for i in ids):
            return 2
        if has_count_or_t:
            return 2
    if labels or ids:
        return 1
    return 0


def setup_world(store: Any) -> Dict[str, Any]:
    """vault / decoy / public + orphan poza bąblem."""
    vault_id = store.create_atom(GOLDEN_ID, S=GOLDEN_S, E=GOLDEN, T=T_HOT)
    decoy_id = store.create_atom("noise1", S="noise", E=DECOY_NOTE, T=50.0)
    pub_id = store.create_atom("pub1", S="public:note", E=PUBLIC_NOTE, T=T_HOT)
    orphan_id = store.create_atom("orphan1", S="orphan", E=ORPHAN_NOTE, T=20.0)

    store.create_bubble("vault", [vault_id], root=True)
    store.create_bubble("decoy", [decoy_id], root=False)
    store.create_bubble("public", [pub_id], root=True)
    # orphan bez bąbla — kontrola false positive

    return {
        "vault_id": vault_id,
        "decoy_id": decoy_id,
        "pub_id": pub_id,
        "orphan_id": orphan_id,
        "golden": GOLDEN,
        "bubbles": ["vault", "decoy", "public"],
        "store": store.stats() if callable(getattr(store, "stats", None)) else {},
    }


def list_bubble_labels(store: Any) -> List[str]:
    out: List[str] = []
    for b in list(getattr(store, "bubbles", []) or []):
        lab = getattr(b, "label", None) or ""
        if lab:
            out.append(str(lab))
    return out


def bubble_snapshot(store: Any, label: str) -> Optional[Dict[str, Any]]:
    b = store.get_bubble(label)
    if b is None:
        return None
    binds = dict(getattr(b, "bindings", {}) or {})
    atoms_meta: List[Dict[str, Any]] = []
    exact = False
    partial: List[str] = []
    for name, aid in binds.items():
        a = store.get_atom(aid)
        if a is None:
            continue
        e = str(getattr(a, "E", "") or "")
        s = str(getattr(a, "S", "") or "")
        if e == GOLDEN or s == GOLDEN_S:
            exact = True
        partial.append(e)
        partial.append(s)
        atoms_meta.append(
            {
                "bind": str(name),
                "id": str(aid),
                "S": s,
                "E": e[:80],
                "T": float(getattr(a, "T", 0) or 0),
                "state": str(getattr(a, "state", "") or ""),
            }
        )
    return {
        "label": label,
        "n_bindings": len(binds),
        "atoms": atoms_meta,
        "exact_golden": exact,
        "partial": partial,
    }


# ─── Świat A: host ───────────────────────────────────────────────────────────


def attack_a_list_bubbles(store: Any) -> AttackResult:
    t0 = time.perf_counter()
    labels = list_bubble_labels(store)
    found_vault = "vault" in labels
    q = 1 if labels else 0
    if found_vault:
        q = max(q, 1)
    return AttackResult(
        world="A",
        phase="discovery",
        name="list_bubbles",
        found_label=found_vault,
        quality=q,
        exact_golden=False,
        detail=f"labels={labels}",
        elapsed_ms=(time.perf_counter() - t0) * 1000,
        meta={"labels": labels},
    )


def attack_a_brute_labels(store: Any) -> AttackResult:
    t0 = time.perf_counter()
    hits: List[str] = []
    for lab in BRUTE_LABELS:
        if store.get_bubble(lab) is not None:
            hits.append(lab)
    found_vault = "vault" in hits
    return AttackResult(
        world="A",
        phase="discovery",
        name="brute_labels",
        found_label=found_vault,
        quality=1 if hits else 0,
        detail=f"hits={hits}",
        elapsed_ms=(time.perf_counter() - t0) * 1000,
        meta={"hits": hits, "tried": list(BRUTE_LABELS)},
    )


def attack_a_scan_atoms(store: Any) -> AttackResult:
    """Pełny skan Store — nie wymaga etykiety bąbla (root na procesie)."""
    t0 = time.perf_counter()
    exact = False
    ids: List[str] = []
    partial: List[str] = []
    for a in store.atoms():
        e = str(getattr(a, "E", "") or "")
        s = str(getattr(a, "S", "") or "")
        aid = str(getattr(a, "id", "") or "")
        if e == GOLDEN or s == GOLDEN_S or aid == GOLDEN_ID:
            exact = True
            ids.append(aid)
        if GOLDEN in e or GOLDEN_S in s or "secret" in s:
            partial.append(f"{aid}:{s}:{e}")
            if aid not in ids:
                ids.append(aid)
    q = _quality_from_payloads(ids=ids, partial_e=partial, exact=exact)
    return AttackResult(
        world="A",
        phase="penetrate",
        name="full_store_scan",
        found_id=bool(ids),
        quality=q,
        exact_golden=exact,
        detail=f"hits={partial[:5]} exact={exact}",
        elapsed_ms=(time.perf_counter() - t0) * 1000,
        meta={"n_atoms": sum(1 for _ in store.atoms()), "ids": ids},
    )


def attack_a_direct_walk(store: Any, label: str = "vault") -> AttackResult:
    t0 = time.perf_counter()
    snap = bubble_snapshot(store, label)
    if snap is None:
        return AttackResult(
            world="A",
            phase="penetrate",
            name="direct_bind_walk",
            quality=0,
            detail=f"get_bubble({label!r})=None",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )
    exact = bool(snap["exact_golden"])
    q = _quality_from_payloads(
        labels=[label],
        ids=[x["id"] for x in snap["atoms"]],
        partial_e=snap["partial"],
        exact=exact,
        has_count_or_t=snap["n_bindings"] > 0,
    )
    return AttackResult(
        world="A",
        phase="penetrate",
        name="direct_bind_walk",
        found_label=True,
        found_id=bool(snap["atoms"]),
        quality=q,
        exact_golden=exact,
        detail=f"n_bindings={snap['n_bindings']} atoms={len(snap['atoms'])}",
        elapsed_ms=(time.perf_counter() - t0) * 1000,
        meta=snap,
    )


def attack_a_lookup_golden_name(store: Any) -> AttackResult:
    """Czy znamy-binding name=E (import_to_bubble kluczuje po E)."""
    t0 = time.perf_counter()
    b = store.get_bubble("vault")
    if b is None:
        return AttackResult(
            world="A",
            phase="penetrate",
            name="lookup_binding_E",
            quality=0,
            detail="no vault",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )
    atom = b.lookup(GOLDEN)  # grzeje!
    exact = atom is not None and str(getattr(atom, "E", "")) == GOLDEN
    return AttackResult(
        world="A",
        phase="penetrate",
        name="lookup_binding_E",
        found_label=True,
        found_id=atom is not None,
        quality=4 if exact else (2 if atom else 1),
        exact_golden=exact,
        dirty=True,  # heat on read
        detail=f"lookup({GOLDEN!r}) -> {getattr(atom, 'id', None)} T={getattr(atom, 'T', None)}",
        elapsed_ms=(time.perf_counter() - t0) * 1000,
        meta={"heated": True},
    )


def attack_a_without_label_guess(store: Any) -> AttackResult:
    """Hard: nie używamy słowa vault — tylko skan atomów S=secret:*."""
    t0 = time.perf_counter()
    hits: List[Dict[str, Any]] = []
    exact = False
    for a in store.atoms():
        s = str(getattr(a, "S", "") or "")
        e = str(getattr(a, "E", "") or "")
        if s.startswith("secret:") or e == GOLDEN:
            hits.append({"id": a.id, "S": s, "E": e})
            if e == GOLDEN:
                exact = True
    q = 4 if exact else (3 if hits else 0)
    return AttackResult(
        world="A",
        phase="penetrate",
        name="scan_secret_S_prefix",
        found_id=bool(hits),
        quality=q,
        exact_golden=exact,
        detail=f"hits={len(hits)}",
        elapsed_ms=(time.perf_counter() - t0) * 1000,
        meta={"hits": hits},
    )


# ─── Świat B: projekcja + Lua ────────────────────────────────────────────────


def project_public_view(host: Any, guest: Any) -> Dict[str, Any]:
    """Montuj tylko public (+ meta) — vault NIE idzie do gościa."""
    meta_id = guest.create_atom(
        "force:meta",
        S="force:meta",
        E="isolated=1;project=public_only;vault=hidden",
        T=T_HOT,
    )
    guest.create_bubble("public", root=True)
    guest.create_bubble("force_view", root=True)
    n_pub = 0
    hb = host.get_bubble("public")
    if hb is not None:
        for name, aid in dict(hb.bindings).items():
            a = host.get_atom(aid)
            if a is None:
                continue
            gid = guest.create_atom(
                str(a.id),
                S=str(a.S or ""),
                E=str(a.E or ""),
                T=float(a.T or T_INIT),
            )
            guest.import_to_bubble("public", gid)
            guest.import_to_bubble("force_view", gid)
            n_pub += 1
    guest.import_to_bubble("force_view", meta_id)
    return {
        "projected_public": n_pub,
        "guest_stats": guest.stats() if callable(getattr(guest, "stats", None)) else {},
        "host_stats": host.stats() if callable(getattr(host, "stats", None)) else {},
    }


def attack_b_guest_api(guest: Any, *, mode: str) -> List[AttackResult]:
    """Ataki po API hosta, ale na guest Store (symulacja tego, co widzi Lua)."""
    results: List[AttackResult] = []

    t0 = time.perf_counter()
    labels = list_bubble_labels(guest)
    results.append(
        AttackResult(
            world="B",
            phase="discovery",
            name=f"guest_list_bubbles[{mode}]",
            found_label="vault" in labels,
            quality=1 if labels else 0,
            detail=f"labels={labels}",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            meta={"labels": labels, "mode": mode},
        )
    )

    t0 = time.perf_counter()
    snap = bubble_snapshot(guest, "vault")
    if snap is None:
        results.append(
            AttackResult(
                world="B",
                phase="penetrate",
                name=f"guest_walk_vault[{mode}]",
                quality=0,
                detail="vault absent on guest",
                elapsed_ms=(time.perf_counter() - t0) * 1000,
                meta={"mode": mode},
            )
        )
    else:
        exact = snap["exact_golden"]
        results.append(
            AttackResult(
                world="B",
                phase="penetrate",
                name=f"guest_walk_vault[{mode}]",
                found_label=True,
                quality=4 if exact else 2,
                exact_golden=exact,
                detail=f"n={snap['n_bindings']}",
                elapsed_ms=(time.perf_counter() - t0) * 1000,
                meta={**snap, "mode": mode},
            )
        )

    t0 = time.perf_counter()
    exact = False
    partial: List[str] = []
    for a in guest.atoms():
        e = str(getattr(a, "E", "") or "")
        s = str(getattr(a, "S", "") or "")
        if e == GOLDEN or s == GOLDEN_S:
            exact = True
        if "GOLDEN" in e or "secret" in s or e == PUBLIC_NOTE:
            partial.append(f"{a.id}:{s}:{e}")
    q = 4 if exact else (3 if any(GOLDEN in p for p in partial) else (2 if partial else 0))
    # public note only → quality 2 (treść publiczna, nie vault)
    if not exact and any(PUBLIC_NOTE in p for p in partial):
        q = max(q, 2)
        if all(PUBLIC_NOTE in p or "force:meta" in p or "isolated" in p for p in partial):
            q = 2  # tylko projekcja public
    results.append(
        AttackResult(
            world="B",
            phase="penetrate",
            name=f"guest_full_scan[{mode}]",
            quality=q,
            exact_golden=exact,
            detail=f"partial={partial[:6]}",
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            meta={"partial": partial, "mode": mode, "n": sum(1 for _ in guest.atoms())},
        )
    )
    return results


def run_lua_probe(store: Any, *, isolated_note: str) -> Tuple[str, Optional[str]]:
    """Uruchom lua_bin/bubble_probe.lua na danym Store. Zwraca (body, error)."""
    lua_bin = ROOT / "lua_bin"
    if not (lua_bin / "bubble_probe.lua").is_file():
        return "", "brak bubble_probe.lua"
    try:
        sys.path.insert(0, str(ROOT / "LUA"))
        from _paths import ensure_kernel_on_path, ensure_lua_package  # type: ignore

        ensure_kernel_on_path(str(ROOT / "LUA"))
        ensure_lua_package(str(ROOT / "LUA"))
        from karmazyn_host import install_karmazyn_host, run_lua_tool  # type: ignore
        import karmazyn_boot as boot  # type: ignore

        ev = boot.mount_evaluator(store, kind="lua", lua_bin=str(lua_bin))
        install_karmazyn_host(ev, store=store)
        ret = run_lua_tool(ev, "bubble_probe", lua_bin=str(lua_bin))
        body = ev.format_run_result(ret=ret)
        return f"[{isolated_note}]\n{body}", None
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def analyze_lua_body(body: str, *, mode: str) -> AttackResult:
    exact = GOLDEN in body
    found_vault = "vault" in body.lower() and "label=vault" in body.replace(" ", "")
    q = 0
    if exact:
        q = 4
    elif "secret:doc" in body:
        q = 3
    elif found_vault and ("n_bind" in body or "bindings" in body):
        q = 2
    elif found_vault or "public" in body:
        q = 1 if found_vault else (1 if "public" in body else 0)
        if PUBLIC_NOTE in body:
            q = max(q, 2)
    elif PUBLIC_NOTE in body:
        q = 2
    return AttackResult(
        world="B",
        phase="penetrate",
        name=f"lua_probe[{mode}]",
        found_label=found_vault,
        quality=q,
        exact_golden=exact,
        detail=body[:500].replace("\n", " | "),
        meta={"mode": mode, "body_len": len(body)},
    )


# ─── Werdykt ─────────────────────────────────────────────────────────────────


def verdict(results: Sequence[AttackResult]) -> Dict[str, Any]:
    a = [r for r in results if r.world == "A"]
    b_iso = [r for r in results if r.world == "B" and "isolate" in r.name]
    b_shared = [r for r in results if r.world == "B" and "shared" in r.name]

    def best(rs: Sequence[AttackResult]) -> Dict[str, Any]:
        if not rs:
            return {"quality": None, "exact": False, "names": []}
        m = max(rs, key=lambda r: (r.quality, r.exact_golden))
        return {
            "quality": m.quality,
            "exact": any(r.exact_golden for r in rs),
            "best_attack": m.name,
            "max_quality": m.quality,
        }

    ba, bi, bs = best(a), best(b_iso), best(b_shared)
    lines = [
        f"Świat A (host Store): penetracja={'TAK' if ba.get('exact') else 'częściowa/nie'} "
        f"jakość={ba.get('max_quality')} — bąbel to struktura reach/API, nie sejf kryptograficzny.",
        f"Świat B isolate (projekcja public): vault "
        f"{'NIE widoczny / brak GOLDEN' if not bi.get('exact') else 'WYCIEK'} "
        f"jakość_max={bi.get('max_quality')}.",
        f"Świat B shared (ten sam Store): "
        f"{'pełny dostęp do vault' if bs.get('exact') else 'ograniczony'} "
        f"jakość_max={bs.get('max_quality')}.",
        "Wniosek: tajemnica ≠ etykieta bąbla; granica to co host włożył do projekcji / sesji, "
        "plus root na procesie (full_store_scan = jakość 4 bez znajomości etykiety).",
    ]
    return {
        "A": ba,
        "B_isolate": bi,
        "B_shared": bs,
        "summary_pl": lines,
    }


def print_table(results: Sequence[AttackResult]) -> None:
    print()
    print(f"{'world':5} {'phase':10} {'attack':32} {'Q':>2} {'gold':>4} {'ms':>7}  detail")
    print("-" * 100)
    for r in results:
        print(
            f"{r.world:5} {r.phase:10} {r.name:32} {r.quality:2} "
            f"{'Y' if r.exact_golden else '.':>4} {r.elapsed_ms:7.2f}  {r.detail[:48]}"
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Siłowe wejście do bąbla — doświadczenie A+B")
    ap.add_argument(
        "--json",
        default="out/bubble_force_report.json",
        help="ścieżka raportu JSON",
    )
    ap.add_argument("--no-lua", action="store_true", help="pomiń bubble_probe.lua")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    os.environ["KARMAZYN_SUBSTRATE"] = "python"
    host = open_store(thermal=True, backend="python")
    setup = setup_world(host)
    results: List[AttackResult] = []

    # ── A
    results.append(attack_a_list_bubbles(host))
    results.append(attack_a_brute_labels(host))
    results.append(attack_a_direct_walk(host, "vault"))
    results.append(attack_a_lookup_golden_name(host))
    results.append(attack_a_without_label_guess(host))
    results.append(attack_a_scan_atoms(host))

    host_alive_before_b = (host.stats() or {}).get("alive")

    # ── B isolate
    guest = open_store(thermal=True, backend="python")
    proj = project_public_view(host, guest)
    results.extend(attack_b_guest_api(guest, mode="isolate"))

    lua_iso_body = ""
    lua_shared_body = ""
    if not args.no_lua:
        lua_iso_body, err = run_lua_probe(guest, isolated_note="isolate view")
        if err:
            results.append(
                AttackResult(
                    world="B",
                    phase="penetrate",
                    name="lua_probe[isolate]",
                    quality=0,
                    detail=err,
                )
            )
        else:
            results.append(analyze_lua_body(lua_iso_body, mode="isolate"))

        # shared = ten sam host store
        lua_shared_body, err2 = run_lua_probe(host, isolated_note="shared host")
        if err2:
            results.append(
                AttackResult(
                    world="B",
                    phase="penetrate",
                    name="lua_probe[shared]",
                    quality=0,
                    detail=err2,
                )
            )
        else:
            results.append(analyze_lua_body(lua_shared_body, mode="shared"))

    # shared guest API (atakujący dostał referencję do host store)
    results.extend(attack_b_guest_api(host, mode="shared"))

    host_alive_after = (host.stats() or {}).get("alive")
    verd = verdict(results)

    report = {
        "protocol": "bubble-force-entry-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden": GOLDEN,
        "setup": setup,
        "projection": proj,
        "host_alive_before_B": host_alive_before_b,
        "host_alive_after_B": host_alive_after,
        "catalog_stable": host_alive_before_b == host_alive_after,
        "results": [r.as_dict() for r in results],
        "verdict": verd,
        "quality_legend": {
            "0": "nic/szum",
            "1": "etykieta/id",
            "2": "meta (n, T, state) lub treść publiczna",
            "3": "częściowa treść secret",
            "4": "exact GOLDEN",
        },
        "lua_isolate_excerpt": (lua_iso_body or "")[:1200],
        "lua_shared_excerpt": (lua_shared_body or "")[:1200],
    }

    out_path = ROOT / args.json
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if not args.quiet:
        print("=== bubble force entry (A host + B guest) ===")
        print(f"setup bubbles={setup['bubbles']} golden={GOLDEN!r}")
        print(f"projection public atoms={proj.get('projected_public')} guest={proj.get('guest_stats')}")
        print_table(results)
        print()
        print("--- VERDICT ---")
        for line in verd["summary_pl"]:
            print("•", line)
        print(f"\nreport → {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
