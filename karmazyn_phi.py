"""
karmazyn_phi.py — Phi-Space KarmazynOS v1.0.1
==============================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Warstwa phi-space: atomy, bąble, hologramy.
Używa karmazyn_atom.Atom jako jedynego modelu atomu.

FIX v1.0.1:
  - Usunięto zduplikowaną definicję list_bubbles()
  - Naprawiono len(b.atoms) → len(b) (atoms to metoda, nie property)
  - step() zwraca generator (atom, event) zamiast Dict

Interfejs kompatybilny z istniejącym runtime.py:
  phi.create_atom(id, S, E, T)
  phi.get_atom(id)
  phi.matrix.has_atom(id)
  phi.matrix.atoms()
  phi.consolidate(atom_id)
  phi.get_bubble(label)
  phi.import_to_bubble(label, atom_id)
  phi.archive_to_hologram(topic, atom_ids)
  phi.events.on(event, handler)
  phi.events.emit(event, atom)

Nowe możliwości (ponad runtime.py):
  phi.tick()                — GC + decay wszystkich atomów
  phi.thermal_map()         — mapa temperatur
  phi.find_resonating(q, T_min) — atomy rezonujące z zapytaniem
  bubble.resonates_with(atom, threshold) — sprawdzenie rezonansu

Opcjonalna integracja HRR:
  phi.enable_hrr(D=2048)    — aktywuje wektorowe osadzenia
  phi.find_similar(atom)    — nearest-neighbor przez HRR
"""

import hashlib
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from karmazyn_atom import (
    Atom, AtomRegistry,
    T_INIT, T_MAX, T_HOT, T_WARM, T_TOMB,
    DECAY_DEFAULT, state_for_T,
)


# ─── EventBus ─────────────────────────────────────────────────────────────────

class EventBus:
    """
    Minimalny EventBus — nie polling, tylko emit/on.
    Scheduler słucha, atomy emitują.
    """

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}

    def on(self, event: str, handler: Callable) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event: str, handler: Callable) -> None:
        if event in self._handlers:
            try:
                self._handlers[event].remove(handler)
            except ValueError:
                pass

    def emit(self, event: str, *args, **kwargs) -> None:
        for h in list(self._handlers.get(event, [])):
            try:
                h(*args, **kwargs)
            except Exception:
                pass

    def has_listeners(self, event: str) -> bool:
        return bool(self._handlers.get(event))


# ─── PhiBubble ────────────────────────────────────────────────────────────────

class PhiBubble:
    """
    Bąbel — kolekcja atomów z etykietą i treścią.

    Zastępuje rozproszone listy atom_ids w starym kodzie.
    Temperatura bąbla = średnia temperatura jego atomów.
    """

    def __init__(self, label: str, phi: "PhiSpace"):
        self.label    = label
        self._phi     = phi
        self._ids:    List[str] = []
        self.content: str = ""          # tekstowa treść bąbla
        self._T:      float = T_INIT

    def add(self, atom_id: str) -> None:
        if atom_id not in self._ids:
            self._ids.append(atom_id)
            self._update_T()

    def remove(self, atom_id: str) -> None:
        if atom_id in self._ids:
            self._ids.remove(atom_id)
            self._update_T()

    def atoms(self) -> List[Atom]:
        return [a for id in self._ids
                if (a := self._phi.matrix.get(id)) is not None]

    def hot_atoms(self) -> List[Atom]:
        return [a for a in self.atoms() if a.is_hot]

    def resonates_with(self, atom: Atom,
                       threshold: float = 0.5) -> bool:
        """
        Sprawdza czy atom rezonuje z bąblem.
        Heurystyka: atom jest w bąblu lub ma podobne S.
        """
        if atom.id in self._ids:
            return True
        # Rezonans przez S (semantyczne S)
        for a in self.atoms():
            if (a.S == atom.S
                    or (a.S and atom.S and
                        a.S.split(":")[0] == atom.S.split(":")[0])):
                return True
        return False

    def _update_T(self) -> None:
        atom_list = self.atoms()
        if atom_list:
            self._T = sum(a.T for a in atom_list) / len(atom_list)

    @property
    def T(self) -> float:
        self._update_T()
        return self._T

    @property
    def state(self) -> str:
        return state_for_T(self.T)

    def __len__(self) -> int:
        return len(self._ids)

    def __repr__(self) -> str:
        return f"PhiBubble({self.label!r}, n={len(self._ids)}, T={self.T:.1f})"


# ─── PhiHologram ─────────────────────────────────────────────────────────────

class PhiHologram:
    """
    Hologram — prototyp + generatory.
    Reprezentuje uogólnioną strukturę (np. historię commitów, dokumenty).
    """

    def __init__(self, id: str, topic: str):
        self.id             = id
        self.topic          = topic
        self.prototype_id:  Optional[str] = None
        self.generator_ids: List[str]     = []
        self._created       = time.monotonic()

    def age(self) -> float:
        return time.monotonic() - self._created

    def __repr__(self) -> str:
        return f"PhiHologram({self.id!r}, topic={self.topic!r}, generators={len(self.generator_ids)})"


# ─── PhiSpace ─────────────────────────────────────────────────────────────────

class PhiSpace:
    """
    Główny interfejs phi-space KarmazynOS.

    Kompatybilny z istniejącym runtime.py — drop-in replacement
    lub uzupełnienie dla warstw które nie mogą zmienić runtime.

    Wszystkie atomy używają karmazyn_atom.Atom.
    Jeden punkt prawdy dla T, state, decay.
    """

    def __init__(self):
        self.matrix   = AtomRegistry()
        self._bubbles: Dict[str, PhiBubble]   = {}
        self._holos:   Dict[str, PhiHologram] = {}
        self.events    = EventBus()
        self._hrr      = None   # opcjonalny — aktywowany przez enable_hrr()
        self._tick_n   = 0
        self._started  = time.monotonic()

    # ── Atomy ─────────────────────────────────────────────────────────────────

    def create_atom(self, id: str, S: str = "", E: str = "",
                    T: float = T_INIT, **kwargs) -> Atom:
        """Tworzy atom i emituje zdarzenie atom_created."""
        if self.matrix.has(id):
            # Aktualizuj istniejący
            a = self.matrix.get(id)
            a.S = S; a.E = E
            if T > a.T:
                a.heat(T - a.T)
            else:
                a.cool(a.T - T)
            return a
        a = self.matrix.create(id, S, E, T, **kwargs)
        # Podepnij callback do EventBus
        a.on_state_change(lambda atom: self._on_state_change(atom))
        # Opcjonalnie: generuj wektor HRR
        if self._hrr is not None:
            a.vector = self._hrr.atom_vector(id)
        self.events.emit("atom_created", a)
        return a

    def get_atom(self, id: str) -> Optional[Atom]:
        """Pobierz atom i ogrzej (dostęp użytkownika)."""
        a = self.matrix.get(id)
        if a:
            a.touch()
        return a

    def embed(self, text: str, dim: int = 15) -> "np.ndarray":
        """
        Deterministyczny embedding tekstu → wektor dim-wymiarowy.

        Algorytm:
          1. Tokenizuj tekst (słowa > 1 znak)
          2. Dla każdego tokenu: MD5 → seed → losowy wektor N-D
          3. Sumuj wektory i normalizuj do sfery jednostkowej

        Właściwości:
          - Deterministyczny: ten sam tekst → ten sam wektor
          - Bez zewnętrznych modeli (zero zależności)
          - Podobne słowa → podobne wektory (przez częściowe overlap tokenów)

        Używany przez PhiBuffer do projekcji semantycznej
        i przez DOMMapper do osadzania węzłów DOM w phi-space.

        Izomorfizm: text → punkt na sferze S^(dim-1)
        Odpowiada atom.S gdy S to string semantyczny.
        """
        import hashlib as _hl, re as _re
        try:
            import numpy as _np
        except ImportError:
            return None

        tokens = [w for w in _re.split(r"\W+", text.lower()) if len(w) > 1]
        if not tokens:
            tokens = [text[:8] if text else "phi"]

        vec = _np.zeros(dim, dtype=_np.float32)
        for tok in set(tokens):
            seed = int(_hl.md5(tok.encode()).hexdigest(), 16) % (2 ** 32)
            v    = _np.random.default_rng(seed).standard_normal(dim).astype(_np.float32)
            vec += v

        norm = _np.linalg.norm(vec)
        return (vec / norm) if norm > 1e-9 else vec

    def peek_atom(self, id: str) -> Optional[Atom]:
        """Pobierz atom BEZ ogrzewania — do użytku wewnętrznego
        (render, scheduler, audyt). Nie zmienia T."""
        return self.matrix.get(id)

    def delete_atom(self, id: str) -> bool:
        a = self.matrix.get(id)
        if a:
            a.kill()
            self.events.emit("vacuum_decay", a)
            self.matrix.delete(id)
            return True
        return False

    def has_atom(self, id: str) -> bool:
        return self.matrix.has(id)

    def step(self, rate: float = DECAY_DEFAULT):
        """
        Jeden krok termodynamiczny — odpowiednik tick() z eventami.

        Różnica od tick():
          tick() → zwraca Dict[str, int] (statystyki)
          step() → yields (atom, event_type) — reaktywny, do iteracji

        Event types:
          "tick"          — atom żyje, standardowy krok
          "state_changed" — zmiana HOT/WARM/COLD
          "vacuum_decay"  — atom przekroczył próg TOMB

        Użycie:
          for atom, event in phi.step():
              if event == "vacuum_decay":
                  cleanup(atom)

        Kompatybilny z HSSKarmazynMatrix.step() (ten sam protokół).
        """
        self._tick_n += 1
        to_remove = []

        for atom in list(self.matrix.atoms()):
            old_state = atom.state
            atom.decay(rate)

            if atom.is_dead():
                to_remove.append(atom.id)
                self.events.emit("vacuum_decay", atom)
                yield atom, "vacuum_decay"
            else:
                yield atom, "tick"
                if atom.state != old_state:
                    self.events.emit("state_changed", atom)
                    yield atom, "state_changed"

        for atom_id in to_remove:
            self.matrix.delete(atom_id)

    # ── Bąble ─────────────────────────────────────────────────────────────────

    def consolidate(self, atom_id: str,
                    bubble_label: Optional[str] = None) -> Optional[PhiBubble]:
        """
        Konsoliduje atom do bąbla.
        Jeśli bubble_label = None, używa atom_id jako etykiety.
        """
        a = self.matrix.get(atom_id)
        if a is None:
            return None
        label  = bubble_label or atom_id
        bubble = self._bubbles.setdefault(label, PhiBubble(label, self))
        bubble.add(atom_id)
        return bubble

    def get_bubble(self, label: str) -> Optional[PhiBubble]:
        return self._bubbles.get(label)

    def create_bubble(self, label: str) -> PhiBubble:
        if label not in self._bubbles:
            self._bubbles[label] = PhiBubble(label, self)
        return self._bubbles[label]

    def import_to_bubble(self, label: str, atom_id: str) -> bool:
        bubble = self._bubbles.get(label)
        if bubble is None or not self.matrix.has(atom_id):
            return False
        bubble.add(atom_id)
        return True

    # FIX v1.0.1: Jedna definicja list_bubbles z poprawnymi polami
    # Usunięto zduplikowaną drugą definicję która nadpisywała tę
    # i miała bug len(b.atoms) zamiast len(b)
    def list_bubbles(self) -> List[Dict[str, Any]]:
        """Zwraca listę bąbli z metadanymi dla FM i innych komponentów."""
        result = []
        for label, bubble in self._bubbles.items():
            result.append({
                "label":        label,
                "id":           label,
                # FIX: len(bubble) zamiast len(bubble.atoms)
                # bubble.atoms to metoda (zwraca listę), len() na metodzie = TypeError
                # lub zawsze 1 (truthy). len(bubble) wywołuje __len__ = len(self._ids)
                "active_atoms": len(bubble),
                "T":            round(bubble.T, 1),
                "state":        bubble.state,
            })
        return result

    # ── Hologramy ─────────────────────────────────────────────────────────────

    def archive_to_hologram(self, topic: str,
                             atom_ids: List[str],
                             remove_originals: bool = False) -> str:
        """Archiwizuje atomy jako hologram."""
        hid = f"holo_{hashlib.md5(topic.encode()).hexdigest()[:8]}"
        h   = PhiHologram(hid, topic)
        h.prototype_id  = atom_ids[0] if atom_ids else None
        h.generator_ids = atom_ids[1:]
        self._holos[hid] = h
        if remove_originals:
            for aid in atom_ids:
                self.delete_atom(aid)
        return hid

    def get_hologram(self, hid: str) -> Optional[PhiHologram]:
        return self._holos.get(hid)

    # ── Tick / GC ─────────────────────────────────────────────────────────────

    def tick(self, rate: float = DECAY_DEFAULT) -> Dict[str, int]:
        """
        Jeden tick schedulera:
          1. Decay wszystkich atomów
          2. Emituj vacuum_decay dla martwych
          3. GC
        Wywoływany przez ThermalScheduler — nie polling.
        """
        self._tick_n += 1
        dead_ids = self.matrix.tick(rate)

        for id in dead_ids:
            a = self.matrix.get(id)
            if a:
                self.events.emit("vacuum_decay", a)

        collected = self.matrix.gc(dead_ids)
        return {
            "tick":      self._tick_n,
            "collected": collected,
            "atoms":     len(self.matrix),
        }

    def _on_state_change(self, atom: Atom) -> None:
        """Emituje state_changed przez EventBus."""
        self.events.emit("state_changed", atom)
        if atom.state == "TOMB":
            self.events.emit("vacuum_decay", atom)

    # ── Zapytania ─────────────────────────────────────────────────────────────

    def find_resonating(self, query: str,
                        T_min: float = 0.0,
                        limit: int   = 20) -> List[Atom]:
        """
        Znajdź atomy rezonujące z zapytaniem (substring w S lub E).
        Posortowane wg T malejąco.
        """
        q      = query.lower()
        result = [
            a for a in self.matrix.atoms()
            if a.T >= T_min and (
                q in (a.S or "").lower() or
                q in (a.E or "").lower()
            )
        ]
        result.sort(key=lambda a: -a.T)
        return result[:limit]

    def thermal_map(self) -> List[Tuple[str, float, str]]:
        """Lista (id, T, state) posortowana wg T malejąco."""
        atoms = self.matrix.atoms()
        atoms.sort(key=lambda a: -a.T)
        return [(a.id, a.T, a.state) for a in atoms]

    def stop_loop(self) -> None:
        """Zatrzymaj phi-space — stub kompatybilności z SanctuaryRuntime."""
        pass

    def stabilize_atom(self, atom_id: str) -> bool:
        """Stabilizuj atom (ustaw T=T_WARM) — stub."""
        a = self.matrix.get(atom_id)
        if a is None:
            return False
        if a.T < T_WARM:
            a.heat(T_WARM - a.T)
        return True

    def corrupt_atom(self, atom_id: str, amount: float = 25) -> bool:
        """Oznacz atom jako uszkodzony (T→1) — stub."""
        a = self.matrix.get(atom_id)
        if a is None:
            return False
        a.cool(a.T - 1.0)
        return True

    def status_summary(self) -> Dict[str, int]:
        return self.matrix.stats()

    def uptime(self) -> float:
        return time.monotonic() - self._started

    # ── HRR (opcjonalna warstwa wektorowa) ───────────────────────────────────

    def enable_hrr(self, D: int = 2048) -> None:
        """
        Aktywuje osadzenia HRR dla atomów.
        Po aktywacji: każdy nowy atom dostaje wektor.
        Istniejące atomy dostają wektory retroaktywnie.
        """
        try:
            from karmazyn_hrr import HRROperations
            self._hrr = HRROperations(D)
            # Retroaktywnie
            for atom in self.matrix.atoms():
                if atom.vector is None:
                    atom.vector = self._hrr.atom_vector(atom.id)
        except ImportError:
            pass

    def find_similar_hrr(self, atom: Atom,
                         top_k: int = 5,
                         threshold: float = 0.15) -> List[Tuple[float, Atom]]:
        """
        Nearest-neighbor przez HRR (jeśli aktywowane).
        Zwraca [(similarity, atom), ...].
        """
        if self._hrr is None or atom.vector is None:
            return []
        results = []
        av = atom.vector
        for a in self.matrix.atoms():
            if a is atom or a.vector is None:
                continue
            s = self._hrr.similarity(av, a.vector)
            if s >= threshold:
                results.append((s, a))
        results.sort(key=lambda x: -x[0])
        return results[:top_k]

    # ── Serializacja ──────────────────────────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        """Snapshot stanu phi-space (dla debugowania)."""
        return {
            "tick":    self._tick_n,
            "uptime":  round(self.uptime(), 1),
            "atoms":   self.matrix.stats(),
            "bubbles": len(self._bubbles),
            "holos":   len(self._holos),
            "hrr":     self._hrr is not None,
        }