# -*- coding: utf-8 -*-
"""Symulacja: I/O × matryca termiczna (wzorzec Luneta).

  python software/sim_io_thermal.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "software"), os.path.join(ROOT, "kernel")]

os.environ.setdefault("KARMAZYN_SUBSTRATE", "python")
os.environ.setdefault("KARMAZYN_IO", "queue")
os.environ.setdefault("KARMAZYN_LUA", os.path.join(ROOT, "LUA"))

from karmazyn_io import (  # noqa: E402
    QueueIo,
    attach_thermal,
    KeyboardAdapter,
    DisplayAdapter,
    NAME_CONSOLE as AID_CONSOLE,
    NAME_KEYBOARD as AID_KEYBOARD,
    NAME_DISPLAY as AID_DISPLAY,
    HEAT_HIT,
)
from karmazyn_kernel import Store  # noqa: E402
import karmazyn_boot as boot  # noqa: E402


def bar(T, w=20):
    T = max(0.0, min(100.0, float(T or 0.0)))
    n = int(round(T / 100.0 * w))
    return "[" + "#" * n + "." * (w - n) + f"] {T:5.1f}"


def snap(surface, title):
    st = surface.stats()
    print(f"\n=== {title} ===")
    print(f"  backend={st['io']}  focus={st['focus']}")
    for name, key in (
        ("console", "T_console"),
        ("keyboard", "T_keyboard"),
        ("display", "T_display"),
    ):
        print(f"  io:{name:8} {bar(st[key])}")


def main():
    print("=" * 60)
    print("  SYMULACJA: I/O × matryca termiczna (wzorzec Luneta)")
    print("=" * 60)

    sink = []
    io = QueueIo(sink=sink)
    store = Store(thermal=True)
    surface = attach_thermal(store, io=io)
    kbd = KeyboardAdapter(surface)
    disp = DisplayAdapter(surface)

    snap(surface, "0. cold start — atomy I/O w Store")

    store.create_atom("page:title", "title", "Karmazyn boot", T=40.0)
    store.create_atom("page:link", "link", "docs/runtime", T=35.0)
    store.create_atom("page:body", "text", "hello substrate", T=55.0)
    print("\n--- utworzono atomy treści (page:*) ---")
    for aid in ("page:title", "page:link", "page:body"):
        a = store.get_atom(aid)
        print(f"  {aid:12} T={a.T:5.1f}  {a.S}:{a.E}")

    print("\n--- 1. KEYBOARD: 3 linie (heat_input) ---")
    for line in ("x = 10", "return x*2", ":help"):
        kbd.on_line(line)
        print(
            f"  key line: {line!r:20}  "
            f"T_kbd={surface._atom_by_name(AID_KEYBOARD).T:.1f}  "
            f"T_console={surface._atom_by_name(AID_CONSOLE).T:.1f}"
        )
    snap(surface, "1. po klawiaturze")

    print("\n--- 2. MOUSE hit-test (heat_hit jak hover-heat) ---")
    surface.heat_hit("page:link", amount=HEAT_HIT)
    surface.heat_hit("page:link", amount=HEAT_HIT)
    surface.heat_hit("page:body", amount=HEAT_HIT * 0.5)
    for aid in ("page:link", "page:body", "page:title"):
        a = store.get_atom(aid)
        print(f"  {aid:12} T={a.T:5.1f} state={a.state}")
    snap(surface, "2. po hover")

    print("\n--- 3. DISPLAY frame (project_hot + note_visible) ---")
    recs = disp.frame(min_T=30.0, limit=10)
    print("  DisplayList-lite (backend tylko blituje):")
    for r in recs:
        print(
            f"    {r['T']:5.1f} {r['state']:4} {r['id']:16} "
            f"{r['S']}:{r['E'][:30]}"
        )
    snap(surface, "3. po klatce display")

    print("\n--- 4. SCHEDULER tick ×40 (stygnięcie) ---")
    labels = (
        (AID_CONSOLE, surface.name_to_aid[AID_CONSOLE]),
        (AID_KEYBOARD, surface.name_to_aid[AID_KEYBOARD]),
        (AID_DISPLAY, surface.name_to_aid[AID_DISPLAY]),
        ("page:link", "page:link"),
        ("page:body", "page:body"),
        ("page:title", "page:title"),
    )

    def _T(aid):
        a = store.get_atom(aid)
        return None if a is None else float(a.T)

    before = {lab: _T(aid) for lab, aid in labels}
    reaped0 = store.stats().get("reaped", 0)
    store.settle(40)
    after = {lab: _T(aid) for lab, aid in labels}
    reaped1 = store.stats().get("reaped", 0)
    for lab, _aid in labels:
        b, a = before[lab], after[lab]
        if b is None and a is None:
            print(f"  {lab:12}  (brak)")
        elif a is None:
            print(f"  {lab:12} {b:5.1f} -> VACUUM (sierota wystygła — GC)")
        else:
            bb = b if b is not None else 0.0
            print(f"  {lab:12} {bb:5.1f} -> {a:5.1f}  delta={a - bb:+.1f}")
    print(f"  reaped: {reaped0} -> {reaped1}  (+{reaped1 - reaped0})")
    print(f"  name_to_aid: {surface.name_to_aid}")
    snap(surface, "4. po stygnięciu (korzenie I/O żyją)")

    print("\n--- 5. ANTI SELF-HEAT: note_visible + settle musi schłodzić ---")
    store2 = Store(thermal=True)
    s2 = attach_thermal(store2, io=QueueIo())
    for _ in range(5):
        s2.note_visible([AID_DISPLAY], amount=3.0)
    t_after_pump = s2._atom_by_name(AID_DISPLAY).T
    store2.settle(80)
    t_after_cool = s2._atom_by_name(AID_DISPLAY).T
    print(f"  po 5× note_visible: T_display={t_after_pump:.1f}")
    print(f"  po settle(80):      T_display={t_after_cool:.1f}")
    if t_after_cool >= t_after_pump:
        raise SystemExit("FAIL: matryca samo-grzeje (brak stygnięcia)")
    print("  OK — tick stygnie, to nie grzejnik")

    print("\n--- 6. BOOT + shell.feed ---")
    _store_b, shell = boot.boot(verbose_events=False)
    print("\n  interakcje shell.feed (każda grzeje fokus):")
    for ln in ("x = 7", "return x + 1", ":io", ":hot 6"):
        out = shell.feed(ln)
        tc = shell.thermal.stats()["T_console"] if shell.thermal else None
        print(f"  karmazyn> {ln}")
        if out:
            for row in str(out).splitlines()[:10]:
                print(f"    | {row}")
        print(f"    (T_console={tc})")

    print("\n" + "=" * 60)
    print("  SYMULACJA OK — klawiatura/display = adaptery, Store = matryca T")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
