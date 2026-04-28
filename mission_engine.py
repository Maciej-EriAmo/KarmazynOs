# ============================================================
# mission_engine.py — Silnik misji dla KarmazynOS
# ============================================================
# Wycięty z shell.py, niezależny od reszty.
# Użycie:
#     from mission_engine import MissionEngine, describe_cel
#     mission = MissionEngine(runtime)
#     mission.start(mission_dict)
# ============================================================

import time
import threading
from typing import Optional, List


class MissionEngine:
    """
    Sprawdza warunki wygranej i przegranej misji.

    Obsługiwane cele:
        utrzymaj_<id>_przez_<n>_sekund  — atom musi przeżyć n sekund
        ocal_<n>_atomow                 — n atomów musi przeżyć do końca
        utrzymaj_temperature_<n>        — średnia T > n przez cały czas
        utrzymaj_alfe_przez_<n>_sekund  — alias dla pierwszego atomu

    Warunki przegranej:
        limit_ciszy  — gdy tyle atomów trafi do TOMB
        czas_misji   — przekroczony limit czasu
    """

    def __init__(self, runtime):
        self.runtime     = runtime
        self._active     = False
        self._start_time: Optional[float] = None
        self._atom_birth: dict = {}
        self._survived:   dict = {}
        self._result:     Optional[str] = None
        self._thread:     Optional[threading.Thread] = None

    # ── public API ──────────────────────────────────────────

    def start(self, mission: dict):
        """Uruchamia monitoring misji w tle."""
        self._active     = True
        self._start_time = time.time()
        self._result     = None
        self._atom_birth = {}
        self._survived   = {}

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
        return time.time() - self._start_time if self._start_time else 0.0

    def status_lines(self) -> List[str]:
        """Zwraca linie statusu do wyświetlenia."""
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
            lines.append(f"Cel:     {describe_cel(cel, self._survived)}")

        limit_ciszy = m.get("limit_ciszy", 0)
        if limit_ciszy:
            tomb = self.runtime.status_summary().get("TOMB", 0)
            lines.append(f"Cisza:   {tomb} / {limit_ciszy} atomów TOMB")

        return lines

    # ── pętla główna ────────────────────────────────────────

    def _loop(self):
        while self._active:
            time.sleep(1.0)
            if not self.runtime.current_mission:
                continue

            m       = self.runtime.current_mission
            elapsed = self.elapsed()

            # Aktualizuj czas przeżycia
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
                    self.runtime.events.emit(
                        "mission_lost", {"powód": "cisza_ostateczna"}
                    )
                    return

            # Sprawdź przegraną — limit czasu
            czas_misji = m.get("czas_misji", 0)
            if czas_misji and elapsed > czas_misji:
                if self._check_win(m, elapsed):
                    self._result = "win"
                else:
                    self._result = "loss"
                self._active = False
                event = "mission_won" if self._result == "win" else "mission_lost"
                self.runtime.events.emit(event, {"czas": elapsed})
                return

            # Sprawdź wygraną bez limitu czasu
            if not czas_misji and self._check_win(m, elapsed):
                self._result = "win"
                self._active = False
                self.runtime.events.emit("mission_won", {"czas": elapsed})
                return

    # ── sprawdzanie celów ───────────────────────────────────

    def _check_win(self, mission: dict, elapsed: float) -> bool:
        cele = mission.get("cele", [])
        if not cele:
            return False
        return all(self._check_cel(cel, elapsed) for cel in cele)

    def _check_cel(self, cel: str, elapsed: float) -> bool:
        # utrzymaj_<id>_przez_<n>_sekund
        if cel.startswith("utrzymaj_") and "_przez_" in cel:
            parts = cel.split("_przez_")
            atom_id = parts[0].replace("utrzymaj_", "")
            try:
                n = int(parts[1].replace("_sekund", ""))
            except ValueError:
                return False
            return self._survived.get(atom_id, 0.0) >= n

        # utrzymaj_alfe_przez_<n>_sekund
        if cel.startswith("utrzymaj_alfe"):
            try:
                n = int(cel.split("_przez_")[1].replace("_sekund", ""))
            except (IndexError, ValueError):
                n = 60
            for aid, s in self._survived.items():
                if "alfa" in aid.lower() or "alfe" in aid.lower():
                    return s >= n
            return any(s >= n for s in self._survived.values())

        # ocal_<n>_atomow
        if cel.startswith("ocal_") and "_atomow" in cel:
            try:
                n = int(cel.replace("ocal_", "").replace("_atomow", ""))
            except ValueError:
                return False
            return len(self.runtime.matrix.atoms()) >= n

        # utrzymaj_temperature_<n>
        if cel.startswith("utrzymaj_temperature_"):
            try:
                n = float(cel.replace("utrzymaj_temperature_", ""))
            except ValueError:
                return False
            atoms = self.runtime.matrix.atoms()
            if not atoms:
                return False
            return sum(a.T for a in atoms) / len(atoms) >= n

        return False


# ── funkcja pomocnicza ──────────────────────────────────────

def describe_cel(cel: str, survived: dict) -> str:
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


# Alias dla kompatybilności z shell.py
describe_cel = describe_cel
