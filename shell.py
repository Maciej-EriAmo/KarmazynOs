#!/usr/bin/env python3
"""KarmazynOS Shell (ksh) v3.5"""

import os, sys, time, threading, readline, shlex
from typing import Optional

# Registry jako pierwszy import — rejestruje czas startu natychmiast
from sys_registry import REGISTRY, ServiceStatus  # type: ignore

from runtime import SanctuaryRuntime, SystemState
REGISTRY.register("runtime", ServiceStatus.OK, version="SanctuaryRuntime v1.4")

from karmazyn_fs import KarmazynFS
from karmazyn_ui import theme, gfx
from karmazyn_ui.editor import EmanationEditor

import bubble_commands as _bc
from bubble_commands import (
    CTX as BUBBLE_CTX,
    cmd_bubble, cmd_edit, cmd_import, cmd_gallery, cmd_export, cmd_view,
)
from bedit import (
    KarmazynIntegration as BubbleRuntime,
    KARMAZYN_LOADED, BUBBLEFS_LOADED, SOUL_LOADED,
)

try:
    from karmazyn_lang import KarmazynExecutor, parse_file
    KARM_LOADED = True
    REGISTRY.register("karm", ServiceStatus.OK, version="KarmazynScript + lark")
except ImportError as e:
    KARM_LOADED = False
    REGISTRY.register("karm", ServiceStatus.MISSING, message=str(e)[:60])

try:
    from karmazyn_lua import LuaExecutor
    LUA_AVAILABLE = True
    REGISTRY.register("lua", ServiceStatus.OK, version="lupa/LuaJIT")
except ImportError as e:
    LUA_AVAILABLE = False
    REGISTRY.register("lua", ServiceStatus.MISSING, message=str(e)[:60])

try:
    from Nooedit import cmd_nooedit as _nooedit_cmd
    NOOEDIT_LOADED = True
    REGISTRY.register("nooedit", ServiceStatus.OK, version="NooEdit TUI+GUI")
except ImportError as e:
    NOOEDIT_LOADED = False
    REGISTRY.register("nooedit", ServiceStatus.MISSING, message=str(e)[:60])

try:
    from karmazyn_scheduler import ThermalScheduler, attach_system_rules, cmd_scheduler
    from karmazyn_net import KarmazynNet, cmd_net
    SCHEDULER_LOADED = True
    REGISTRY.register("scheduler", ServiceStatus.OK, version="ThermalScheduler v1.0")
    REGISTRY.register("net",       ServiceStatus.OK, version="HTTP/FTP/Git/LLM")
except ImportError as e:
    SCHEDULER_LOADED = False
    REGISTRY.register("scheduler", ServiceStatus.MISSING, message=str(e)[:60])
    REGISTRY.register("net",       ServiceStatus.MISSING, message=str(e)[:60])

# Radio + AudioDaemon (karmazyn_audio dołącza automatycznie przez KarmazynRadio)
try:
    from karmazyn_radio import KarmazynRadio, cmd_radio
    from karmazyn_audio import cmd_audio
    RADIO_LOADED = True
    REGISTRY.register("radio", ServiceStatus.OK, version="KarmazynRadio v1.1")
    REGISTRY.register("audio", ServiceStatus.OK, version="AudioDaemon v1.2 mpv/IPC")
except ImportError as e:
    RADIO_LOADED = False
    REGISTRY.register("radio", ServiceStatus.MISSING, message=str(e)[:60])
    REGISTRY.register("audio", ServiceStatus.MISSING, message=str(e)[:60])

# Luneta — tekstowa przeglądarka HTTP z integracją DOMMapper
try:
    from karmazyn_browser import KarmazynBrowser as Luneta, cmd_browse as cmd_luneta
    from karmazyn_dom import cmd_dom, DOMMapper
    LUNETA_LOADED = True
    REGISTRY.register("luneta", ServiceStatus.OK, version="Luneta v4.4")
    REGISTRY.register("dom",    ServiceStatus.OK, version="DOMMapper v1.2")
except ImportError as e:
    LUNETA_LOADED = False
    REGISTRY.register("luneta", ServiceStatus.MISSING, message=str(e)[:60])
    REGISTRY.register("dom",    ServiceStatus.MISSING, message=str(e)[:60])

from command_engine import Command, CommandRegistry, make_arg_schema

# ── Inicjalizacja systemu ──────────────────────────────────────────────────────

RUNTIME = SanctuaryRuntime()
REGISTRY.set_runtime(RUNTIME)

# HSS z mikrojądra runtime
if RUNTIME._hss_available:
    REGISTRY.register("hss", ServiceStatus.OK, version="HSSDaemon/ukernel")
else:
    REGISTRY.register("hss", ServiceStatus.MISSING, message="hss_demo.py nie znaleziono")

BUBBLES = BubbleRuntime()
BUBBLES.hss_daemon = RUNTIME.hss

if KARMAZYN_LOADED:
    REGISTRY.register("karmazyn_kernel", ServiceStatus.OK,    version="karmazyn.py")
else:
    REGISTRY.register("karmazyn_kernel", ServiceStatus.MISSING, message="brak karmazyn.py")

if BUBBLEFS_LOADED:
    REGISTRY.register("bubblefs",  ServiceStatus.OK,    version="BubbleFS v1.0")
else:
    REGISTRY.register("bubblefs",  ServiceStatus.MISSING, message="brak bubblefs.py")

if SOUL_LOADED:
    REGISTRY.register("soul_store", ServiceStatus.OK,    version=".soul JSONL")
else:
    REGISTRY.register("soul_store", ServiceStatus.MISSING, message="brak soul_store.py")

# Globale bubble_commands
_bc.BUBBLES = BUBBLES
_bc.RUNTIME = RUNTIME

# Auto-save cichy — emitowany z wątku runtime
def _silent_auto_save():
    BUBBLES.save_all(silent=True)
    REGISTRY.log("DEBUG", "Auto-save", service="bubbles")

RUNTIME.events.on("trigger_hard_save", lambda: _silent_auto_save())

FS   = KarmazynFS(RUNTIME, bubbles_runtime=BUBBLES)
KARM = KarmazynExecutor(RUNTIME) if KARM_LOADED else None

if LUA_AVAILABLE:
    LUA_EXECUTOR = LuaExecutor(RUNTIME)
    LUA_EXECUTOR.bind_system_services(
        resolver_func=FS.resolve_alias,
        importer_func=BUBBLES.import_to_bubble,
    )
else:
    LUA_EXECUTOR = None

# Scheduler startuje PO runtime — słucha jego eventów
RUNTIME.start_loop()
REGISTRY.log("INFO", "Petla runtime uruchomiona", service="runtime")

if SCHEDULER_LOADED:
    SCHEDULER = ThermalScheduler(RUNTIME)
    attach_system_rules(SCHEDULER, RUNTIME)
    SCHEDULER.start()
    NET = KarmazynNet(RUNTIME)
    REGISTRY.log("INFO", "Scheduler i Net aktywne", service="shell")
else:
    SCHEDULER = None
    NET       = None

# Radio — AudioDaemon (mpv IPC) dołącza automatycznie w KarmazynRadio.__init__
if RADIO_LOADED:
    RADIO = KarmazynRadio(RUNTIME)
    REGISTRY.log("INFO", f"Radio: player={RADIO._audio._mpv_path or 'brak mpv'}",
                 service="shell")
else:
    RADIO = None

# Luneta — DOMMapper dołącza automatycznie w KarmazynBrowser.__init__
if LUNETA_LOADED:
    LUNETA_INST = Luneta(RUNTIME)
    REGISTRY.log("INFO",
                 f"Luneta: DOMMapper={'aktywny' if LUNETA_INST._has_dom else 'brak'}",
                 service="shell")
else:
    LUNETA_INST = None

# ── HUD ───────────────────────────────────────────────────────────────────────

def print_hud():
    loop_dead = hasattr(RUNTIME, 'is_alive') and not RUNTIME.is_alive()
    if loop_dead:
        REGISTRY.log("ERROR", "Petla runtime martwa!", service="runtime")

    s   = RUNTIME.status_summary()
    now = time.strftime("%H:%M:%S")
    hud = (f"{theme.ansi_fg('phi_ghost')}{now}{theme.RESET} "
           f"HOT:{s['HOT']} WARM:{s['WARM']} COLD:{s['COLD']} TOMB:{s['TOMB']}")

    if loop_dead:
        hud += " [RUNTIME DEAD]"

    # Radio — status odtwarzania w HUD
    if RADIO_LOADED and RADIO and RADIO.is_playing():
        now_pl = RADIO.now_playing() or "?"
        hud += f"  ▶ {now_pl[:18]}"

    # Aktywny bąbel
    if BUBBLE_CTX.current_bubble_name:
        label = BUBBLE_CTX.current_label
        b = RUNTIME._bubbles.get(label) if label else None
        if b is not None:
            try:
                rez_count = sum(1 for a in RUNTIME.list_atoms()
                                if b.resonates_with(a, 0.5))
            except Exception:
                rez_count = 0
        else:
            rez_count = 0
        hud += f"  {BUBBLE_CTX.current_bubble_name}({rez_count})"

    print(hud)

# ── Komendy systemu ───────────────────────────────────────────────────────────

def cmd_ls(args):
    atoms = RUNTIME.matrix.atoms()
    if atoms:
        rows = []
        for a in atoms:
            bar = gfx.progress_bar(a.T, a.T_max, fg=SystemState.color_for(a))
            rows.append(f"{a.id:12} {bar} {a.T:5.1f} {a.state}")
        return gfx.draw_frame("ATOMY", rows)
    return FS.ls(args[0] if args else None)

def cmd_cd(args):    return FS.cd(args[0] if args else "HOT")
def cmd_pwd(args):   return FS.pwd()
def cmd_touch(args): return FS.touch(*args) if args else "TOUCH <id> [S] [E] [T]"
def cmd_rm(args):    return FS.rm(args[0]) if args else "RM <id>"
def cmd_cp(args):    return FS.cp(args[0], args[1]) if len(args) > 1 else "CP <src> <dst>"
def cmd_mv(args):    return FS.mv(args[0], args[1]) if len(args) > 1 else "MV <id> <warstwa>"
def cmd_sete(args):  return FS.setE(args[0], args[1]) if len(args) > 1 else "SETE <id> <E>"
def cmd_find(args):  return FS.find(" ".join(args)) if args else "FIND <q>"

def cmd_monitor(args):
    s = RUNTIME.status_summary()
    return gfx.draw_frame("MONITOR", [f"{k}: {v}" for k, v in s.items()])

def cmd_status(args):
    return gfx.draw_frame("STATUS SYSTEMU", REGISTRY.format_status().split("\n"))

def cmd_syslog(args):
    if not args:
        return gfx.draw_frame("SYSLOG", REGISTRY.format_log(40).split("\n"))
    sub = args[0].upper()
    if sub == "CLEAR":
        REGISTRY.clear_log()
        REGISTRY.log("INFO", "Log wyczyszczony", service="shell")
        return "Log wyczyszczony."
    if sub in ("ERROR", "WARN", "INFO", "DEBUG", "EVENT"):
        n = int(args[1]) if len(args) > 1 else 40
        return gfx.draw_frame(f"SYSLOG [{sub}]",
                               REGISTRY.format_log(n, level=sub).split("\n"))
    try:
        return gfx.draw_frame("SYSLOG", REGISTRY.format_log(int(args[0])).split("\n"))
    except ValueError:
        return "SYSLOG [n | ERROR | WARN | EVENT | clear]"

def cmd_scheduler_cmd(args):
    if not SCHEDULER_LOADED or SCHEDULER is None:
        return "Scheduler niedostepny (brak karmazyn_scheduler.py)"
    return cmd_scheduler(args, SCHEDULER)

def cmd_net_cmd(args):
    if not SCHEDULER_LOADED or NET is None:
        return "Net niedostepny (brak karmazyn_net.py)"
    return cmd_net(args, NET)

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
        atom_id, bubble_name = ((target, BUBBLE_CTX.current_bubble_name)
                                if RUNTIME.has_atom(target) else (None, target))
    else:
        atom_id, bubble_name = args[0], args[1]
    if not bubble_name:
        return "Najpierw otworz babel lub podaj nazwe."
    bubble_id = BUBBLES.find_bubble_by_name(bubble_name) or BUBBLES.create_bubble(bubble_name)
    if atom_id:
        res = BUBBLES.import_to_bubble(bubble_id, atom_id, RUNTIME)
        if res:
            REGISTRY.log("INFO", f"Atom {atom_id} -> {bubble_name}", service="bubbles")
            return f"OK {atom_id} -> {bubble_name}"
        return f"BLAD konsolidacji {atom_id}"
    atoms = RUNTIME.matrix.atoms()
    if not atoms:
        return "Brak atomow."
    count = BUBBLES.snapshot_runtime(bubble_id, atoms)
    return f"OK Snapshot {count} atomow -> {bubble_name}"

def cmd_stabilizuj(args):
    if not args: return "STABILIZUJ <id>"
    if RUNTIME.current_mission and RUNTIME.resources.get("zywica", 0) <= 0:
        return "Brak Zywicy!"
    if RUNTIME.current_mission:
        RUNTIME.resources["zywica"] -= 1
    try:
        RUNTIME.stabilize_atom(args[0])
        return f"Stabilizowano {args[0]} (Zywica: {RUNTIME.resources.get('zywica', 'inf')})"
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
                    bar = gfx.progress_bar(a.T, a.T_max, fg=col)
                    rows.append(f"{a.id:10} {bar} {a.T:5.1f} {a.state}")
                sys.stdout.write("\033[H\033[J")
                sys.stdout.write(gfx.draw_frame("OBSERWACJA", rows) + "\n")
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
    return gfx.draw_frame(f"ATOM {atom.id}", [
        f"S: {atom.S}   E: {atom.E}",
        f"T: {atom.T:.1f}   Stan: {atom.state}   Wiek: {atom.age}",
        gfx.progress_bar(atom.T, atom.T_max, fg=col),
    ])

# ── Komendy skryptów ──────────────────────────────────────────────────────────

def cmd_run(args):
    if not KARM_LOADED: return "BLAD karm nie zaladowany"
    if not args: return "RUN <plik.karm>"
    if not os.path.isfile(args[0]): return f"BLAD brak pliku: {args[0]}"
    try:
        REGISTRY.log("INFO", f"RUN {args[0]}", service="karm")
        KARM.run_file(args[0])
        return f"OK {args[0]}"
    except Exception as e:
        REGISTRY.log("ERROR", f"RUN {args[0]}: {e}", service="karm")
        return f"BLAD {e}"

def cmd_compile(args):
    if not KARM_LOADED: return "BLAD karm nie zaladowany"
    if not args: return "COMPILE <plik.karm>"
    if not os.path.isfile(args[0]): return f"BLAD brak pliku: {args[0]}"
    try:
        program = parse_file(args[0])
        lines = [f"AST: {args[0]}", "=" * 50]
        for i, stmt in enumerate(program.statements, 1):
            fields = {k: v for k, v in stmt.__dict__.items()
                      if not k.startswith('_')}
            lines.append(f"{i}. {type(stmt).__name__}: {fields}")
        return "\n".join(lines)
    except Exception as e:
        return f"BLAD {e}"

def cmd_lua(args):
    if not LUA_AVAILABLE: return "BLAD lua niedostepny"
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
    REGISTRY.log("INFO", f"LUA {filepath}", service="lua")
    r = LUA_EXECUTOR.run_file(filepath, args=args[1:])
    return f"BLAD {r}" if isinstance(r, str) and r.startswith("Blad") else f"OK {filepath}"

def cmd_nooedit(args):
    if not NOOEDIT_LOADED: return "BLAD Nooedit.py nie znaleziono"
    REGISTRY.log("INFO", f"NOOEDIT {args[0] if args else '?'}", service="nooedit")
    return _nooedit_cmd(args, runtime=RUNTIME)

# ── Pomoc i wyjście ───────────────────────────────────────────────────────────

def cmd_help(args):
    if not args:
        lines = ["Dostepne kategorie:"]
        for cat in registry.get_categories():
            lines.append(f"  {cat}")
        lines += ["", "HELP <komenda|kategoria>"]
        return "\n".join(lines)
    topic     = args[0].upper()
    topic_low = args[0].lower()
    if topic_low in registry.get_categories():
        cmds  = registry.list_commands(category=topic_low)
        lines = [f"Kategoria '{topic_low}':"]
        for cname in cmds:
            c = registry.get(cname)
            lines.append(f"  {cname:<22} {c.help_text[:48]}")
        return "\n".join(lines)
    cmd = registry.get(topic)
    return cmd.format_help() if cmd else f"Nie znaleziono: {args[0]}"

def cmd_exit(args):
    global _observer_running
    _observer_running = False

    # Scheduler — zapisz i zatrzymaj
    if SCHEDULER_LOADED and SCHEDULER is not None:
        SCHEDULER.save()
        SCHEDULER.stop()
        REGISTRY.log("INFO", "Scheduler zatrzymany", service="scheduler")

    # Radio — zatrzymaj odtwarzanie i wątki AudioDaemon
    if RADIO_LOADED and RADIO is not None:
        if RADIO.is_playing():
            RADIO.stop()
        if RADIO._audio is not None:
            RADIO._audio.shutdown()   # join() wątków meta i watchdog
            REGISTRY.log("INFO", "AudioDaemon zatrzymany", service="audio")

    REGISTRY.log("INFO", f"Shell zamkniety po {REGISTRY.uptime_str()}", service="shell")
    RUNTIME.stop_loop()
    BUBBLES.save_all()
    sys.exit(0)

# ── Edytor emanacji ───────────────────────────────────────────────────────────

def cmd_emanation_edit(args, current_bubble, runtime, resolver_func,
                       bubble_getter, bubble_importer):
    if len(args) < 2:
        print("EDIT <babel> <atom_id>")
        return
    bubble_alias, atom_id = args[0], args[1]
    target_bubble_id = resolver_func(bubble_alias)
    if not target_bubble_id:
        print(f"Nieznany babel: {bubble_alias}")
        return
    existing_content = ""
    for a in bubble_getter(target_bubble_id):
        a_id = a.get('id') if isinstance(a, dict) else getattr(a, 'id', None)
        if str(a_id) == atom_id:
            existing_content = (a.get('E') if isinstance(a, dict)
                                else getattr(a, 'E', ""))
            break
    editor = EmanationEditor(target_name=f"{bubble_alias}::{atom_id}",
                             initial_content=existing_content)
    while True:
        new_content = editor.run()
        if new_content is None:
            print("Brak zmian.")
            break
        if not new_content.strip():
            print("BLAD: Pusta Emanacja.")
            input("Enter aby kontynuowac...")
            editor = EmanationEditor(
                target_name=f"{bubble_alias}::{atom_id} [PUSTA]",
                initial_content=new_content)
            continue
        buffer_id = f"__edit_buffer_{atom_id}_{int(time.time())}"
        try:
            runtime.create_atom(buffer_id, "LUA_SCRIPT", new_content, 100.0)
            result = bubble_importer(target_bubble_id, buffer_id, runtime,
                                     target_name=atom_id)
            if isinstance(result, dict) and result.get("status") == "reflected":
                coh = result.get("coherence", 0.0)
                REGISTRY.log("WARN",
                             f"Odbicie: {bubble_alias}::{atom_id} coh={coh:.2f}",
                             service="bubbles")
                print(f"ODBICIE coh={coh:.2f}")
                if input("Operator R? [t/n]: ").strip().lower() != 't':
                    break
                editor = EmanationEditor(
                    target_name=f"{bubble_alias}::{atom_id} [POPRAWKA]",
                    initial_content=new_content)
            else:
                REGISTRY.log("INFO",
                             f"Emanacja: {bubble_alias}::{atom_id}",
                             service="bubbles")
                print("Stabilizacja zakonczona.")
                break
        except Exception as e:
            REGISTRY.log("ERROR", f"Konsolidacja {buffer_id}: {e}",
                         service="bubbles")
            print(f"Blad: {e}")
            if input("Ponownie? [t/n]: ").strip().lower() != 't':
                break
            editor = EmanationEditor(
                target_name=f"{bubble_alias}::{atom_id} [BLAD]",
                initial_content=new_content)
        finally:
            try:
                runtime.delete_atom(buffer_id)
            except Exception:
                pass

def cmd_emanation_edit_wrapper(args):
    return cmd_emanation_edit(
        args, BUBBLE_CTX.current_bubble_id, RUNTIME,
        FS.resolve_alias, BUBBLES.get_active_atoms, BUBBLES.import_to_bubble,
    )

# ── Rejestracja komend ────────────────────────────────────────────────────────

registry = CommandRegistry()

def reg(name, handler, help_text="", category="general", args_schema=None):
    registry.register(Command(name, handler, help_text, category, args_schema or []))

# Nawigacja
reg("LS",             cmd_ls,           "Listuje atomy lub FS",        category="navigation")
reg("CD",             cmd_cd,           "Zmienia warstwe",             category="navigation")
reg("PWD",            cmd_pwd,          "Biezaca warstwa",             category="navigation")

# Atomy
reg("TOUCH",          cmd_touch,        "Tworzy atom",                 category="atoms",
    args_schema=[make_arg_schema("id", True),  make_arg_schema("S", False),
                 make_arg_schema("E", False),  make_arg_schema("T", False, "float")])
reg("RM",             cmd_rm,           "Usuwa atom",                  category="atoms",
    args_schema=[make_arg_schema("id", True)])
reg("CP",             cmd_cp,           "Kopiuje atom",                category="atoms",
    args_schema=[make_arg_schema("src", True), make_arg_schema("dst", True)])
reg("MV",             cmd_mv,           "Przenosi atom",               category="atoms",
    args_schema=[make_arg_schema("id", True),  make_arg_schema("warstwa", True)])
reg("SETE",           cmd_sete,         "Zmienia emanacje",            category="atoms",
    args_schema=[make_arg_schema("id", True),  make_arg_schema("E", True)])
reg("FIND",           cmd_find,         "Szuka w atomach",             category="atoms",
    args_schema=[make_arg_schema("q", True)])
reg("CONSOLIDATE",    cmd_consolidate,  "Atom -> babel",               category="atoms",
    args_schema=[make_arg_schema("id", True),  make_arg_schema("babel", False)])
reg("STABILIZUJ",     cmd_stabilizuj,   "Podnosi temperature",         category="atoms",
    args_schema=[make_arg_schema("id", True)])
reg("DOTKNIJ PUSTKI", cmd_dotknij_pustki, "Obniza temperature",        category="atoms",
    args_schema=[make_arg_schema("id", True)])
reg("ATOM STATUS",    cmd_atom_status,  "Szczegoly atomu",             category="atoms",
    args_schema=[make_arg_schema("id", True)])

# Bąble
reg("BUBBLE",      cmd_bubble,                 "Babble [LS|NEW|STATUS|TICK|RESONATE|DECAY|COPY|PASTE]",
                                                                        category="bubbles")
reg("BUBBLE_EDIT", cmd_edit,                   "Edytor babli",         category="bubbles")
reg("EDIT",        cmd_emanation_edit_wrapper, "Edytor emanacji",      category="bubbles")
reg("IMPORT",      cmd_import,                 "Importuje tekst",      category="bubbles")
reg("VIEW",        cmd_view,                   "Pokazuje aktywny babel",category="bubbles")
reg("GALLERY",     cmd_gallery,                "Stan semantyczny babli",category="bubbles")
reg("EXPORT",      cmd_export,                 "Eksportuje .soul JSONL",category="bubbles")
reg("NOOEDIT",     cmd_nooedit,                "NooEdit dla Babla",    category="bubbles",
    args_schema=[make_arg_schema("label", True)])

# Skrypty
reg("RUN",     cmd_run,     "Wykonuje plik .karm",      category="scripting",
    args_schema=[make_arg_schema("plik", True)])
reg("COMPILE", cmd_compile, "AST pliku .karm",          category="scripting",
    args_schema=[make_arg_schema("plik", True)])
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

# Sieć
reg("NET", cmd_net_cmd, "Siec [FETCH|GIT|LLM|FTP|PUSH|PULL|STATUS]",           category="network")

# Media
reg("RADIO",  cmd_radio_cmd,  "Radio [PLAY|STOP|LS|ADD|FAV|VOL|NOW|SEARCH]",   category="media")
reg("AUDIO",  cmd_audio_cmd,  "AudioDaemon [STATUS|PAUSE|VOL|STOP|INFO|EVENTS]",category="media")
reg("LUNETA", cmd_luneta_cmd, "Luneta [<url>|BACK|FORWARD|LINKS|FOLLOW|FIND|SCROLL|BM|DOM]",
                                                                                category="media")
reg("L",      cmd_luneta_cmd, "Alias: LUNETA",                                  category="media")
reg("DOM",    cmd_dom_cmd,    "DOMMapper [MAP|OUTLINE|READER|FIND|PHI|STATS]",  category="media")

# ── Autocomplete ──────────────────────────────────────────────────────────────

def completer(text, state):
    line   = readline.get_line_buffer()
    begidx = readline.get_begidx()
    try:
        tokens = shlex.split(line[:begidx])
    except ValueError:
        tokens = []
    cur = line[begidx:readline.get_endidx()]

    if len(tokens) == 0:
        matches = [c for c in registry.list_commands()
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
        cands = [c for c in registry.list_commands() if c.startswith(first + " ")]
        words = [c.split()[1] for c in cands]
        m = [w for w in words if w.lower().startswith(cur.lower())]
        return m[state] if state < len(m) else None

    return None

readline.set_completer(completer)
readline.parse_and_bind("tab: complete")

# ── Główna pętla ──────────────────────────────────────────────────────────────

def main():
    # Banner startowy
    banner_lines = REGISTRY.startup_report()
    if RADIO_LOADED:
        banner_lines.append(
            f"Radio:   {RADIO._audio._mpv_path or 'brak mpv — pkg install mpv'}"
        )
    if LUNETA_LOADED:
        dom_status = "aktywny" if LUNETA_INST._has_dom else "brak karmazyn_dom.py"
        banner_lines.append(f"Luneta:  DOMMapper {dom_status}")
    print(gfx.draw_frame("KARMAZYN OS", banner_lines, style="phi_core"))

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
        FS.set_config_bubble(config_bubble_id)
        REGISTRY.log("INFO", f"Konfiguracja: {config_bubble_id}", service="shell")
        for a in BUBBLES.get_active_atoms(config_bubble_id):
            s_val = a.get('S') if isinstance(a, dict) else a.S
            if s_val == "BIN":
                cmd_id = a.get('id') if isinstance(a, dict) else a.id
                target = a.get('E') if isinstance(a, dict) else a.E

                def make_handler(t):
                    return lambda args: (LUA_EXECUTOR.run_file(t)
                                         if t.endswith('.lua')
                                         else LUA_EXECUTOR.run_bubble(t))

                registry.register(Command(
                    cmd_id.upper(), make_handler(target),
                    f"Narzedzie: {target}", "tools",
                ))
                REGISTRY.log("INFO", f"BIN: {cmd_id} -> {target}", service="shell")

    REGISTRY.log("INFO", "Shell gotowy", service="shell")

    while True:
        try:
            line = input(f"{theme.ansi_fg('phi_signal')}ksh>{theme.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nZamykanie...")
            cmd_exit([])
            break
        if not line:
            continue
        result = process_command(line)
        if result:
            print(result)
        print_hud()


def process_command(line: str) -> str:
    try:
        parts = shlex.split(line)
    except ValueError as e:
        return f"Blad skladni: {e}"
    if not parts:
        return ""

    verb1 = parts[0].upper()
    if len(parts) > 1:
        verb2 = f"{verb1} {parts[1].upper()}"
        cmd   = registry.get(verb2)
        args  = parts[2:] if cmd else None
        if not cmd:
            cmd  = registry.get(verb1)
            args = parts[1:]
    else:
        cmd  = registry.get(verb1)
        args = []

    if cmd is None:
        lua_path = os.path.join(
            "lua_bin",
            verb1.lower() + ("" if verb1.lower().endswith(".lua") else ".lua"),
        )
        if LUA_AVAILABLE and os.path.isfile(lua_path):
            try:
                r = LUA_EXECUTOR.run_file(lua_path, args=parts[1:])
                return r if r else ""
            except Exception as e:
                REGISTRY.log("ERROR", f"LUA {lua_path}: {e}", service="lua")
                return f"[BLAD LUA] {e}"
        REGISTRY.log("WARN", f"Nieznana: {verb1}", service="shell")
        return f"[BLAD] Nieznana komenda: {verb1}"

    ok, err = cmd.validate_args(args)
    if not ok:
        return f"[BLAD] {err}"
    try:
        return cmd.handler(args) or ""
    except Exception as e:
        REGISTRY.log("ERROR", f"{verb1}: {e}", service="shell")
        return f"[BLAD] {e}"


if __name__ == "__main__":
    main()