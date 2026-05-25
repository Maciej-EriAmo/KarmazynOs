#!/usr/bin/env python3
"""
shell.py — KarmazynOS Shell (ksh) v3.6
=======================================
Główna powłoka systemu. Punkt wejścia KarmazynOS.

Architektura:
  main()          — inicjalizuje podsystemy, uruchamia pętlę SDL lub terminal
  shell_worker()  — wątek roboczy (wejście/wyjście poleceń)
  load_programs() — rejestruje programy z karmazyn_programs.json
  reg()           — rejestruje komendę w REGISTRY shella

Warstwy systemu (kolejność inicjalizacji):
  1. karmazyn_syslog  — rejestr serwisów i logger
  2. karmazyn_phi     — przestrzeń phi (atomy, bąble)
  3. karmazyn_hss     — szyfrowanie HSS/Ring-LWE
  4. karmazyn_display — SDL workspace (opcjonalny)
  5. karmazyn_fb      — framebuffer (opcjonalny, --fb)
  6. Programy         — browser, logo, edytory, sieć

Filozofia:
  Terminal jest prawem. Panele SDL są soczewką.
  shell_worker nie dotyka SDL — tylko TerminalState.
  Programy są atomami phi-space: używane = gorące.
"""

import os
import sys
import time
import threading
import shlex
try:
    import readline
except ImportError:
    readline = None
import json
import importlib
from typing import Optional, Dict, Any

# ── Rejestr serwisów ──────────────────────────────────────────────────────────
try:
    from karmazyn_syslog import SystemLog, ServiceEntry
    REGISTRY = SystemLog()
except ImportError:
    class _MinLog:
        """Minimalny rejestr — fallback gdy brak karmazyn_syslog.py."""
        def register(self, name, status="OK", **kw): pass
        def log(self, level, msg, service="shell", **kw):
            if level not in ("DEBUG",):
                print(f"[{level}] {service}: {msg}")
        def summary(self): return "SystemLog: fallback"
    REGISTRY = _MinLog()

class ServiceStatus:
    """Stany serwisu dla REGISTRY.register()."""
    OK      = "OK"
    MISSING = "MISSING"
    ERROR   = "ERROR"

# ── Phi-space ─────────────────────────────────────────────────────────────────
from karmazyn_phi import PhiSpace
from karmazyn_atom import Atom, AtomRegistry, AtomsWrapper

RUNTIME = PhiSpace()

# ── HSS Daemon (szyfrowanie Ring-LWE) ────────────────────────────────────────
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

# ── Framebuffer (--fb) ────────────────────────────────────────────────────────
try:
    from karmazyn_fb import KarmazynFB
    FB_LOADED = True
    REGISTRY.register("fb", ServiceStatus.OK, version="KarmazynFB v1.0")
except ImportError as e:
    FB_LOADED = False
    REGISTRY.register("fb", ServiceStatus.MISSING, message=str(e)[:60])

# ── Luneta — przeglądarka ─────────────────────────────────────────────────────
try:
    from karmazyn_browser import KarmazynBrowser as Luneta, cmd_browse as cmd_luneta
    from karmazyn_dom import cmd_dom, DOMMapper
    LUNETA_LOADED = True
    REGISTRY.register("luneta", ServiceStatus.OK, version="Luneta v4.5")
    REGISTRY.register("dom",    ServiceStatus.OK, version="DOMMapper v1.2")
except ImportError as e:
    LUNETA_LOADED = False
    REGISTRY.register("luneta", ServiceStatus.MISSING, message=str(e)[:60])
    REGISTRY.register("dom",    ServiceStatus.MISSING, message=str(e)[:60])

LUNETA_INST = None

# ── LOGO ──────────────────────────────────────────────────────────────────────
try:
    from karmazyn_logo import LogoShell as _LogoShell
    LOGO_LOADED = True
    REGISTRY.register("logo", ServiceStatus.OK, version="KarmazynLOGO v4.0")
except ImportError as e:
    LOGO_LOADED = False
    REGISTRY.register("logo", ServiceStatus.MISSING, message=str(e)[:60])

LOGO = None

# ── NooEdit ───────────────────────────────────────────────────────────────────
try:
    from Nooedit import cmd_nooedit as _nooedit_cmd, NooContext
    NOOEDIT_LOADED = True
    REGISTRY.register("nooedit", ServiceStatus.OK, "NooEdit SDL v5.2")
except (ImportError, ModuleNotFoundError) as e:
    NOOEDIT_LOADED    = False
    _nooedit_cmd      = None
    REGISTRY.log("WARN", "nooedit", f"NooEdit niedostepny: {e}")
    REGISTRY.register("nooedit", ServiceStatus.MISSING, str(e)[:80])

# ── AstraEdit ─────────────────────────────────────────────────────────────────
try:
    from AstraEdit import cmd_astraedit as _astraedit_cmd
    ASTRAEDIT_LOADED = True
    REGISTRY.register("astraedit", ServiceStatus.OK, version="AstraEdit v5.1")
except ImportError as e:
    ASTRAEDIT_LOADED = False
    REGISTRY.register("astraedit", ServiceStatus.MISSING, message=str(e)[:60])

# ── Scheduler + Net ───────────────────────────────────────────────────────────
try:
    from karmazyn_scheduler import ThermalScheduler, cmd_scheduler
    from karmazyn_net import KarmazynNet, cmd_net_cmd as _ext_cmd_net
    SCHEDULER_LOADED = True
    REGISTRY.register("scheduler", ServiceStatus.OK, version="ThermalScheduler v1.0")
    REGISTRY.register("net",       ServiceStatus.OK, version="KarmazynNet v1.0")
except ImportError as e:
    SCHEDULER_LOADED = False
    REGISTRY.register("scheduler", ServiceStatus.MISSING, message=str(e)[:60])
    REGISTRY.register("net",       ServiceStatus.MISSING, message=str(e)[:60])

SCHEDULER = None
NET       = None

# ── Zabezpieczenia braku Karmin i Lua ─────────────────────────────────────────
KARM_LOADED = False
KARM = None

# ── Radio + Audio ─────────────────────────────────────────────────────────────
try:
    from karmazyn_radio import KarmazynRadio, cmd_radio
    from karmazyn_audio import cmd_audio
    RADIO_LOADED = True
    REGISTRY.register("radio", ServiceStatus.OK, version="KarmazynRadio v1.1")
    REGISTRY.register("audio", ServiceStatus.OK, version="AudioDaemon v1.2")
except ImportError as e:
    RADIO_LOADED = False
    REGISTRY.register("radio", ServiceStatus.MISSING, message=str(e)[:60])
    REGISTRY.register("audio", ServiceStatus.MISSING, message=str(e)[:60])

RADIO = None

# ── Bubble commands ───────────────────────────────────────────────────────────
try:
    import bubble_commands as _bc
    from bubble_commands import cmd_bubble, cmd_edit, cmd_view
    BUBBLE_CMD_LOADED = True
except ImportError:
    BUBBLE_CMD_LOADED = False
    # Fallback — puste komendy żeby rejestracja nie crashowała
    def cmd_bubble(args, **kw): return "bubble_commands niedostepny"
    def cmd_edit(args, **kw):   return "bubble_commands niedostepny"
    def cmd_view(args, **kw):   return "bubble_commands niedostepny"

# ── Rejestr komend shella ─────────────────────────────────────────────────────
LUA_EXECUTOR = None  # opcjonalny — inicjalizowany gdy LuaExecutor dostępny

_COMMANDS: Dict[str, Any] = {}

def reg(name: str, handler,
        desc: str = "", help_text: str = "",
        category: str = "system",
        args_schema=None) -> None:
    """
    Rejestruje komendę w shellu.
    Przyjmuje zarówno desc= jak i help_text= (kompatybilność).
    """
    _COMMANDS[name.upper()] = handler
    description = desc or help_text
    REGISTRY.register(f"cmd.{name.lower()}", ServiceStatus.OK,
                      description[:60] if description else category)


def _draw_frame(title: str, lines: list) -> str:
    """Prosta ramka ASCII — zamiennik gfx.draw_frame."""
    sep  = "─" * 50
    body = "\n".join(f"  {l}" for l in lines if l)
    return f"\n{sep}\n  {title}\n{sep}\n{body}\n{sep}"


def _progress_bar(val: float, max_val: float = 100.0) -> str:
    """Prosta belka postępu."""
    pct    = max(0.0, min(1.0, float(val) / max(1.0, float(max_val))))
    filled = int(pct * 20)
    return "[" + "█" * filled + "░" * (20 - filled) + f"] {val:5.1f}"


def cmd_ls(args):
    atoms = RUNTIME.matrix.atoms()
    if atoms:
        rows = []
        for a in atoms:
            bar = _progress_bar(a.T, a.T_max)
            rows.append(f"{a.id:12} {bar} {a.T:5.1f} {a.state}")
        return _draw_frame("ATOMY", rows)
    # Listuj atomy phi-space
    atoms = RUNTIME.matrix.atoms()
    if not atoms:
        return "(brak atomów)"
    lines = []
    for a in sorted(atoms, key=lambda x: -x.T)[:20]:
        bar = "█" * max(0,int(a.T/10)) + "░"*(10-max(0,int(a.T/10)))
        lines.append(f"  {a.id:<30} [{bar}] {a.T:5.1f}° {a.state}")
    return "\n".join(lines)

def cmd_cat(args) -> str:
    """Wyświetl zawartość pliku."""
    if not args:
        return "Uzycie: CAT <plik>"
    path = args[0]
    if not os.path.exists(path):
        return f"Brak pliku: {path}"
    if os.path.isdir(path):
        return f"{path} to katalog"
    try:
        content = open(path, encoding="utf-8", errors="replace").read()
        if not content:
            return "(pusty)"
        return content
    except Exception as e:
        return f"Blad odczytu: {e}"


def cmd_mkdir(args) -> str:
    """Utwórz katalog."""
    if not args:
        return "Uzycie: MKDIR <katalog>"
    try:
        os.makedirs(args[0], exist_ok=True)
        return f"OK: {args[0]}"
    except Exception as e:
        return f"Blad: {e}"


def cmd_echo(args) -> str:
    """Wypisz tekst."""
    return " ".join(args)


def cmd_head(args) -> str:
    """Wyświetl pierwsze N linii pliku (domyślnie 10)."""
    if not args:
        return "Uzycie: HEAD <plik> [N]"
    path = args[0]
    n    = int(args[1]) if len(args) > 1 else 10
    if not os.path.exists(path):
        return f"Brak pliku: {path}"
    try:
        lines = open(path, encoding="utf-8", errors="replace").readlines()
        return "".join(lines[:n])
    except Exception as e:
        return f"Blad: {e}"


def cmd_wc(args) -> str:
    """Policz linie, słowa, bajty pliku."""
    if not args:
        return "Uzycie: WC <plik>"
    path = args[0]
    if not os.path.exists(path):
        return f"Brak pliku: {path}"
    try:
        content = open(path, encoding="utf-8", errors="replace").read()
        lines   = content.count("\n")
        words   = len(content.split())
        bts     = len(content.encode())
        return f"{lines:6}  {words:6}  {bts:6}  {path}"
    except Exception as e:
        return f"Blad: {e}"


def cmd_cd(args):
    return f"Warstwa: {args[0] if args else 'phi'} (phi-space nie ma warstw)"
def cmd_pwd(args):
    return f"phi-space: {len(RUNTIME.matrix.atoms())} atomow"
def cmd_touch(args):
    if not args: return "TOUCH <id> [S] [E] [T]"
    try:
        a = RUNTIME.create_atom(args[0], S=args[1] if len(args)>1 else "",
                                E=args[2] if len(args)>2 else "",
                                T=float(args[3]) if len(args)>3 else 50.0)
        return f"OK: {a.id} T={a.T:.1f}"
    except Exception as e: return f"Blad: {e}"
def cmd_rm(args):
    if not args: return "RM <id>"
    ok = RUNTIME.matrix.delete(args[0])
    return f"OK: usunięto {args[0]}" if ok else f"Brak: {args[0]}"

# Odwołania do brakującego FS wycięte na rzecz pustej odpowiedz:
def cmd_cp(args):    return "Komenda niedostepna (brak FS)"
def cmd_mv(args):    return "Komenda niedostepna (brak FS)"
def cmd_sete(args):  return "Komenda niedostepna (brak FS)"

def cmd_find(args):
    if not args: return "FIND <query>"
    q = " ".join(args).lower()
    hits = [a for a in RUNTIME.matrix.atoms()
            if q in a.id.lower() or q in str(a.S).lower() or q in str(a.E).lower()]
    if not hits: return f"Brak wynikow dla: {q}"
    return "\n".join(f"  {a.id} T={a.T:.1f} {a.state}" for a in hits[:10])

def cmd_monitor(args):
    s = RUNTIME.status_summary()
    return _draw_frame("MONITOR", [f"{k}: {v}" for k, v in s.items()])

def cmd_status(args):
    return _draw_frame("STATUS SYSTEMU", REGISTRY.format_status().split("\n"))

def cmd_syslog(args):
    if not args:
        return _draw_frame("SYSLOG", REGISTRY.format_log(40).split("\n"))
    sub = args[0].upper()
    if sub == "CLEAR":
        REGISTRY.clear_log()
        REGISTRY.log("INFO", "shell", "Log wyczyszczony")
        return "Log wyczyszczony."
    if sub in ("ERROR", "WARN", "INFO", "DEBUG", "EVENT"):
        n = int(args[1]) if len(args) > 1 else 40
        return _draw_frame(f"SYSLOG [{sub}]",
                               REGISTRY.format_log(n, level=sub).split("\n"))
    try:
        return _draw_frame("SYSLOG", REGISTRY.format_log(int(args[0])).split("\n"))
    except ValueError:
        return "SYSLOG [n | ERROR | WARN | EVENT | clear]"

def cmd_scheduler_cmd(args):
    if not SCHEDULER_LOADED or SCHEDULER is None:
        return "Scheduler niedostepny (brak karmazyn_scheduler.py)"
    return cmd_scheduler(args, SCHEDULER)

def cmd_net_cmd(args):
    if not SCHEDULER_LOADED or NET is None:
        return "Net niedostepny (brak karmazyn_net.py)"
    return _ext_cmd_net(args, NET)

# ── Komendy mediów ────────────────────────────────────────────────────────────

def cmd_radio_cmd(args):
    if not RADIO_LOADED or RADIO is None:
        return ("Radio niedostepne.\n"
                "  Termux: pkg install mpv && pip install karmazyn_radio")
    return cmd_radio(args, RADIO)

def cmd_audio_cmd(args):
    if not RADIO_LOADED or RADIO is None or RADIO._audio is None:
        return "AudioDaemon niedostepny (brak karmazyn_audio.py lub mpv)"
    return cmd_audio(args, RADIO._audio)

def cmd_luneta_cmd(args):
    if not LUNETA_LOADED or LUNETA_INST is None:
        return ("Luneta niedostepna (brak karmazyn_browser.py).\n"
                "  pip install karmazyn_browser")
    return cmd_luneta(args, LUNETA_INST)

def cmd_dom_cmd(args):
    if not LUNETA_LOADED or LUNETA_INST is None:
        return "DOMMapper niedostepny (brak karmazyn_browser.py / karmazyn_dom.py)"
    if not LUNETA_INST._has_dom or LUNETA_INST.dom_mapper is None:
        return "DOMMapper niedostepny (brak karmazyn_dom.py w katalogu projektu)"
    return cmd_dom(args, LUNETA_INST, LUNETA_INST.dom_mapper)

# ── Komendy atomów / bąbli ────────────────────────────────────────────────────

def cmd_consolidate(args):
    if not args:
        return "CONSOLIDATE <id> [babel]"
    if len(args) == 1:
        target = args[0]
        current_b_name = getattr(RUNTIME, "current_bubble_name", "default")
        atom_id, bubble_name = ((target, current_b_name)
                                if RUNTIME.has_atom(target) else (None, target))
    else:
        atom_id, bubble_name = args[0], args[1]
    if not bubble_name:
        return "Najpierw otworz babel lub podaj nazwe."
    bubble_id = BUBBLES.find_bubble_by_name(bubble_name) or BUBBLES.create_bubble(bubble_name)
    if atom_id:
        res = BUBBLES.import_to_bubble(bubble_id, atom_id, RUNTIME)
        if res:
            REGISTRY.log("INFO", "bubbles", f"Atom {atom_id} -> {bubble_name}")
            return f"OK {atom_id} -> {bubble_name}"
        return f"BLAD konsolidacji {atom_id}"
    atoms = RUNTIME.matrix.atoms()
    if not atoms:
        return "Brak atomow."
    count = BUBBLES.snapshot_runtime(bubble_id, atoms)
    return f"OK Snapshot {count} atomow -> {bubble_name}"

def cmd_stabilizuj(args):
    if not args: return "STABILIZUJ <id>"
    if getattr(RUNTIME, "current_mission", None) and getattr(RUNTIME, "resources", {}).get("zywica", 0) <= 0:
        return "Brak Zywicy!"
    if getattr(RUNTIME, "current_mission", None):
        RUNTIME.resources["zywica"] -= 1
    try:
        RUNTIME.stabilize_atom(args[0])
        res = getattr(RUNTIME, "resources", {}).get('zywica', 'inf')
        return f"Stabilizowano {args[0]} (Zywica: {res})"
    except ValueError as e:
        return str(e)

def cmd_dotknij_pustki(args):
    if not args: return "DOTKNIJ PUSTKI <id>"
    try:
        RUNTIME.corrupt_atom(args[0], 25)
        atom = RUNTIME.get_atom(args[0])
        return f"Dotknieto {args[0]}. T={atom.T:.1f}" if atom else f"Dotknieto {args[0]}"
    except ValueError as e:
        return str(e)

_observer_running = False

def cmd_obserwuj(args):
    global _observer_running
    if _observer_running: return "Obserwacja juz trwa."
    _observer_running = True
    def _observe():
        global _observer_running
        try:
            while _observer_running:
                rows = []
                for a in RUNTIME.matrix.atoms():
                    col = ("phi_thermal" if a.T > 70
                           else "phi_signal" if a.T > 30 else "phi_decay")
                    bar = _progress_bar(a.T, a.T_max)
                    rows.append(f"{a.id:10} {bar} {a.T:5.1f} {a.state}")
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

def cmd_atom_status(args):
    if not args: return "ATOM STATUS <id>"
    atom = RUNTIME.get_atom(args[0])
    if not atom: return "Atom nie istnieje."
    col = ("phi_thermal" if atom.T > 70
           else "phi_signal" if atom.T > 30 else "phi_decay")
    return _draw_frame(f"ATOM {atom.id}", [
        f"S: {atom.S}   E: {atom.E}",
        f"T: {atom.T:.1f}   Stan: {atom.state}   Wiek: {getattr(atom, 'age', '?')}",
        _progress_bar(atom.T, atom.T_max),
    ])

# ── Komendy skryptów ──────────────────────────────────────────────────────────

def cmd_run(args):
    if not KARM_LOADED: return "BLAD karm nie zaladowany"
    if not args: return "RUN <plik.karm>"
    if not os.path.isfile(args[0]): return f"BLAD brak pliku: {args[0]}"
    try:
        REGISTRY.log("INFO", "karm", f"RUN {args[0]}")
        KARM.run_file(args[0])
        return f"OK {args[0]}"
    except Exception as e:
        REGISTRY.log("ERROR", "karm", f"RUN {args[0]}: {e}")
        return f"BLAD {e}"

def cmd_compile(args):
    if not KARM_LOADED: return "BLAD karm nie zaladowany"
    if not args: return "COMPILE <plik.karm>"
    if not os.path.isfile(args[0]): return f"BLAD brak pliku: {args[0]}"
    try:
        # Zależność od karmazyn_karm, który jest u Ciebie obecnie pomijany
        return "Brak parsera karmin."
    except Exception as e:
        return f"BLAD {e}"

def cmd_lua(args):
    if LUA_EXECUTOR is None:
        return "BLAD: lua niedostepny (brak LuaExecutor)"
    if not args: return "LUA <plik.lua> | LUA BUBBLE <babel>"
    if args[0].upper() == "BUBBLE":
        if len(args) < 2: return "BLAD podaj nazwe babla"
        r = LUA_EXECUTOR.run_bubble(args[1])
        return f"BLAD {r}" if isinstance(r, str) and r.startswith("Blad") else f"OK {args[1]}"
    filepath = args[0]
    if not os.path.isfile(filepath):
        alt = os.path.join("lua_bin",
                           filepath if filepath.endswith(".lua") else filepath + ".lua")
        if os.path.isfile(alt):
            filepath = alt
    REGISTRY.log("INFO", "lua", f"LUA {filepath}")
    r = LUA_EXECUTOR.run_file(filepath, args=args[1:])
    return f"BLAD {r}" if isinstance(r, str) and r.startswith("Blad") else f"OK {filepath}"

# cmd_nooedit zdefiniowana niżej w bloku 'programy systemowe'
# jako cmd_nooedit_wrap z obsługą term_state

# ── Pomoc i wyjście ───────────────────────────────────────────────────────────

def cmd_help(args) -> str:
    """Pokaż dostępne komendy."""
    if args:
        # Pomoc dla konkretnej komendy
        cmd_name = args[0].upper()
        if cmd_name in _COMMANDS:
            fn = _COMMANDS[cmd_name]
            doc = fn.__doc__ or "(brak opisu)"
            return f"{cmd_name}: {doc.strip()}"
        return f"Nieznana komenda: {cmd_name}"
    # Pełna lista
    cmds = sorted(_COMMANDS.keys())
    lines = [f"  {c}" for c in cmds]
    return _draw_frame(f"KOMENDY ({len(cmds)})", lines)

def cmd_exit(args):
    global _observer_running
    _observer_running = False

    # Scheduler — zapisz i zatrzymaj
    if SCHEDULER_LOADED and SCHEDULER is not None:
        SCHEDULER.save()
        SCHEDULER.stop()
        REGISTRY.log("INFO", "scheduler", "Scheduler zatrzymany")

    # Radio — zatrzymaj odtwarzanie i wątki AudioDaemon
    if RADIO_LOADED and RADIO is not None:
        if RADIO.is_playing():
            RADIO.stop()
        if RADIO._audio is not None:
            RADIO._audio.shutdown()   # join() wątków meta i watchdog
            REGISTRY.log("INFO", "audio", "AudioDaemon zatrzymany")

    if DISPLAY_LOADED and DISPLAY is not None and DISPLAY.available:
        if DISPLAY.renderer and DISPLAY.renderer.term_state:
            DISPLAY.renderer.term_state.shutdown()

    REGISTRY.log("INFO", "shell", "Shell zamkniety")
    # Zatrzymaj phi-space (PhiSpace nie ma stop_loop — wystarczy sys.exit)
    if hasattr(RUNTIME, "stop_loop"):
        RUNTIME.stop_loop()
    sys.exit(0)

# ── Edytor emanacji ───────────────────────────────────────────────────────────

def cmd_emanation_edit_wrapper(args):
    return "cmd_emanation_edit niedostepne."

# ── Rejestracja komend ────────────────────────────────────────────────────────

# reg() i _COMMANDS zdefiniowane wcześniej

if not ASTRAEDIT_LOADED:
    def cmd_astraedit(args, **kw): return 'astraedit niedostepny'

# Auto-fallbacki dla brakujących komend
def cmd_bubble(args, **kw): return 'cmd_bubble: komenda niedostepna'
def cmd_edit(args, **kw): return 'cmd_edit: komenda niedostepna'
def cmd_export(args, **kw): return 'cmd_export: komenda niedostepna'
def cmd_gallery(args, **kw): return 'cmd_gallery: komenda niedostepna'
def cmd_import(args, **kw): return 'cmd_import: komenda niedostepna'
def cmd_view(args, **kw): return 'cmd_view: komenda niedostepna'

# Nawigacja
reg("LS",             cmd_ls,           "Listuje atomy lub FS",        category="navigation")
reg("CD",             cmd_cd,           "Zmienia warstwe",             category="navigation")
reg("PWD",            cmd_pwd,          "Biezaca warstwa",             category="navigation")

# Atomy
reg("TOUCH",          cmd_touch,        "Tworzy atom",                 category="atoms")
reg("RM",             cmd_rm,           "Usuwa atom",                  category="atoms")
reg("CP",             cmd_cp,           "Kopiuje atom",                category="atoms")
reg("MV",             cmd_mv,           "Przenosi atom",               category="atoms")
reg("SETE",           cmd_sete,         "Zmienia emanacje",            category="atoms")
reg("FIND",           cmd_find,         "Szuka w atomach",             category="atoms")
reg("CONSOLIDATE",    cmd_consolidate,  "Atom -> babel",               category="atoms")
reg("STABILIZUJ",     cmd_stabilizuj,   "Podnosi temperature",         category="atoms")
reg("DOTKNIJ PUSTKI", cmd_dotknij_pustki, "Obniza temperature",        category="atoms")
reg("ATOM STATUS",    cmd_atom_status,  "Szczegoly atomu",             category="atoms")

# Bąble
reg("BUBBLE",      cmd_bubble,                 "Babble [LS|NEW|STATUS|TICK|RESONATE|DECAY|COPY|PASTE]",
                                                                        category="bubbles")
reg("BUBBLE_EDIT", cmd_edit,                   "Edytor babli",         category="bubbles")
reg("EDIT",        cmd_emanation_edit_wrapper, "Edytor emanacji",      category="bubbles")
reg("VIEW",        cmd_view,                   "Pokazuje aktywny babel",category="bubbles")
# NOOEDIT zarejestrowany w bloku programów systemowych

# Skrypty
reg("RUN",     cmd_run,     "Wykonuje plik .karm",      category="scripting")
reg("COMPILE", cmd_compile, "AST pliku .karm",          category="scripting")
reg("LUA",     cmd_lua,     "Wykonuje .lua lub babel",  category="scripting")

# System
reg("MONITOR",    cmd_monitor,       "Podsumowanie stanow atomow",              category="system")
reg("STATUS",     cmd_status,        "Pelny status uslug i runtime",            category="system")
reg("SYSLOG",     cmd_syslog,        "Log systemowy [n|ERROR|WARN|clear]",      category="system")
reg("OBSERWUJ",   cmd_obserwuj,      "Dynamiczny podglad atomow",               category="system")
reg("SCHEDULER",  cmd_scheduler_cmd, "Triggery termiczne [LS|LOG|SAVE|ON|OFF|RM]",
                                                                                category="system")
reg("HELP",       cmd_help,          "Pomoc",                                   category="system")
reg("EXIT",       cmd_exit,          "Konczy shell",                            category="system")


# Display
def cmd_display_cmd(args):
    if not DISPLAY_LOADED or DISPLAY is None:
        return "Display niedostepny (brak karmazyn_display.py lub pygame)"
    sub = args[0].upper() if args else "STATUS"
    if sub == "STATUS":
        return f"Display: {'aktywny' if DISPLAY.available else 'brak X11'}"
    if sub == "BENCH":
        from karmazyn_display import benchmark
        r = benchmark(100)
        return (f"Benchmark: {r['ms_per_frame']:.2f} ms/frame  "
                f"{r['fps_capacity']:.0f} fps max  "
                f"{r['ms_per_frame']/16.67*100:.0f}% budzetu")
    return "DISPLAY STATUS | BENCH"


def completer(text, state):
    line   = readline.get_line_buffer()
    begidx = readline.get_begidx()
    try:
        tokens = shlex.split(line[:begidx])
    except ValueError:
        tokens = []
    cur = line[begidx:readline.get_endidx()]

    if len(tokens) == 0:
        matches = [c for c in list(_COMMANDS.keys())
                   if c.lower().startswith(cur.lower())]
        if os.path.isdir("lua_bin"):
            for f in os.listdir("lua_bin"):
                if f.endswith(".lua"):
                    s = f[:-4].upper()
                    if s.startswith(cur.upper()) and s not in matches:
                        matches.append(s)
        matches.sort()
        return matches[state] if state < len(matches) else None

    if len(tokens) == 1:
        first = tokens[0].upper()
        if first == "LUA" and os.path.isdir("lua_bin"):
            m = [f for f in os.listdir("lua_bin")
                 if f.endswith(".lua") and f.lower().startswith(cur.lower())]
            return m[state] if state < len(m) else None
        cands = [c for c in list(_COMMANDS.keys()) if c.startswith(first + " ")]
        words = [c.split()[1] for c in cands]
        m = [w for w in words if w.lower().startswith(cur.lower())]
        return m[state] if state < len(m) else None

    return None

if readline: readline.set_completer(completer)
if readline: readline.parse_and_bind("tab: complete")

# ── Główna pętla ──────────────────────────────────────────────────────────────



# ─── Loader programów z karmazyn_programs.json ────────────────────────────────

def load_programs(config_path: str = "karmazyn_programs.json") -> int:
    """
    Ładuje programy z pliku JSON i rejestruje w shellu.
    Zwraca liczbę załadowanych programów.

    Format wpisu:
      type=function  → module.handler(args)
      type=object    → module.Class(**kwargs).method(args)

    Konteksty ($ZMIENNA) rozwiązywane do obiektów shella:
      $RUNTIME  → RUNTIME
      $DISPLAY  → DISPLAY (lub None)
      $BUBBLES  → BUBBLES
    """
    import json, importlib, os

    # Szukaj pliku w kolejności: obok shell.py → bieżący katalog → sys.path
    if not os.path.isabs(config_path):
        candidates = []
        # 1. Obok shell.py (najczęstszy przypadek)
        try:
            _shell_dir = os.path.dirname(os.path.abspath(__file__))
            candidates.append(os.path.join(_shell_dir, config_path))
        except NameError:
            pass
        # 2. Bieżący katalog roboczy
        candidates.append(os.path.join(os.getcwd(), config_path))
        # 3. Katalog pierwszego elementu sys.path
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

    # Kontekst wstrzykiwany do programów
    _term = (DISPLAY.renderer.term_state
             if DISPLAY_LOADED and DISPLAY is not None
             and DISPLAY.available and DISPLAY.renderer else None)
    ctx = {
        "$RUNTIME":    RUNTIME,       # PhiSpace
        "$DISPLAY":    DISPLAY,       # KarmazynDisplay lub None
        "$BUBBLES":    BUBBLES,       # BubbleVFS
        "$TERM_STATE": _term,         # TerminalState (SDL) lub None
        "$HSS":        HSS,           # HSSDaemon lub None
    }

    def resolve(v):
        """Zamień $ZMIENNA na obiekt z kontekstu."""
        if isinstance(v, str) and v.startswith("$"):
            return ctx.get(v)   # None jeśli brak — bezpieczne
        return v

    loaded = 0
    for prog in config.get("programs", []):
        # Ignoruj wpisy komentarzowe
        if "_comment" in prog and len(prog) == 1:
            continue

        name    = prog.get("name")
        module  = prog.get("module")
        p_type  = prog.get("type", "function")
        desc    = prog.get("description", name)
        cat     = prog.get("category", "system")
        ver     = prog.get("version", "")
        aliases = prog.get("aliases", [])

        if not name or not module:
            continue

        try:
            mod = importlib.import_module(module)

            if p_type == "object":
                cls_name = prog["class"]
                method   = prog.get("method", "cmd")
                kwargs   = {k: resolve(v) for k, v in prog.get("kwargs", {}).items()}
                instance = getattr(mod, cls_name)(**kwargs)
                handler  = getattr(instance, method)

            else:  # function
                fn_name = prog.get("handler")
                raw_fn  = getattr(mod, fn_name)
                # Wstrzyknij kontekst jako kwargs jeśli funkcja go przyjmuje
                ctx_keys = prog.get("context_kwargs", {})
                if ctx_keys:
                    resolved = {k: resolve(v) for k, v in ctx_keys.items()}
                    handler = lambda args, _fn=raw_fn, _kw=resolved: _fn(args, **_kw)
                else:
                    handler = raw_fn

            # Atom w phi-space — program jako termodynamiczny byt
            atom_id   = f"program.{name.lower()}"
            prog_atom = None
            # RUNTIME jest teraz PhiSpace — używamy bezpośrednio
            if hasattr(RUNTIME, "create_atom"):
                try:
                    prog_atom = RUNTIME.create_atom(
                        atom_id, S="program", E=desc, T=50.0)
                except Exception:
                    pass

            # Wrapper: touch() przy każdym wywołaniu
            def _make_handler(h, a):
                def _wrapped(args):
                    if a is not None:
                        a.touch()
                    return h(args)
                return _wrapped

            wrapped = _make_handler(handler, prog_atom)

            reg(name, wrapped, desc, category=cat)
            for alias in aliases:
                reg(alias, wrapped, f"Alias: {name}", category=cat)

            REGISTRY.register(name.lower(), ServiceStatus.OK, version=ver)
            loaded += 1

        except ImportError as e:
            REGISTRY.register(name.lower(), ServiceStatus.MISSING,
                              message=str(e)[:60])
            # Atom niedostępnego programu — T=1 → TOMB przy pierwszym tick
            _phi = getattr(RUNTIME, "matrix", None)  # PhiSpace.matrix = AtomRegistry
            if name and _phi and hasattr(_phi, "create_atom"):
                try:
                    _phi.create_atom(
                        f"program.{name.lower()}",
                        S="program.missing", E=str(e)[:64], T=1.0)
                except Exception:
                    pass
        except Exception as e:
            REGISTRY.log("WARN",
                         f"Program {name}: {type(e).__name__}: {e}",
                         service="loader")

    REGISTRY.log("INFO", "loader", f"Załadowano {loaded} programów z {config_path}")
    return loaded

# ── Programy systemowe ────────────────────────────────────────────────────────
if LOGO_LOADED:
    def cmd_logo(args):
        """LOGO [RUN <kod>|FILE <ścieżka>|RESET|HELP]"""
        return LOGO.cmd(args) if LOGO else "LOGO niedostepny"
    reg("LOGO",    cmd_logo,    "LOGO interpreter graficzny",  category="programs")
    reg("LG",      cmd_logo,    "Alias: LOGO",                category="programs")

if LUNETA_LOADED:
    def cmd_luneta_wrap(args):
        """LUNETA [<url>|j|k|b|N|l|o]"""
        return cmd_luneta(args, LUNETA_INST) if LUNETA_INST else "Luneta niedostepna"
    reg("LUNETA",  cmd_luneta_wrap, "Przeglądarka tekstowa",  category="programs")
    reg("L",       cmd_luneta_wrap, "Alias: LUNETA",          category="programs")

if RADIO_LOADED:
    def cmd_radio_wrap(args):
        """RADIO [PLAY <url>|STOP|STATUS|STATIONS]"""
        return cmd_radio(args, RADIO) if RADIO else "Radio niedostepne"
    reg("RADIO",   cmd_radio_wrap,  "Radio internetowe",      category="programs")

    def cmd_audio_wrap(args):
        """AUDIO [VOL <n>|MUTE|STATUS]"""
        return cmd_audio(args, RADIO._audio if RADIO else None)
    reg("AUDIO",   cmd_audio_wrap,  "Kontrola audio",         category="programs")

if SCHEDULER_LOADED:
    def cmd_net_wrap(args):
        """NET [GET <url>|STATUS]"""
        return cmd_net_cmd(args, NET) if NET else "Net niedostepny"
    reg("NET",     cmd_net_wrap,    "Siec i HTTP",            category="programs")

if ASTRAEDIT_LOADED:
    def cmd_ae(args):
        """ASTRAEDIT <plik> [--gui|--tui|--sdl]"""
        term = (DISPLAY.renderer.term_state
                if DISPLAY and DISPLAY.available and DISPLAY.renderer else None)
        return _astraedit_cmd(args, runtime=RUNTIME, term_state=term)
    reg("ASTRAEDIT", cmd_ae, "Edytor plików (GUI/TUI/SDL)", category="programs")
    reg("AE",        cmd_ae, "Alias: ASTRAEDIT",            category="programs")

def cmd_nooedit_wrap(args):
    """NOOEDIT <label> [--py|--lua|--md|--karm]"""
    if not NOOEDIT_LOADED:
        return ('BLAD: Nooedit.py nie zaladowany.\n'
                'Upewnij sie ze Nooedit.py jest w katalogu i'
                ' ze wszystkie zaleznosci sa dostepne.')
    term = (DISPLAY.renderer.term_state
            if DISPLAY and DISPLAY.available and DISPLAY.renderer else None)
    # POPRAWKA 1: Podajemy bezpośrednio DISPLAY do Nooedit
    return _nooedit_cmd(args, runtime=RUNTIME, term_state=term, display=DISPLAY)

reg("NOOEDIT", cmd_nooedit_wrap, "Edytor babli (SDL)",    category="programs")
reg("EDIT",    cmd_nooedit_wrap, "Alias: NOOEDIT",        category="programs")

def cmd_display_wrap(args):
    """DISPLAY [STATUS|BENCH|F1|F2]"""
    if not DISPLAY or not DISPLAY.available:
        return "Display niedostepny (brak X11/SDL)"
    sub = args[0].upper() if args else "STATUS"
    if sub == "STATUS":
        return f"Display: {'aktywny' if DISPLAY.available else 'brak'}"
    if sub == "BENCH":
        from karmazyn_display import benchmark
        r = benchmark(100)
        return (f"Benchmark: {r['ms_per_frame']:.2f} ms/frame  "
                f"{r['fps_capacity']} fps max")
    if sub == "F1":
        DISPLAY.renderer.release_left()
        return "Panel lewy zwolniony"
    if sub == "F2":
        state = DISPLAY.renderer.toggle_phi()
        return f"Phi-map: {'widoczna' if state else 'ukryta'}"
    return "DISPLAY STATUS | BENCH | F1 | F2"

reg("DISPLAY", cmd_display_wrap, "Kontrola okna SDL",    category="system")


# ── KernelContext — kontener stanu systemu ────────────────────────────────────

class KernelContext:
    """
    Kontener stanu kernela KarmazynOS.

    Cel: zastąpić rozrzucone globale (DISPLAY, RADIO, LOGO...) jednym
    obiektem który można przekazywać, testować i serializować.

    Migracja stopniowa:
      Faza 1 (teraz):  ctx = KernelContext(); ctx.display = DISPLAY  ← alias
      Faza 2 (potem):  przepisanie shell_worker i komend na ctx.*
      Faza 3 (docelowo): ctx przekazywany wszędzie zamiast globali

    Zawiera też event bus phi-space — komendy mogą emitować zdarzenia
    zamiast bezpośrednio wołać term_state.append().
    """

    __slots__ = (
        "runtime", "display", "logo", "luneta",
        "radio", "scheduler", "net", "hss", "bubbles",
        "registry", "events",
    )

    def __init__(self):
        self.runtime   = None
        self.display   = None
        self.logo      = None
        self.luneta    = None
        self.radio     = None
        self.scheduler = None
        self.net       = None
        self.hss       = None
        self.bubbles   = None
        self.registry  = None
        self.events    = None

    def setup(self, runtime, display=None, logo=None,
              luneta=None, radio=None, scheduler=None,
              net=None, hss=None, bubbles=None,
              registry=None) -> "KernelContext":
        """
        Inicjalizuje kontekst jedną operacją.
        Zwraca self dla łańcuchowania: CTX.setup(...).bind_phi()
        """
        self.runtime   = runtime
        self.display   = display
        self.logo      = logo
        self.luneta    = luneta
        self.radio     = radio
        self.scheduler = scheduler
        self.net       = net
        self.hss       = hss
        self.bubbles   = bubbles
        self.registry  = registry
        return self

    def bind_phi(self) -> None:
        """Podpina event bus z runtime do kontekstu."""
        if self.runtime and hasattr(self.runtime, "events"):
            self.events = self.runtime.events

    @property
    def term_state(self):
        """Skrót do TerminalState SDL."""
        if (self.display and self.display.available
                and self.display.renderer):
            return self.display.renderer.term_state
        return None

    def emit(self, event: str, data=None) -> None:
        """Wyemituj zdarzenie przez event bus phi-space."""
        if self.events:
            try:
                self.events.emit(event, data)
            except Exception:
                pass

    def all_services(self) -> dict:
        """Zwraca słownik nazwa→obiekt dla wszystkich serwisów."""
        return {
            slot: getattr(self, slot)
            for slot in self.__slots__
            if getattr(self, slot) is not None
        }


# Globalny kontekst — inicjalizowany w main()
CTX = KernelContext()


def shell_worker(term):
    """Shell w watku SDL. I/O przez TerminalState, logika przez process_command()."""
    C_RESULT = (255, 255, 255)   # biały — wynik komendy
    C_STATUS = (160, 160, 200)   # jasnoniebieski — komunikaty systemu
    C_ERROR  = (255,  80,  80)   # czerwony — błędy
    C_ACCENT = (180,  60,  60)   # karmazynowy — akcent
    C_OK     = (100, 220, 100)   # zielony — sukces

    def out(text, color=C_RESULT):
        if not text:
            return
        for line in str(text).split("\n"):
            term.append(line, color)

    def hud():
        try:
            s = RUNTIME.status_summary()
            term.append(
                f"phi HOT:{s['HOT']} WARM:{s['WARM']} COLD:{s['COLD']}",
                C_STATUS)
        except Exception:
            pass

    out("KarmazynOS -- tryb graficzny", C_ACCENT)
    try:
        bubbles = BUBBLES.list_bubbles()
        if bubbles:
            total = sum(b.get("active_atoms", 0) for b in bubbles)
            out(f"Bable: {len(bubbles)} ({total} atomow)", C_STATUS)
    except Exception:
        pass
    # Pokaż dostępne komendy dynamicznie
        cmd_list = "  ".join(sorted(_COMMANDS.keys())[:12])
        out(f"Komendy: {cmd_list}...", C_STATUS)

    while not term._shutdown:
        try:
            line = term.get_input_blocking()
        except KeyboardInterrupt:
            break
        if not line:
            break
        line = line.strip()
        if not line:
            continue
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
            out(f"[BLAD] {e}", C_ERROR)
        hud()


def main():
    """Inicjalizacja systemu i uruchomienie pętli shella."""

    # ── Inicjalizacja podsystemów ─────────────────────────────────────────────
    global DISPLAY, LOGO, LUNETA_INST, RADIO, SCHEDULER, NET

    # Display SDL
    if DISPLAY_LOADED:
        DISPLAY = KarmazynDisplay()
        if DISPLAY.init():
            DISPLAY.bind_phi(RUNTIME)  # PhiSpace samo jest phi — ma .matrix.atoms()
            REGISTRY.log("INFO", "display", "Display SDL aktywny")
        else:
            DISPLAY = None
            REGISTRY.log("INFO", "display", "Display: brak X11/SDL")

    # LOGO
    if LOGO_LOADED:
        LOGO = _LogoShell(display=DISPLAY)

    # Luneta
    if LUNETA_LOADED:
        LUNETA_INST = Luneta(RUNTIME)
        if DISPLAY and DISPLAY.available and hasattr(DISPLAY, "bind_browser"):
            DISPLAY.bind_browser(LUNETA_INST)

    # Radio
    if RADIO_LOADED:
        try:
            RADIO = KarmazynRadio(RUNTIME)
        except Exception as e:
            REGISTRY.log("WARN", "radio", f"Radio: {e}")
            RADIO = None

    # Scheduler
    if SCHEDULER_LOADED:
        try:
            SCHEDULER = ThermalScheduler(RUNTIME)
            NET       = KarmazynNet(RUNTIME)
            SCHEDULER.start()
        except Exception as e:
            REGISTRY.log("WARN", "scheduler", f"Scheduler: {e}")

    # Wczytaj programy z JSON
    load_programs()

    # ── Wypełnij KernelContext aliasami globali ──────────────────────────
    CTX.setup(
        runtime   = RUNTIME,
        display   = DISPLAY,
        logo      = LOGO,
        luneta    = LUNETA_INST,
        radio     = RADIO,
        scheduler = SCHEDULER,
        net       = NET,
        hss       = HSS,
        bubbles   = BUBBLES,
        registry  = REGISTRY,
    ).bind_phi()

    # ── Banner startowy ───────────────────────────────────────────────────────
    lines = ["KarmazynOS Shell (ksh)  |  phi-space aktywny"]

    # Status opcjonalnych serwisów — tylko gdy załadowane I działające
    status_checks = [
        (DISPLAY    is not None and getattr(DISPLAY, "available", False),
         "Display: SDL aktywny"),
        (LUNETA_INST is not None,
         "Luneta:  przeglądarka aktywna"),
        (LOGO       is not None,
         "LOGO:    interpreter aktywny"),
        (RADIO      is not None,
         f"Radio:   {getattr(getattr(RADIO,'_audio',None),'_mpv_path',None) or 'brak mpv'}"),
        (SCHEDULER  is not None,
         "Sched:   ThermalScheduler aktywny"),
        (HSS        is not None,
         "HSS:     Ring-LWE aktywny"),
    ]
    for ok, msg in status_checks:
        if ok:
            lines.append(msg)

    print("\n" + "═"*60)
    print("  KarmazynOS  —  ksh")
    print("═"*60)
    for l in lines:
        print(f"  {l}")
    print("═"*60)
    print("  Wpisz HELP aby zobaczyć komendy\n")

    bubbles = BUBBLES.list_bubbles()
    if bubbles:
        total = sum(b['active_atoms'] for b in bubbles)
        print(f"Bable: {len(bubbles)} ({total} atomow)")

    print("  STATUS  SYSLOG  SCHEDULER  NET  RADIO  LUNETA  DOM  HELP\n")

    # Auto-discovery konfiguracji
    config_bubble_id = None
    for b in BUBBLES.list_bubbles():
        if b.get('label') == 'sys_config' or 'sys_config' in str(b.get('id', '')):
            config_bubble_id = b['id']
            break

    if config_bubble_id:
        pass  # FS.set_config_bubble
        REGISTRY.log("INFO", "shell", f"Konfiguracja: {config_bubble_id}")
        for a in BUBBLES.get_active_atoms(config_bubble_id):
            s_val = a.get('S') if isinstance(a, dict) else a.S
            if s_val == "BIN":
                cmd_id = a.get('id') if isinstance(a, dict) else a.id
                target = a.get('E') if isinstance(a, dict) else a.E

                def make_handler(t):
                    return lambda args: (LUA_EXECUTOR.run_file(t)
                                         if t.endswith('.lua')
                                         else LUA_EXECUTOR.run_bubble(t))

                try:
                    reg(cmd_id.upper(), make_handler(target), f"Narzedzie: {target}", category="tools")
                    REGISTRY.log("INFO", "shell", f"BIN: {cmd_id} -> {target}")
                except Exception:
                    pass

    REGISTRY.log("INFO", "shell", "Shell gotowy")

    # Dynamiczne programy z karmazyn_programs.json
    load_programs()

    if DISPLAY_LOADED and DISPLAY is not None and DISPLAY.available:
        print("\n[KarmazynOS] Tryb graficzny SDL -- zamknij okno lub Ctrl+Q")
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
        if not line:
            continue
        result = process_command(line)
        if result:
            print(result)


def process_command(line: str) -> str:
    """Parsuj i wykonaj komendę. Szuka w _COMMANDS (dict)."""
    try:
        parts = shlex.split(line)
    except ValueError as e:
        return f"Blad skladni: {e}"
    if not parts:
        return ""

    verb1 = parts[0].upper()
    # Sprawdź dwusłowne komendy (np. "ATOM STATUS")
    cmd  = None
    args = []
    if len(parts) > 1:
        verb2 = f"{verb1} {parts[1].upper()}"
        if verb2 in _COMMANDS:
            cmd  = _COMMANDS[verb2]
            args = parts[2:]
    if cmd is None:
        cmd  = _COMMANDS.get(verb1)
        args = parts[1:]

    if cmd is None:
        # Fallback: sprawdź plik .lua w lua_bin/
        lua_path = os.path.join(
            "lua_bin",
            verb1.lower() + ("" if verb1.lower().endswith(".lua") else ".lua"),
        )
        if os.path.isfile(lua_path):
            try:
                r = f"Lua: {lua_path} (brak LuaExecutor w tej wersji)"  # LUA_EXECUTOR.run_file(lua_path, args=parts[1:])
                return r if r else ""
            except Exception as e:
                REGISTRY.log("ERROR", "lua", f"LUA {lua_path}: {e}")
                return f"[BLAD LUA] {e}"
        REGISTRY.log("WARN", "shell", f"Nieznana: {verb1}")
        return f"[BLAD] Nieznana komenda: {verb1}"

    # cmd to zwykła funkcja z _COMMANDS dict
    try:
        result = cmd(args)
        return str(result) if result is not None else ""
    except Exception as e:
        REGISTRY.log("ERROR", "shell", f"{verb1}: {e}")
        return f"[BLAD] {e}"


if __name__ == "__main__":
    main()