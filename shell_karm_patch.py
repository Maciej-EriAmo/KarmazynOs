"""
shell_karm_patch.py — Integracja języka .karm z KarmazynOS shell.py v1.4
=========================================================================
Maciej Mazur — KarmazynOS, Warsaw 2026

Patch jest cienki — cała logika semantyczna żyje w SanctuaryRuntime v1.2.
KarmazynExecutor woła runtime bezpośrednio, bez pośredników.

Integracja z shell.py — dwie linie po bloku COMMANDS:
    from shell_karm_patch import apply_karm_to_shell
    _karm = apply_karm_to_shell(RUNTIME, COMMANDS, COMMAND_LIST)

Nowe komendy shella:
    KARM <plik.karm>        — wykonaj plik
    KARM RUN <kod>          — wykonaj fragment inline
    KARM LOAD <plik.karm>   — załaduj bez wykonania
    KARM EXEC <nazwa>       — wykonaj załadowany
    KARM LIST               — lista załadowanych
    KARM STATUS             — stan runtime + executora
    KARM MONITOR [sek]      — sprawdzaj monitory w tle
    KARM STOP               — zatrzymaj scheduler i monitor

Komenda EDIT <plik.karm> auto-wykonuje plik po wyjściu z edytora.
"""

import io
import os
import subprocess
import sys
import threading
import traceback
from typing import Dict, List, Optional, Any

# =====================================================================
# KARM SHELL
# =====================================================================

class KarmShell:
    """
    Dispatcher komend KARM w shellu.
    Jeden KarmazynExecutor na sesję — trzyma stan (etykiety, agenci,
    hologramy) między kolejnymi wywołaniami KARM.
    """

    def __init__(self, runtime):
        from karmazyn_lang import KarmazynExecutor, parse_file, parse_source
        self._parse_file   = parse_file
        self._parse_source = parse_source
        self.executor      = KarmazynExecutor(runtime)
        self.runtime       = runtime
        self._loaded: Dict[str, Any] = {}       # nazwa → ProgramAST
        self._monitor_stop = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None

    # ── główny dispatch ───────────────────────────────────────────────

    def handle(self, args: List[str]) -> str:
        if not args:
            return _HELP

        sub  = args[0].upper()
        rest = args[1:]

        # KARM <plik.karm> lub KARM <ścieżka>
        if args[0].lower().endswith(".karm") or os.path.isfile(args[0]):
            return self._run_file(args[0])

        dispatch = {
            "RUN":     self._cmd_run,
            "LOAD":    self._cmd_load,
            "EXEC":    self._cmd_exec,
            "LIST":    self._cmd_list,
            "STATUS":  self._cmd_status,
            "MONITOR": self._cmd_monitor,
            "STOP":    self._cmd_stop,
        }
        fn = dispatch.get(sub)
        if fn is None:
            return f"[KARM] Nieznana podkomenda: {sub}\n{_HELP}"
        return fn(rest)

    # ── podkomendy ────────────────────────────────────────────────────

    def _cmd_run(self, args: List[str]) -> str:
        if not args:
            return "Użycie: KARM RUN <kod .karm>"
        return self._run_source(" ".join(args), "<inline>")

    def _cmd_load(self, args: List[str]) -> str:
        if not args:
            return "Użycie: KARM LOAD <plik.karm>"
        fp = args[0]
        if not os.path.isfile(fp):
            return f"[KARM] Plik nie istnieje: {fp}"
        try:
            prog = self._parse_file(fp)
            name = os.path.basename(fp)
            self._loaded[name] = prog
            return f"[KARM] Załadowano '{name}' — {len(prog.statements)} stmt"
        except Exception as e:
            return f"[KARM LOAD ERROR] {e}"

    def _cmd_exec(self, args: List[str]) -> str:
        if not args:
            if not self._loaded:
                return "[KARM] Brak załadowanych programów."
            return "Załadowane: " + ", ".join(self._loaded)
        name = args[0]
        if name not in self._loaded:
            ext = name if name.endswith(".karm") else name + ".karm"
            if ext not in self._loaded:
                return f"[KARM] Nie załadowano: '{args[0]}'"
            name = ext
        try:
            lines = []
            _run_captured(self.executor, self._loaded[name], lines)
            return f"[KARM EXEC] '{name}'\n" + "\n".join(lines)
        except Exception as e:
            return f"[KARM EXEC ERROR] {e}\n{traceback.format_exc()}"

    def _cmd_list(self, args: List[str]) -> str:
        if not self._loaded:
            return "[KARM] Brak załadowanych programów."
        return "Załadowane:\n" + "\n".join(
            f"  {n}  ({len(p.statements)} stmt)"
            for n, p in self._loaded.items()
        )

    def _cmd_status(self, args: List[str]) -> str:
        rt = self.runtime
        ex = self.executor
        s  = rt.status_summary()
        lines = [
            f"Atomy      : HOT={s['HOT']} WARM={s['WARM']} COLD={s['COLD']} TOMB={s['TOMB']}",
            f"Φ epoch    : {rt.phi.epoch}",
            f"Φ embed    : {len(rt.phi._sem)}",
            f"Bąble      : {len(rt._bubbles)}",
            f"Hologramy  : {len(rt._holograms)}",
            f"Agenci     : {len(rt._agents)}",
            f"Monitory   : {len(ex._monitors)}",
            f"Scheduler  : {'aktywny' if ex._scheduler._threads else 'zatrzymany'}",
            f"Monitor bg : {'aktywny' if self._monitor_thread and self._monitor_thread.is_alive() else 'zatrzymany'}",
        ]
        return "[KARM STATUS]\n" + "\n".join(lines)

    def _cmd_monitor(self, args: List[str]) -> str:
        if self._monitor_thread and self._monitor_thread.is_alive():
            return "[KARM] Monitor już działa. KARM STOP aby zatrzymać."
        interval = float(args[0]) if args else 10.0
        self._monitor_stop.clear()

        def _loop():
            while not self._monitor_stop.is_set():
                self.executor.check_monitors()
                self._monitor_stop.wait(interval)

        self._monitor_thread = threading.Thread(
            target=_loop, daemon=True, name="karm-monitor"
        )
        self._monitor_thread.start()
        return f"[KARM] Monitor uruchomiony (co {interval}s). KARM STOP aby zatrzymać."

    def _cmd_stop(self, args: List[str]) -> str:
        self._monitor_stop.set()
        self.executor.stop_scheduler()
        return "[KARM] Scheduler i monitor zatrzymane."

    # ── helpers ───────────────────────────────────────────────────────

    def _run_file(self, filepath: str) -> str:
        if not os.path.isfile(filepath):
            return f"[KARM] Plik nie istnieje: {filepath}"
        try:
            prog  = self._parse_file(filepath)
            lines = []
            _run_captured(self.executor, prog, lines)
            name = os.path.basename(filepath)
            return f"[KARM] '{name}' — {len(prog.statements)} stmt\n" + "\n".join(lines)
        except Exception as e:
            return f"[KARM ERROR] {filepath}: {e}"

    def _run_source(self, source: str, label: str = "<source>") -> str:
        try:
            prog  = self._parse_source(source)
            lines = []
            _run_captured(self.executor, prog, lines)
            return f"[KARM] '{label}' — {len(prog.statements)} stmt\n" + "\n".join(lines)
        except Exception as e:
            return f"[KARM ERROR] {label}: {e}"


# =====================================================================
# HELPERS
# =====================================================================

_HELP = (
    "Użycie: KARM <podkomenda>\n"
    "  KARM <plik.karm>        — wykonaj plik\n"
    "  KARM RUN <kod>          — wykonaj inline\n"
    "  KARM LOAD <plik.karm>   — załaduj bez wykonania\n"
    "  KARM EXEC <nazwa>       — wykonaj załadowany\n"
    "  KARM LIST               — lista załadowanych\n"
    "  KARM STATUS             — stan runtime + executora\n"
    "  KARM MONITOR [sek]      — monitoring bąbli w tle\n"
    "  KARM STOP               — zatrzymaj scheduler/monitor\n"
)


def _run_captured(executor, program, lines: list):
    """Wykonuje program zbierając stdout."""
    old = sys.stdout
    sys.stdout = buf = io.StringIO()
    try:
        executor.run_program(program)
    finally:
        sys.stdout = old
    out = buf.getvalue()
    if out:
        lines.extend(out.rstrip().split("\n"))


# =====================================================================
# PATCH — dwie linie w shell.py
# =====================================================================

def apply_karm_to_shell(runtime, commands: dict,
                        command_list: list) -> KarmShell:
    """
    Dodaje obsługę .karm do shell.py.

    Wywołaj po definicji COMMANDS i COMMAND_LIST:

        from shell_karm_patch import apply_karm_to_shell
        _karm = apply_karm_to_shell(RUNTIME, COMMANDS, COMMAND_LIST)
    """
    karm = KarmShell(runtime)

    commands["KARM"] = karm.handle
    _patch_edit(commands, karm)

    for c in ["KARM", "KARM RUN", "KARM LOAD", "KARM EXEC",
              "KARM LIST", "KARM STATUS", "KARM MONITOR", "KARM STOP"]:
        if c not in command_list:
            command_list.append(c)

    print("[KARM] Język .karm aktywny. Wpisz: KARM STATUS")
    return karm


def _patch_edit(commands: dict, karm: KarmShell):
    """EDIT <plik.karm> → edytor + auto-wykonanie po wyjściu."""
    original = commands.get("EDIT", lambda a: "[Powrót z edytora]")

    def patched_edit(args):
        if not args:
            return "Użycie: EDIT <ścieżka>"
        fp = args[0]
        subprocess.run([sys.executable, "karmazyn_edit.py", fp])
        if fp.lower().endswith(".karm") and os.path.isfile(fp):
            print(f"[KARM] Auto-wykonuję '{fp}' po edycji...")
            return karm._run_file(fp)
        return "[Powrót z edytora]"

    commands["EDIT"] = patched_edit
