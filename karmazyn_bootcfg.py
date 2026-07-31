# -*- coding: utf-8 -*-
"""karmazyn_bootcfg — BootConfig (faza B, L1 host).

Jedno źródło prawdy startu: defaults < env < argv.
GRUB cmdline (L2) mapuje się na ten sam kontrakt później.

  from karmazyn_bootcfg import BootConfig, parse_boot_config
  cfg = parse_boot_config()
  cfg.apply_env()   # ustawia KARMAZYN_*
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class BootConfig:
    substrate: str = "native"       # native | python
    guest: str = "lua"              # lua | exec
    io: str = "stdio"               # stdio | queue | null | sdl
    project: Optional[str] = None
    tick_ms: int = 2000
    quiet: bool = False
    verbose: bool = False
    rescue: bool = False
    io_optional: bool = False
    # skąd wzięto kluczowe pola (do :info)
    sources: Dict[str, str] = field(default_factory=dict)

    def apply_env(self) -> None:
        """Wypchnij config do env (boot / studio czytają KARMAZYN_*)."""
        if self.rescue:
            os.environ["KARMAZYN_SUBSTRATE"] = "python"
            self.sources["substrate"] = self.sources.get("substrate", "rescue")
        else:
            os.environ["KARMAZYN_SUBSTRATE"] = self.substrate
        os.environ["KARMAZYN_GUEST"] = self.guest
        os.environ["KARMAZYN_IO"] = self.io
        if self.project:
            os.environ["KARMAZYN_PROJECT"] = self.project
        if self.io_optional:
            os.environ["KARMAZYN_IO_OPTIONAL"] = "1"
        elif "KARMAZYN_IO_OPTIONAL" in os.environ and not self.io_optional:
            # nie kasuj jeśli user ustawil ręcznie poza parserem
            pass

    def summary_lines(self) -> List[str]:
        lines = [
            f"substrate={self.substrate}  (source={self.sources.get('substrate', 'default')})",
            f"guest={self.guest}  (source={self.sources.get('guest', 'default')})",
            f"io={self.io}  (source={self.sources.get('io', 'default')})",
            f"project={self.project or '-'}  (source={self.sources.get('project', 'default')})",
            f"tick_ms={self.tick_ms}  quiet={self.quiet} verbose={self.verbose} rescue={self.rescue}",
        ]
        return lines

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def _set(cfg: BootConfig, key: str, value: Any, source: str) -> None:
    setattr(cfg, key, value)
    cfg.sources[key] = source


def parse_boot_config(
    argv: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
) -> BootConfig:
    """Złóż BootConfig: defaults → env → argv (argv wygrywa)."""
    cfg = BootConfig()
    cfg.sources = {
        "substrate": "default",
        "guest": "default",
        "io": "default",
        "project": "default",
    }
    env = dict(os.environ if env is None else env)
    argv = list(sys.argv[1:] if argv is None else argv)

    # --- env ---
    if env.get("KARMAZYN_SUBSTRATE"):
        raw = env["KARMAZYN_SUBSTRATE"].strip().lower()
        if raw in ("rust", "c", "dll", "ksub"):
            raw = "native"
        if raw in ("native", "python", "both"):
            _set(cfg, "substrate", "python" if raw == "both" else raw, "env")
    if env.get("KARMAZYN_GUEST"):
        g = env["KARMAZYN_GUEST"].strip().lower()
        if g in ("exec", "lisp", "scheme", "mini-lisp"):
            g = "exec"
        if g in ("lua", "exec"):
            _set(cfg, "guest", g, "env")
    if env.get("KARMAZYN_IO"):
        io = env["KARMAZYN_IO"].strip().lower()
        if io in ("stdio", "queue", "null", "sdl", "q", "test"):
            if io in ("q", "test"):
                io = "queue"
            _set(cfg, "io", io, "env")
    if env.get("KARMAZYN_PROJECT"):
        p = env["KARMAZYN_PROJECT"].strip()
        if p:
            _set(cfg, "project", os.path.abspath(p), "env")
    if env.get("KARMAZYN_IO_OPTIONAL", "").strip().lower() in ("1", "true", "yes", "on"):
        cfg.io_optional = True
        cfg.sources["io_optional"] = "env"

    # --- argv ---
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--native", "--rust"):
            _set(cfg, "substrate", "native", "argv")
        elif a == "--python":
            _set(cfg, "substrate", "python", "argv")
        elif a == "--lua":
            _set(cfg, "guest", "lua", "argv")
        elif a in ("--lisp", "--exec"):
            _set(cfg, "guest", "exec", "argv")
        elif a == "--guest" and i + 1 < len(argv):
            i += 1
            g = argv[i].strip().lower()
            if g in ("exec", "lisp"):
                g = "exec"
            if g in ("lua", "exec"):
                _set(cfg, "guest", g, "argv")
        elif a == "--project" and i + 1 < len(argv):
            i += 1
            _set(cfg, "project", os.path.abspath(argv[i]), "argv")
        elif a == "--io" and i + 1 < len(argv):
            i += 1
            io = argv[i].strip().lower()
            if io in ("stdio", "queue", "null", "sdl"):
                _set(cfg, "io", io, "argv")
        elif a == "--rescue":
            cfg.rescue = True
            _set(cfg, "substrate", "python", "argv")
            cfg.sources["rescue"] = "argv"
        elif a == "--quiet":
            cfg.quiet = True
            cfg.sources["quiet"] = "argv"
        elif a == "--verbose":
            cfg.verbose = True
            cfg.sources["verbose"] = "argv"
        elif a == "--io-optional":
            cfg.io_optional = True
            cfg.sources["io_optional"] = "argv"
        i += 1

    return cfg


def parse_cmdline_string(s: str) -> BootConfig:
    """Parse GRUB-like cmdline: key=val flags (faza L2 prep)."""
    parts = s.split()
    # zamień key=val na pseudo-argv
    argv: List[str] = []
    for p in parts:
        if "=" in p and not p.startswith("-"):
            k, _, v = p.partition("=")
            k = k.strip().lower()
            v = v.strip()
            if k == "substrate":
                argv.extend(["--" + ("python" if v == "python" else "native")])
            elif k == "guest":
                argv.extend(["--guest", v])
            elif k == "io":
                argv.extend(["--io", v])
            elif k == "project":
                argv.extend(["--project", v])
            elif k == "rescue" and v in ("1", "true", "yes"):
                argv.append("--rescue")
        else:
            flag = p.lower()
            if flag in ("rescue", "quiet", "verbose"):
                argv.append("--" + flag)
            elif flag in ("native", "python", "lua", "lisp", "exec"):
                argv.append("--" + flag)
    return parse_boot_config(argv=argv, env={})
