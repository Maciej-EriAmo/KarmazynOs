#!/usr/bin/env python3
"""
KarmazynOS — Shell (ksh) v3.0
Zrefaktorowany z użyciem Command Engine v1.
"""

import os
import sys
import time
import threading
import readline
import shlex
from typing import Optional

from runtime import SanctuaryRuntime, SystemState
from karmazyn_fs import KarmazynFS
from karmazyn_ui import theme, gfx

# Bąble
from bedit import KarmazynIntegration as BubbleRuntime
from bubble_commands import (
    CTX as BUBBLE_CTX,
    cmd_edit, cmd_import, cmd_gallery, cmd_export,
    init as bubble_init,
)

# KarmazynScript
try:
    from karmazyn_lang import KarmazynExecutor, parse_file
    KARM_LOADED = True
except ImportError:
    KARM_LOADED = False

# Lua
try:
    from karmazyn_lua import LuaExecutor
    LUA_AVAILABLE = True
except ImportError:
    LUA_AVAILABLE = False

# Command Engine
from command_engine import Command, CommandRegistry, make_arg_schema

# ----------------------------------------------------------------------
# Inicjalizacja systemu i wiązanie spójności
# ----------------------------------------------------------------------
RUNTIME = SanctuaryRuntime()
BUBBLES = BubbleRuntime()
bubble_init(BUBBLES, RUNTIME)

# Wstrzykujemy BUBBLES do FS, aby umożliwić nawigację po bąblach i aliasy
FS = KarmazynFS(RUNTIME, bubbles_runtime=BUBBLES)

KARM = KarmazynExecutor(RUNTIME) if KARM_LOADED else None

if LUA_AVAILABLE:
    LUA_EXECUTOR = LuaExecutor(RUNTIME)
    # DEPENDENCY INJECTION: Wiążemy środowisko Lua z usługami powłoki
    LUA_EXECUTOR.bind_system_services(
        resolver_func=FS.resolve_alias,
        importer_func=BUBBLES.import_to_bubble
    )
else:
    LUA_EXECUTOR = None

RUNTIME.start_loop()

# ----------------------------------------------------------------------
# HUD (z informacją o stanie pętli runtime)
# ----------------------------------------------------------------------
def print_hud():
    loop_status = ""
    # Używamy metody is_alive() zamiast _loop_thread – czystsza enkapsulacja
    if hasattr(RUNTIME, 'is_alive') and not RUNTIME.is_alive():
        loop_status = f"{theme.ansi_fg('phi_ghost')} [RUNTIME DEAD]{theme.RESET}"

    s = RUNTIME.status_summary()
    hud = (f"{theme.ansi_fg('phi_stable')}HOT:{s['HOT']}{theme.RESET} "
           f"{theme.ansi_fg('phi_thermal')}WARM:{s['WARM']}{theme.RESET} "
           f"{theme.ansi_fg('phi_signal')}COLD:{s['COLD']}{theme.RESET} "
           f"{theme.ansi_fg('phi_ghost')}TOMB:{s['TOMB']}{theme.RESET}{loop_status}")

    if BUBBLE_CTX.current_bubble_name:
        atoms = BUBBLES.get_active_atoms(BUBBLE_CTX.current_bubble_id) if BUBBLE_CTX.current_bubble_id else []
        bubble = BUBBLES.get_bubble(BUBBLE_CTX.current_bubble_id)
        media = ""
        if bubble:
            if hasattr(bubble, 'manifest'):
                stats = bubble.manifest.get('media_stats', {})
            elif isinstance(bubble, dict):
                stats = bubble.get('bubble', {}).get('manifest', {}).get('media_stats', {})
            else:
                stats = {}
            parts = []
            if stats.get('image', 0): parts.append(f"🖼{stats['image']}")
            if stats.get('audio', 0): parts.append(f"🎵{stats['audio']}")
            if stats.get('document', 0): parts.append(f"📄{stats['document']}")
            if parts: media = f" [{','.join(parts)}]"
        hud += f"  🫧{BUBBLE_CTX.current_bubble_name}({len(atoms)}){media}"
    print(hud)

# ----------------------------------------------------------------------
# HANDLERY KOMEND (istniejące, bez zmian)
# ----------------------------------------------------------------------
def cmd_ls(args):
    atoms = RUNTIME.matrix.atoms()
    if atoms:
        rows = []
        for a in atoms:
            bar = gfx.progress_bar(a.T, a.T_max, fg=SystemState.color_for(a))
            rows.append(f"{a.id:12} {bar} {a.T:5.1f}° {a.state}")
        return gfx.draw_frame("ATOMY", rows)
    return FS.ls(args[0] if args else None)

def cmd_cd(args):
    return FS.cd(args[0] if args else "HOT")

def cmd_pwd(args):
    return FS.pwd()

def cmd_touch(args):
    return FS.touch(*args) if len(args) >= 1 else "TOUCH <id> [S] [E] [T]"

def cmd_rm(args):
    return FS.rm(args[0]) if args else "RM <id>"

def cmd_cp(args):
    return FS.cp(args[0], args[1]) if len(args) > 1 else "CP <src> <dst>"

def cmd_mv(args):
    return FS.mv(args[0], args[1]) if len(args) > 1 else "MV <id> <warstwa>"

def cmd_sete(args):
    return FS.setE(args[0], args[1]) if len(args) > 1 else "SETE <id> <E>"

def cmd_find(args):
    return FS.find(" ".join(args)) if args else "FIND <zapytanie>"

def cmd_monitor(args):
    s = RUNTIME.status_summary()
    return gfx.draw_frame("MONITOR", [f"{k}: {v}" for k, v in s.items()])

def cmd_consolidate(args):
    if not args:
        return "CONSOLIDATE <id_lub_nazwa_bąbla> [id_atomu]"

    # Obsługa przypadku: CONSOLIDATE <nazwa_bąbla> (konsoliduje wszystkie aktywne atomy z Φ do bąbla)
    # Lub: CONSOLIDATE <atom_id> <nazwa_bąbla>

    if len(args) == 1:
        # Jeśli tylko jeden argument, sprawdzamy czy to id atomu w Φ czy nazwa bąbla
        target = args[0]
        if RUNTIME.has_atom(target):
            atom_id = target
            bubble_name = BUBBLE_CTX.current_bubble_name
        else:
            bubble_name = target
            atom_id = None
    else:
        atom_id = args[0]
        bubble_name = args[1]

    if not bubble_name:
        return "❌ Najpierw otwórz bąbel (EDIT <nazwa>) lub podaj nazwę bąbla."

    bubble_id = BUBBLES.find_bubble_by_name(bubble_name)
    if not bubble_id:
        bubble_id = BUBBLES.create_bubble(bubble_name)

    if atom_id:
        res = BUBBLES.import_to_bubble(bubble_id, atom_id, RUNTIME)
        if res:
            return f"✅ Atom {atom_id} skonsolidowany do bąbla {bubble_name} ({bubble_id})"
        return f"❌ Nie udało się skonsolidować atomu {atom_id}"
    else:
        # Konsolidacja wszystkich atomów (snapshot)
        atoms = RUNTIME.matrix.atoms()
        if not atoms:
            return "Brak atomów w Φ do konsolidacji."
        count = BUBBLES.snapshot_runtime(bubble_id, atoms)
        return f"✅ Skonsolidowano {count} atomów do bąbla {bubble_name}"

def cmd_stabilizuj(args):
    if not args:
        return "STABILIZUJ <id>"
    if RUNTIME.current_mission and RUNTIME.resources.get("żywica", 0) <= 0:
        return "Brak Żywicy!"
    if RUNTIME.current_mission:
        RUNTIME.resources["żywica"] -= 1
    try:
        RUNTIME.stabilize_atom(args[0])
        zywica = RUNTIME.resources.get("żywica", "∞")
        return f"Stabilizowano {args[0]} (Żywica: {zywica})"
    except ValueError as e:
        return str(e)

def cmd_dotknij_pustki(args):
    if not args:
        return "DOTKNIJ PUSTKI <id>"
    try:
        RUNTIME.corrupt_atom(args[0], 25)
        atom = RUNTIME.get_atom(args[0])
        if atom:
            return f"Dotknięto Pustką {args[0]}. T={atom.T:.1f}"
        return f"Dotknięto {args[0]}"
    except ValueError as e:
        return str(e)

# Asynchroniczna wersja OBSERWUJ (nie blokuje shella)
_observer_running = False

def cmd_obserwuj(args):
    global _observer_running
    if _observer_running:
        return "Obserwacja już trwa."
    _observer_running = True

    def _observe():
        global _observer_running
        try:
            while _observer_running:
                rows = []
                for a in RUNTIME.matrix.atoms():
                    if a.T > 70: color = "phi_thermal"
                    elif a.T > 30: color = "phi_signal"
                    else: color = "phi_decay"
                    bar = gfx.progress_bar(a.T, a.T_max, fg=color)
                    rows.append(f"{a.id:10} {bar} {a.T:5.1f}° {a.state}")
                sys.stdout.write("\033[H\033[J")
                sys.stdout.write(gfx.draw_frame("OBSERWACJA", rows) + "\n")
                sys.stdout.flush()
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            _observer_running = False

    threading.Thread(target=_observe, daemon=True).start()
    return "Obserwacja uruchomiona. Wpisz dowolną komendę (np. LS) aby zakończyć."

def cmd_atom_status(args):
    if not args:
        return "ATOM STATUS <id>"
    atom = RUNTIME.get_atom(args[0])
    if not atom:
        return "Atom nie istnieje."
    if atom.T > 70: color = "phi_thermal"
    elif atom.T > 30: color = "phi_signal"
    else: color = "phi_decay"
    return gfx.draw_frame(f"ATOM {atom.id}", [
        f"S: {atom.S}   E: {atom.E}",
        f"T: {atom.T:.1f}   Stan: {atom.state}",
        f"Wiek: {atom.age}",
        gfx.progress_bar(atom.T, atom.T_max, fg=color),
    ])

def cmd_run(args):
    if not KARM_LOADED:
        return "❌ karmazyn_lang.py nie znaleziony (pip install lark)"
    if not args:
        return "RUN <plik.karm>"
    if not os.path.isfile(args[0]):
        return f"❌ Plik: {args[0]}"
    try:
        KARM.run_file(args[0])
        return f"✅ {args[0]}"
    except Exception as e:
        return f"❌ {e}"

def cmd_compile(args):
    if not KARM_LOADED:
        return "❌ karmazyn_lang.py nie znaleziony"
    if not args:
        return "COMPILE <plik.karm>"
    if not os.path.isfile(args[0]):
        return f"❌ Plik: {args[0]}"
    try:
        program = parse_file(args[0])
        lines = [f"📜 AST: {args[0]}", "=" * 50]
        for i, stmt in enumerate(program.statements, 1):
            name = type(stmt).__name__
            fields = {k: v for k, v in stmt.__dict__.items() if not k.startswith('_')}
            lines.append(f"{i}. {name}: {fields}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ {e}"

def cmd_lua(args):
    if not LUA_AVAILABLE:
        return "❌ Moduł Lua nie jest dostępny (brak lupa lub błąd importu)."
    if not args:
        return "Użycie: LUA <plik.lua> lub LUA BUBBLE <nazwa_bąbla>"
    if args[0].upper() == "BUBBLE":
        if len(args) < 2:
            return "❌ Podaj nazwę bąbla: LUA BUBBLE <nazwa_bąbla>"
        result = LUA_EXECUTOR.run_bubble(args[1])
        if isinstance(result, str) and result.startswith("Błąd"):
            return f"❌ {result}"
        return f"✅ Wykonano bąbel Lua: {args[1]}"
    filepath = args[0]
    result = LUA_EXECUTOR.run_file(filepath)
    if isinstance(result, str) and result.startswith("Błąd"):
        return f"❌ {result}"
    return f"✅ Wykonano plik Lua: {filepath}"

def cmd_help(args):
    """Wyświetla pomoc. Użycie: HELP [komenda|kategoria]"""
    if not args:
        lines = ["Dostępne kategorie:"]
        for cat in registry.get_categories():
            lines.append(f"  {cat}")
        lines.append("Użyj HELP <komenda> aby uzyskać szczegóły.")
        lines.append("Użyj HELP <kategoria> aby wyświetlić komendy w danej kategorii.")
        return "\n".join(lines)
    topic = args[0].upper()
    cmd = registry.get(topic)
    if cmd:
        return cmd.format_help()
    if topic in registry.get_categories():
        cmds = registry.list_commands(category=topic)
        lines = [f"Komendy w kategorii '{topic}':"]
        for cname in cmds:
            c = registry.get(cname)
            lines.append(f"  {cname:<20} – {c.help_text[:50]}")
        return "\n".join(lines)
    return f"Nie znaleziono komendy ani kategorii: {topic}"

def cmd_exit(args):
    """Zatrzymuje pętlę, zapisuje stan i kończy pracę powłoki."""
    global _observer_running
    _observer_running = False
    RUNTIME.stop_loop()
    BUBBLES.save_all()
    sys.exit(0)

# ----------------------------------------------------------------------
# REJESTRACJA KOMEND (Command Engine)
# ----------------------------------------------------------------------
registry = CommandRegistry()

def reg(name: str, handler, help_text: str = "", category: str = "general", args_schema=None):
    registry.register(Command(name, handler, help_text, category, args_schema or []))

# Komendy jedno- i dwuczłonowe rejestrujemy z pełną nazwą
reg("LS", cmd_ls, "Listuje atomy lub zawartość systemu plików", category="navigation")
reg("CD", cmd_cd, "Zmienia bieżącą warstwę termodynamiczną (HOT/WARM/COLD)", category="navigation")
reg("PWD", cmd_pwd, "Pokazuje bieżącą warstwę", category="navigation")
reg("TOUCH", cmd_touch, "Tworzy nowy atom", category="atoms",
    args_schema=[make_arg_schema("id", required=True),
                 make_arg_schema("S", required=False),
                 make_arg_schema("E", required=False),
                 make_arg_schema("T", required=False, arg_type="float")])
reg("RM", cmd_rm, "Usuwa atom (przenosi do TOMB)", category="atoms",
    args_schema=[make_arg_schema("id", required=True)])
reg("CP", cmd_cp, "Kopiuje atom", category="atoms",
    args_schema=[make_arg_schema("src", required=True),
                 make_arg_schema("dst", required=True)])
reg("MV", cmd_mv, "Przenosi atom między warstwami", category="atoms",
    args_schema=[make_arg_schema("id", required=True),
                 make_arg_schema("warstwa", required=True)])
reg("SETE", cmd_sete, "Zmienia emanację atomu", category="atoms",
    args_schema=[make_arg_schema("id", required=True),
                 make_arg_schema("E", required=True)])
reg("FIND", cmd_find, "Szuka tekstu w atomach", category="atoms",
    args_schema=[make_arg_schema("zapytanie", required=True)])
reg("MONITOR", cmd_monitor, "Wyświetla podsumowanie stanów atomów", category="system")
reg("CONSOLIDATE", cmd_consolidate, "Przenosi atom do bąbla (trwały zapis)", category="atoms",
    args_schema=[make_arg_schema("id", required=True),
                 make_arg_schema("nazwa_bąbla", required=False)])
reg("STABILIZUJ", cmd_stabilizuj, "Podnosi temperaturę atomu", category="atoms",
    args_schema=[make_arg_schema("id", required=True)])
reg("DOTKNIJ PUSTKI", cmd_dotknij_pustki, "Obniża temperaturę atomu", category="atoms",
    args_schema=[make_arg_schema("id", required=True)])
reg("OBSERWUJ", cmd_obserwuj, "Uruchamia dynamiczny podgląd atomów (asynchroniczny)", category="system")
reg("ATOM STATUS", cmd_atom_status, "Wyświetla szczegóły atomu", category="atoms",
    args_schema=[make_arg_schema("id", required=True)])
reg("EDIT", cmd_edit, "Uruchamia edytor bąbli", category="bubbles")
reg("IMPORT", cmd_import, "Importuje plik lub katalog do bąbla", category="bubbles")
reg("GALLERY", cmd_gallery, "Pokazuje multimedia w bąblu", category="bubbles")
reg("EXPORT", cmd_export, "Eksportuje multimedia z bąbla", category="bubbles")
reg("RUN", cmd_run, "Wykonuje plik .karm (KarmazynScript)", category="scripting",
    args_schema=[make_arg_schema("plik", required=True)])
reg("COMPILE", cmd_compile, "Pokazuje AST pliku .karm", category="scripting",
    args_schema=[make_arg_schema("plik", required=True)])
reg("LUA", cmd_lua, "Wykonuje plik .lua lub bąbel Lua", category="scripting")
reg("HELP", cmd_help, "Wyświetla pomoc", category="system")
reg("EXIT", cmd_exit, "Kończy pracę powłoki", category="system")

# ----------------------------------------------------------------------
# AUTOCOMPLETE (kontekstowe, wspiera komendy dwuczłonowe)
# ----------------------------------------------------------------------
def completer(text, state):
    line = readline.get_line_buffer()
    begidx = readline.get_begidx()
    endidx = readline.get_endidx()
    try:
        tokens = shlex.split(line[:begidx])
    except ValueError:
        tokens = []
    current_token = line[begidx:endidx]

    # Brak tokenów – podpowiadamy pierwsze słowo komendy
    if len(tokens) == 0:
        matches = registry.complete(current_token, state)
        if matches is not None:
            return matches
    # Jeden token – podpowiadamy drugie słowo dla komend dwuczłonowych
    elif len(tokens) == 1:
        first = tokens[0].upper()
        full_candidates = [cmd for cmd in registry.list_commands() if cmd.startswith(first + " ")]
        second_words = [cmd.split()[1] for cmd in full_candidates]
        matches = [w for w in second_words if w.lower().startswith(current_token.lower())]
        if state < len(matches):
            return matches[state]
    # Dla dalszych argumentów – na razie brak podpowiedzi
    return None

readline.set_completer(completer)
readline.parse_and_bind("tab: complete")

# ----------------------------------------------------------------------
# GŁÓWNA PĘTLA
# ----------------------------------------------------------------------
def main():
    print(gfx.draw_frame(
        "KARMAZYN OS",
        [
            "Shell v3.0 — Command Engine",
            "Tab = kontekstowe autouzupełnianie",
            "HELP - pomoc",
        ],
        style="phi_core",
    ))

    bubbles = BUBBLES.list_bubbles()
    if bubbles:
        total = sum(b['active_atoms'] for b in bubbles)
        print(f"🫧 {len(bubbles)} bąbli ({total} atomów)", end="")
        imgs = sum(b.get('media_stats', {}).get('image', 0) for b in bubbles)
        if imgs:
            print(f", 🖼{imgs} obrazów", end="")
        print()

    if KARM_LOADED:
        print("📜 KarmazynScript gotowy")
    if LUA_AVAILABLE:
        print("🌙 Środowisko LuaJIT gotowe")

    # Sekcja Auto-Discovery konfiguracji
    config_bubble_id = None
    all_bubbles = BUBBLES.list_bubbles()
    for b in all_bubbles:
        if b.get('label') == 'sys_config' or 'sys_config' in str(b.get('id', '')):
            config_bubble_id = b['id']
            break

    if config_bubble_id:
        FS.set_config_bubble(config_bubble_id)
        print(f"⚙️ System: Wczytano konfigurację z bąbla {config_bubble_id}")

        # Rejestracja narzędzi: Szukamy atomów S="BIN" (E = ścieżka .lua lub id bąbla)
        config_atoms = BUBBLES.get_active_atoms(config_bubble_id)
        for a in config_atoms:
            s_val = a.get('S') if isinstance(a, dict) else a.S
            if s_val == "BIN":
                cmd_id = a.get('id') if isinstance(a, dict) else a.id
                cmd_name = cmd_id.upper()
                target = a.get('E') if isinstance(a, dict) else a.E

                # Tworzymy domknięcie (closure) dla handlera
                def create_lua_handler(t):
                    return lambda args: LUA_EXECUTOR.run_file(t) if t.endswith('.lua') else LUA_EXECUTOR.run_bubble(t)

                registry.register(Command(
                    cmd_name,
                    create_lua_handler(target),
                    f"Narzędzie użytkownika: {target}",
                    "tools"
                ))
        print(f"🔧 Narzędzia systemowe zarejestrowane.")
    print()

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
        return f"Błąd składni: {e}"

    if not parts:
        return ""

    # Rozpoznanie komendy (jedno- lub dwuczłonowa)
    verb1 = parts[0].upper()
    if len(parts) > 1:
        verb2 = f"{verb1} {parts[1].upper()}"
        cmd = registry.get(verb2)
        if cmd:
            args = parts[2:]
        else:
            cmd = registry.get(verb1)
            args = parts[1:]
    else:
        cmd = registry.get(verb1)
        args = parts[1:]

    if cmd is None:
        return f"{theme.ansi_fg('phi_bright')}[BŁĄD]{theme.RESET} Nieznana komenda: {verb1}"

    # Walidacja argumentów
    ok, err_msg = cmd.validate_args(args)
    if not ok:
        return f"{theme.ansi_fg('phi_bright')}[BŁĄD]{theme.RESET} {err_msg}"

    try:
        result = cmd.handler(args)
    except Exception as e:
        result = f"{theme.ansi_fg('phi_bright')}[BŁĄD]{theme.RESET} {e}"

    return result if result else ""


if __name__ == "__main__":
    main()