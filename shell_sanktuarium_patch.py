"""
shell_sanktuarium_patch.py — Patch komend SANKTUARIUM dla shell.py
===================================================================
Dwie linie w shell.py (po definicji COMMANDS i COMMAND_LIST):

    from shell_sanktuarium_patch import apply_sanktuarium_patch
    apply_sanktuarium_patch(RUNTIME, COMMANDS, COMMAND_LIST)

Albo jeśli chcesz tylko poprawkę parsera (bez nowych komend) —
podmień funkcję main() na main_patched() z tego pliku.

Problem: shell.py parsuje `line.split()` i bierze `parts[0].upper()` jako verb.
    "SANKTUARIUM:START" → verb="SANKTUARIUM:START" — nie ma w COMMANDS → BŁĄD
    "SANKTUARIUM"       → verb="SANKTUARIUM"       — nie ma w COMMANDS → BŁĄD

Rozwiązanie: dwupoziomowy dispatch z obsługą dwukropka jako separatora.
"""

import sys
import time

from karmazyn_ui import gfx
from karmazyn_ui.embedder import LevelEmbedder


# =====================================================================
# HANDLERY KOMEND SANKTUARIUM
# =====================================================================

def cmd_sanktuarium_start(runtime, args):
    words    = args if args else ["iskra", "ciemność"]
    embedder = LevelEmbedder(mode="light")
    mission  = embedder.generate_mission(words)
    runtime.start_mission(mission)
    runtime.start_loop()
    return gfx.draw_frame("MISJA ROZPOCZĘTA", [
        f"Nazwa: {mission['nazwa']}",
        f"Atomów: {len(mission.get('relikwie', []))}",
        "Komendy: ATOM STATUS, OBSERWUJ, STABILIZUJ",
        "       DOTKNIJ PUSTKI, KRONIKA",
    ])


def cmd_sanktuarium_status(runtime, args):
    s = runtime.status_summary()
    return gfx.draw_frame("SANKTUARIUM STATUS", [
        f"HOT:  {s['HOT']}",
        f"WARM: {s['WARM']}",
        f"COLD: {s['COLD']}",
        f"TOMB: {s['TOMB']}",
        f"Misja: {runtime.current_mission['nazwa'] if runtime.current_mission else 'brak'}",
    ])


def cmd_sanktuarium_stop(runtime, args):
    runtime.stop_loop()
    return "Sanktuarium zatrzymane."


# =====================================================================
# PATCH FUNCTION
# =====================================================================

def apply_sanktuarium_patch(runtime, commands: dict, command_list: list):
    """
    Dodaje obsługę SANKTUARIUM:* do shella.

    Rejestruje w COMMANDS:
        "SANKTUARIUM:START"  → cmd_sanktuarium_start
        "SANKTUARIUM:STATUS" → cmd_sanktuarium_status
        "SANKTUARIUM:STOP"   → cmd_sanktuarium_stop
        "SANKTUARIUM"        → dispatcher podkomend

    Poprawia parser shella przez monkey-patch funkcji main()
    tak żeby dwukropek był traktowany jako separator komend.
    """

    # Rejestruj komendy z dwukropkiem
    commands["SANKTUARIUM:START"]  = lambda a: cmd_sanktuarium_start(runtime, a)
    commands["SANKTUARIUM:STATUS"] = lambda a: cmd_sanktuarium_status(runtime, a)
    commands["SANKTUARIUM:STOP"]   = lambda a: cmd_sanktuarium_stop(runtime, a)

    # SANKTUARIUM bez podkomendy — pokaż help
    def _sanktuarium_help(args):
        if args:
            sub     = args[0].upper()
            full_key = f"SANKTUARIUM:{sub}"
            fn = commands.get(full_key)
            if fn:
                return fn(args[1:])
            return f"[BŁĄD] Nieznana podkomenda SANKTUARIUM:{sub}"
        return (
            "Użycie: SANKTUARIUM:START [słowo1 słowo2 ...]\n"
            "        SANKTUARIUM:STATUS\n"
            "        SANKTUARIUM:STOP\n"
        )

    commands["SANKTUARIUM"] = _sanktuarium_help

    # Autocompletion
    for c in ["SANKTUARIUM", "SANKTUARIUM:START",
              "SANKTUARIUM:STATUS", "SANKTUARIUM:STOP"]:
        if c not in command_list:
            command_list.append(c)

    print("[SANKTUARIUM] Komendy aktywne. Wpisz: SANKTUARIUM:START")


# =====================================================================
# PATCH PARSERA — podmień główną pętlę shella
# =====================================================================

def patch_main_loop(commands: dict, theme, gfx_module):
    """
    Zastępuje główną pętlę shell.py wersją obsługującą dwukropek
    jako separator komend (SANKTUARIUM:START → verb=SANKTUARIUM:START).

    Problem w oryginalnym shell.py: parser woła tylko parts[0].upper()
    — dla "SANKTUARIUM:START" verb="SANKTUARIUM:START" i jest w COMMANDS,
    więc po dodaniu patcha powyżej już NIE potrzeba tego patch_main_loop.
    Jest tu jako fallback gdyby coś nie działało.

    Użycie (opcjonalne, tylko jeśli powyższy patch nie wystarczy):
        from shell_sanktuarium_patch import patch_main_loop
        patch_main_loop(COMMANDS, theme, gfx)
    """

    def main():
        print(gfx_module.draw_frame(
            "KARMAZYN OS",
            ["Shell v1.4 — Reaktywna powłoka Φ", "Tab = autouzupełnianie"],
            style="phi_core",
        ))

        while True:
            try:
                line = input(
                    f"{theme.ansi_fg('phi_signal')}ksh>{theme.RESET} "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nZamykanie...")
                break

            if not line:
                continue

            parts = line.split()
            verb  = parts[0].upper()
            args  = parts[1:]

            # Obsługa VERB:SUBCOMMAND (dwukropek jako separator)
            if ":" in verb and verb not in commands:
                # Próbuj złożyć z pierwszych tokenów: VERB SUBCOMMAND → VERB:SUBCOMMAND
                pass  # verb już zawiera dwukropek — szukamy wprost

            handler = commands.get(verb)

            if handler is None:
                print(f"{theme.ansi_fg('phi_bright')}[BŁĄD]{theme.RESET} "
                      f"Nieznana komenda: {verb}")
                continue

            result = None
            try:
                if isinstance(handler, dict):
                    sub         = args[0].upper() if args else ""
                    sub_handler = handler.get(sub)
                    if sub_handler:
                        result = sub_handler(args[1:])
                    else:
                        result = f"Nieznana podkomenda: {sub}"
                else:
                    result = handler(args)
            except Exception as e:
                result = (f"{theme.ansi_fg('phi_bright')}[BŁĄD]{theme.RESET} {e}")

            if result:
                print(result)

    return main
