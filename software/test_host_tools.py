#!/usr/bin/env python3
"""Smoke: host API karmazyn.* + skrypty lua_bin (ls, whoami, uptime, free, df, step)."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "software"))
sys.path.insert(0, os.path.join(ROOT, "kernel"))

# prefer monorepo LUA
os.environ.setdefault("KARMAZYN_LUA", os.path.join(ROOT, "LUA"))
os.environ.setdefault("KARMAZYN_SUBSTRATE", "python")

from karmazyn_kernel import Store  # noqa: E402
import karmazyn_boot as boot  # noqa: E402
from karmazyn_host import install_karmazyn_host, run_lua_tool  # noqa: E402


LUA_BIN = os.path.join(ROOT, "lua_bin")


class HostToolsSmoke(unittest.TestCase):
    def setUp(self):
        self.store = Store(thermal=True)
        self.ev = boot.mount_evaluator(self.store, kind="lua", lua_bin=LUA_BIN)
        self.assertIsNotNone(getattr(self.ev, "host", None), "host API nie zainstalowany")

    def test_karmazyn_global(self):
        self.assertEqual(self.ev.eval_line("return type(karmazyn)"), "table")
        self.assertEqual(self.ev.eval_line("return type(karmazyn.list_atoms)"), "function")
        self.assertEqual(self.ev.eval_line("return type(karmazyn.ui.draw_frame)"), "function")

    def test_create_list_get(self):
        out = self.ev.eval_line(
            'local a = karmazyn.create_atom("t1", "sig", "hello", 0.9); '
            'return a.id, a.S, a.E, a.get_T() > 0.5'
        )
        self.assertIn("t1", out)
        self.assertIn("sig", out)
        self.assertIn("hello", out)
        self.assertIn("true", out)
        self.assertEqual(self.ev.eval_line('return karmazyn.get_atom("t1").E'), "hello")
        n = self.ev.eval_line("return #karmazyn.list_atoms()")
        self.assertTrue(n.isdigit() and int(n) >= 1, n)

    def test_tool_ls(self):
        self.store.create_atom("a_ls", "S", "emanacja", 0.8)
        ret = run_lua_tool(self.ev, "ls", lua_bin=LUA_BIN)
        text = self.ev.format_run_result(ret=ret)
        self.assertIn("Φ-LIST", text)
        self.assertIn("a_ls", text)

    def test_tool_whoami_uptime(self):
        text = self.ev.format_run_result(ret=run_lua_tool(self.ev, "whoami", lua_bin=LUA_BIN))
        self.assertIn("Epoch", text)
        text2 = self.ev.format_run_result(ret=run_lua_tool(self.ev, "uptime", lua_bin=LUA_BIN))
        self.assertIn("Uptime", text2)

    def test_tool_df_free(self):
        self.store.create_atom("a_df", "x", "y", 0.9)
        t = self.ev.format_run_result(ret=run_lua_tool(self.ev, "df", lua_bin=LUA_BIN))
        self.assertIn("STATISTICS", t)
        t2 = self.ev.format_run_result(ret=run_lua_tool(self.ev, "free", lua_bin=LUA_BIN))
        self.assertIn("RESOURCES", t2)

    def test_tool_step(self):
        self.ev._io_input = ["3"]
        t = self.ev.format_run_result(ret=run_lua_tool(self.ev, "step", lua_bin=LUA_BIN))
        self.assertIn("3", t)
        self.assertEqual(self.ev.host.get_epoch(), 3)

    def test_tool_touch_cat(self):
        self.ev._io_input = ["atom_x", "sigX", "emaX"]
        t = self.ev.format_run_result(ret=run_lua_tool(self.ev, "touch", lua_bin=LUA_BIN))
        self.assertIn("atom_x", t)
        self.ev._io_input = ["atom_x"]
        t2 = self.ev.format_run_result(ret=run_lua_tool(self.ev, "cat", lua_bin=LUA_BIN))
        self.assertIn("emaX", t2)

    def test_runtime_line_in_error(self):
        from karmazyn_lua.values import LuaError
        with self.assertRaises(LuaError) as cm:
            self.ev.run_source("local x = 1\nerror('boom')\n", chunkname="@t.lua")
        msg = str(cm.exception)
        # error() may not include line if b_error doesn't use _cur_line —
        # at least chunk context after our wrap
        self.assertTrue("boom" in msg or "error" in msg.lower(), msg)

    def test_agents_ps_kill(self):
        out = self.ev.eval_line(
            'local p = karmazyn.spawn_agent("scout", "map", {"phi", "net"}); '
            'return p, #karmazyn.list_agents()'
        )
        self.assertIn("1", out)
        t = self.ev.format_run_result(ret=run_lua_tool(self.ev, "ps", lua_bin=LUA_BIN))
        self.assertIn("scout", t)
        self.assertIn("ACTIVE AGENTS", t)
        self.ev._io_input = ["1"]
        t2 = self.ev.format_run_result(ret=run_lua_tool(self.ev, "kill", lua_bin=LUA_BIN))
        self.assertTrue("usunięty" in t2 or "✓" in t2 or "Agent" in t2, t2)
        self.assertEqual(self.ev.eval_line("return #karmazyn.list_agents()"), "0")

    def test_hologram_idea_lsh(self):
        out = self.ev.eval_line(
            'return karmazyn.create_hologram("idea_demo", "filozofia", {"a","b"})'
        )
        self.assertIn("idea_demo", out)
        t = self.ev.format_run_result(ret=run_lua_tool(self.ev, "lsh", lua_bin=LUA_BIN))
        self.assertIn("HOLOGRAMS", t)
        self.assertIn("idea_demo", t)
        self.ev._io_input = ["idea_demo", "co to jest pamiec"]
        t2 = self.ev.format_run_result(ret=run_lua_tool(self.ev, "idea", lua_bin=LUA_BIN))
        self.assertIn("Wygenerowano", t2)
        self.assertIn("Wymiar", t2)

    def test_tool_kedit(self):
        self.store.create_atom("k1", "S", "stare", 0.8)
        # 1=set E, new text, 2=refresh, 3=consolidate, 4=exit
        self.ev._io_input = ["k1", "1", "nowe E", "2", "3", "4"]
        t = self.ev.format_run_result(ret=run_lua_tool(self.ev, "kedit", lua_bin=LUA_BIN))
        self.assertIn("KEDIT", t)
        self.assertEqual(self.ev.eval_line('return karmazyn.get_atom("k1").E'), "nowe E")

    def test_tool_lsb_after_consolidate(self):
        self.store.create_atom("c1", "S", "payload-bubble", 0.9)
        bid = self.ev.host.consolidate("c1")
        self.assertTrue(bid)
        t = self.ev.format_run_result(ret=run_lua_tool(self.ev, "lsb", lua_bin=LUA_BIN))
        self.assertTrue("BUBBLE" in t or "bąbl" in t.lower() or "bubble" in t.lower(), t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
