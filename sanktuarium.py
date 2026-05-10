"""
KarmazynOS — Sanktuarium Stygnących Danych
Gra demonstrująca architekturę systemu.
Używa wspólnego runtime'u.
"""
import sys
import time
from runtime import SanctuaryRuntime
from karmazyn_ui import gfx
from karmazyn_ui.embedder import LevelEmbedder

RUNTIME = SanctuaryRuntime()

def cmd_sanktuarium_start(args):
    words = args if args else ["iskra", "ciemność"]
    embedder = LevelEmbedder(mode="light")
    mission = embedder.generate_mission(words)
    RUNTIME.start_mission(mission)
    RUNTIME.start_system_loop()
    print(gfx.draw_frame("MISJA ROZPOCZĘTA", [
        f"Nazwa: {mission['nazwa']}",
        f"Atomów: {len(mission['relikwie'])}",
        "Komendy: ATOM STATUS, OBSERWUJ, STABILIZUJ",
        "       DOTKNIJ PUSTKI, KRONIKA"
    ]))

def cmd_atom_status(args):
    if not args:
        print("Użycie: ATOM STATUS <id>")
        return
    atom = RUNTIME.get_atom(args[0])
    if atom is None:
        print(f"Atom {args[0]} nie istnieje.")
        return
    color = "phi_thermal" if atom.T > 70 else ("phi_signal" if atom.T > 30 else "phi_decay")
    bar = gfx.progress_bar(atom.T, atom.T_max, fg=color)
    print(gfx.draw_frame(f"ATOM {atom.id}", [
        f"S: {atom.S}   E: {atom.E}",
        f"T: {atom.T:.1f}   Stan: {atom.state}",
        bar
    ]))

def cmd_obserwuj(args):
    print("Obserwuję stan atomów (Ctrl+C by wyjść)...")
    try:
        while True:
            rows = []
            for atom in RUNTIME.matrix.atoms():
                color = "phi_thermal" if atom.T > 70 else ("phi_signal" if atom.T > 30 else "phi_decay")
                bar = gfx.progress_bar(atom.T, atom.T_max, fg=color)
                rows.append(f"{atom.id:6} {bar} {atom.T:5.1f}° {atom.state}")
            # Czyścimy ekran
            print("\033[H\033[J")
            print(gfx.draw_frame("OBSERWACJA", rows))
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nKoniec obserwacji.")

def cmd_stabilizuj(args):
    if not args:
        print("Użycie: STABILIZUJ <id>")
        return
    atom = RUNTIME.get_atom(args[0])
    if atom is None:
        print("Atom nie istnieje.")
        return
    if RUNTIME.resources["żywica"] <= 0:
        print("Brak Żywicy! Nie możesz stabilizować.")
        return
    atom.T = min(atom.T_max, atom.T + 20)
    atom.state = "HOT"
    RUNTIME.resources["żywica"] -= 1
    RUNTIME.events.emit("stabilized", atom)
    print(f"Stabilizowano {atom.id}. (Żywica: {RUNTIME.resources['żywica']})")

def cmd_dotknij_pustki(args):
    if not args:
        print("Użycie: DOTKNIJ PUSTKI <id>")
        return
    atom = RUNTIME.get_atom(args[0])
    if atom is None:
        print("Atom nie istnieje.")
        return
    atom.T = max(0, atom.T - 25)
    if atom.T == 0:
        RUNTIME.events.emit("vacuum_decay", atom)
    else:
        RUNTIME.events.emit("corruption", atom)
    print(f"Dotknięto Pustką {atom.id}. T={atom.T:.1f}")

def cmd_kronika(args):
    if RUNTIME.current_mission is None:
        print("Sanktuarium milczy. Rozpocznij misję.")
        return
    print(gfx.draw_frame("KRONIKA", [
        "W ciemności drzemie iskra.",
        "Obserwuj temperaturę.",
        "Gdy zgaśnie — nastąpi Cisza Ostateczna.",
        "Użyj STABILIZUJ, by podtrzymać Żar.",
    ]))

def run():
    RUNTIME.start_system_loop()
    print(gfx.draw_frame("SANKTUARIUM", ["Wpisz SANKTUARIUM:START"]))
    while True:
        try:
            cmd = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSanktuarium zamyka się.")
            break
        parts = cmd.split()
        if not parts:
            continue
        verb = parts[0].upper()
        args = parts[1:] if len(parts) > 1 else []

        if verb == "SANKTUARIUM:START":
            cmd_sanktuarium_start(args)
        elif verb == "ATOM" and args and args[0].upper() == "STATUS":
            cmd_atom_status(args[1:])
        elif verb == "OBSERWUJ":
            cmd_obserwuj(args)
        elif verb == "STABILIZUJ":
            cmd_stabilizuj(args)
        elif verb == "DOTKNIJ" and args and args[0].upper() == "PUSTKI":
            cmd_dotknij_pustki(args[1:])
        elif verb == "KRONIKA":
            cmd_kronika(args)
        elif verb == "EXIT":
            break
        else:
            print(f"Nieznana komenda: {cmd}")

if __name__ == "__main__":
    run()