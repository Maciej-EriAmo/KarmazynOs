# -*- coding: utf-8 -*-
"""Unit tests: BootConfig parser (faza B)."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "software")]

from karmazyn_bootcfg import BootConfig, parse_boot_config, parse_cmdline_string  # noqa: E402


class BootConfigTests(unittest.TestCase):
    def test_defaults(self):
        cfg = parse_boot_config(argv=[], env={})
        self.assertEqual(cfg.substrate, "native")
        self.assertEqual(cfg.guest, "lua")
        self.assertEqual(cfg.io, "stdio")
        self.assertEqual(cfg.sources["substrate"], "default")

    def test_env_overrides_default(self):
        cfg = parse_boot_config(argv=[], env={"KARMAZYN_SUBSTRATE": "python", "KARMAZYN_GUEST": "exec"})
        self.assertEqual(cfg.substrate, "python")
        self.assertEqual(cfg.guest, "exec")
        self.assertEqual(cfg.sources["substrate"], "env")

    def test_argv_wins_over_env(self):
        cfg = parse_boot_config(
            argv=["--native", "--lua"],
            env={"KARMAZYN_SUBSTRATE": "python", "KARMAZYN_GUEST": "exec"},
        )
        self.assertEqual(cfg.substrate, "native")
        self.assertEqual(cfg.guest, "lua")
        self.assertEqual(cfg.sources["substrate"], "argv")

    def test_rescue(self):
        cfg = parse_boot_config(argv=["--rescue"], env={})
        self.assertTrue(cfg.rescue)
        self.assertEqual(cfg.substrate, "python")

    def test_io_queue(self):
        cfg = parse_boot_config(argv=["--io", "queue"], env={})
        self.assertEqual(cfg.io, "queue")

    def test_cmdline_string(self):
        cfg = parse_cmdline_string("substrate=python guest=exec rescue=1")
        self.assertEqual(cfg.substrate, "python")
        self.assertEqual(cfg.guest, "exec")
        self.assertTrue(cfg.rescue)

    def test_apply_env(self):
        cfg = parse_boot_config(argv=["--python", "--io", "null"], env={})
        # isolate
        old = os.environ.get("KARMAZYN_SUBSTRATE")
        old_tick = os.environ.get("KARMAZYN_TICK_MS")
        try:
            cfg.apply_env()
            self.assertEqual(os.environ.get("KARMAZYN_SUBSTRATE"), "python")
            self.assertEqual(os.environ.get("KARMAZYN_IO"), "null")
        finally:
            if old is None:
                os.environ.pop("KARMAZYN_SUBSTRATE", None)
            else:
                os.environ["KARMAZYN_SUBSTRATE"] = old
            if old_tick is None:
                os.environ.pop("KARMAZYN_TICK_MS", None)
            else:
                os.environ["KARMAZYN_TICK_MS"] = old_tick

    def test_substrate_both_is_python(self):
        env = parse_boot_config(argv=[], env={"KARMAZYN_SUBSTRATE": "both"})
        self.assertEqual(env.substrate, "python")
        cmd = parse_cmdline_string("substrate=both")
        self.assertEqual(cmd.substrate, "python")

    def test_tick_and_io_optional_clear(self):
        cfg = parse_boot_config(argv=["--tick", "250"], env={"KARMAZYN_TICK_MS": "4000"})
        self.assertEqual(cfg.tick_ms, 250)
        self.assertEqual(cfg.sources["tick_ms"], "argv")
        cfg.io_optional = False
        os.environ["KARMAZYN_IO_OPTIONAL"] = "1"
        try:
            cfg.apply_env()
            self.assertNotIn("KARMAZYN_IO_OPTIONAL", os.environ)
            self.assertEqual(os.environ.get("KARMAZYN_TICK_MS"), "250")
        finally:
            os.environ.pop("KARMAZYN_IO_OPTIONAL", None)
            os.environ.pop("KARMAZYN_TICK_MS", None)

    def test_summary(self):
        cfg = parse_boot_config(argv=["--verbose"], env={})
        text = "\n".join(cfg.summary_lines())
        self.assertIn("substrate=", text)
        self.assertIn("source=", text)


if __name__ == "__main__":
    unittest.main()
