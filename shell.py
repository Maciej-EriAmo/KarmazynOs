#!/usr/bin/env python3
"""
KarmazynOS — Shell (ksh) v1.4
Reaktywna powłoka z trwałym HUD-em, autouzupełnianiem i spójnym kontraktem komend.
"""
import os, sys, time, subprocess, threading, readline
from typing import Optional, List
from runtime import SanctuaryRuntime, SystemState
from karmazyn_fs import KarmazynFS
from karmazyn_ui import theme, gfx

# ═══════════════════════════════════════════
# INICJALIZACJA SYSTEMU
# ═══════════════════════════════════════════
RUNTIME = SanctuaryRuntime()
FS = KarmazynFS(RUNTIME)
RUNTIME.start_loop()

# ═══════════════════════════════════════════
# TRWAŁY HUD (osobny wątek)
# ═══════════════════════════════════════════
_last_hud = ""
def hud_line() -> str:
    s = RUNTIME.status_summary()
    return (f"{theme.ansi_fg('phi_stable')}HOT:{s['HOT']}{theme.RESET} "
            f"{theme.ansi_fg('phi_thermal')}WARM:{s['WARM']}{theme.RESET} "
            f"{theme.ansi_fg('phi_signal')}COLD:{s['COLD']}{theme.RESET} "
            f"{theme.ansi_fg('phi_ghost')}TOMB:{s['TOMB']}{theme.RESET}")

def hud_thread():
    global _last_hud
    while True:
        line = hud_line()
        if line != _last_hud:
            sys.stdout.write("\0337")          # zapamiętaj kursor
            sys.stdout.write("\033[999;0H")    # idź na dół terminala
            sys.stdout.write("\033[K")         # wyczyść linię
            sys.stdout.write(line)
            sys.stdout.write("\0338")          # przywróć kursor
            sys.stdout.flush()
            _last_hud = line
        time.sleep(0.5)

threading.Thread(target=hud_thread, daemon=True).start()

# ═══════════════════════════════════════════
# AUTOCOMPLETE
# ═══════════════════════════════════════════
COMMAND_LIST = [
    "LS", "CD", "PWD", "TOUCH", "RM", "CP", "MV", "SETE", "FIND",
    "MONITOR", "STABILIZUJ", "DOTKNIJ PUSTKI", "ATOM STATUS",
    "OBSERWUJ", "KRONIKA", "EDIT", "EXIT"
]
def completer(text, state):
    options = [c for c in COMMAND_LIST if c.startswith(text.upper())]
    return options[state] if state < len(options) else None
readline.set_completer(completer)
readline.parse_and_bind("tab: complete")

# ═══════════════════════════════════════════
# KOMENDY (zwracają string, nie printują)
# ═══════════════════════════════════════════
def cmd_ls(args) -> str:           return FS.ls(args[0] if args else None)
def cmd_cd(args) -> str:           return FS.cd(args[0] if args else "HOT")
def cmd_pwd(args) -> str:          return FS.pwd()
def cmd_touch(args) -> str:        return FS.touch(*args) if len(args)>=1 else "Użycie: TOUCH <id> [S] [E] [T]"
def cmd_rm(args) -> str:           return FS.rm(args[0]) if args else "Użycie: RM <id>"
def cmd_cp(args) -> str:           return FS.cp(args[0], args[1]) if len(args)>1 else "Użycie: CP <src> <dst>"
def cmd_mv(args) -> str:           return FS.mv(args[0], args[1]) if len(args)>1 else "Użycie: MV <id> <warstwa>"
def cmd_sete(args) -> str:         return FS.setE(args[0], args[1]) if len(args)>1 else "Użycie: SETE <id> <E>"
def cmd_find(args) -> str:         return FS.find(" ".join(args)) if args else "Użycie: FIND <zapytanie>"
def cmd_monitor(args) -> str:
    s = RUNTIME.status_summary()
    return gfx.draw_frame("MONITOR", [f"{k}: {v}" for k,v in s.items()])
def cmd_stabilizuj(args) -> str:
    if not args: return "Użycie: STABILIZUJ <id>"
    try: RUNTIME.stabilize_atom(args[0]); return f"Stabilizowano {args[0]}."
    except ValueError as e: return str(e)
def cmd_dotknij_pustki(args) -> str:
    if not args: return "Użycie: DOTKNIJ PUSTKI <id>"
    try: RUNTIME.corrupt_atom(args[0], 25); return f"Dotknięto Pustką {args[0]}."
    except ValueError as e: return str(e)
def cmd_atom_status(args) -> str:
    if not args: return "Użycie: ATOM STATUS <id>"
    atom = RUNTIME.get_atom(args[0])
    if not atom: return "Atom nie istnieje."
    return gfx.draw_frame(f"ATOM {atom.id}", [f"S: {atom.S}  E: {atom.E}", f"T: {atom.T:.1f}  Stan: {atom.state}", gfx.progress_bar(atom.T, atom.T_max, fg=SystemState.color_for(atom))])
def cmd_obserwuj(args) -> str:
    print("Obserwacja (Ctrl+C aby wyjść)...")
    try:
        while True:
            rows = [f"{a.id:6} {gfx.progress_bar(a.T, a.T_max, fg=SystemState.color_for(a))} {a.T:5.1f}° {a.state}" for a in RUNTIME.list_atoms()]
            sys.stdout.write("\033[H\033[J")
            sys.stdout.write(gfx.draw_frame("OBSERWACJA", rows) + "\n")
            sys.stdout.flush()
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    return "Koniec obserwacji."
def cmd_kronika(args) -> str:
    if not RUNTIME.current_mission: return "Sanktuarium milczy. Rozpocznij misję: SANKTUARIUM:START"
    return gfx.draw_frame("KRONIKA", [RUNTIME.current_mission.get("nazwa",""), RUNTIME.current_mission.get("opis_kroniki","")])
def cmd_edit(args) -> str:
    if not args: return "Użycie: EDIT <ścieżka>"
    filepath = args[0]
    subprocess.run([sys.executable, "karmazyn_edit.py", filepath])
    # Po powrocie z edytora dajemy sygnał do HUD-a
    return "[Powrót z edytora]"

# ═══════════════════════════════════════════
# DWUPOZIOMOWY PARSER
# ═══════════════════════════════════════════
COMMANDS = {
    "LS": cmd_ls, "CD": cmd_cd, "PWD": cmd_pwd, "TOUCH": cmd_touch,
    "RM": cmd_rm, "CP": cmd_cp, "MV": cmd_mv, "SETE": cmd_sete,
    "FIND": cmd_find, "MONITOR": cmd_monitor, "STABILIZUJ": cmd_stabilizuj,
    "OBSERWUJ": cmd_obserwuj, "KRONIKA": cmd_kronika, "EDIT": cmd_edit,
    "DOTKNIJ": { "PUSTKI": cmd_dotknij_pustki },
    "ATOM": { "STATUS": cmd_atom_status },
    "EXIT": lambda a: sys.exit(0),
}

# ═══════════════════════════════════════════
# GŁÓWNA PĘTLA
# ═══════════════════════════════════════════
def main():
    print(gfx.draw_frame("KARMAZYN OS", ["Shell v1.4 — Reaktywna powłoka Φ", "Tab = autouzupełnianie"], style="phi_core"))
    while True:
        try:
            line = input(f"{theme.ansi_fg('phi_signal')}ksh>{theme.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nZamykanie..."); break
        if not line: continue

        parts = line.split()
        verb = parts[0].upper()
        args = parts[1:]

        handler = COMMANDS.get(verb)
        if handler is None:
            print(f"{theme.ansi_fg('phi_bright')}[BŁĄD]{theme.RESET} Nieznana komenda: {verb}")
            continue

        result: Optional[str] = None
        try:
            if isinstance(handler, dict):
                sub = args[0].upper() if args else ""
                sub_handler = handler.get(sub)
                if sub_handler:
                    result = sub_handler(args[1:])
                else:
                    result = f"Nieznana podkomenda: {sub}"
            else:
                result = handler(args)
        except Exception as e:
            result = f"{theme.ansi_fg('phi_bright')}[BŁĄD]{theme.RESET} {e}"

        if result:
            print(result)

if __name__ == "__main__":
    main()