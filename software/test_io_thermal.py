# -*- coding: utf-8 -*-
"""Stage 1 tests: IoPort × matryca termiczna (python + native)."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "software"))
sys.path.insert(0, os.path.join(ROOT, "kernel"))
sys.path.insert(0, os.path.join(ROOT, "native"))

os.environ.setdefault("KARMAZYN_LUA", os.path.join(ROOT, "LUA"))
# Stage1: nie dziedzicz default native — golden tests na python, native osobno
os.environ["KARMAZYN_SUBSTRATE"] = "python"

from karmazyn_io import (  # noqa: E402
    QueueIo,
    attach_thermal,
    DisplayAdapter,
    KeyboardAdapter,
    NAME_CONSOLE,
    NAME_KEYBOARD,
    NAME_DISPLAY,
    HEAT_INPUT,
)
import karmazyn_boot as boot  # noqa: E402
from karmazyn_kernel import (  # noqa: E402
    open_store,
    native_substrate_available as native_available,
)


def _open_python():
    return open_store(thermal=True, backend="python")


def _open_native():
    if not native_available():
        return None
    return open_store(thermal=True, backend="native")


class IoThermalPython(unittest.TestCase):
    def setUp(self):
        self.store = _open_python()
        self.sink = []
        self.io = QueueIo(lines=["hello", "world"], sink=self.sink)
        self.surface = attach_thermal(self.store, io=self.io)

    def test_matrix_names_resolve(self):
        st = self.surface.stats()
        self.assertEqual(st["stage"], 1)
        for name in (NAME_CONSOLE, NAME_KEYBOARD, NAME_DISPLAY):
            self.assertIn(name, self.surface.name_to_aid)
            aid = self.surface.name_to_aid[name]
            self.assertIsNotNone(self.store.get_atom(aid))

    def test_heat_input_raises_T(self):
        a = self.surface._atom_by_name(NAME_CONSOLE)
        t0 = a.T
        self.surface.heat_input(amount=HEAT_INPUT)
        self.assertGreater(a.T, t0)

    def test_empty_read_line_no_heat(self):
        io = QueueIo(lines=["", "  ", "x"])
        s = attach_thermal(_open_python(), io=io)
        a = s._atom_by_name(NAME_CONSOLE)
        t0 = a.T
        self.assertEqual(s.read_line(""), "")
        self.assertEqual(a.T, t0)  # empty
        self.assertEqual(s.read_line(""), "  ")
        self.assertEqual(a.T, t0)  # whitespace only
        self.assertEqual(s.read_line(""), "x")
        self.assertGreater(a.T, t0)

    def test_read_line_heats(self):
        t0 = self.surface._atom_by_name(NAME_CONSOLE).T
        line = self.surface.read_line("> ")
        self.assertEqual(line, "hello")
        self.assertGreater(self.surface._atom_by_name(NAME_CONSOLE).T, t0)

    def test_note_visible_cools_with_tick(self):
        d = self.surface._atom_by_name(NAME_DISPLAY)
        self.surface.note_visible([NAME_DISPLAY], amount=20.0)
        t_hot = d.T
        self.assertGreater(t_hot, 30.0)
        self.store.settle(50)
        self.assertLess(d.T, t_hot)

    def test_project_hot_default_no_mark_visible(self):
        """Stage 1: skan nie grzeje całego store."""
        aid = self.store.create_atom("user_hot", "S", "content", T=90.0)
        t_user = self.store.get_atom(aid).T
        t_disp = self.surface._atom_by_name(NAME_DISPLAY).T
        recs = self.surface.project_hot(min_T=30.0, limit=20, mark_visible=False)
        self.assertIn(aid, [r["id"] for r in recs])
        # bez mark_visible T user nie rośnie z project_hot
        self.assertEqual(self.store.get_atom(aid).T, t_user)
        self.assertEqual(self.surface._atom_by_name(NAME_DISPLAY).T, t_disp)

    def test_display_frame_heats_only_display_surface(self):
        aid = self.store.create_atom("vis", "text", "hello", T=80.0)
        atom = self.store.get_atom(aid)
        t_vis0 = atom.T
        t_d0 = self.surface._atom_by_name(NAME_DISPLAY).T
        da = DisplayAdapter(self.surface)
        recs = da.frame(min_T=30.0)
        self.assertTrue(any(r["id"] == aid for r in recs))
        # treść nie dostaje note_visible z frame
        self.assertEqual(self.store.get_atom(aid).T, t_vis0)
        self.assertGreater(self.surface._atom_by_name(NAME_DISPLAY).T, t_d0)

    def test_keyboard_adapter(self):
        kb = KeyboardAdapter(self.surface)
        t0 = self.surface._atom_by_name(NAME_KEYBOARD).T
        kb.on_line("cmd")
        self.assertGreater(self.surface._atom_by_name(NAME_KEYBOARD).T, t0)
        kb.on_line("")  # empty — no heat bump required
        # still alive
        self.assertIsNotNone(self.surface._atom_by_name(NAME_KEYBOARD))

    def test_boot_wires_thermal_python(self):
        os.environ["KARMAZYN_SUBSTRATE"] = "python"
        os.environ["KARMAZYN_IO"] = "queue"
        try:
            store, shell = boot.boot(verbose_events=False)
        finally:
            os.environ.pop("KARMAZYN_IO", None)
        self.assertIsNotNone(shell.thermal)
        self.assertEqual(shell.thermal.stats().get("stage"), 1)
        info = shell.feed(":io")
        self.assertIn("io:console", info)
        hot = shell.feed(":hot")
        self.assertIn("hot", hot)

    def test_host_read_line_uses_thermal(self):
        store = _open_python()
        io = QueueIo(lines=["3"])
        thermal = attach_thermal(store, io=io)
        ev = boot.mount_evaluator(store, kind="lua", io=io, thermal=thermal)
        self.assertIsNotNone(getattr(ev, "host", None))
        t0 = thermal._atom_by_name(NAME_CONSOLE).T
        line = ev.host.read_line("")
        self.assertEqual(line, "3")
        self.assertGreater(thermal._atom_by_name(NAME_CONSOLE).T, t0)


@unittest.skipUnless(
    __import__("karmazyn_backend", fromlist=["native_available"]).native_available(),
    "native substrate not built",
)
class IoThermalNative(unittest.TestCase):
    """Stage 1 gate: matryca MUSI działać na Product default (Rust)."""

    def setUp(self):
        self.store = _open_native()
        self.assertIsNotNone(self.store)
        self.io = QueueIo(lines=["ping"])
        self.surface = attach_thermal(self.store, io=self.io)

    def test_native_name_table_int_ids(self):
        st = self.surface.stats()
        self.assertEqual(st["stage"], 1)
        for name, aid in self.surface.name_to_aid.items():
            self.assertIsInstance(aid, int, f"{name} should map to int on native")
            self.assertIsNotNone(self.store.get_atom(aid))

    def test_native_heat_and_stats(self):
        t0 = self.surface.stats()["T_console"]
        self.surface.heat_input()
        t1 = self.surface.stats()["T_console"]
        self.assertGreater(t1, t0)

    def test_native_boot_has_thermal(self):
        os.environ["KARMAZYN_SUBSTRATE"] = "native"
        os.environ["KARMAZYN_IO"] = "queue"
        try:
            store, shell = boot.boot(verbose_events=False)
        finally:
            os.environ.pop("KARMAZYN_IO", None)
            os.environ["KARMAZYN_SUBSTRATE"] = "python"
        self.assertIsNotNone(shell.thermal, "Stage1: native boot MUST mount thermal")
        self.assertEqual(shell.thermal.stats().get("stage"), 1)
        # name_to_aid all ints
        for aid in shell.thermal.name_to_aid.values():
            self.assertIsInstance(aid, int)
        out = shell.feed(":io")
        self.assertIn("stage=1", out)

    def test_native_host_string_id_alias(self):
        """Product: Lua/tools używają string id; core = u32 — host mapuje."""
        store = _open_native()
        self.assertIsNotNone(store)
        ev = boot.mount_evaluator(store, kind="lua")
        host = getattr(ev, "host", None)
        self.assertIsNotNone(host)
        proxy = host.create_atom("tool_x", "S", "hello", 50.0)
        self.assertNotIsInstance(proxy, str, msg=proxy)
        got = host.get_atom("tool_x")
        self.assertIsNotNone(got)
        # real id w Store jest int
        real = host._resolve_aid("tool_x")
        self.assertIsInstance(real, int)
        self.assertTrue(store.has_atom(real))


if __name__ == "__main__":
    unittest.main()
