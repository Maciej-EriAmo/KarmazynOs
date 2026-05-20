"""
karmazyn_db.py — KarminQL Database Engine KarmazynOS v1.0
==========================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Minimalny silnik bazy danych oparty na architekturze PhiSpace.
Nie używa tabel ani sztywnych relacji. Operuje na termodynamice i rezonansie.

Obsługiwane komendy KarminQL:
  UTRWAL "X" JAKO BĄBEL
  WSTRZYKNIJ "C" -> "W" DO "X"
  SZUKAJ BĄBLI REZONUJĄCYCH Z "Q"
  ZAPYTAJ ANALOGII: "A" do "B" JAK "C" do ?
"""

import time
from typing import Any, List
import numpy as np

# Próba importu z nowego fundamentu
try:
    from karmazyn_phi import PhiSpace
    from karmazyn_atom import T_HOT
except ImportError:
    pass

class KarminDatabase:
    def __init__(self, phi_space: 'PhiSpace'):
        self.phi = phi_space
        # Baza danych wymaga aktywnego HRR do analogii i rezonansu wektorowego
        if self.phi._hrr is None:
            self.phi.enable_hrr(D=2048)

    def execute(self, script: str) -> List[Any]:
        """Główna pętla wykonawcza dla skryptów KarminQL."""
        lines = script.strip().split('\n')
        results = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                res = self._eval_line(line)
                if res is not None:
                    results.append(res)
            except Exception as e:
                results.append(f"BŁĄD ({line}): {e}")
        return results

    def _eval_line(self, line: str) -> Any:
        tokens = line.split()
        cmd = tokens[0].upper()

        # ─── 1. TWORZENIE BĄBLI (KONTEKSTÓW) ───
        if cmd == "UTRWAL":
            # UTRWAL "użytkownik_maciej" JAKO BĄBEL
            name = tokens[1].strip('",')
            bubble = self.phi.create_bubble(name)
            return f"Utworzono mgławicę: {bubble.label}"

        # ─── 2. WSTRZYKIWANIE WIEDZY (ATOMÓW) ───
        elif cmd == "WSTRZYKNIJ":
            # WSTRZYKNIJ "rola" -> "architekt" DO "użytkownik_maciej"
            parts = line.split(' DO ')
            if len(parts) != 2:
                raise SyntaxError("Brak klauzuli DO")
            
            bubble_name = parts[1].strip('",')
            left = parts[0].replace('WSTRZYKNIJ ', '').split('->')
            cecha = left[0].strip().strip('",')
            wartosc = left[1].strip().strip('",')

            # Unikalne ID, aby zapobiec kolizjom w słowniku
            uid = f"db_{bubble_name}_{cecha}_{time.monotonic_ns()}"
            atom = self.phi.create_atom(uid, S=cecha, E=wartosc, T=T_HOT)
            self.phi.import_to_bubble(bubble_name, uid)
            return f"Wstrzyknięto [{cecha}: {wartosc}] do {bubble_name}"

        # ─── 3. MIĘKKIE WYSZUKIWANIE (REZONANS) ───
        elif cmd == "SZUKAJ":
            # SZUKAJ BĄBLI REZONUJĄCYCH Z "architekt"
            if "REZONUJĄCYCH" in line:
                idx = tokens.index("Z")
                pojecie = tokens[idx+1].strip('",')
                
                # Szukamy najgorętszych atomów rezonujących semantycznie
                atoms = self.phi.find_resonating(pojecie, T_min=0.0, limit=10)
                
                # Odtwarzamy bąble z atomów
                found_bubbles = set()
                for a in atoms:
                    # Podnosimy temperaturę przy odczycie (Termodynamika DB)
                    a.touch()
                    for bubble in self.phi._bubbles.values():
                        if a.id in bubble._ids:
                            found_bubbles.add(bubble.label)
                
                return f"Rezonans z '{pojecie}': {list(found_bubbles)}"

        # ─── 4. WNIOSKOWANIE Z ANALOGII ───
        elif cmd == "ZAPYTAJ":
            # ZAPYTAJ ANALOGII: "Polska" do "Warszawa" JAK "KarmazynOS" do ?
            idx_do1 = tokens.index("do")
            idx_jak = tokens.index("JAK")
            idx_do2 = tokens.index("do", idx_jak)

            # Ekstrakcja terminów
            A = tokens[idx_do1 - 1].strip('":,')
            B = tokens[idx_jak - 1].strip('",')
            C = tokens[idx_do2 - 1].strip('",')

            hrr = self.phi._hrr
            V_A = hrr.atom_vector(A)
            V_B = hrr.atom_vector(B)
            V_C = hrr.atom_vector(C)

            # Arytmetyka wektorowa przesunięcia semantycznego: C + (B - A)
            V_analogy = V_C + (V_B - V_A)
            V_analogy = V_analogy / np.linalg.norm(V_analogy)

            # Szukamy najbliższego rezonującego wektora w przestrzeni
            hits = hrr.nearest(V_analogy, k=1, threshold=0.1)
            wynik = hits[0][1] if hits else "Szum (Brak rezonansu)"
            
            return f"Analogia {A}->{B} :: {C}->{wynik}"

        return f"Nieznana komenda: {cmd}"

# --- SZYBKI TEST ---
if __name__ == "__main__":
    phi = PhiSpace()
    db = KarminDatabase(phi)
    
    skrypt = """
    UTRWAL "projekt_karmazyn" JAKO BĄBEL
    WSTRZYKNIJ "typ" -> "system_operacyjny" DO "projekt_karmazyn"
    WSTRZYKNIJ "cecha" -> "termodynamika" DO "projekt_karmazyn"
    
    UTRWAL "projekt_linux" JAKO BĄBEL
    WSTRZYKNIJ "typ" -> "system_operacyjny" DO "projekt_linux"
    WSTRZYKNIJ "cecha" -> "monolityczny" DO "projekt_linux"
    
    SZUKAJ BĄBLI REZONUJĄCYCH Z "termodynamika"
    """
    
    wyniki = db.execute(skrypt)
    for w in wyniki:
        print(w)