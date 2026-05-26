#!/usr/bin/env python3
"""
shell.py — KarmazynOS Shell (ksh) v4.0
=======================================
Cienka warstwa – komendy ładowane dynamicznie z karmazyn_programs.json.
"""

import os
import sys
import time
import threading
import shlex
import json
import importlib
from typing import Optional, Dict, Any

# ── Rejestr serwisów ──────────────────────────────────────────────────────────
try:
    from karmazyn_syslog import SystemLog, ServiceEntry
    REGISTRY = SystemLog()
except ImportError:
    class _MinLog:
        def register(self, name, status="OK", **kw): pass
        def log(self, level, msg, service="shell", **kw):
            if level not in ("DEBUG",):
                print(f"[{level}] {service}: {msg}")
        def summary(self): return "SystemLog: fallback"
    REGISTRY = _MinLog()

class ServiceStatus:
    OK      = "OK"
    MISSING = "MISSING"
    ERROR   = "ERROR"

# ── Phi-space ─────────────────────────────────────────────────────────────────
from karmazyn_phi import PhiSpace
RUNTIME = PhiSpace()

# ── HSS Daemon ────────────────────────────────────────────────────────────────
try:
    from karmazyn_hss import HSSDaemon
    HSS = HSSDaemon()
    REGISTRY.register("hss", ServiceStatus.OK, version="HSSDaemon Ring-LWE v1.0")
except ImportError as e:
    HSS = None
    REGISTRY.register("hss", ServiceStatus.MISSING, message=str(e)[:60])

# ── VFS ───────────────────────────────────────────────────────────────────────
from karmazyn_vfs import BubbleVFS
BUBBLES = BubbleVFS()

# ── SDL Display ───────────────────────────────────────────────────────────────
try:
    from karmazyn_display import KarmazynDisplay
    DISPLAY_LOADED = True
    REGISTRY.register("display", ServiceStatus.OK, version="KarmazynDisplay SDL v1.0")
except ImportError as e:
    DISPLAY_LOADED = False
    REGISTRY.register("display", ServiceStatus.MISSING, message=str(e)[:60])

DISPLAY: Optional[Any] = None

# ── Pozostałe komponenty (inicjalizowane w main) ──────────────────────────────
LOGO = None
LUNETA_INST = None
RADIO = None
SCHEDULER = None
NET = None

# ── Rejestr komend (wypełniany przez load_programs) ───────────────────────────
_COMMANDS: Dict[str, Any] = {}

def reg(name: str, handler, desc: str = "", category: str = "system") -> None:
    """Rejestruje komendę w shellu."""
    _COMMANDS[name.upper()] = handler
    REGISTRY.register(f"cmd.{name.lower()}", ServiceStatus.OK, description=desc[:60])

# ── Loader programów z JSON ───────────────────────────────────────────────────
def load_programs(config_path: str = "karmazyn_programs.json") -> int:
    """Ładuje komendy z pliku JSON i rejestruje w shellu."""
    import json, importlib, os

    if not os.path.isabs(config_path):
        candidates = []
        try:
            _shell_dir = os.path.dirname(os.path.abspath(__file__))
            candidates.append(os.path.join(_shell_dir, config_path))
        except NameError:
            pass
        candidates.append(os.path.join(os.getcwd(), config_path))
        if sys.path and sys.path[0]:
            candidates.append(os.path.join(sys.path[0], config_path))
        for _c in candidates:
            if os.path.exists(_c):
                config_path = _c
                break

    if not os.path.exists(config_path):
        REGISTRY.log("WARN", "loader", f"Brak {config_path}")
        return 0

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        REGISTRY.log("ERR", "loader", f"Błąd odczytu programs.json: {e}")
        return 0

    # Kontekst wstrzykiwany do programów (dodano $CLUSTER)
    ctx = {
        "$RUNTIME": RUNTIME,
        "$DISPLAY": DISPLAY,
        "$BUBBLES": BUBBLES,
        "$HSS": HSS,
        "$CLUSTER": None,   # <--- DODANE dla TOP, CLUSTER itp.
    }

    def resolve(v):
        if isinstance(v, str) and v.startswith("$"):
            return ctx.get(v)
        return v

    loaded = 0
    for prog in config.get("programs", []):
        if "_comment" in prog and len(prog) == 1:
            continue
        name = prog.get("name")
        module = prog.get("module")
        if not name or not module:
            continue
        try:
            mod = importlib.import_module(module)
            p_type = prog.get("type", "function")
            if p_type == "object":
                cls_name = prog["class"]
                method = prog.get("method", "cmd")
                kwargs = {k: resolve(v) for k, v in prog.get("kwargs", {}).items()}
                instance = getattr(mod, cls_name)(**kwargs)
                handler = getattr(instance, method)
            else:
                fn_name = prog.get("handler")
                raw_fn = getattr(mod, fn_name)
                ctx_keys = prog.get("context_kwargs", {})
                if ctx_keys:
                    resolved = {k: resolve(v) for k, v in ctx_keys.items()}
                    handler = lambda args, _fn=raw_fn, _kw=resolved: _fn(args, **_kw)
                else:
                    handler = raw_fn
            desc = prog.get("description", name)
            cat = prog.get("category", "system")
            reg(name, handler, desc, cat)
            loaded += 1
        except Exception as e:
            REGISTRY.log("WARN", "loader", f"Program {name}: {e}")
    REGISTRY.log("INFO", "loader", f"Załadowano {loaded} programów")
    return loaded

# ── Główne funkcje shella ─────────────────────────────────────────────────────
def shell_worker(term):
    """Wątek roboczy dla trybu graficznego SDL."""
    C_RESULT = (255,255,255)
    C_STATUS = (160,160,200)
    C_ACCENT = (180,60,60)

    def out(text, color=C_RESULT):
        if not text: return
        for line in str(text).split("\n"):
            term.append(line, color)

    out("KarmazynOS -- tryb graficzny", C_ACCENT)
    cmd_list = "  ".join(sorted(_COMMANDS.keys())[:12])
    out(f"Komendy: {cmd_list}...", C_STATUS)

    while not term._shutdown:
        line = term.get_input_blocking()
        if not line: break
        line = line.strip()
        if not line: continue
        if line.lower() in ("exit", "quit"):
            term.shutdown()
            try:
                import pygame
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            except Exception:
                pass
            break
        try:
            result = process_command(line)
            out(result)
        except SystemExit:
            break
        except Exception as e:
            out(f"[BLAD] {e}", (255,80,80))

def process_command(line: str) -> str:
    try:
        parts = shlex.split(line)
    except ValueError as e:
        return f"Blad skladni: {e}"
    if not parts:
        return ""
    cmd_name = parts[0].upper()
    args = parts[1:]
    if cmd_name in _COMMANDS:
        try:
            result = _COMMANDS[cmd_name](args)
            return str(result) if result is not None else ""
        except Exception as e:
            REGISTRY.log("ERROR", "shell", f"{cmd_name}: {e}")
            return f"[BLAD] {e}"
    else:
        REGISTRY.log("WARN", "shell", f"Nieznana: {cmd_name}")
        return f"[BLAD] Nieznana komenda: {cmd_name}"

def print_hud():
    try:
        s = RUNTIME.status_summary()
        print(f"phi HOT:{s['HOT']} WARM:{s['WARM']} COLD:{s['COLD']}")
    except Exception:
        pass

def cmd_exit(args):
    global _observer_running
    _observer_running = False
    if SCHEDULER:
        try: SCHEDULER.save(); SCHEDULER.stop()
        except: pass
    if RADIO:
        try: RADIO.stop()
        except: pass
    if DISPLAY and DISPLAY.available and DISPLAY.renderer:
        DISPLAY.renderer.term_state.shutdown()
    REGISTRY.log("INFO", "shell", f"Shell zamkniety")
    sys.exit(0)

# ── Główna pętla ─────────────────────────────────────────────────────────────
def main():
    global DISPLAY, LOGO, LUNETA_INST, RADIO, SCHEDULER, NET

    # Inicjalizacja podsystemów
    if DISPLAY_LOADED:
        DISPLAY = KarmazynDisplay()
        if DISPLAY.init():
            DISPLAY.bind_phi(RUNTIME)
            REGISTRY.log("INFO", "display", "Display SDL aktywny")
        else:
            DISPLAY = None

    # Wczytaj programy z JSON (to rejestruje wszystkie komendy)
    load_programs()

    # Rejestracja KarminDB (KQL, INDEX, SEARCH) – DODANE
    try:
        from karmazyn_karmindb import register_karmindb
        register_karmindb(reg, RUNTIME)
        REGISTRY.log("INFO", "karmindb", "KarminDB zarejestrowany")
    except ImportError:
        REGISTRY.log("WARN", "karmindb", "Brak karmazyn_karmindb – pomijam")
    except Exception as e:
        REGISTRY.log("ERROR", "karmindb", f"Błąd rejestracji: {e}")

    # Banner startowy
    print("\n" + "═"*60)
    print("  KarmazynOS  —  ksh  (komendy z JSON)")
    print("═"*60)
    print("  Wpisz HELP aby zobaczyć komendy\n")

    if DISPLAY and DISPLAY.available:
        print("[KarmazynOS] Tryb graficzny SDL -- zamknij okno lub Ctrl+Q")
        DISPLAY.renderer.run(
            shell_main=shell_worker,
            on_quit=lambda: cmd_exit([]),
        )
        return

    while True:
        try:
            line = input("ksh> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nZamykanie...")
            cmd_exit([])
            break
        if not line: continue
        result = process_command(line)
        if result: print(result)
        print_hud()

if __name__ == "__main__":
    main()