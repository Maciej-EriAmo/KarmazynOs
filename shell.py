#!/usr/bin/env python3
"""
shell.py — KarmazynOS Shell (ksh) v4.0
=======================================
Cienka warstwa – komendy ładowane dynamicznie z karmazyn_programs.json.

Fix #11: Integracja BubbleSync – mostek RAM (RUNTIME._bubbles) ↔ VFS (BubbleVFS)
         Automatyczna synchronizacja przy starcie oraz komenda BSYNC.
"""

import os
import sys
import time
import threading
import shlex
import json
import importlib
import karmazyn_wm
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
BUBBLE_SYNC = None          # <--- FIX #11: globalny uchwyt dla mostka synchronizacji
PROCS = None                # tablica procesów (warstwa procesów KarmazynOS)

# ── Rejestr komend (wypełniany przez load_programs) ───────────────────────────
_COMMANDS: Dict[str, Any] = {}

def reg(name: str, handler, desc: str = "", category: str = "system") -> None:
    """Rejestruje komendę w shellu ORAZ jako atom w phi (program żyje w phi-space)."""
    _COMMANDS[name.upper()] = handler
    REGISTRY.register(f"cmd.{name.lower()}", ServiceStatus.OK, description=desc[:60])
    _register_program_atom(name.upper(), desc)

def _register_program_atom(name: str, desc: str = "") -> None:
    """
    Program istnieje w phi jako atom prog::<NAZWA> (S="program"), zgrupowany
    w bąblu systemowym 'sys::programs'. Logika systemu: PROGRAM = zainstalowany,
    nieaktywny → COLD (T niskie); uruchomiony PROCES → HOT (proc::<pid>).
    Atomy nie stygną same (PhiSpace nie tika automatycznie), więc program
    persystuje aż do jawnego usunięcia.
    """
    try:
        aid = f"prog::{name}"
        RUNTIME.create_atom(aid, "program", desc or name, 20.0)   # COLD = zainstalowany
        bub = RUNTIME.get_bubble("sys::programs")
        if bub is None:
            bub = RUNTIME.create_bubble("sys::programs")
        bub.add(aid)
    except Exception:
        pass   # phi-rejestracja jest dodatkiem, nie może zablokować rejestracji komendy


def _boot_ontology(runtime, data_dir: str = None) -> bool:
    """
    Boot warstwy holograficznej (opcja A — jeden root-sekret).

    Genom ontologii jest WYPROWADZONY z kanonicznej tożsamości systemu
    (phi._p2s w identity.bin, zarządzanej przez soul_store) — nie jest nowym,
    osobnym sekretem, więc nie dubluje istniejącego modelu klucza ani nie
    tworzy nowego artefaktu trwałości.

    Pierwszy start (lub brak identity.bin): geneza tożsamości (os.urandom) i
    zapis przez soul_store. identity.bin jest zaciemniony fingerprintem maszyny,
    więc sam plik przeniesiony gdzie indziej zwróci złe p2s → genom nieodtwarzalny
    poza pełnym klonem migawki na tej maszynie.

    Gdy HRR/numpy niedostępne — HRR pozostaje wyłączony, system boot-uje normalnie
    (zachowanie identyczne jak bez warstwy holograficznej).
    """
    import os
    from karmazyn_phi import derive_genome
    data_dir = data_dir or os.environ.get("KARMAZYN_DATA", "./karmazyn_data")
    p2s = None
    try:
        import soul_store
        p2s = soul_store.load_identity(data_dir)
    except Exception:
        pass
    if p2s is None:
        # Pierwszy start (lub inna maszyna) — geneza tożsamości systemu
        p2s = os.urandom(32)
        try:
            import soul_store
            soul_store.save_identity(p2s, data_dir)
        except Exception:
            pass   # bez soul_store genom działa w tej sesji, po prostu nie persystuje
    try:
        runtime.enable_hrr(genome=derive_genome(p2s))
        if runtime._hrr is not None:
            REGISTRY.log("INFO", "ontology",
                         "Warstwa holograficzna aktywna (genom z tożsamości systemu)")
            return True
        REGISTRY.log("WARN", "ontology", "HRR niedostępny (brak numpy/karmazyn_hrr)")
    except Exception as e:
        REGISTRY.log("WARN", "ontology", f"HRR nieaktywne: {e}")
    return False

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

# ── FIX #11: Inicjalizacja BubbleSync Bridge ─────────────────────────────────
def _init_bubble_sync():
    """Inicjalizuj bridge synchronizacji bąbli RAM ↔ VFS."""
    global BUBBLE_SYNC
    BUBBLE_SYNC = None
    try:
        from karmazyn_bubble_sync import BubbleSync
        BUBBLE_SYNC = BubbleSync(RUNTIME, BUBBLES)
        # Automatyczna synchronizacja VFS → RAM przy starcie
        synced = BUBBLE_SYNC.sync_vfs_to_ram()
        if synced > 0:
            REGISTRY.log("INFO", "bubble_sync",
                         f"Załadowano {synced} bąbli z VFS do RAM")
        # Rejestracja komendy BSYNC
        BUBBLE_SYNC.register_commands(reg)
        REGISTRY.register("bubble_sync", "OK",
                          detail=f"Bridge RAM↔VFS aktywny")
    except ImportError:
        REGISTRY.register("bubble_sync", "MISSING",
                          detail="Brak karmazyn_bubble_sync.py")
    except Exception as e:
        REGISTRY.register("bubble_sync", "ERROR",
                          detail=str(e)[:60])
# ──────────────────────────────────────────────────────────────────────────────

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

def cmd_ps(args):
    """Lista procesów KarmazynOS."""
    import karmazyn_process
    t = karmazyn_process.get_table()
    if t is None:
        return "Brak tablicy procesów (tryb konsolowy)"
    return t.ps()

def cmd_kill(args):
    """Zakończ proces po PID."""
    import karmazyn_process
    t = karmazyn_process.get_table()
    if t is None:
        return "Brak tablicy procesów (tryb konsolowy)"
    if not args:
        return "KILL <pid>"
    try:
        pid = int(args[0])
    except ValueError:
        return "PID musi być liczbą"
    return f"Zakończono proces {pid}" if t.kill(pid) else f"Brak procesu {pid}"

def _shutdown_system():
    """
    PEŁNE zamknięcie systemu — TYLKO przy zamknięciu pulpitu (QUIT) lub w trybie
    konsoli. Kończy wszystkie procesy i kończy proces Pythona.
    """
    global _observer_running
    _observer_running = False
    if PROCS:
        try: PROCS.close_all()      # zakończ wszystkie procesy KarmazynOS
        except: pass
    if SCHEDULER:
        try: SCHEDULER.save(); SCHEDULER.stop()
        except: pass
    if RADIO:
        try: RADIO.stop()
        except: pass
    if DISPLAY and DISPLAY.available and DISPLAY.renderer:
        DISPLAY.renderer.term_state.shutdown()
    REGISTRY.log("INFO", "shell", "System zamkniety")
    sys.exit(0)


def cmd_exit(args):
    """
    EXIT kończy BIEŻĄCY program (to okno): zapis pracy (przez store) + koniec
    tylko TEGO procesu i jego okna. Inne okna/procesy i cały system żyją dalej.

    Cały system gaśnie wyłącznie przy zamknięciu pulpitu (QUIT → _shutdown_system)
    albo w trybie konsoli (brak procesu/WM).
    """
    try:
        from karmazyn_process import current_process
        p = current_process()
    except Exception:
        p = None

    if p is None:
        # tryb konsoli / brak procesu-właściciela → pełne zamknięcie
        _shutdown_system()
        return

    win = getattr(p.ctx, "window", None)
    wm  = None
    if DISPLAY is not None:
        try:    wm = karmazyn_wm.get_active() or karmazyn_wm.get_wm()
        except Exception: wm = None

    if win is not None and wm is not None:
        # zamknięcie okna uruchomi on_close = zapis pracy + koniec tego procesu
        try:
            wm.close(win)
            return "Zamykanie okna…"
        except Exception:
            pass

    # brak okna → zapis pracy i koniec tylko tego procesu
    try: p.ctx.save_work()
    except Exception: pass
    p.request_stop()
    return "Zamykanie programu…"

# ── Główna pętla ─────────────────────────────────────────────────────────────
def main():
    global DISPLAY, LOGO, LUNETA_INST, RADIO, SCHEDULER, NET

    # Boot warstwy holograficznej PRZED tworzeniem atomów/programów — genom
    # ontologii z tożsamości systemu (opcja A). Dzięki temu programy rodzą się
    # już ze współrzędną holograficzną vector = bind(onto(S), val(E)).
    _boot_ontology(RUNTIME)

    # Inicjalizacja podsystemów
    if DISPLAY_LOADED:
        DISPLAY = KarmazynDisplay()
        if DISPLAY.init():
            DISPLAY.bind_phi(RUNTIME)
            REGISTRY.log("INFO", "display", "Display SDL aktywny")
        else:
            DISPLAY = None

    # ── FIX #11: Inicjalizacja bridge synchronizacji bąbli ─────────────────
    _init_bubble_sync()
    # ───────────────────────────────────────────────────────────────────────

    # Wczytaj programy z JSON (to rejestruje wszystkie komendy)
    load_programs()

    # Komendy warstwy procesów (PS/KILL) — wgląd systemu we własne procesy
    reg("PS",   cmd_ps,   "Lista procesów", "system")
    reg("KILL", cmd_kill, "Zakończ proces (KILL <pid>)", "system")

    # Rejestracja KarminDB (KQL, INDEX, SEARCH)
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
        print("[KarmazynOS] Uruchamianie Karmazyn Window Manager...")
        # Warstwa procesów: każde okno terminala = proces powłoki (wątek OS +
        # własny TTY + atom w phi). Wszystkie dzielą jeden RUNTIME/kernel.
        # Sesja terminala to po prostu proces, którego target=terminal_main.
        from karmazyn_process import (ProcessTable, terminal_main,
                                      default_banner, set_table)
        from karmazyn_display import TerminalState
        global PROCS
        PROCS = ProcessTable(kernel=RUNTIME)
        set_table(PROCS)   # rejestr globalny — PS/KILL i aplikacje go widzą

        def _save_terminal_work(ctx, term):
            # Realny zapis pracy terminala: transcript sesji → store (bąbel
            # keyowany hologramem programu, trwałość przez Proca — atomowo).
            try:
                lines = getattr(term, "_lines", None) or []
                text  = "\n".join(getattr(l, "text", str(l)) for l in lines)
                if text.strip():
                    ctx.store(f"session::{ctx.pid}", text, S="terminal:transcript")
            except Exception:
                pass

        def _spawn_terminal():
            term = TerminalState()
            win  = karmazyn_wm.get_wm().open_terminal(term)   # okno na świeżym TTY
            proc = PROCS.spawn(
                "ksh",
                terminal_main(process_command,
                              banner=default_banner("ksh", list(_COMMANDS.keys()))),
                tty=term,
            )
            # Powiązanie okno ↔ proces: zamknięcie okna zapisuje pracę i kończy
            # TYLKO ten proces (nie cały system). EXIT robi to samo przez okno.
            proc.ctx.window  = win
            proc.ctx.on_save = lambda c=proc.ctx, t=term: _save_terminal_work(c, t)
            if win is not None:
                win.on_close = lambda p=proc: (p.ctx.save_work(), PROCS.kill(p.pid))

        karmazyn_wm.start_desktop(DISPLAY, spawn_terminal=_spawn_terminal)
        DISPLAY.run(on_quit=lambda: _shutdown_system())
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