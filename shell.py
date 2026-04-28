#!/usr/bin/env python3
"""
KarmazynOS — Shell (ksh) v1.6
Reaktywna powłoka z silnikiem misji Sanktuarium.

Obsługuje format misji:
    cele            — lista warunków wygranej
    limit_ciszy     — max atomów TOMB przed przegraną
    czas_misji      — limit czasu w sekundach
    startowa_zywica — zasób stabilizacji
"""
import json
import os
import sys
import time
import subprocess
import threading
import readline
from typing import Optional, List

from runtime import SanctuaryRuntime, SystemState
from karmazyn_fs import KarmazynFS
from karmazyn_ui import theme, gfx
from karmazyn_ui.embedder import LevelEmbedder

# ═══════════════════════════════════════════
# INICJALIZACJA SYSTEMU
# ═══════════════════════════════════════════
RUNTIME = SanctuaryRuntime()
FS      = KarmazynFS(RUNTIME)
RUNTIME.start_loop()

# ═══════════════════════════════════════════
# SILNIK MISJI
# ═══════════════════════════════════════════

class MissionEngine:
    """
    Sprawdza warunki wygranej i przegranej misji.

    Obsługiwane cele:
        utrzymaj_<id>_przez_<n>_sekund  — atom musi przeżyć n sekund
        ocal_<n>_atomow                 — n atomów musi przeżyć do końca
        utrzymaj_temperature_<n>        — średnia T > n przez cały czas

    Warunki przegranej:
        limit_ciszy  — gdy tyle atomów trafi do TOMB
        czas_misji   — przekroczony limit czasu
    """

    def __init__(self, runtime: SanctuaryRuntime):
        self.runtime     = runtime
        self._active     = False
        self._start_time: Optional[float] = None
        self._atom_birth: dict = {}      # atom_id → czas stworzenia
        self._survived:   dict = {}      # atom_id → sekundy przeżyte
        self._result:     Optional[str] = None   # "win" / "loss" / None
        self._thread:     Optional[threading.Thread] = None

    def start(self, mission: dict):
        """Uruchamia monitoring misji w tle."""
        self._active     = True
        self._start_time = time.time()
        self._result     = None
        self._atom_birth = {}
        self._survived   = {}

        # Rejestruj czas startu dla każdego atomu misji
        for r in mission.get("relikwie", []):
            self._atom_birth[str(r["id"])] = self._start_time

        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="mission-engine"
        )
        self._thread.start()

    def stop(self):
        self._active = False

    def result(self) -> Optional[str]:
        return self._result

    def elapsed(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def status_lines(self) -> List[str]:
        """Zwraca linie statusu do wyświetlenia w SANKTUARIUM:STATUS."""
        if not self.runtime.current_mission:
            return []
        m       = self.runtime.current_mission
        elapsed = self.elapsed()
        limit   = m.get("czas_misji", 0)
        lines   = []

        if limit:
            pozostało = max(0.0, limit - elapsed)
            lines.append(f"Czas:    {elapsed:.0f}s / {limit}s  (pozostało: {pozostało:.0f}s)")
        else:
            lines.append(f"Czas:    {elapsed:.0f}s")

        lines.append(f"Żywica:  {self.runtime.resources.get('żywica', 0)}")

        for cel in m.get("cele", []):
            lines.append(f"Cel:     {_describe_cel(cel, self._survived)}")

        limit_ciszy = m.get("limit_ciszy", 0)
        if limit_ciszy:
            tomb = self.runtime.status_summary().get("TOMB", 0)
            lines.append(f"Cisza:   {tomb} / {limit_ciszy} atomów TOMB")

        return lines

    def _loop(self):
        """Pętla monitoringu — sprawdza warunki co sekundę."""
        while self._active:
            time.sleep(1.0)
            if not self.runtime.current_mission:
                continue

            m       = self.runtime.current_mission
            elapsed = self.elapsed()

            # Aktualizuj czas przeżycia żywych atomów
            for atom in self.runtime.matrix.atoms():
                aid = atom.id
                if aid not in self._atom_birth:
                    self._atom_birth[aid] = time.time()
                self._survived[aid] = time.time() - self._atom_birth[aid]

            # Sprawdź przegraną — limit ciszy
            limit_ciszy = m.get("limit_ciszy", 0)
            if limit_ciszy:
                tomb = self.runtime.status_summary().get("TOMB", 0)
                if tomb >= limit_ciszy:
                    self._result = "loss"
                    self._active = False
                    self.runtime.events.emit("mission_lost",
                                             {"powód": "cisza_ostateczna"})
                    return

            # Sprawdź przegraną — limit czasu
            czas_misji = m.get("czas_misji", 0)
            if czas_misji and elapsed > czas_misji:
                # Sprawdź czy cele spełnione przed ogłoszeniem wyniku
                if self._check_win(m, elapsed):
                    self._result = "win"
                else:
                    self._result = "loss"
                self._active = False
                event = "mission_won" if self._result == "win" else "mission_lost"
                self.runtime.events.emit(event, {"czas": elapsed})
                return

            # Sprawdź wygraną — cele bez limitu czasowego
            if not czas_misji and self._check_win(m, elapsed):
                self._result = "win"
                self._active = False
                self.runtime.events.emit("mission_won", {"czas": elapsed})
                return

    def _check_win(self, mission: dict, elapsed: float) -> bool:
        """Sprawdza czy wszystkie cele są spełnione."""
        cele = mission.get("cele", [])
        if not cele:
            return False
        return all(self._check_cel(cel, elapsed) for cel in cele)

    def _check_cel(self, cel: str, elapsed: float) -> bool:
        """Sprawdza pojedynczy cel."""
        # utrzymaj_<id>_przez_<n>_sekund
        if cel.startswith("utrzymaj_") and "_przez_" in cel:
            parts = cel.split("_przez_")
            atom_id = parts[0].replace("utrzymaj_", "")
            try:
                n = int(parts[1].replace("_sekund", ""))
            except ValueError:
                return False
            survived = self._survived.get(atom_id, 0.0)
            return survived >= n

        # utrzymaj_alfe_przez_<n>_sekund — alias dla rel_0 lub Alfa
        if cel.startswith("utrzymaj_alfe"):
            try:
                n = int(cel.split("_przez_")[1].replace("_sekund", ""))
            except (IndexError, ValueError):
                n = 60
            # Szukaj atomu "Alfa" lub pierwszego atomu misji
            for aid, survived in self._survived.items():
                if "alfa" in aid.lower() or "alfe" in aid.lower():
                    return survived >= n
            # Fallback: sprawdź czy jakikolwiek atom przeżył n sekund
            return any(s >= n for s in self._survived.values())

        # ocal_<n>_atomow
        if cel.startswith("ocal_") and "_atomow" in cel:
            try:
                n = int(cel.replace("ocal_", "").replace("_atomow", ""))
            except ValueError:
                return False
            żywe = len(self.runtime.matrix.atoms())
            return żywe >= n

        # utrzymaj_temperature_<n>
        if cel.startswith("utrzymaj_temperature_"):
            try:
                n = float(cel.replace("utrzymaj_temperature_", ""))
            except ValueError:
                return False
            atoms = self.runtime.matrix.atoms()
            if not atoms:
                return False
            avg_T = sum(a.T for a in atoms) / len(atoms)
            return avg_T >= n

        # Nieznany cel — logujemy i zwracamy False
        return False


def _describe_cel(cel: str, survived: dict) -> str:
    """Opis celu do wyświetlenia graczowi."""
    if cel.startswith("utrzymaj_") and "_przez_" in cel:
        parts   = cel.split("_przez_")
        atom_id = parts[0].replace("utrzymaj_", "")
        try:
            n = int(parts[1].replace("_sekund", ""))
        except ValueError:
            n = "?"
        s = survived.get(atom_id, 0.0)
        return f"Utrzymaj {atom_id} przez {n}s  [{s:.0f}/{n}s]"

    if cel.startswith("utrzymaj_alfe"):
        try:
            n = int(cel.split("_przez_")[1].replace("_sekund", ""))
        except (IndexError, ValueError):
            n = 60
        best = max(survived.values()) if survived else 0.0
        return f"Utrzymaj Alfę przez {n}s  [{best:.0f}/{n}s]"

    if cel.startswith("ocal_") and "_atomow" in cel:
        try:
            n = cel.replace("ocal_", "").replace("_atomow", "")
        except Exception:
            n = "?"
        return f"Ocal {n} atomów"

    return cel


# Singleton silnika misji
MISSION = MissionEngine(RUNTIME)

# Podłącz eventy misji do wyświetlania
def _on_mission_won(data):
    print(f"\n{theme.ansi_fg('phi_stable')}╔══════════════════╗")
    print(f"║  MISJA UKOŃCZONA  ║")
    print(f"╚══════════════════╝{theme.RESET}")
    print(f"Czas: {data.get('czas', 0):.1f}s")

def _on_mission_lost(data):
    print(f"\n{theme.ansi_fg('phi_bright')}╔═════════════════════════╗")
    print(f"║  CISZA OSTATECZNA       ║")
    print(f"╚═════════════════════════╝{theme.RESET}")
    print(f"Powód: {data.get('powód', data.get('czas', '?'))}")

RUNTIME.events.on("mission_won",  _on_mission_won)
RUNTIME.events.on("mission_lost", _on_mission_lost)

# ═══════════════════════════════════════════
# HUD
# ═══════════════════════════════════════════

def print_hud():
    s = RUNTIME.status_summary()
    hud = (f"{theme.ansi_fg('phi_stable')}HOT:{s['HOT']}{theme.RESET} "
           f"{theme.ansi_fg('phi_thermal')}WARM:{s['WARM']}{theme.RESET} "
           f"{theme.ansi_fg('phi_signal')}COLD:{s['COLD']}{theme.RESET} "
           f"{theme.ansi_fg('phi_ghost')}TOMB:{s['TOMB']}{theme.RESET}")

    # Dopisz czas misji i żywicę jeśli trwa
    if RUNTIME.current_mission and MISSION._active:
        elapsed    = MISSION.elapsed()
        czas_misji = RUNTIME.current_mission.get("czas_misji", 0)
        żywica     = RUNTIME.resources.get("żywica", 0)
        if czas_misji:
            pozostało = max(0.0, czas_misji - elapsed)
            hud += f"  ⏱ {pozostało:.0f}s"
        hud += f"  🌿{żywica}"

    print(hud)

    # Wynik misji jeśli gotowy
    if MISSION.result() == "win" and not MISSION._active:
        pass   # event już wydrukował komunikat
    elif MISSION.result() == "loss" and not MISSION._active:
        pass

# ═══════════════════════════════════════════
# AUTOCOMPLETE
# ═══════════════════════════════════════════
COMMAND_LIST = [
    "LS", "CD", "PWD", "TOUCH", "RM", "CP", "MV", "SETE", "FIND",
    "MONITOR", "STABILIZUJ", "DOTKNIJ PUSTKI", "ATOM STATUS",
    "OBSERWUJ", "KRONIKA", "EDIT", "EXIT",
    "SANKTUARIUM:START", "SANKTUARIUM:STATUS", "SANKTUARIUM:STOP",
    "SANKTUARIUM:LOAD",
]

def completer(text, state):
    options = [c for c in COMMAND_LIST if c.startswith(text.upper())]
    return options[state] if state < len(options) else None

readline.set_completer(completer)
readline.parse_and_bind("tab: complete")

# ═══════════════════════════════════════════
# KOMENDY SYSTEMOWE
# ═══════════════════════════════════════════

def cmd_ls(args) -> str:
    atoms = RUNTIME.matrix.atoms()
    if atoms:
        rows = []
        for a in atoms:
            bar = gfx.progress_bar(a.T, a.T_max, fg=SystemState.color_for(a))
            rows.append(f"{a.id:12} {bar} {a.T:5.1f}° {a.state}")
        return gfx.draw_frame("ATOMY", rows)
    return FS.ls(args[0] if args else None)

def cmd_cd(args) -> str:
    return FS.cd(args[0] if args else "HOT")

def cmd_pwd(args) -> str:
    return FS.pwd()

def cmd_touch(args) -> str:
    return FS.touch(*args) if len(args) >= 1 else "Użycie: TOUCH <id> [S] [E] [T]"

def cmd_rm(args) -> str:
    return FS.rm(args[0]) if args else "Użycie: RM <id>"

def cmd_cp(args) -> str:
    return FS.cp(args[0], args[1]) if len(args) > 1 else "Użycie: CP <src> <dst>"

def cmd_mv(args) -> str:
    return FS.mv(args[0], args[1]) if len(args) > 1 else "Użycie: MV <id> <warstwa>"

def cmd_sete(args) -> str:
    return FS.setE(args[0], args[1]) if len(args) > 1 else "Użycie: SETE <id> <E>"

def cmd_find(args) -> str:
    return FS.find(" ".join(args)) if args else "Użycie: FIND <zapytanie>"

def cmd_monitor(args) -> str:
    s = RUNTIME.status_summary()
    return gfx.draw_frame("MONITOR", [f"{k}: {v}" for k, v in s.items()])

def cmd_stabilizuj(args) -> str:
    if not args:
        return "Użycie: STABILIZUJ <id>"
    if RUNTIME.current_mission is not None:
        if RUNTIME.resources.get("żywica", 0) <= 0:
            return "Brak Żywicy! Nie możesz stabilizować."
        RUNTIME.resources["żywica"] -= 1
    try:
        RUNTIME.stabilize_atom(args[0])
        żywica = RUNTIME.resources.get("żywica", "∞")
        return f"Stabilizowano {args[0]}. (Żywica: {żywica})"
    except ValueError as e:
        return str(e)

def cmd_dotknij_pustki(args) -> str:
    if not args:
        return "Użycie: DOTKNIJ PUSTKI <id>"
    try:
        RUNTIME.corrupt_atom(args[0], 25)
        atom = RUNTIME.get_atom(args[0])
        T    = atom.T if atom else 0.0
        return f"Dotknięto Pustką {args[0]}. T={T:.1f}"
    except ValueError as e:
        return str(e)

def cmd_atom_status(args) -> str:
    if not args:
        return "Użycie: ATOM STATUS <id>"
    atom = RUNTIME.get_atom(args[0])
    if not atom:
        return "Atom nie istnieje."
    color = "phi_thermal" if atom.T > 70 else ("phi_signal" if atom.T > 30 else "phi_decay")
    survived = MISSION._survived.get(atom.id, 0.0)
    return gfx.draw_frame(f"ATOM {atom.id}", [
        f"S: {atom.S}   E: {atom.E}",
        f"T: {atom.T:.1f}   Stan: {atom.state}",
        f"Wiek: {atom.age} kroków   Przeżyte: {survived:.0f}s",
        gfx.progress_bar(atom.T, atom.T_max, fg=color),
    ])

def cmd_obserwuj(args) -> str:
    print("Obserwuję stan atomów (Ctrl+C by wyjść)...")
    try:
        while True:
            rows = []
            for atom in RUNTIME.matrix.atoms():
                color    = "phi_thermal" if atom.T > 70 else ("phi_signal" if atom.T > 30 else "phi_decay")
                bar      = gfx.progress_bar(atom.T, atom.T_max, fg=color)
                survived = MISSION._survived.get(atom.id, 0.0)
                rows.append(f"{atom.id:10} {bar} {atom.T:5.1f}° {atom.state}  ⏱{survived:.0f}s")
            sys.stdout.write("\033[H\033[J")
            sys.stdout.write(gfx.draw_frame("OBSERWACJA", rows) + "\n")
            sys.stdout.flush()
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    return "Koniec obserwacji."

def cmd_kronika(args) -> str:
    if not RUNTIME.current_mission:
        return "Sanktuarium milczy. Rozpocznij misję: SANKTUARIUM:START"
    m     = RUNTIME.current_mission
    cele  = m.get("cele", [])
    lines = [
        m.get("nazwa", ""),
        m.get("opis_kroniki", ""),
        "",
    ]
    lines.append("WARUNEK WYGRANEJ:")
    for cel in cele:
        lines.append(f"  ✦ {_describe_cel(cel, MISSION._survived)}")
    limit_ciszy = m.get("limit_ciszy", 0)
    if limit_ciszy:
        lines.append(f"\nWARUNEK PRZEGRANEJ:")
        lines.append(f"  ✗ {limit_ciszy} atom(y) osiągną Ciszę Ostateczną")
    czas = m.get("czas_misji", 0)
    if czas:
        lines.append(f"  ✗ Upłynie {czas}s bez spełnienia celów")
    return gfx.draw_frame("KRONIKA", lines)

def cmd_edit(args) -> str:
    if not args:
        return "Użycie: EDIT <ścieżka>"
    subprocess.run([sys.executable, "karmazyn_edit.py", args[0]])
    return "[Powrót z edytora]"

# ═══════════════════════════════════════════
# KOMENDY SANKTUARIUM
# ═══════════════════════════════════════════

def _start_mission(mission: dict) -> str:
    """Wspólna logika startu misji z dowolnego źródła."""
    MISSION.stop()
    RUNTIME.start_mission(mission)
    MISSION.start(mission)
    cele = mission.get("cele", [])
    return gfx.draw_frame("MISJA ROZPOCZĘTA", [
        f"Nazwa:   {mission['nazwa']}",
        f"Atomów:  {len(mission.get('relikwie', []))}",
        f"Czas:    {mission.get('czas_misji', '∞')}s",
        f"Żywica:  {RUNTIME.resources.get('żywica', 0)}",
        "",
        "CEL:",
    ] + [f"  ✦ {_describe_cel(c, {})}" for c in cele] + [
        "",
        "Komendy: LS, ATOM STATUS <id>, OBSERWUJ",
        "         STABILIZUJ <id>, DOTKNIJ PUSTKI <id>",
        "         KRONIKA, SANKTUARIUM:STATUS",
    ])

def cmd_sanktuarium_start(args) -> str:
    words    = args if args else ["iskra", "ciemność"]
    embedder = LevelEmbedder(mode="light")
    mission  = embedder.generate_mission(words)
    return _start_mission(mission)

def cmd_sanktuarium_load(args) -> str:
    """SANKTUARIUM:LOAD <plik.json> — wczytaj misję z pliku."""
    if not args:
        return "Użycie: SANKTUARIUM:LOAD <plik.json>"
    path = args[0]
    if not os.path.isfile(path):
        return f"Plik nie istnieje: {path}"
    try:
        with open(path, encoding="utf-8") as f:
            mission = json.load(f)
        return _start_mission(mission)
    except Exception as e:
        return f"[BŁĄD] Nie można wczytać misji: {e}"

def cmd_sanktuarium_status(args) -> str:
    if not RUNTIME.current_mission:
        return "Brak aktywnej misji. Wpisz: SANKTUARIUM:START"
    s     = RUNTIME.status_summary()
    lines = [
        f"Misja:   {RUNTIME.current_mission.get('nazwa', '?')}",
        f"HOT:{s['HOT']}  WARM:{s['WARM']}  COLD:{s['COLD']}  TOMB:{s['TOMB']}",
    ] + MISSION.status_lines()
    return gfx.draw_frame("SANKTUARIUM STATUS", lines)

def cmd_sanktuarium_stop(args) -> str:
    MISSION.stop()
    RUNTIME.stop_loop()
    return "Sanktuarium zatrzymane."

def cmd_sanktuarium(args) -> str:
    if not args:
        return (
            "Użycie:\n"
            "  SANKTUARIUM:START [słowa...]  — nowa misja z embeddera\n"
            "  SANKTUARIUM:LOAD <plik.json>  — wczytaj misję z pliku\n"
            "  SANKTUARIUM:STATUS            — stan aktywnej misji\n"
            "  SANKTUARIUM:STOP              — zatrzymaj\n"
        )
    sub = args[0].upper()
    fn  = COMMANDS.get(f"SANKTUARIUM:{sub}")
    if fn:
        return fn(args[1:])
    return f"Nieznana podkomenda: SANKTUARIUM:{sub}"

# ═══════════════════════════════════════════
# DWUPOZIOMOWY PARSER
# ═══════════════════════════════════════════
COMMANDS = {
    "LS": cmd_ls, "CD": cmd_cd, "PWD": cmd_pwd, "TOUCH": cmd_touch,
    "RM": cmd_rm, "CP": cmd_cp, "MV": cmd_mv,   "SETE": cmd_sete,
    "FIND": cmd_find, "MONITOR": cmd_monitor,
    "STABILIZUJ": cmd_stabilizuj,
    "OBSERWUJ":   cmd_obserwuj,
    "KRONIKA":    cmd_kronika,
    "DOTKNIJ":    {"PUSTKI": cmd_dotknij_pustki},
    "ATOM":       {"STATUS": cmd_atom_status},
    "SANKTUARIUM":        cmd_sanktuarium,
    "SANKTUARIUM:START":  cmd_sanktuarium_start,
    "SANKTUARIUM:LOAD":   cmd_sanktuarium_load,
    "SANKTUARIUM:STATUS": cmd_sanktuarium_status,
    "SANKTUARIUM:STOP":   cmd_sanktuarium_stop,
    "EDIT": cmd_edit,
    "EXIT": lambda a: sys.exit(0),
}

try:
    from shell_karm_patch import apply_karm_to_shell
    _karm = apply_karm_to_shell(RUNTIME, COMMANDS, COMMAND_LIST)
except ImportError:
    pass

# ═══════════════════════════════════════════
# GŁÓWNA PĘTLA
# ═══════════════════════════════════════════
def main():
    print(gfx.draw_frame(
        "KARMAZYN OS",
        ["Shell v1.6 — Reaktywna powłoka Φ", "Tab = autouzupełnianie"],
        style="phi_core",
    ))
    while True:
        try:
            line = input(f"{theme.ansi_fg('phi_signal')}ksh>{theme.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nZamykanie...")
            MISSION.stop()
            break
        if not line:
            continue

        parts   = line.split()
        verb    = parts[0].upper()
        args    = parts[1:]
        handler = COMMANDS.get(verb)

        if handler is None:
            print(f"{theme.ansi_fg('phi_bright')}[BŁĄD]{theme.RESET} Nieznana komenda: {verb}")
            print_hud()
            continue

        result: Optional[str] = None
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
            result = f"{theme.ansi_fg('phi_bright')}[BŁĄD]{theme.RESET} {e}"

        if result:
            print(result)
        print_hud()

if __name__ == "__main__":
    main()