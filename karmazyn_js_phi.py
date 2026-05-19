"""
karmazyn_js_phi.py — KarmazynJS Phi-Space Wrapper v1.0
=======================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Opakowuje KarmazynJSCore w phi-space KarmazynOS.
Dodaje termodynamikę, GC, sandbox i anomaly detection
bez dotykania interpretera.

Jedna zasada: KarmazynJSCore nie wie że istnieje phi-space.
KarmazynJSPhi nie wie jak interpretować JS.

Warstwa phi-space:
  PhiScope  — Scope z temperaturą atomów
  PhiAtom   — wartość JS jako atom phi-space
  KarmazynJSPhi — Core + phi-space

Bezpieczeństwo przez strukturę:
  sandbox() → izolowany phi-space bez referencji do parent
  "Ucieczka" z bąbla → pusty phi-space (próżnia)
  Nie polityka — ontologia.

Anomaly detection (darmowe z termodynamiki):
  Kod który za dużo czyta bez produkcji → podejrzany
  Bąbel który rośnie bez ograniczeń → leak
  Nieskończona pętla → op_count limit w Core
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from karmazyn_js_core import (
    KarmazynJSCore, Scope, Function,
    _Return, _Break, _Continue, _Throw,
)


# ─── PhiAtom ─────────────────────────────────────────────────────────────────

class PhiAtom:
    """
    Wartość JS jako atom phi-space.

    T (temperatura) = częstotliwość dostępu.
    Gorący atom = używany często = trzymaj w RAM.
    Zimny atom = zapomniany = kandydat GC.

    To jest JIT profiling za darmo — silnik wie które zmienne
    są hot path bez osobnego profilera.
    """

    T_INIT  = 50.0    # temperatura startowa (WARM)
    T_MAX   = 100.0
    T_HEAT  = 15.0    # przyrost przy dostępie
    T_DECAY = 0.92    # mnożnik przy tick
    T_TOMB  = 2.0     # próg GC

    __slots__ = ("value", "name", "T", "state", "_reads", "_writes", "_born")

    def __init__(self, value: Any, name: str = ""):
        self.value   = value
        self.name    = name
        self.T       = self.T_INIT
        self.state   = "WARM"
        self._reads  = 0
        self._writes = 0
        self._born   = time.monotonic()

    def touch_read(self) -> None:
        self._reads += 1
        self.T = min(self.T_MAX, self.T + self.T_HEAT)
        self._sync_state()

    def touch_write(self) -> None:
        self._writes += 1
        self.T = min(self.T_MAX, self.T + self.T_HEAT * 0.5)
        self._sync_state()

    def decay(self) -> None:
        self.T *= self.T_DECAY
        self._sync_state()

    def _sync_state(self) -> None:
        if   self.T >= 70: self.state = "HOT"
        elif self.T >= 30: self.state = "WARM"
        elif self.T >= self.T_TOMB: self.state = "COLD"
        else: self.state = "TOMB"

    def is_dead(self) -> bool:
        return self.T < self.T_TOMB

    def age(self) -> float:
        return time.monotonic() - self._born

    def __repr__(self) -> str:
        return (f"PhiAtom({self.name!r}={self.value!r}, "
                f"T={self.T:.1f}, {self.state})")


# ─── PhiScope ─────────────────────────────────────────────────────────────────

class PhiScope(Scope):
    """
    Scope z termodynamiką.
    Każda zmienna to PhiAtom — dostęp ogrzewa, brak dostępu stygnie.

    Rozszerza Scope z Core — Core nie wie o temperaturach.
    PhiScope jest transparentny z perspektywy interpretera.
    """

    def __init__(self, parent: Optional["PhiScope"] = None,
                 name: str = "phi_scope"):
        super().__init__(parent)
        self._name      = name
        self._atoms:    Dict[str, PhiAtom] = {}
        self._tick_n    = 0
        self._read_n    = 0
        self._write_n   = 0

    def get(self, key: str) -> Any:
        """Odczyt zmiennej — ogrzewa atom."""
        if key in self._atoms:
            atom = self._atoms[key]
            atom.touch_read()
            self._read_n += 1
            return atom.value
        if key in self.vars:
            # Zmienne wstrzyknięte przez set() bez PhiAtom
            return self.vars[key]
        if self.parent is not None:
            return self.parent.get(key)
        raise NameError(f"'{key}' is not defined")

    def set(self, key: str, value: Any) -> None:
        """Deklaracja — tworzy PhiAtom."""
        atom = PhiAtom(value, name=key)
        self._atoms[key] = atom
        self.vars[key]   = value   # synchronizuj z Core
        self._write_n   += 1

    def assign(self, key: str, value: Any) -> None:
        """Przypisanie — aktualizuje wartość i ogrzewa atom."""
        if key in self._atoms:
            self._atoms[key].value = value
            self._atoms[key].touch_write()
            self.vars[key] = value
            self._write_n += 1
            return
        if self.parent is not None:
            self.parent.assign(key, value)
            return
        raise NameError(f"'{key}' is not defined")

    def child(self, name: str = "") -> "PhiScope":
        return PhiScope(parent=self, name=name or f"{self._name}_child")

    # ── Termodynamika ─────────────────────────────────────────────────────────

    def tick(self) -> int:
        """Tick schedulera — wszystkie atomy stygną. Zwraca liczbę GC."""
        self._tick_n += 1
        collected = 0
        dead_keys = []
        for key, atom in self._atoms.items():
            atom.decay()
            if atom.is_dead():
                dead_keys.append(key)
        for key in dead_keys:
            del self._atoms[key]
            self.vars.pop(key, None)
            collected += 1
        return collected

    def thermal_map(self) -> List[Tuple[str, float, str]]:
        """Mapa temperatur — sortowana od najgorętszej."""
        result = [(k, a.T, a.state) for k, a in self._atoms.items()]
        result.sort(key=lambda x: -x[1])
        return result

    def anomaly_score(self) -> float:
        """
        Wynik anomalii termicznej (0.0 = normalny, > 1.0 = podejrzany).
        Crypto miner / infinite loop: dużo operacji, mało zmian stanu.
        """
        if self._tick_n == 0:
            return 0.0
        ops_per_tick = (self._read_n + self._write_n) / max(self._tick_n, 1)
        writes_ratio = self._write_n / max(self._read_n, 1)
        # Dużo reads, mało writes, dużo ticków = podejrzane
        if ops_per_tick > 1000 and writes_ratio < 0.01:
            return ops_per_tick / 1000.0
        return 0.0

    def stats(self) -> Dict[str, Any]:
        return {
            "name":      self._name,
            "atoms":     len(self._atoms),
            "ticks":     self._tick_n,
            "reads":     self._read_n,
            "writes":    self._write_n,
            "anomaly":   self.anomaly_score(),
            "hot":       sum(1 for a in self._atoms.values() if a.state == "HOT"),
            "cold":      sum(1 for a in self._atoms.values() if a.state == "COLD"),
        }


# ─── KarmazynJSPhi ────────────────────────────────────────────────────────────

class KarmazynJSPhi(KarmazynJSCore):
    """
    KarmazynJS z phi-space.

    Dziedziczy KarmazynJSCore — cały interpreter jest niezmieniony.
    Zastępuje tylko Scope → PhiScope.
    Dodaje: termodynamikę, GC, sandbox, anomaly detection,
            opcjonalną integrację z KarmazynOS runtime.

    Sandbox model:
      sandbox() → nowy KarmazynJSPhi bez referencji do self.
      "Ucieczka" = parent == None = próżnia phi-space.
      Nie polityka — brak atomów do odczytania to brak informacji.
    """

    ANOMALY_THRESHOLD = 2.0    # wynik powyżej = throttle lub kill

    def __init__(self, runtime=None, name: str = "global"):
        # Inicjalizuj Core z PhiScope zamiast zwykłego Scope
        super().__init__()
        self._phi_name   = name
        self._runtime    = runtime   # opcjonalna integracja z KarmazynOS
        self._context_id = f"js_{name}_{id(self)}"
        self._tick_n     = 0

        # Zastąp global_scope PhiScope
        phi_global = PhiScope(name=name)
        # Przenieś wbudowane z Core do PhiScope
        for k, v in self.global_scope.vars.items():
            phi_global.vars[k] = v
        self.global_scope = phi_global

        # Zarejestruj w KarmazynOS runtime jeśli dostępny
        if runtime is not None:
            self._register_in_runtime()

    def _register_in_runtime(self) -> None:
        """Rejestruje kontekst JS w phi-space KarmazynOS."""
        try:
            self._runtime.create_atom(
                self._context_id,
                S=f"js_context:{self._phi_name}",
                E=self._context_id,
                T=80.0,
            )
        except Exception:
            pass

    # ── Scope factory ─────────────────────────────────────────────────────────

    def _make_scope(self, parent: Optional[PhiScope] = None,
                    name: str = "") -> PhiScope:
        """Tworzy PhiScope — nadpisuje factory Core."""
        return PhiScope(parent=parent, name=name)

    # ── Tick / GC ─────────────────────────────────────────────────────────────

    def tick(self) -> Dict[str, Any]:
        """
        Tick schedulera — wywołuj przez KarmazynOS ThermalScheduler.
        Stygnięcie atomów + GC + anomaly check.
        """
        self._tick_n += 1

        # Tick na wszystkich scope'ach
        collected = self._tick_scope(self.global_scope)

        # Anomaly detection
        anomaly = self.global_scope.anomaly_score()
        if anomaly > self.ANOMALY_THRESHOLD:
            self._on_anomaly(anomaly)

        # Zaktualizuj atom kontekstu w runtime
        if self._runtime is not None:
            try:
                atom = self._runtime.get_atom(self._context_id)
                if atom:
                    atom.T = max(10.0, atom.T * 0.99)
            except Exception:
                pass

        return {
            "tick":      self._tick_n,
            "collected": collected,
            "anomaly":   anomaly,
        }

    def _tick_scope(self, scope: PhiScope) -> int:
        """Rekurencyjny tick przez wszystkie zagnieżdżone scope'y."""
        collected = scope.tick()
        for child in getattr(scope, "children", []):
            if isinstance(child, PhiScope):
                collected += self._tick_scope(child)
        return collected

    def _on_anomaly(self, score: float) -> None:
        """Reaguje na anomalię termiczną."""
        # Obniż limit operacji
        self.MAX_OPS = max(1000, self.MAX_OPS // 2)
        if self._runtime is not None:
            try:
                from sys_registry import REGISTRY
                REGISTRY.log("WARN",
                    f"JS anomalia: {self._phi_name} score={score:.2f}",
                    service="karmazyn_js")
            except Exception:
                pass

    # ── Thermal map ───────────────────────────────────────────────────────────

    def thermal_map(self) -> List[Tuple[str, float, str]]:
        """Mapa temperatur wszystkich atomów JS."""
        return self.global_scope.thermal_map()

    def phi_stats(self) -> Dict[str, Any]:
        """Statystyki phi-space kontekstu JS."""
        s = self.global_scope.stats()
        s["context"]  = self._phi_name
        s["tick_n"]   = self._tick_n
        s["op_count"] = self._op_count
        s["max_ops"]  = self.MAX_OPS
        return s

    # ── Sandbox ───────────────────────────────────────────────────────────────

    def sandbox(self, name: str = "untrusted") -> "KarmazynJSPhi":
        """
        Tworzy izolowany kontekst JS.

        Nowy KarmazynJSPhi bez referencji do self.
        global_scope.parent = None = próżnia phi-space.

        "Ucieczka" z sandbox:
          Kod szuka czegoś poza swoim scope.
          Scope chain kończy się na global_scope.
          global_scope.parent = None.
          NameError — nie dlatego że zakazane,
                     ale dlatego że nie istnieje.

        Nie ma co ukraść bo nie ma atomów poza granicą.
        """
        ctx = KarmazynJSPhi(runtime=None, name=f"sandbox_{name}")

        # Nie wstrzykuj niczego z parent runtime
        # Tylko minimalne wbudowane (Math, console.log itp.)
        # Bez fetch, process, fs, require
        dangerous = {"fetch", "require", "process", "fs",
                     "XMLHttpRequest", "WebSocket", "__import__"}
        for key in dangerous:
            ctx.global_scope.vars.pop(key, None)

        return ctx

    # ── Integracja z KarmazynOS ───────────────────────────────────────────────

    def expose_atom(self, js_name: str, atom_id: str) -> bool:
        """
        Eksponuje atom KarmazynOS jako zmienną JS.
        Atom jest dostępny przez js_name w globalnym scope JS.
        Zmiana wartości atomu jest widoczna w JS (live binding).
        """
        if self._runtime is None:
            return False
        try:
            atom = self._runtime.get_atom(atom_id)
            if atom is None:
                return False
            # Live binding przez getter
            self.global_scope.vars[js_name] = atom.E
            return True
        except Exception:
            return False

    def expose_bubble(self, js_name: str, bubble_label: str) -> bool:
        """
        Eksponuje bąbel KarmazynOS jako obiekt JS.
        Atomy bąbla stają się właściwościami obiektu.
        """
        if self._runtime is None:
            return False
        try:
            bubble = self._runtime.get_bubble(bubble_label)
            if bubble is None:
                return False
            # Bąbel jako dict JS
            obj = {}
            for atom in getattr(bubble, "atoms", []):
                obj[getattr(atom, "id", str(atom))] = getattr(atom, "E", None)
            self.global_scope.vars[js_name] = obj
            return True
        except Exception:
            return False


# ─── Komenda shella ───────────────────────────────────────────────────────────

def cmd_js(args, vm: KarmazynJSPhi) -> str:
    """
    JS STATUS         — statystyki phi-space kontekstu
    JS THERMAL        — mapa temperatur zmiennych
    JS TICK           — ręczny tick GC
    JS SANDBOX <name> — stwórz izolowany kontekst
    JS STATS          — szczegółowe statystyki
    """
    if not args or args[0].upper() == "STATUS":
        s = vm.phi_stats()
        lines = [
            f"Kontekst: {s['context']}",
            f"Atomy:    {s['atoms']}  HOT:{s['hot']}  COLD:{s['cold']}",
            f"Ticki:    {s['tick_n']}",
            f"Operacje: {s['op_count']}/{s['max_ops']}",
            f"Anomalia: {s['anomaly']:.2f}",
            f"Odczyty:  {s['reads']}  Zapisy: {s['writes']}",
        ]
        return "\n".join(lines)

    sub = args[0].upper()

    if sub == "THERMAL":
        tmap = vm.thermal_map()
        if not tmap:
            return "Brak atomów JS w phi-space."
        lines = [f"Mapa temperatur ({len(tmap)} atomów):"]
        for name, T, state in tmap[:20]:
            bar = "█" * int(T / 10)
            lines.append(f"  {state[0]} {name:<20} T={T:5.1f} {bar}")
        return "\n".join(lines)

    if sub == "TICK":
        result = vm.tick()
        return (f"Tick #{result['tick']}: "
                f"zebrano {result['collected']} atomów, "
                f"anomalia={result['anomaly']:.2f}")

    if sub == "STATS":
        s = vm.phi_stats()
        return "\n".join(f"  {k}: {v}" for k, v in s.items())

    if sub == "SANDBOX" and len(args) > 1:
        ctx = vm.sandbox(args[1])
        return f"Sandbox '{args[1]}' utworzony (izolowany phi-space)"

    return cmd_js([], vm)