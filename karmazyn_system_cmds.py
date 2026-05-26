#!/usr/bin/env python3
"""Komendy systemowe (status, log, monitor, pomoc, wyjście)."""
import sys
import time
import threading

_RUNTIME = None
_REGISTRY = None
_COMMANDS = None  # referencja do słownika komend (dla HELP)

def _init(runtime=None, registry=None, commands=None):
    global _RUNTIME, _REGISTRY, _COMMANDS
    if runtime is not None: _RUNTIME = runtime
    if registry is not None: _REGISTRY = registry
    if commands is not None: _COMMANDS = commands

def _draw_frame(title, lines):
    sep = "─" * 50
    body = "\n".join(f"  {l}" for l in lines if l)
    return f"\n{sep}\n  {title}\n{sep}\n{body}\n{sep}"

def cmd_status(args):
    s = _RUNTIME.status_summary()
    lines = [f"{k}: {v}" for k, v in s.items()]
    return _draw_frame("STATUS SYSTEMU", lines)

def cmd_syslog(args):
    if not _REGISTRY: return "Rejestr niedostępny"
    if not args:
        return _draw_frame("SYSLOG", _REGISTRY.format_log(40).split("\n"))
    sub = args[0].upper()
    if sub == "CLEAR":
        _REGISTRY.clear_log()
        _REGISTRY.log("INFO", "shell", "Log wyczyszczony")
        return "Log wyczyszczony."
    if sub in ("ERROR","WARN","INFO","DEBUG","EVENT"):
        n = int(args[1]) if len(args) > 1 else 40
        return _draw_frame(f"SYSLOG [{sub}]", _REGISTRY.format_log(n, level=sub).split("\n"))
    try:
        return _draw_frame("SYSLOG", _REGISTRY.format_log(int(args[0])).split("\n"))
    except ValueError:
        return "SYSLOG [n | ERROR | WARN | EVENT | clear]"

def cmd_monitor(args):
    s = _RUNTIME.status_summary()
    return _draw_frame("MONITOR", [f"{k}: {v}" for k, v in s.items()])

_observer_running = False

def cmd_obserwuj(args):
    global _observer_running
    if _observer_running: return "Obserwacja już trwa."
    _observer_running = True
    def _observe():
        global _observer_running
        try:
            while _observer_running:
                rows = []
                for a in _RUNTIME.matrix.atoms():
                    bar = "[" + "█" * max(0,int(a.T/10)) + "░"*(10-max(0,int(a.T/10))) + f"] {a.T:5.1f}"
                    rows.append(f"{a.id:10} {bar} {a.state}")
                sys.stdout.write("\033[H\033[J")
                sys.stdout.write(_draw_frame("OBSERWACJA", rows) + "\n")
                sys.stdout.flush()
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            _observer_running = False
    threading.Thread(target=_observe, daemon=True).start()
    return "Obserwacja uruchomiona."

def cmd_help(args):
    if not _COMMANDS:
        return "Brak zarejestrowanych komend"
    if args:
        cmd = args[0].upper()
        if cmd in _COMMANDS:
            doc = getattr(_COMMANDS[cmd], "__doc__", "(brak opisu)")
            return f"{cmd}: {doc}"
        return f"Nieznana komenda: {cmd}"
    cmds = sorted(_COMMANDS.keys())
    lines = [f"  {c}" for c in cmds]
    return _draw_frame(f"KOMENDY ({len(cmds)})", lines)

def cmd_exit(args):
    global _observer_running
    _observer_running = False
    sys.exit(0)