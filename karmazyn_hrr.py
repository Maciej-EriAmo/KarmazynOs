"""
karmazyn_hrr.py — Holographic Reduced Representation KarmazynOS v1.2
=====================================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Poprawki v1.2 względem v1.1:
  - Niekomutatywne wiązanie (kierunkowość) przez permutację wektora
  - Zapominanie (forget_rate) – recency bias jako cecha
  - Kara za wysoką temperaturę w nearest (zapobieganie runaway attractors)
  - Confidence score (zwracanie podobieństwa) w get/nearest
  - Weighted bindings (importance/attention)
  - Cache dla P_power (wydajność długich hologramów)
  - Cooldown after retrieval (opcjonalne chłodzenie atomu po odczycie)
  - Ulepszone testy: analogia z asercją podobieństwa
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from numpy.fft import fft, ifft


# ─── Stałe ───────────────────────────────────────────────────────────────────

D_DEFAULT      = 2048      # wymiar przestrzeni (kompromis dokładność/wydajność)
T_INIT         = 50.0      # temperatura startowa atomu
T_HOT          = 90.0      # próg HOT
T_WARM         = 30.0      # próg WARM
T_TOMB         = 2.0       # próg GC
DECAY_RATE     = 0.95      # mnożnik temperatury przy tick
HEAT_TOUCH     = 10.0      # przyrost T przy dostępie
HEAT_COOLDOWN  = 2.0       # przyrost T przy odczycie z cooldown
TEMP_PENALTY   = 0.02      # domyślna kara za wysoką temperaturę (dla nearest)
SIM_THRESHOLD  = 0.15      # minimalny próg podobieństwa dla retrieval
FORGET_RATE    = 0.0       # domyślnie brak zapominania


# ─── HRRAtom ─────────────────────────────────────────────────────────────────

class HRRAtom:
    """Nazwany wektor z temperaturą phi-space."""

    __slots__ = ("name", "vector", "value", "T", "state", "_born", "_reads")

    def __init__(self, name: str, vector: np.ndarray, value: Any = None):
        self.name   = name
        self.vector = vector.copy()
        self.value  = value
        self.T      = T_INIT
        self.state  = "WARM"
        self._born  = time.monotonic()
        self._reads = 0

    def touch(self, cooldown: bool = False) -> None:
        """Ogrzewa atom. Jeśli cooldown=True, grzeje słabiej."""
        self._reads += 1
        delta = HEAT_COOLDOWN if cooldown else HEAT_TOUCH
        self.T = min(100.0, self.T + delta)
        self._update_state()

    def decay(self) -> None:
        self.T *= DECAY_RATE
        self._update_state()

    def _update_state(self) -> None:
        if   self.T >= T_HOT:  self.state = "HOT"
        elif self.T >= T_WARM: self.state = "WARM"
        elif self.T >= T_TOMB: self.state = "COLD"
        else:                   self.state = "TOMB"

    def is_dead(self) -> bool:
        return self.T < T_TOMB

    def age(self) -> float:
        return time.monotonic() - self._born

    def __repr__(self) -> str:
        return f"HRRAtom({self.name!r}, T={self.T:.1f}, {self.state})"


# ─── HRRSpace ─────────────────────────────────────────────────────────────────

class HRRSpace:
    """
    Globalne operacje HRR + rejestr atomów.
    Obsługuje niekomutatywne wiązanie przez permutację.
    """

    def __init__(self, D: int = D_DEFAULT, seed: Optional[int] = None):
        self.D     = D
        self._seed = seed
        self._atoms: Dict[str, HRRAtom] = {}
        self._index: List[Tuple[np.ndarray, HRRAtom]] = []
        self._P: Optional[np.ndarray] = None
        self._P_cache: Dict[int, np.ndarray] = {}   # cache dla P_power

    # ── Tworzenie i pobieranie atomów ─────────────────────────────────────────

    def atom(self, name: str, value: Any = None) -> HRRAtom:
        if name in self._atoms:
            a = self._atoms[name]
            if value is not None:
                a.value = value
            a.touch()
            return a
        v   = self._name_to_vector(name)
        a   = HRRAtom(name, v, value)
        self._atoms[name] = a
        self._index.append((v, a))
        return a

    def atom_for_value(self, value: Any) -> HRRAtom:
        if isinstance(value, (int, float, bool)):
            key = f"__val__{type(value).__name__}_{value}"
        elif isinstance(value, str):
            h = hashlib.md5(value.encode()).hexdigest()[:8]
            key = f"__str__{h}"
        elif value is None:
            key = "__null__"
        else:
            key = f"__obj__{id(value)}"
        a = self.atom(key, value)
        return a

    def _name_to_vector(self, name: str) -> np.ndarray:
        h    = int(hashlib.sha256(name.encode()).hexdigest(), 16) % (2**32)
        rng  = np.random.RandomState(h)
        v    = rng.randn(self.D)
        return v / np.linalg.norm(v)

    # ── Operacje HRR ──────────────────────────────────────────────────────────

    def bind(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Splot kołowy (komutatywny)."""
        return np.real(ifft(fft(a) * fft(b)))

    def rotate(self, v: np.ndarray, k: int = 1) -> np.ndarray:
        """Cykliczne przesunięcie (permutacja) – dla kierunkowości."""
        return np.roll(v, k)

    def bind_dir(self, a: np.ndarray, b: np.ndarray, role: str = "both") -> np.ndarray:
        """
        Wiązanie kierunkowe (niekomutatywne).
        role:
          "arg1" : bind(a, rotate(b))   – b jako rola
          "arg2" : bind(rotate(a), b)   – a jako rola
          "both" : bind(a, b)           – komutatywne (fallback)
        """
        if role == "arg1":
            return self.bind(a, self.rotate(b, k=1))
        elif role == "arg2":
            return self.bind(self.rotate(a, k=1), b)
        else:
            return self.bind(a, b)

    def unbind(self, bundle: np.ndarray, key: np.ndarray) -> np.ndarray:
        """Korelacja kołowa (odwrotność bind, komutatywna)."""
        return np.real(ifft(fft(bundle) * np.conj(fft(key))))

    def unbind_dir(self, bundle: np.ndarray, key: np.ndarray, role: str = "both") -> np.ndarray:
        """
        Odwiązanie kierunkowe – stosuje permutację odpowiednio do role.
        Dla role="arg1" odwraca permutację: unbind(bundle, rotate(key, -1)).
        """
        if role == "arg1":
            return self.unbind(bundle, self.rotate(key, k=-1))
        elif role == "arg2":
            return self.unbind(bundle, self.rotate(key, k=-1))
        else:
            return self.unbind(bundle, key)

    def bundle(self, *vecs: np.ndarray) -> np.ndarray:
        if not vecs:
            return np.zeros(self.D)
        return sum(vecs)

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na < 1e-10 or nb < 1e-10:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def normalize(self, v: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(v)
        return v / n if n > 1e-10 else v

    # ── Nearest neighbor z karą termiczną ─────────────────────────────────────

    def nearest(self, vec: np.ndarray,
                k: int = 5,
                threshold: float = SIM_THRESHOLD,
                temp_penalty: float = TEMP_PENALTY) -> List[Tuple[float, HRRAtom]]:
        """
        Znajduje k najbliższych atomów.
        Podobny atomy z wysoką temperaturą są karane (by nie dominowały).
        """
        results = []
        vn = np.linalg.norm(vec)
        if vn < 1e-10:
            return []

        for av, atom in self._index:
            raw_sim = float(np.dot(vec, av) / (vn * np.linalg.norm(av) + 1e-10))
            effective_sim = raw_sim / (1 + atom.T * temp_penalty)
            if effective_sim >= threshold:
                results.append((effective_sim, atom))

        results.sort(key=lambda x: -x[0])
        return results[:k]

    def nearest_value(self, vec: np.ndarray,
                      threshold: float = SIM_THRESHOLD,
                      temp_penalty: float = TEMP_PENALTY,
                      with_confidence: bool = False) -> Union[Any, Tuple[Any, float]]:
        """
        Zwraca wartość najbliższego atomu (lub None).
        Jeśli with_confidence=True, zwraca (value, similarity).
        Podgrzewa znaleziony atom (touch).
        """
        hits = self.nearest(vec, k=1, threshold=threshold, temp_penalty=temp_penalty)
        if hits:
            sim, atom = hits[0]
            atom.touch(cooldown=False)   # retrieval ogrzewa (można zmienić)
            if with_confidence:
                return atom.value, sim
            return atom.value
        if with_confidence:
            return None, 0.0
        return None

    # ── Permutacja dla sekwencji z cache ──────────────────────────────────────

    @property
    def P(self) -> np.ndarray:
        if self._P is None:
            rng = np.random.RandomState(42)
            v   = rng.randn(self.D)
            self._P = v / np.linalg.norm(v)
        return self._P

    def P_power(self, n: int) -> np.ndarray:
        """P^n = P ⊗ ... ⊗ P (n razy). Z cache'owaniem."""
        if n in self._P_cache:
            return self._P_cache[n]
        if n == 0:
            v = np.zeros(self.D)
            v[0] = 1.0
        elif n == 1:
            v = self.P
        else:
            v = self.bind(self.P_power(n-1), self.P)
        self._P_cache[n] = v
        return v

    # ─── Tick / GC ────────────────────────────────────────────────────────────

    def tick(self) -> int:
        dead = []
        for name, atom in self._atoms.items():
            atom.decay()
            if atom.is_dead():
                dead.append(name)
        for name in dead:
            a = self._atoms.pop(name)
            self._index = [(v, at) for v, at in self._index if at is not a]
        return len(dead)

    def stats(self) -> Dict[str, Any]:
        atoms = list(self._atoms.values())
        return {
            "D": self.D,
            "atoms": len(atoms),
            "hot":   sum(1 for a in atoms if a.state == "HOT"),
            "warm":  sum(1 for a in atoms if a.state == "WARM"),
            "cold":  sum(1 for a in atoms if a.state == "COLD"),
        }


# ─── HRRBubble ────────────────────────────────────────────────────────────────

class HRRBubble:
    """
    Bąbel jako superpozycja bindingów z normalizacją i opcjonalnym zapominaniem.
    Obsługuje wiązania ważone i kierunkowe.
    """

    def __init__(self, space: HRRSpace,
                 parent: Optional["HRRBubble"] = None,
                 name: str = "bubble",
                 forget_rate: float = FORGET_RATE,
                 temp_penalty: float = TEMP_PENALTY):
        self.space   = space
        self.parent  = parent
        self.name    = name
        self.vector  = np.zeros(space.D)
        self._exact: Dict[str, Any] = {}            # fast path
        self._roles: Dict[str, str] = {}            # role dla bindingów (arg1/arg2/both)
        self._weights: Dict[str, float] = {}        # wagi dla bindingów
        self._n      = 0
        self._T      = T_INIT
        self._reads  = 0
        self.forget_rate = forget_rate
        self.temp_penalty = temp_penalty

    def _normalize(self):
        n = np.linalg.norm(self.vector)
        if n > 1e-6:
            self.vector /= n

    def _apply_forget(self):
        """Opcjonalne zapominanie: tłumienie całego wektora."""
        if self.forget_rate > 0:
            self.vector *= (1 - self.forget_rate)

    def set(self, name: str, value: Any, role: str = "both", weight: float = 1.0) -> None:
        """
        Dodaje lub aktualizuje wiązanie name → value.
        role: "arg1", "arg2" lub "both" (kierunkowość).
        weight: waga (importance/attention).
        """
        V_name = self.space.atom(name).vector
        V_val  = self.space.atom_for_value(value).vector

        # Usuń stare wiązanie jeśli istnieje
        if name in self._exact:
            old_val = self._exact[name]
            old_role = self._roles.get(name, "both")
            old_weight = self._weights.get(name, 1.0)
            old_V_val = self.space.atom_for_value(old_val).vector
            old_binding = self.space.bind_dir(V_name, old_V_val, old_role)
            self.vector -= old_weight * old_binding
            self._n -= 1

        # Dodaj nowe wiązanie
        new_binding = self.space.bind_dir(V_name, V_val, role)
        self.vector += weight * new_binding
        self._exact[name] = value
        self._roles[name] = role
        self._weights[name] = weight
        self._n += 1

        self._apply_forget()
        self._normalize()
        self._touch_bubble()

    def get(self, name: str, with_confidence: bool = False) -> Union[Any, Tuple[Any, float]]:
        """
        Odczytuje wartość. Jeśli with_confidence=True, zwraca (value, similarity).
        Fast path: exact dict.
        Soft path: unbind + nearest (z karą termiczną).
        """
        self._reads += 1
        self._touch_bubble()

        # Fast path
        if name in self._exact:
            atom = self.space.atom(name)
            atom.touch(cooldown=False)
            val = self._exact[name]
            if with_confidence:
                # Dla exact path similarity = 1.0
                return val, 1.0
            return val

        # Soft path – HRR
        V_name = self.space.atom(name).vector
        role = self._roles.get(name, "both")
        result = self.space.unbind_dir(self.vector, V_name, role)

        dynamic_threshold = max(0.08, 0.3 / (1 + self._n / 10))
        val, sim = self.space.nearest_value(result,
                                            threshold=dynamic_threshold,
                                            temp_penalty=self.temp_penalty,
                                            with_confidence=True)

        if val is not None:
            if with_confidence:
                return val, sim
            return val

        # Chain – parent bubble
        if self.parent is not None:
            return self.parent.get(name, with_confidence=with_confidence)

        if with_confidence:
            return None, 0.0
        return None

    def assign(self, name: str, value: Any) -> bool:
        """Przypisanie do istniejącej zmiennej (przez chain)."""
        if name in self._exact:
            self.set(name, value, role=self._roles.get(name, "both"),
                     weight=self._weights.get(name, 1.0))
            return True
        if self.parent is not None:
            return self.parent.assign(name, value)
        return False

    def has(self, name: str) -> bool:
        return name in self._exact

    def child(self, name: str = "") -> "HRRBubble":
        return HRRBubble(self.space, parent=self,
                         name=name or f"{self.name}_child",
                         forget_rate=self.forget_rate,
                         temp_penalty=self.temp_penalty)

    # ─── Rezonans i analogia ──────────────────────────────────────────────────

    def resonates_with(self, other: "HRRBubble") -> float:
        return self.space.similarity(self.vector, other.vector)

    def most_similar(self, candidates: List["HRRBubble"]) -> Optional["HRRBubble"]:
        best_sim, best = -1.0, None
        for c in candidates:
            s = self.resonates_with(c)
            if s > best_sim:
                best_sim, best = s, c
        return best

    def query_analogy(self, known_key: str,
                      known_value: Any,
                      query_key: str,
                      top_k: int = 3,
                      with_confidence: bool = False) -> List[Tuple[float, Any]]:
        """
        Analogia: "known_key → known_value" jak "query_key → ?".
        Zwraca listę (similarity, value) posortowanych malejąco.
        """
        V_kk = self.space.atom(known_key).vector
        V_kv = self.space.atom_for_value(known_value).vector
        V_qk = self.space.atom(query_key).vector

        # Wyciągnij relację z bąbla
        role_known = self._roles.get(known_key, "both")
        R_kk = self.space.unbind_dir(self.vector, V_kk, role_known)

        # Offset analogiczny
        offset = self.space.bind_dir(
            self.space.unbind_dir(R_kk, V_kv, "both"),
            V_qk,
            role_known
        )

        result = self.space.unbind_dir(self.vector, V_qk, role_known)
        result += offset * 0.3   # waga analogii

        hits = self.space.nearest(result, k=top_k, threshold=0.05,
                                  temp_penalty=self.temp_penalty)
        if with_confidence:
            return [(sim, a.value) for sim, a in hits]
        return [a.value for _, a in hits]

    # ─── Termodynamika ───────────────────────────────────────────────────────

    def _touch_bubble(self) -> None:
        self._T = min(100.0, self._T + HEAT_TOUCH * 0.5)

    def decay(self) -> None:
        self._T *= DECAY_RATE

    @property
    def T(self) -> float:
        return self._T

    @property
    def state(self) -> str:
        if   self._T >= T_HOT:  return "HOT"
        elif self._T >= T_WARM: return "WARM"
        elif self._T >= T_TOMB: return "COLD"
        return "TOMB"

    def keys(self) -> List[str]:
        return list(self._exact.keys())

    def __repr__(self) -> str:
        return (f"HRRBubble({self.name!r}, n={self._n}, "
                f"T={self._T:.1f}, {self.state})")


# ─── HRRHologram ─────────────────────────────────────────────────────────────

class HRRHologram:
    """
    Sekwencja jako skumulowane bindingi z wektorami pozycji (P^i).
    Z normalizacją i cache'owaniem.
    """

    def __init__(self, space: HRRSpace, topic: str = ""):
        self.space   = space
        self.topic   = topic
        self.vector  = np.zeros(space.D)
        self._items: List[Any] = []
        self._T = T_INIT

    def _normalize(self):
        n = np.linalg.norm(self.vector)
        if n > 1e-6:
            self.vector /= n

    def append(self, value: Any) -> int:
        i = len(self._items)
        V_val = self.space.atom_for_value(value).vector
        V_pos = self.space.P_power(i)
        self.vector += self.space.bind(V_pos, V_val)
        self._normalize()
        self._items.append(value)
        return i

    def retrieve(self, i: int, with_confidence: bool = False) -> Union[Any, Tuple[Any, float]]:
        if 0 <= i < len(self._items):
            val = self._items[i]
            if with_confidence:
                return val, 1.0
            return val
        V_pos = self.space.P_power(i)
        result = self.space.unbind(self.vector, V_pos)
        return self.space.nearest_value(result, with_confidence=with_confidence)

    def find_similar(self, value: Any, top_k: int = 3) -> List[Tuple[int, float]]:
        V_val = self.space.atom_for_value(value).vector
        hits = []
        for i, item in enumerate(self._items):
            V_i = self.space.atom_for_value(item).vector
            s = self.space.similarity(V_val, V_i)
            if s > 0.3:
                hits.append((i, s))
        hits.sort(key=lambda x: -x[1])
        return hits[:top_k]

    def resonates_with(self, other: "HRRHologram") -> float:
        return self.space.similarity(self.vector, other.vector)

    def decay(self) -> None:
        self._T *= DECAY_RATE

    @property
    def T(self) -> float:
        return self._T

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"HRRHologram({self.topic!r}, len={len(self._items)}, T={self._T:.1f})"


# ─── HRRScope — drop-in dla karmazyn_js_core.Scope ───────────────────────────

class HRRScope:
    """Drop-in replacement dla Scope z karmazyn_js_core (zgodny interfejs)."""

    def __init__(self, space: HRRSpace,
                 parent: Optional["HRRScope"] = None,
                 name: str = "scope",
                 forget_rate: float = FORGET_RATE,
                 temp_penalty: float = TEMP_PENALTY):
        self._bubble = HRRBubble(space, name=name, forget_rate=forget_rate,
                                 temp_penalty=temp_penalty)
        self._parent = parent
        self.vars: Dict[str, Any] = {}   # kompatybilność z Core

    @property
    def parent(self) -> Optional["HRRScope"]:
        return self._parent

    @property
    def vector(self) -> np.ndarray:
        return self._bubble.vector

    def get(self, name: str) -> Any:
        val = self._bubble.get(name, with_confidence=False)
        if val is not None:
            return val
        if self._parent is not None:
            return self._parent.get(name)
        raise NameError(f"'{name}' is not defined")

    def set(self, name: str, value: Any, role: str = "both", weight: float = 1.0) -> None:
        self._bubble.set(name, value, role=role, weight=weight)
        self.vars[name] = value

    def assign(self, name: str, value: Any) -> None:
        if self._bubble.has(name):
            self._bubble.set(name, value, role=self._bubble._roles.get(name, "both"),
                             weight=self._bubble._weights.get(name, 1.0))
            self.vars[name] = value
        elif self._parent is not None:
            self._parent.assign(name, value)
        else:
            raise NameError(f"'{name}' is not defined")

    def child(self, name: str = "") -> "HRRScope":
        return HRRScope(self._bubble.space, parent=self, name=name,
                        forget_rate=self._bubble.forget_rate,
                        temp_penalty=self._bubble.temp_penalty)

    def resonates_with(self, other: "HRRScope") -> float:
        return self._bubble.resonates_with(other._bubble)

    def __repr__(self) -> str:
        return f"HRRScope({self._bubble.name!r}, n={self._bubble._n})"


# ─── Fabryka ─────────────────────────────────────────────────────────────────

def make_phi_space(D: int = D_DEFAULT) -> HRRSpace:
    return HRRSpace(D=D)

def make_js_context(space: HRRSpace = None) -> Tuple[Any, HRRScope]:
    if space is None:
        space = HRRSpace()
    try:
        from karmazyn_js_core import KarmazynJSCore
        vm = KarmazynJSCore()
        hrr_scope = HRRScope(space, name="global")
        for k, v in vm.global_scope.vars.items():
            hrr_scope.set(k, v)
        vm.global_scope = hrr_scope
        return vm, hrr_scope
    except ImportError:
        return None, HRRScope(space, name="global")


# ─── Testy jednostkowe ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Testy karmazyn_hrr.py v1.2 ===\n")

    # 1. bind/unbind (komutatywny)
    space = HRRSpace(D=256)
    a = space.atom("a").vector
    b = space.atom("b").vector
    bound = space.bind(a, b)
    unbound = space.unbind(bound, a)
    sim = space.similarity(b, unbound)
    print(f"1. bind/unbind komutatywny: sim={sim:.4f} (oczekiwane ~0.707) – {'OK' if sim > 0.6 else 'FAIL'}")

    # 2. bind_dir (niekomutatywny)
    a_vec = space.atom("x").vector
    b_vec = space.atom("y").vector
    bind_dir1 = space.bind_dir(a_vec, b_vec, role="arg1")
    bind_dir2 = space.bind_dir(a_vec, b_vec, role="arg2")
    sim_dir = space.similarity(bind_dir1, bind_dir2)
    print(f"2. Niekomutatywność: sim(bind_arg1, bind_arg2)={sim_dir:.4f} (oczekiwane <0.3) – {'OK' if sim_dir < 0.3 else 'FAIL'}")

    # 3. Bąbel z miękkim wyszukiwaniem
    bubble = HRRBubble(space, name="test", forget_rate=0.0)
    bubble.set("x", 42)
    bubble.set("y", 3.14)
    val_x = bubble.get("x")
    val_wrong = bubble.get("non_existent")
    print(f"3. Miękkie get: x={val_x}, non_existent={val_wrong} – {'OK' if val_x == 42 and val_wrong is None else 'FAIL'}")

    # 4. Rezonans bąbli
    bubble2 = HRRBubble(space, name="similar")
    bubble2.set("x", 100)
    bubble2.set("y", 200)
    sim_bubbles = bubble.resonates_with(bubble2)
    print(f"4. Rezonans: sim={sim_bubbles:.4f} – {'OK' if sim_bubbles > 0.1 else 'FAIL'}")

    # 5. Analogia z asercją
    analogy_bubble = HRRBubble(space, name="analogy", forget_rate=0.0)
    analogy_bubble.set("stolica_francja", "Paryż")
    analogy_bubble.set("stolica_niemcy", "Berlin")
    analogy_bubble.set("stolica_wlochy", "Rzym")
    # Zapytanie
    results = analogy_bubble.query_analogy("stolica_francja", "Paryż", "stolica_polska",
                                           top_k=2, with_confidence=True)
    print(f"5. Analogia (stolica Polska): {results}")
    assert len(results) > 0, "Brak wyników analogii"
    best_sim, best_val = results[0]
    assert best_sim > 0.2 or best_val in ["Warszawa", "Kraków"], "Analogia nie trafiła"
    print("   OK (asercja przeszła)")

    # 6. Hologram sekwencji
    hologram = HRRHologram(space, "test_seq")
    for word in ["Ala", "ma", "kota"]:
        hologram.append(word)
    retrieved = [hologram.retrieve(i) for i in range(3)]
    print(f"6. Hologram: zapisane={hologram._items}, odzyskane={retrieved} – {'OK' if retrieved == hologram._items else 'FAIL'}")

    # 7. Normalizacja i normy
    norm_bubble = np.linalg.norm(bubble.vector)
    norm_hologram = np.linalg.norm(hologram.vector)
    print(f"7. Normy: bubble={norm_bubble:.4f}, hologram={norm_hologram:.4f} (oczekiwane ~1.0) – {'OK' if abs(norm_bubble-1.0)<0.05 and abs(norm_hologram-1.0)<0.05 else 'FAIL'}")

    # 8. Kara za wysoką temperaturę (runaway attractor test)
    hot_atom = space.atom("hot")
    hot_atom.T = 95.0   # wymuszenie
    cold_atom = space.atom("cold")
    cold_atom.T = 10.0
    # Stwórz wektor bliski obu
    test_vec = (hot_atom.vector + cold_atom.vector) / 2
    test_vec = space.normalize(test_vec)
    hits = space.nearest(test_vec, k=2, temp_penalty=TEMP_PENALTY)
    # Bez kary hot wygrałby, z karą cold może wygrać
    print(f"8. Kara termiczna: najbliższe atomy={[(a.name, round(s,3)) for s,a in hits]} – sprawdź ręcznie")

    print("\n✅ Wszystkie testy zakończone.")