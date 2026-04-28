#!/usr/bin/env python3
"""
KarmazynOS — Shell (ksh) v1.3
Pełna powłoka operacyjna z trwałym HUD-em i dwupoziomowym parserem.
"""
import os, sys, time, subprocess, readline
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
# HUD — Pasywny feedback systemu
# ═══════════════════════════════════════════
def hud_line() -> str:
    s = RUNTIME.status_summary()
    return (f"{theme.ansi_fg('phi_stable')}HOT:{s['HOT']}{theme.RESET} "
            f"{theme.ansi_fg('phi_thermal')}WARM:{s['WARM']}{theme.RESET} "
            f"{theme.ansi_fg('phi_signal')}COLD:{s['COLD']}{theme.RESET} "
            f"{theme.ansi_fg('phi_ghost')}TOMB:{s['TOMB']}{theme.RESET}")

# ═══════════════════════════════════════════
# KOMENDY (wszystkie przez runtime)
# ═══════════════════════════════════════════
def cmd_stabilizuj(args):
    if not args: return print("Użycie: STABILIZUJ <id>")
    try:
        RUNTIME.stabilize_atom(args[0])
        print(f"Stabilizowano {args[0]}.")
    except ValueError as e: print(e)

def cmd_dotknij_pustki(args):
    if not args: return print("Użycie: DOTKNIJ PUSTKI <id>")
    try:
        RUNTIME.corrupt_atom(args[0], 25)
        print(f"Dotknięto Pustką {args[0]}.")
    except ValueError as e: print(e)

# ... (pozostałe komendy LS, CD, TOUCH, RM, CP, MV, SETE, FIND, MONITOR, OBSERWUJ, KRONIKA, EDIT bez zmian)

# ═══════════════════════════════════════════
# DWUPOZIOMOWY PARSER
# ═══════════════════════════════════════════
COMMANDS = {
    "LS": lambda a: print(FS.ls(a[0] if a else None)),
    "CD": lambda a: print(FS.cd(a[0] if a else "HOT")),
    "PWD": lambda a: print(FS.pwd()),
    "TOUCH": lambda a: cmd_touch(a),
    "RM": lambda a: print(FS.rm(a[0]) if a else "Użycie: RM <id>"),
    "CP": lambda a: print(FS.cp(a[0], a[1]) if len(a)>1 else "Użycie: CP <src> <dst>"),
    "MV": lambda a: print(FS.mv(a[0], a[1]) if len(a)>1 else "Użycie: MV <id> <warstwa>"),
    "SETE": lambda a: print(FS.setE(a[0], a[1]) if len(a)>1 else "Użycie: SETE <id> <E>"),
    "FIND": lambda a: print(FS.find(" ".join(a)) if a else "Użycie: FIND <zapytanie>"),
    "MONITOR": lambda a: print(gfx.draw_frame("MONITOR", [f"{k}: {v}" for k,v in RUNTIME.status_summary().items()])),
    "STABILIZUJ": cmd_stabilizuj,
    "DOTKNIJ": { "PUSTKI": cmd_dotknij_pustki },
    "ATOM": { "STATUS": lambda a: cmd_atom_status(a) },
    "EDIT": lambda a: subprocess.run([sys.executable, "karmazyn_edit.py", a[0]]) if a else print("Użycie: EDIT <ścieżka>"),
    "EXIT": lambda a: sys.exit(0),
}

# ═══════════════════════════════════════════
# GŁÓWNA PĘTLA (z HUD-em po każdej komendzie)
# ═══════════════════════════════════════════
def main():
    print(gfx.draw_frame("KARMAZYN OS", ["Shell v1.3 — Kontrakt Systemowy", hud_line()], style="phi_core"))
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
            print(f"Nieznana komenda: {verb}")
            continue
        if isinstance(handler, dict):
            sub = args[0].upper() if args else ""
            sub_handler = handler.get(sub)
            if sub_handler:
                try: sub_handler(args[1:])
                except Exception as e: print(f"Błąd: {e}")
            else: print(f"Nieznana podkomenda: {sub}")
        else:
            try: handler(args)
            except Exception as e: print(f"Błąd: {e}")

        # Po każdej komendzie wyświetlamy HUD
        print(hud_line())

if __name__ == "__main__":
    main()