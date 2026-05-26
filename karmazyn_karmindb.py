#!/usr/bin/env python3
"""
karmazyn_karmindb.py — KarminQL Database Engine v1.2
=====================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Silnik zapytań semantycznych wykorzystujący HRR i phi-space.
Komendy: KQL, INDEX, SEARCH.

Nowości v1.2:
- Parsowanie z użyciem shlex (obsługa cytatów, odporność na spacje)
- Mechanizm dirty flag dla wektorów atomów (poprawna invalidacja cache)
- Eksperymentalny indeks bucketingowy HRR (opcjonalny, włączany automatycznie
  przy > 500 atomów)
"""

import time
import shlex
import numpy as np
from typing import Any, List, Dict, Optional, Tuple

try:
    from karmazyn_phi import PhiSpace
    from karmazyn_atom import T_HOT
except ImportError:
    raise ImportError("Wymagane: karmazyn_phi, karmazyn_atom")

# ── Pomocnicze ──────────────────────────────────────────────────────────────
def _hash_vector(v: np.ndarray, bits: int = 8) -> int:
    """Prosty bucketing na podstawie pierwszych `bits` bitów znaku komponentów."""
    # Używamy znaków pierwszych `bits` współrzędnych jako klucza binarnego
    key = 0
    for i in range(min(bits, len(v))):
        if v[i] >= 0:
            key |= (1 << i)
    return key

# ── Warstwa indeksująca (eksperymentalna) ───────────────────────────────────
class SemanticIndexLayer:
    """
    Prosty indeks bucketingowy oparty na pierwszych bitach wektora HRR.
    Dzieli przestrzeń na 2^bits kubełków. Przyspiesza search dla dużych zbiorów.
    """
    def __init__(self, bits: int = 10):
        self.bits = bits
        self.buckets: Dict[int, List[Any]] = {i: [] for i in range(1 << bits)}

    def insert(self, atom: Any, vector: np.ndarray):
        bucket = _hash_vector(vector, self.bits)
        self.buckets[bucket].append(atom)

    def remove(self, atom: Any, vector: np.ndarray):
        bucket = _hash_vector(vector, self.bits)
        try:
            self.buckets[bucket].remove(atom)
        except ValueError:
            pass

    def query(self, query_vector: np.ndarray, top_k_buckets: int = 3) -> List[Any]:
        """
        Zwraca listę atomów z `top_k_buckets` najbliższych kubełków
        (mierzone odległością Hamminga kluczy).
        """
        q_bucket = _hash_vector(query_vector, self.bits)
        # Pobieramy atomy z własnego kubełka i kilku sąsiednich
        candidates = list(self.buckets.get(q_bucket, []))
        # Oblicz odległość Hamminga do wszystkich kluczy
        dists = []
        for key in self.buckets:
            if key == q_bucket:
                continue
            dist = bin(key ^ q_bucket).count('1')
            dists.append((dist, key))
        dists.sort(key=lambda x: x[0])
        for _, key in dists[:top_k_buckets-1]:
            candidates.extend(self.buckets[key])
        return candidates

# ── Baza danych KarminQL ────────────────────────────────────────────────────
class KarminDatabase:
    def __init__(self, phi_space: 'PhiSpace', enable_index: bool = True,
                 index_threshold: int = 500):
        self.phi = phi_space
        if not hasattr(self.phi, '_hrr') or self.phi._hrr is None:
            self.phi.enable_hrr(D=256)
        if self.phi._hrr is None:
            raise RuntimeError("Nie udało się zainicjować HRR w phi-space")

        self._indexed_bubbles = set()
        self._dirty_atoms = set()                     # zbiór atomów z nieaktualnym wektorem
        self._sem_index: Optional[SemanticIndexLayer] = None
        self._index_threshold = index_threshold
        self._use_index = enable_index
        self._atom_count = 0

        # Oznacz wszystkie istniejące atomy jako dirty (wymuszą przeliczenie wektorów)
        for atom in self._all_atoms():
            self._mark_dirty(atom)

    @property
    def _hrr(self):
        return self.phi._hrr

    def _all_atoms(self):
        if hasattr(self.phi, 'matrix') and hasattr(self.phi.matrix, 'atoms'):
            return list(self.phi.matrix.atoms())
        elif hasattr(self.phi, '_atoms_dict'):
            return list(self.phi._atoms_dict.values())
        else:
            raise RuntimeError("PhiSpace nie udostępnia atomów")

    def _get_bubble(self, name: str):
        if hasattr(self.phi, 'get_bubble'):
            return self.phi.get_bubble(name)
        elif hasattr(self.phi, '_bubbles'):
            return self.phi._bubbles.get(name)
        return None

    def _mark_dirty(self, atom: Any):
        """Oznacza atom jako wymagający ponownego wyliczenia wektora."""
        atom.vector_dirty = True
        self._dirty_atoms.add(id(atom))

    def _ensure_vector(self, atom: Any) -> np.ndarray:
        """Zwraca aktualny wektor HRR dla atomu, przeliczając go, jeśli trzeba."""
        if getattr(atom, 'vector', None) is None or getattr(atom, 'vector_dirty', False):
            text = atom.S or atom.E or atom.id
            vec = self._hrr.atom_vector(text)
            atom.vector = vec
            atom.vector_dirty = False
            self._dirty_atoms.discard(id(atom))
            # Jeśli używamy indeksu, zaktualizuj go
            if self._sem_index is not None:
                # usunięcie starego nie jest tu trywialne, więc dla prostoty
                # indeks jest odświeżany wsadowo – pomijamy
                pass
        return atom.vector

    def _maybe_reindex(self):
        """Włącza lub odświeża indeks, jeśli liczba atomów przekracza próg."""
        if not self._use_index:
            return
        atoms = self._all_atoms()
        if len(atoms) > self._index_threshold:
            if self._sem_index is None or len(atoms) > 2 * self._index_threshold:
                # Buduj indeks
                self._sem_index = SemanticIndexLayer(bits=10)
                for a in atoms:
                    vec = self._ensure_vector(a)
                    self._sem_index.insert(a, vec)
        else:
            # Poniżej progu – nie używaj indeksu
            self._sem_index = None

    # ── Parsowanie i wykonanie ──────────────────────────────────────────────
    def execute(self, script: str) -> List[str]:
        lines = script.strip().split('\n')
        results = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                res = self._eval_line(line)
                if res is not None:
                    results.append(str(res))
            except Exception as e:
                results.append(f"BŁĄD ({line}): {e}")
        return results

    def _eval_line(self, line: str) -> Any:
        # Parsuj z użyciem shlex – obsługa cytowań
        tokens = shlex.split(line)
        if not tokens:
            return None
        cmd = tokens[0].upper()

        if cmd == "UTRWAL":
            name = tokens[1].strip('"')
            bubble = self.phi.create_bubble(name)
            return f"Utworzono bąbel: {bubble.label}"

        elif cmd == "WSTRZYKNIJ":
            # Składnia: WSTRZYKNIJ "cecha" -> "wartość" DO "bąbel"
            # shlex już podzielił poprawnie
            try:
                idx_do = tokens.index("DO")
                bubble_name = tokens[idx_do + 1]
                left = tokens[1:idx_do]
                if len(left) < 3 or left[1] != "->":
                    raise SyntaxError("Oczekiwano 'cecha -> wartość'")
                cecha = left[0]
                wartosc = left[2]
            except (ValueError, IndexError):
                raise SyntaxError("Użycie: WSTRZYKNIJ \"cecha\" -> \"wartość\" DO \"bąbel\"")

            uid = f"db_{bubble_name}_{cecha}_{int(time.monotonic_ns())}"
            atom = self.phi.create_atom(uid, S=cecha, E=wartosc, T=T_HOT)
            # Wymuś świeży wektor
            atom.vector_dirty = True
            self._ensure_vector(atom)
            self.phi.import_to_bubble(bubble_name, uid)
            return f"Wstrzyknięto [{cecha}: {wartosc}] do {bubble_name}"

        elif cmd == "SZUKAJ":
            # SZUKAJ REZONUJĄCYCH Z "pojęcie"
            if "REZONUJĄCYCH" in tokens:
                try:
                    idx_z = tokens.index("Z")
                    pojecie = tokens[idx_z + 1]
                except (ValueError, IndexError):
                    return "Błąd składni. Użycie: SZUKAJ REZONUJĄCYCH Z \"pojęcie\""
                atoms = self.phi.find_resonating(pojecie, T_min=0.0, limit=20)
                found_bubbles = set()
                for a in atoms:
                    a.touch()
                    if hasattr(self.phi, '_bubbles'):
                        for bubble in self.phi._bubbles.values():
                            if a.id in getattr(bubble, '_ids', []):
                                found_bubbles.add(bubble.label)
                return f"Rezonans z '{pojecie}': {list(found_bubbles)}"
            else:
                return "Nieobsługiwana składnia SZUKAJ"

        elif cmd == "ZAPYTAJ":
            try:
                idx_do1 = tokens.index("do")
                idx_jak = tokens.index("JAK")
                idx_do2 = tokens.index("do", idx_jak + 1)
                A = tokens[idx_do1 - 1]
                B = tokens[idx_jak - 1]
                C = tokens[idx_do2 - 1]
            except (ValueError, IndexError):
                return "Błąd składni. Użycie: ZAPYTAJ A do B JAK C do D"

            hrr = self._hrr
            vA = hrr.atom_vector(A)
            vB = hrr.atom_vector(B)
            vC = hrr.atom_vector(C)
            v_analogy = vC + (vB - vA)
            norm = np.linalg.norm(v_analogy)
            if norm > 1e-10:
                v_analogy /= norm
            hits = hrr.nearest(v_analogy, k=1, threshold=0.1)
            wynik = hits[0][1] if hits else "Szum (Brak rezonansu)"
            return f"Analogia {A}->{B} :: {C}->{wynik}"

        elif cmd == "INDEKSUJ":
            if len(tokens) < 3 or tokens[1].upper() != "BĄBEL":
                raise SyntaxError("Użycie: INDEKSUJ BĄBEL \"nazwa\"")
            bubble_name = tokens[2]
            bubble = self._get_bubble(bubble_name)
            if not bubble:
                return f"Bąbel {bubble_name} nie istnieje"
            count = self._index_bubble(bubble)
            return f"Zaindeksowano {count} atomów w bąblu {bubble_name}"

        elif cmd == "WYSZUKAJ":
            if len(tokens) < 2:
                return "Brak frazy do wyszukania"
            phrase = tokens[1]
            limit = 10
            if "LIMIT" in tokens:
                idx = tokens.index("LIMIT")
                if idx + 1 < len(tokens):
                    limit = int(tokens[idx + 1])
            results = self.search(phrase, limit)
            if not results:
                return "Brak wyników"
            out = [f"Wyniki dla '{phrase}':"]
            for sim, atom in results[:limit]:
                out.append(f"  {sim:.3f} – {atom.id} (T={atom.T:.1f}) S={atom.S}")
            return "\n".join(out)

        else:
            return f"Nieznana komenda: {cmd}"

    # ── Operacje na bąblach i indeksowaniu ──────────────────────────────────
    def _index_bubble(self, bubble) -> int:
        count = 0
        for atom in bubble.atoms():
            if getattr(atom, 'vector', None) is None or getattr(atom, 'vector_dirty', False):
                self._ensure_vector(atom)
                count += 1
        self._indexed_bubbles.add(bubble.label)
        return count

    # ── Wyszukiwanie semantyczne ────────────────────────────────────────────
    def search(self, query: str, limit: int = 10) -> List[Tuple[float, Any]]:
        # Ewentualnie przebuduj indeks
        self._maybe_reindex()

        hrr = self._hrr
        q_vec = hrr.atom_vector(query)
        results = []

        if self._sem_index is not None:
            # Wyszukiwanie z indeksem
            candidates = self._sem_index.query(q_vec, top_k_buckets=3)
            # Zapewnij aktualne wektory
            for atom in candidates:
                vec = self._ensure_vector(atom)
                sim = hrr.similarity(q_vec, vec)
                results.append((sim, atom))
        else:
            # Brute-force
            for atom in self._all_atoms():
                vec = self._ensure_vector(atom)
                sim = hrr.similarity(q_vec, vec)
                atom.touch()
                results.append((sim, atom))

        results.sort(key=lambda x: -x[0])
        return results[:limit]

    def search_in_bubble(self, bubble_label: str, query: str, limit: int = 10) -> List[Tuple[float, Any]]:
        bubble = self._get_bubble(bubble_label)
        if not bubble or not hasattr(bubble, 'atoms'):
            return []
        hrr = self._hrr
        q_vec = hrr.atom_vector(query)
        results = []
        for atom in bubble.atoms():
            vec = self._ensure_vector(atom)
            sim = hrr.similarity(q_vec, vec)
            atom.touch()
            results.append((sim, atom))
        results.sort(key=lambda x: -x[0])
        return results[:limit]

# ── Komendy shella ──────────────────────────────────────────────────────────
def cmd_kql(args, runtime=None, **_kw) -> str:
    if not args:
        return "Użycie: KQL <tekst> lub KQL @plik.kql"
    if args[0].startswith('@'):
        try:
            with open(args[0][1:], 'r', encoding='utf-8') as f:
                script = f.read()
        except Exception as e:
            return f"Błąd odczytu pliku: {e}"
    else:
        script = ' '.join(args)
    if runtime is None:
        return "Brak phi-space"
    if not hasattr(runtime, '_hrr'):
        return "Obiekt runtime nie jest poprawną przestrzenią Phi"
    db = KarminDatabase(runtime)
    results = db.execute(script)
    return "\n".join(results)

def cmd_index(args, runtime=None, **_kw) -> str:
    if len(args) < 2 or args[0].upper() != "BUBBLE":
        return "Użycie: INDEX BUBBLE <nazwa_bąbla>"
    bubble_name = args[1]
    if runtime is None:
        return "Brak phi-space"
    if not hasattr(runtime, '_hrr'):
        return "Obiekt runtime nie jest poprawną przestrzenią Phi"
    db = KarminDatabase(runtime)
    bubble = db._get_bubble(bubble_name)
    if not bubble:
        return f"Bąbel {bubble_name} nie istnieje"
    count = db._index_bubble(bubble)
    return f"Zaindeksowano {count} atomów w bąblu {bubble_name}"

def cmd_search(args, runtime=None, **_kw) -> str:
    if not args:
        return "Użycie: SEARCH <fraza> [--bubble <nazwa>] [--limit N]"
    # shlex już ogarnia cytaty na poziomie shella – tutaj łączymy ręcznie dla pewności
    merged = []
    i = 0
    while i < len(args):
        if args[i].startswith('"'):
            phrase = args[i][1:]
            while not phrase.endswith('"') and i+1 < len(args):
                i += 1
                phrase += " " + args[i]
            merged.append(phrase.rstrip('"'))
        else:
            merged.append(args[i])
        i += 1

    query = merged[0]
    bubble = None
    limit = 10
    i = 1
    while i < len(merged):
        if merged[i] == "--bubble" and i+1 < len(merged):
            bubble = merged[i+1]
            i += 2
        elif merged[i] == "--limit" and i+1 < len(merged):
            try:
                limit = int(merged[i+1])
            except:
                pass
            i += 2
        else:
            i += 1

    if runtime is None:
        return "Brak phi-space"
    if not hasattr(runtime, '_hrr'):
        return "Obiekt runtime nie jest poprawną przestrzenią Phi"
    db = KarminDatabase(runtime)
    if bubble:
        results = db.search_in_bubble(bubble, query, limit)
    else:
        results = db.search(query, limit)
    if not results:
        return f"Brak wyników dla '{query}'"
    out = [f"Wyniki dla '{query}':"]
    for sim, atom in results:
        out.append(f"  {sim:.3f} – {atom.id} (T={atom.T:.1f}) S={atom.S}")
    return "\n".join(out)

def register_karmindb(reg_fn, runtime):
    reg_fn("KQL", lambda args: cmd_kql(args, runtime=runtime),
           "Wykonaj skrypt KarminQL", category="database")
    reg_fn("INDEX", lambda args: cmd_index(args, runtime=runtime),
           "Indeksuj bąbel", category="database")
    reg_fn("SEARCH", lambda args: cmd_search(args, runtime=runtime),
           "Wyszukiwanie semantyczne", category="database")