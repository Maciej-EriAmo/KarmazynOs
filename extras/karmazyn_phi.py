"""
karmazyn_phi.py — Phi-Space KarmazynOS v1.0.1 (Zintegrowane z Jądrem)
======================================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Warstwa phi-space: atomy, bąble, hologramy.
Używa karmazyn_kernel jako jedynego wejścia do rdzenia systemu (zgodność
z kernel_boundary.py oraz kontraktem AtomStore).

FIX v1.0.1:
  - Usunięto zduplikowaną definicję list_bubbles()
  - Naprawiono len(b.atoms) → len(b) (atoms to metoda, nie property)
  - step() zwraca generator (atom, event) zamiast Dict
  - Integracja z karmazyn_kernel (usunięcie bezpośrednich importów)
  - Dostosowanie sygnatury create_bubble do kontraktu AtomStore

Interfejs kompatybilny z istniejącym runtime.py oraz nowym AtomStore.
"""

import hashlib
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# ─── Granica Jądra: Importujemy TYLKO z publicznej fasady ────────────────────
from karmazyn_kernel import (
    Atom, AtomRegistry,
    T_INIT, T_WARM,                 # FIX: usunięto nieużywane T_MAX, T_HOT, T_TOMB
    DECAY_DEFAULT, state_for_T,
    HRROperations,
    assert_conforms
)


# ─── EventBus ─────────────────────────────────────────────────────────────────

class EventBus:
    """
    Minimalny EventBus — nie polling, tylko emit/on.
    Scheduler słucha, atomy emitują.
    Pozostawiony w warstwie oprogramowania z uwagi na bogatszy interfejs 
    (off, has_listeners) niż ten obecny w natywnym silniku jądra.
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


# ─── Genom ontologii (opcja A: jeden root-sekret) ──────────────────────────────

def derive_genome(system_secret: bytes,
                  info: bytes = b"karmazyn:ontology",
                  length: int = 32) -> bytes:
    """
    Wyprowadza genom ontologii z istniejącego sekretu instancji (np. _system_phi
    z phi_store, przekazany jako bajty) przez HKDF-SHA256. Opcja A: jeden
    root-sekret, bez dublowania — nie rozmydla istniejącego modelu klucza.
    Genom zalążkuje hologramy ontologiczne; jedyny atak to klon pełnej migawki.
    """
    import hmac   # hashlib już zaimportowany na poziomie modułu
    salt = b"\x00" * hashlib.sha256().digest_size
    prk  = hmac.new(salt, system_secret, hashlib.sha256).digest()      # HKDF-Extract
    okm  = hmac.new(prk, info + b"\x01", hashlib.sha256).digest()      # HKDF-Expand (1 blok)
    return okm[:length]


# ─── PhiSpace ─────────────────────────────────────────────────────────────────

class PhiSpace:
    """
    Główny interfejs phi-space KarmazynOS.

    Kompatybilny z istniejącym runtime.py — drop-in replacement
    lub uzupełnienie dla warstw które nie mogą zmienić runtime.
    W 100% kompatybilny z nowym kontraktem jądra: AtomStore.
    """

    def __init__(self):
        self.matrix   = AtomRegistry()
        self._bubbles: Dict[str, PhiBubble]   = {}
        self._holos:   Dict[str, PhiHologram] = {}
        self.events    = EventBus()
        self._hrr      = None   # opcjonalny — aktywowany przez enable_hrr()
        self._genome     = b""  # sekret instancji (zalążek ontologii); pusty = ontologia publiczna (back-compat)
        self._genome_hex = ""
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
            if self._hrr is not None:
                a.vector = self._bind_phi(S, E)   # S/E zmienione → przelicz współrzędną holograficzną
            return a
        a = self.matrix.create(id, S, E, T, **kwargs)
        # Podepnij callback do EventBus
        a.on_state_change(lambda atom: self._on_state_change(atom))
        # Opcjonalnie: współrzędna holograficzna = bind(onto(S), val(E))
        if self._hrr is not None:
            a.vector = self._bind_phi(S, E)
        self.events.emit("atom_created", a)
        return a

    def get_atom(self, id: str) -> Optional[Atom]:
        """Pobierz atom i ogrzej (dostęp użytkownika)."""
        a = self.matrix.get(id)
        if a:
            a.touch()
        return a

    def embed(self, text: str, dim: int = 15) -> Any:
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

        FIX #8: przy braku numpy RZUCA RuntimeError zamiast zwracać None —
        wcześniej cichy None wybuchał AttributeError u wywołującego.
        """
        import re as _re
        try:
            import numpy as _np
        except ImportError as e:
            raise RuntimeError("embed() wymaga numpy (pip install numpy)") from e

        tokens = [w for w in _re.split(r"\W+", text.lower()) if len(w) > 1]
        if not tokens:
            tokens = [text[:8] if text else "phi"]

        vec = _np.zeros(dim, dtype=_np.float32)
        for tok in set(tokens):
            seed = int(hashlib.md5(tok.encode()).hexdigest(), 16) % (2 ** 32)
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
            a.kill()                       # FIX #4: kill→callback _on_state_change→vacuum_decay (jedno źródło)
            self.matrix.delete(id)
            self._purge_from_bubbles(id)   # FIX #6: nie zostawiaj martwego id w bąblach
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
            atom.decay(rate)              # FIX #4: decay→callback emituje state_changed/vacuum_decay (jedno źródło)

            if atom.is_dead():
                to_remove.append(atom.id)
                yield atom, "vacuum_decay"
            else:
                yield atom, "tick"
                if atom.state != old_state:
                    yield atom, "state_changed"

        for atom_id in to_remove:
            self.matrix.delete(atom_id)
            self._purge_from_bubbles(atom_id)   # FIX #6

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

    def create_bubble(self, label: str, atom_ids: Optional[List[str]] = None) -> Optional[str]:
        """FIX #1: zwraca ETYKIETĘ (str) zgodnie z kontraktem AtomStore,
        nie obiekt PhiBubble. Bąbel pobierzesz przez get_bubble(label)."""
        if label not in self._bubbles:
            self._bubbles[label] = PhiBubble(label, self)
        b = self._bubbles[label]
        if atom_ids:
            for aid in atom_ids:
                b.add(aid)
        return label

    def _purge_from_bubbles(self, atom_id: str) -> None:
        """FIX #6: usuwa id usuniętego atomu ze wszystkich bąbli, by lista
        _ids nie rosła bez granic. Łata lokalna — w docelowej re-platformie
        na Store osiągalne atomy są archiwizowane (reach-GC), więc usuwanie
        spod bąbla w ogóle nie zachodzi."""
        for b in self._bubbles.values():
            if atom_id in b._ids:
                b._ids.remove(atom_id)

    def import_to_bubble(self, label: str, atom_id: str) -> bool:
        bubble = self._bubbles.get(label)
        if bubble is None or not self.matrix.has(atom_id):
            return False
        bubble.add(atom_id)
        return True

    def list_bubbles(self) -> List[Dict[str, Any]]:
        """Zwraca listę bąbli z metadanymi dla FM i innych komponentów."""
        result = []
        for label, bubble in self._bubbles.items():
            result.append({
                "label":        label,
                "id":           label,
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
        dead_ids = self.matrix.tick(rate)    # FIX #4: decay→callback emituje vacuum_decay (jedno źródło)
        collected = self.matrix.gc(dead_ids)
        for id in dead_ids:
            self._purge_from_bubbles(id)     # FIX #6
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

    # ── Współrzędne holograficzne (onto ⊛ wartość) ──────────────────────────
    def _holo(self, kind: str, text: str):
        """
        Hologram zalążkowany genomem instancji.
          kind='onto' → hologram ontologiczny (rola, czym rzecz JEST = S)
          kind='val'  → hologram zadaniowy (wartość, treść = E)
        Cache w HRROperations._vectors działa jak rejestr pamięci ontologicznej:
        ten sam (genom, kind, text) → ten sam wektor. Bez genomu (genome_hex='')
        hologramy są publiczne — zgodność wsteczna.
        """
        name = f"{self._genome_hex}|{kind}|{text}"
        return self._hrr.atom_vector(name)

    def _bind_phi(self, S: str, E: str):
        """vector = bind(onto(S), val(E)) — matematyczne odwzorowanie hologramu."""
        onto = self._holo("onto", S or "")    # hologram ontologiczny (rola)
        val  = self._holo("val",  E or "")    # hologram zadaniowy (wartość)
        return self._hrr.bind(onto, val)

    # ── Bąble-wyniki (punkt dostępu keyowany hologramem programu) ────────────
    def result_bubble_label(self, program_name: str) -> str:
        """
        Etykieta bąbla-wyniku keyowana hologramem ontologicznym programu
        (genom-sealed). Tylko ktoś, kto potrafi policzyć onto(program:<name>)
        — czyli zna genom instancji — wyprowadzi tę etykietę i dotrze do bąbla.
        Bez HRR (genom off): fallback po nazwie — działa, bez izolacji geometrycznej.
        """
        if self._hrr is not None:
            onto = self._holo("onto", f"program:{program_name}")
            return "res::" + hashlib.sha256(onto.tobytes()).hexdigest()[:16]
        return f"res::{program_name}"

    def open_result_bubble(self, program_name: str, create: bool = False):
        """
        Punkt dostępu do wyników programu. Zwraca bąbel-wynik (lub None).
        Wymaga genomu (przez result_bubble_label); bez niego etykieta jest
        nieobliczalna → bąbel geometrycznie nieosiągalny, nawet dla twórcy.
        Dostęp po nazwie (Workspace) i globalne atoms() pozostają nietknięte —
        to jest DODATKOWA ścieżka dostępu (addytywny scoping).
        """
        label = self.result_bubble_label(program_name)
        b = self.get_bubble(label)
        if b is None and create:
            self.create_bubble(label)          # zwraca label (str) — FIX #1
            b = self.get_bubble(label)
        return b

    def scoped_atoms(self, program_name: str) -> list:
        """
        Widok scoped hologramem: atomy w przestrzeni danego programu (jego
        bąbel-wynik keyowany hologramem). Wymaga genomu do policzenia etykiety —
        bez właściwego hologramu zwraca pustkę (przestrzeń nieosiągalna).

        ADDYTYWNE: globalne matrix.atoms() i dostęp po nazwie są nietknięte;
        to jest dodatkowa, zawężona ścieżka odczytu (izolacja, nie semantyka).
        """
        bub = self.open_result_bubble(program_name)
        if bub is None:
            return []
        out = []
        for ref in bub.atoms():
            a = self.matrix.get(ref) if isinstance(ref, str) else ref
            if a is not None:
                out.append(a)
        return out

    def enable_hrr(self, D: int = 2048, genome: bytes = None) -> None:
        """
        Aktywuje współrzędne holograficzne HRR dla atomów.

        genome — sekret instancji (zalążek ontologii). Gdy podany, hologram
                 ontologiczny onto(S) jest nieodtwarzalny bez genomu (model
                 'ontologia = klucz'; jedyny atak = klon migawki z genomem).
                 Gdy None — ontologia publiczna (zgodność wsteczna).

        Po aktywacji każdy atom (nowy i istniejący): vector = bind(onto(S), val(E)).
        """
        # Usunięto lokalny import - bierzemy HRROperations prosto z karmazyn_kernel
        self._hrr = HRROperations(D)
        self._genome     = genome or b""
        self._genome_hex = self._genome.hex()
        # Retroaktywnie: nadaj wszystkim atomom współrzędną holograficzną
        for atom in self.matrix.atoms():
            atom.vector = self._bind_phi(atom.S, atom.E)

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

if __name__ == "__main__":
    # Test weryfikujący zintegrowany kontrakt AtomStore ze środowiskiem:
    phi = PhiSpace()
    assert_conforms(phi, "PhiSpace")
    print("✓ PhiSpace spełnia w 100% rygorystyczny kontrakt AtomStore.")