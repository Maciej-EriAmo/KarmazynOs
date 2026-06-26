"""
karmazyn_scheduler.py — Termiczny Scheduler Zdarzeń v1.0
=========================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Atomy same ogłaszają stan termiczny przez EventBus — scheduler SŁUCHA,
nie odpytuje. Odpytywanie byłoby sprzeczne z modelem termodynamicznym:
jeśli atom jest COLD lub TOMB, pytanie o jego stan niepotrzebnie go
„ogrzewa" (interferes with the thermodynamic process).

Wyzwalacze:
  ThermalTrigger  — atom przekracza próg T (przejście HOT/WARM/COLD/TOMB)
  VacuumTrigger   — atom przechodzi do TOMB (vacuum_decay)
  CronTrigger     — regularny interwał czasowy (wątek tła)
  OnceTrigger     — jednorazowe opóźnione wykonanie

Architektura:
  EventBus → ThermalScheduler.dispatch() → dopasowanie triggerów → handler()

Persystencja:
  Harmonogram zapisywany do bąbla 'sys_scheduler' w .soul.
  Przy starcie scheduler wczytuje harmonogram i rejestruje handlery.

Użycie:
    from karmazyn_scheduler import ThermalScheduler
    sched = ThermalScheduler(runtime)
    sched.start()

    # Handlery reagują na zdarzenia termiczne:
    sched.on_vacuum(lambda a: backup(a), label_pattern="*")
    sched.on_threshold(60.0, "below", lambda a: warn(a))
    sched.every(30, "s", lambda: sync_network())
    sched.once(5, "m", lambda: cleanup())
"""

import threading
import time
import re
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Callable, Optional, List, Dict, Any
from enum import Enum


# ─── Typy wyzwalaczy ──────────────────────────────────────────────────────────

class TriggerType(Enum):
    THERMAL   = "thermal"    # przejście stanu HOT/WARM/COLD
    VACUUM    = "vacuum"     # atom → TOMB
    THRESHOLD = "threshold"  # T przekracza wartość
    CRON      = "cron"       # regularny interwał
    ONCE      = "once"       # jednorazowe opóźnienie
    CREATED   = "created"    # nowy atom


@dataclass
class Trigger:
    """Definicja wyzwalacza."""
    trigger_id:    str
    trigger_type:  TriggerType
    handler:       Callable
    label_pattern: str   = "*"    # glob dla id atomu, * = wszystkie
    state_target:  str   = ""     # dla THERMAL: "HOT", "WARM", "COLD"
    threshold_T:   float = 0.0    # dla THRESHOLD
    direction:     str   = "below" # "below" | "above"
    interval_s:    float = 0.0    # dla CRON/ONCE
    description:   str   = ""
    enabled:       bool  = True
    _last_fired:   float = field(default=0.0, repr=False)
    _fired_count:  int   = field(default=0,   repr=False)


# ─── Persystencja harmonogramu ────────────────────────────────────────────────

SCHEDULE_BUBBLE = "sys_scheduler"
SCHEDULE_DIR    = ".bubbles/store"


def _save_schedule(triggers: List[Trigger]) -> None:
    """Zapisuje opisy triggerów do .bubbles/store/sys_scheduler.jsonl"""
    os.makedirs(SCHEDULE_DIR, exist_ok=True)
    path = os.path.join(SCHEDULE_DIR, f"{SCHEDULE_BUBBLE}.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for t in triggers:
            if t.trigger_type in (TriggerType.CRON, TriggerType.ONCE,
                                  TriggerType.THERMAL, TriggerType.VACUUM,
                                  TriggerType.THRESHOLD, TriggerType.CREATED):
                rec = {
                    "id":            t.trigger_id,
                    "type":          t.trigger_type.value,
                    "label_pattern": t.label_pattern,
                    "state_target":  t.state_target,
                    "threshold_T":   t.threshold_T,
                    "direction":     t.direction,
                    "interval_s":    t.interval_s,
                    "description":   t.description,
                    "enabled":       t.enabled,
                    "fired_count":   t._fired_count,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load_schedule(path: str) -> List[dict]:
    """Wczytuje opisy triggerów (bez handlerów — te rejestruje kod)."""
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


# ─── Główna klasa schedulera ──────────────────────────────────────────────────

class ThermalScheduler:
    """
    Scheduler oparty na nasłuchu EventBus.

    Nie odpytuje atomów — reaguje na zdarzenia które atomy same emitują:
      - atom_created    → CREATED triggers
      - tick            → THRESHOLD triggers (T porównywane z progiem)
      - state_changed   → THERMAL triggers
      - vacuum_decay    → VACUUM triggers

    Wątki tła obsługują tylko triggery czasowe (CRON, ONCE).
    """

    def __init__(self, runtime):
        self.runtime   = runtime
        self._triggers: Dict[str, Trigger] = {}
        self._lock     = threading.RLock()
        self._running  = False
        self._cron_thread: Optional[threading.Thread] = None
        self._log: List[dict] = []   # historia wykonań (ostatnie 200)

    # ── Start / Stop ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Podpina nasłuchy do EventBus i startuje wątek CRON."""
        if self._running:
            return
        self._running = True

        rt = self.runtime
        rt.events.on("atom_created",  self._on_atom_created)
        rt.events.on("tick",          self._on_tick)
        rt.events.on("state_changed", self._on_state_changed)
        rt.events.on("vacuum_decay",  self._on_vacuum_decay)

        # Wątek CRON — odpala tylko triggery czasowe (nie dotyka atomów)
        self._cron_thread = threading.Thread(
            target=self._cron_loop, daemon=True, name="karmazyn-scheduler"
        )
        self._cron_thread.start()

    def stop(self) -> None:
        self._running = False
        if self._cron_thread and self._cron_thread.is_alive():
            self._cron_thread.join(timeout=2.0)

    # ── Rejestracja triggerów ──────────────────────────────────────────────────

    def on_vacuum(self, handler: Callable,
                  label_pattern: str = "*",
                  description: str = "") -> str:
        """
        Reaguje gdy atom przechodzi do TOMB (vacuum_decay).
        handler(atom) → wywoływany z atomem który umarł.
        """
        return self._add(Trigger(
            trigger_id    = self._make_id("vacuum", label_pattern),
            trigger_type  = TriggerType.VACUUM,
            handler       = handler,
            label_pattern = label_pattern,
            description   = description or f"vacuum:{label_pattern}",
        ))

    def on_state(self, state: str, handler: Callable,
                 label_pattern: str = "*",
                 description: str = "") -> str:
        """
        Reaguje gdy atom wchodzi w dany stan (HOT/WARM/COLD).
        state: "HOT" | "WARM" | "COLD"
        handler(atom) → wywoływany z atomem.
        """
        return self._add(Trigger(
            trigger_id    = self._make_id(f"state_{state}", label_pattern),
            trigger_type  = TriggerType.THERMAL,
            handler       = handler,
            label_pattern = label_pattern,
            state_target  = state.upper(),
            description   = description or f"state:{state}:{label_pattern}",
        ))

    def on_threshold(self, T: float, direction: str, handler: Callable,
                     label_pattern: str = "*",
                     description: str = "") -> str:
        """
        Reaguje gdy T atomu przekracza próg.
        direction: "below" (T < próg) | "above" (T > próg)
        handler(atom) → wywoływany z atomem.
        """
        return self._add(Trigger(
            trigger_id    = self._make_id(f"thr_{direction}_{T:.0f}", label_pattern),
            trigger_type  = TriggerType.THRESHOLD,
            handler       = handler,
            label_pattern = label_pattern,
            threshold_T   = float(T),
            direction     = direction,
            description   = description or f"threshold:{direction}:{T}:{label_pattern}",
        ))

    def on_created(self, handler: Callable,
                   label_pattern: str = "*",
                   description: str = "") -> str:
        """
        Reaguje gdy tworzony jest nowy atom.
        handler(atom) → wywoływany z nowym atomem.
        """
        return self._add(Trigger(
            trigger_id    = self._make_id("created", label_pattern),
            trigger_type  = TriggerType.CREATED,
            handler       = handler,
            label_pattern = label_pattern,
            description   = description or f"created:{label_pattern}",
        ))

    def every(self, n: float, unit: str, handler: Callable,
              description: str = "") -> str:
        """
        Regularny interwał czasowy.
        unit: "s" (sekundy) | "m" (minuty) | "h" (godziny)
        handler() → wywoływany bez argumentów.
        """
        intervals = {"s": 1.0, "m": 60.0, "h": 3600.0}
        if unit not in intervals:
            raise ValueError(f"Nieznana jednostka: {unit}. Użyj: s/m/h")
        interval_s = n * intervals[unit]
        return self._add(Trigger(
            trigger_id   = self._make_id(f"cron_{n}{unit}", ""),
            trigger_type = TriggerType.CRON,
            handler      = handler,
            interval_s   = interval_s,
            description  = description or f"every:{n}{unit}",
        ))

    def once(self, n: float, unit: str, handler: Callable,
             description: str = "") -> str:
        """
        Jednorazowe opóźnione wykonanie.
        unit: "s" | "m" | "h"
        """
        intervals = {"s": 1.0, "m": 60.0, "h": 3600.0}
        if unit not in intervals:
            raise ValueError(f"Nieznana jednostka: {unit}")
        interval_s = n * intervals[unit]
        return self._add(Trigger(
            trigger_id   = self._make_id(f"once_{n}{unit}", ""),
            trigger_type = TriggerType.ONCE,
            handler      = handler,
            interval_s   = interval_s,
            description  = description or f"once:{n}{unit}",
        ))

    def remove(self, trigger_id: str) -> bool:
        with self._lock:
            if trigger_id in self._triggers:
                del self._triggers[trigger_id]
                return True
            return False

    def enable(self, trigger_id: str, enabled: bool = True) -> bool:
        with self._lock:
            if trigger_id in self._triggers:
                self._triggers[trigger_id].enabled = enabled
                return True
            return False

    # ── Status i diagnostyka ──────────────────────────────────────────────────

    def list_triggers(self) -> List[dict]:
        with self._lock:
            return [
                {
                    "id":          t.trigger_id,
                    "type":        t.trigger_type.value,
                    "description": t.description,
                    "enabled":     t.enabled,
                    "fired":       t._fired_count,
                    "pattern":     t.label_pattern,
                }
                for t in self._triggers.values()
            ]

    def log_tail(self, n: int = 20) -> List[dict]:
        return self._log[-n:]

    def save(self) -> None:
        """Zapisuje harmonogram do .bubbles/store/sys_scheduler.jsonl"""
        with self._lock:
            _save_schedule(list(self._triggers.values()))

    # ── Handlery EventBus ─────────────────────────────────────────────────────

    def _on_atom_created(self, atom) -> None:
        self._dispatch(atom, TriggerType.CREATED)

    def _on_tick(self, atom) -> None:
        """Sprawdza progi T przy każdym takcie. Nie odpytuje — reaguje na emit."""
        self._dispatch(atom, TriggerType.THRESHOLD)

    def _on_state_changed(self, atom) -> None:
        """Atom sam ogłasza zmianę stanu — nie trzeba go odpytywać."""
        self._dispatch(atom, TriggerType.THERMAL)

    def _on_vacuum_decay(self, atom) -> None:
        self._dispatch(atom, TriggerType.VACUUM)

    def _dispatch(self, atom, trigger_type: TriggerType) -> None:
        """Dopasowuje zdarzenie do triggerów i wywołuje handlery."""
        now = time.time()
        with self._lock:
            triggers = [t for t in self._triggers.values()
                        if t.enabled and t.trigger_type == trigger_type]

        for t in triggers:
            try:
                if not self._matches(t, atom):
                    continue
                t._fired_count += 1
                t._last_fired   = now
                self._log_entry(t, atom)
                t.handler(atom)
            except Exception as e:
                self._log_entry(t, atom, error=str(e))

    def _matches(self, trigger: Trigger, atom) -> bool:
        """Sprawdza czy zdarzenie pasuje do triggera."""
        # Dopasowanie wzorca etykiety
        if trigger.label_pattern != "*":
            atom_id = getattr(atom, 'id', '')
            if not _glob_match(trigger.label_pattern, atom_id):
                return False

        if trigger.trigger_type == TriggerType.THERMAL:
            return atom.state == trigger.state_target

        if trigger.trigger_type == TriggerType.THRESHOLD:
            T = getattr(atom, 'T', 0.0)
            if trigger.direction == "below":
                return T < trigger.threshold_T
            else:
                return T > trigger.threshold_T

        # VACUUM, CREATED — zawsze pasują (wzorzec już sprawdzony)
        return True

    # ── Wątek CRON ────────────────────────────────────────────────────────────

    def _cron_loop(self) -> None:
        """Wątek obsługujący wyłącznie triggery czasowe (CRON i ONCE)."""
        while self._running:
            now = time.time()
            with self._lock:
                time_triggers = [
                    t for t in self._triggers.values()
                    if t.enabled and t.trigger_type in (TriggerType.CRON,
                                                         TriggerType.ONCE)
                ]

            for t in time_triggers:
                elapsed = now - t._last_fired
                if t._last_fired == 0.0:
                    # Pierwszy raz — zapamiętaj start, nie wywołuj
                    with self._lock:
                        t._last_fired = now
                    continue

                if elapsed >= t.interval_s:
                    try:
                        with self._lock:
                            t._last_fired   = now
                            t._fired_count += 1
                        self._log_entry(t, None)
                        t.handler()
                        if t.trigger_type == TriggerType.ONCE:
                            self.remove(t.trigger_id)
                    except Exception as e:
                        self._log_entry(t, None, error=str(e))

            # Rozdzielczość: min(1s, połowa najmniejszego interwału).
            # Zapobiega przesypianiu krótkich triggerów CRON/ONCE.
            with self._lock:
                intervals = [t.interval_s for t in self._triggers.values()
                             if t.enabled and t.trigger_type.value in ("cron","once")
                             and t.interval_s > 0]
            min_sleep = min(1.0, min(intervals) / 2) if intervals else 1.0
            time.sleep(min_sleep)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _add(self, trigger: Trigger) -> str:
        with self._lock:
            self._triggers[trigger.trigger_id] = trigger
        return trigger.trigger_id

    def _make_id(self, kind: str, pattern: str) -> str:
        raw = f"{kind}:{pattern}:{time.time()}"
        return f"sched_{hashlib.md5(raw.encode()).hexdigest()[:8]}"

    def _log_entry(self, trigger: Trigger, atom,
                   error: Optional[str] = None) -> None:
        entry = {
            "ts":      time.time(),
            "trigger": trigger.trigger_id,
            "desc":    trigger.description,
            "atom":    getattr(atom, 'id', None) if atom else None,
            "T":       getattr(atom, 'T', None) if atom else None,
            "state":   getattr(atom, 'state', None) if atom else None,
            "error":   error,
        }
        self._log.append(entry)
        if len(self._log) > 200:
            self._log = self._log[-200:]


# ─── Wbudowane reguły systemowe ───────────────────────────────────────────────

def attach_system_rules(scheduler: ThermalScheduler,
                        runtime,
                        save_interval_s: float = 300.0) -> None:
    """
    Rejestruje standardowe reguły systemowe KarmazynOS.

    Zasada: żadna reguła nie odpytuje atomów — wszystkie reagują na zdarzenia.

    Reguły:
      1. Auto-save co save_interval_s sekund
      2. Log vacuum_decay do sys_registry
      3. Ostrzeżenie gdy atom systemowy (sys_*) przechodzi do COLD
      4. Hard save po vacuum_decay (persystencja przed utratą danych)
    """
    from sys_registry import REGISTRY

    # 1. Regularny auto-save
    def _auto_save():
        try:
            scheduler.save()
            REGISTRY.log("DEBUG", "Scheduler: auto-save harmonogramu", "scheduler")
        except Exception as e:
            REGISTRY.log("ERROR", f"Scheduler: blad auto-save: {e}", "scheduler")

    scheduler.every(save_interval_s / 60, "m", _auto_save,
                    description="auto-save harmonogramu")

    # 2. Log vacuum_decay przez registry (nie duplikuj logiki runtime.py)
    def _on_any_vacuum(atom):
        REGISTRY.log("EVENT",
                     f"vacuum_decay: {atom.id} (T={atom.T:.1f})",
                     "scheduler")

    scheduler.on_vacuum(_on_any_vacuum, label_pattern="*",
                        description="log vacuum_decay")

    # 3. Ostrzeżenie dla atomów systemowych schładzających się do COLD
    def _sys_cold_warn(atom):
        REGISTRY.log("WARN",
                     f"Atom systemowy COLD: {atom.id} (T={atom.T:.1f})",
                     "scheduler")

    scheduler.on_state("COLD", _sys_cold_warn, label_pattern="sys_*",
                       description="ostrzezenie sys_* → COLD")

    # 4. Hard save tuż po vacuum_decay (runtime emituje trigger_hard_save,
    #    ale scheduler dodaje własny zapis harmonogramu)
    def _hard_save_on_vacuum(atom):
        try:
            scheduler.save()
            REGISTRY.log("INFO",
                         f"Hard save po vacuum: {atom.id}",
                         "scheduler")
        except Exception as e:
            REGISTRY.log("ERROR",
                         f"Hard save blad: {e}",
                         "scheduler")

    scheduler.on_vacuum(_hard_save_on_vacuum,
                        label_pattern="*",
                        description="hard-save po vacuum_decay")


# ─── Glob matching ────────────────────────────────────────────────────────────

def _glob_match(pattern: str, text: str) -> bool:
    """
    Minimalne dopasowanie glob: * = dowolny ciąg, ? = jeden znak.
    Nie używa fnmatch żeby uniknąć importu i być deterministyczne.
    """
    if pattern == "*":
        return True
    # Zamieniamy na regex
    regex = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    return bool(re.fullmatch(regex, text))


# ─── Integracja z shell.py ────────────────────────────────────────────────────

def cmd_scheduler(args, scheduler: ThermalScheduler) -> str:
    """
    Komenda SCHEDULER dla shell.py.
    SCHEDULER LS          — lista triggerów
    SCHEDULER LOG [n]     — ostatnie n wykonań (domyślnie 20)
    SCHEDULER SAVE        — zapisz harmonogram
    SCHEDULER OFF <id>    — wyłącz trigger
    SCHEDULER ON <id>     — włącz trigger
    SCHEDULER RM <id>     — usuń trigger
    """
    if not args:
        triggers = scheduler.list_triggers()
        if not triggers:
            return "Brak triggerów. Użyj attach_system_rules() lub dodaj ręcznie."
        lines = [f"{'ID':<16} {'TYP':<12} {'OPIS':<30} {'FIRES':>6} {'STATUS'}"]
        lines.append("─" * 72)
        for t in triggers:
            status = "ON " if t["enabled"] else "OFF"
            lines.append(
                f"{t['id']:<16} {t['type']:<12} "
                f"{t['description'][:30]:<30} {t['fired']:>6} {status}"
            )
        lines.append(f"\nLacznie: {len(triggers)} triggerów")
        return "\n".join(lines)

    sub = args[0].upper()

    if sub == "LS":
        return cmd_scheduler([], scheduler)

    if sub == "LOG":
        n = int(args[1]) if len(args) > 1 else 20
        entries = scheduler.log_tail(n)
        if not entries:
            return "Log pusty."
        import datetime
        lines = []
        for e in entries:
            dt  = datetime.datetime.fromtimestamp(e["ts"]).strftime("%H:%M:%S")
            err = f" [ERR: {e['error']}]" if e.get("error") else ""
            atom_info = f" atom={e['atom']} T={e['T']:.1f}" if e.get("atom") else ""
            lines.append(f"[{dt}] {e['desc']}{atom_info}{err}")
        return "\n".join(lines)

    if sub == "SAVE":
        scheduler.save()
        return "Harmonogram zapisany."

    if sub in ("OFF", "ON") and len(args) > 1:
        ok = scheduler.enable(args[1], sub == "ON")
        return f"Trigger {args[1]}: {'ON' if sub == 'ON' else 'OFF'}" if ok \
               else f"Nie znaleziono triggera: {args[1]}"

    if sub == "RM" and len(args) > 1:
        ok = scheduler.remove(args[1])
        return f"Usunięto: {args[1]}" if ok \
               else f"Nie znaleziono triggera: {args[1]}"

    return ("SCHEDULER [LS|LOG [n]|SAVE|OFF <id>|ON <id>|RM <id>]")