"""
karmazyn_syslog.py — System Log & Service Registry v1.0
========================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Singleton SYSLOG dostępny w całym ekosystemie.
Rejestruje usługi, loguje zdarzenia, mierzy czas działania.

Użycie w shell.py:
    from karmazyn_syslog import SYSLOG, OK, FAIL, DEGRADED, WARN

    SYSLOG.register("SanctuaryRuntime", OK)
    SYSLOG.register("LuaJIT", FAIL, str(import_error))
    SYSLOG.info("shell", "Loop uruchomiony")
    SYSLOG.error("runtime", "Atom nie istnieje")

Komendy shella:
    STATUS       — tabela usług + czas systemowy + epoch
    SYSLOG [n]   — ostatnie n wpisów logu (domyślnie 30)
    SYSLOG WARN  — tylko WARN i ERROR
    SYSLOG ERROR — tylko ERROR
"""

from __future__ import annotations

import datetime
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ─── Stałe statusów usług ────────────────────────────────────────────────────

OK       = "OK"
FAIL     = "FAIL"
DEGRADED = "DEGRADED"
DISABLED = "DISABLED"

# ─── Stałe poziomów logów ────────────────────────────────────────────────────

INFO  = "INFO"
WARN  = "WARN"
ERROR = "ERROR"
DEBUG = "DEBUG"

_LEVEL_ORDER = {DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3}

# ─── Ikony ───────────────────────────────────────────────────────────────────

_STATUS_ICON = {
    OK:       "✅",
    FAIL:     "❌",
    DEGRADED: "⚠️ ",
    DISABLED: "⬜",
}

_LEVEL_COLOR = {
    INFO:  "\033[36m",   # cyan
    WARN:  "\033[33m",   # yellow
    ERROR: "\033[31m",   # red
    DEBUG: "\033[90m",   # dark grey
}
_RESET = "\033[0m"


# ─── Struktury danych ────────────────────────────────────────────────────────

@dataclass
class LogEntry:
    ts:      float
    level:   str
    source:  str
    message: str

    def format(self, use_color: bool = True) -> str:
        t = datetime.datetime.fromtimestamp(self.ts).strftime("%H:%M:%S")
        col = _LEVEL_COLOR.get(self.level, "") if use_color else ""
        rst = _RESET if use_color else ""
        lvl = f"{col}{self.level:<5}{rst}"
        src = f"{self.source:<12}"
        return f"  {t} {lvl} {src} {self.message}"


@dataclass
class ServiceEntry:
    name:       str
    status:     str
    detail:     str  = ""
    started_at: float = field(default_factory=time.time)

    def format(self) -> str:
        icon   = _STATUS_ICON.get(self.status, "?")
        status = f"{self.status:<8}"
        detail = f"  {self.detail}" if self.detail else ""
        return f"  {icon} {self.name:<28} {status}{detail}"


# ─── SystemLog ───────────────────────────────────────────────────────────────

class SystemLog:
    """
    Singleton rejestru usług i logów KarmazynOS.
    Thread-safe. Dostępny przez moduł jako SYSLOG.
    """

    def __init__(self, max_entries: int = 500):
        self._boot_time = time.time()
        self._lock      = threading.Lock()
        self._entries:  deque                  = deque(maxlen=max_entries)
        self._services: Dict[str, ServiceEntry] = {}
        # Zachowujemy kolejność rejestracji
        self._service_order: List[str] = []

    # ── Rejestr usług ────────────────────────────────────────────────────────

    def register(self, name: str, status: str, detail: str = "", **kwargs):
        """
        Rejestruje usługę z podanym statusem.
        Jeśli usługa już istnieje — aktualizuje status.
        """
        with self._lock:
            if name not in self._services:
                self._service_order.append(name)
            self._services[name] = ServiceEntry(
                name=name, status=status, detail=detail
            )
        level = INFO if status == OK else (WARN if status == DEGRADED else ERROR)
        msg = f"{name}: {status}"
        if detail:
            msg += f" — {detail}"
        self._append(level, "sysreg", msg)

    def update(self, name: str, status: str, detail: str = ""):
        """Aktualizuje status istniejącej usługi (np. runtime po załadowaniu kernela)."""
        with self._lock:
            if name in self._services:
                self._services[name].status = status
                self._services[name].detail = detail
            else:
                self._service_order.append(name)
                self._services[name] = ServiceEntry(
                    name=name, status=status, detail=detail
                )
        self._append(INFO, "sysreg", f"{name} → {status}" + (f" — {detail}" if detail else ""))

    def get_service(self, name: str) -> Optional[ServiceEntry]:
        with self._lock:
            return self._services.get(name)

    def all_ok(self) -> bool:
        """Zwraca True jeśli wszystkie zarejestrowane usługi mają status OK lub DISABLED."""
        with self._lock:
            return all(
                s.status in (OK, DISABLED)
                for s in self._services.values()
            )

    def failed_services(self) -> List[str]:
        with self._lock:
            return [
                name for name, s in self._services.items()
                if s.status == FAIL
            ]

    # ── Logi ─────────────────────────────────────────────────────────────────

    def log(self, level: str, source: str, message: str = "", **kwargs):
        self._append(level, source, message)

    def info(self,  source: str, msg: str): self._append(INFO,  source, msg)
    def warn(self,  source: str, msg: str): self._append(WARN,  source, msg)
    def error(self, source: str, msg: str): self._append(ERROR, source, msg)
    def debug(self, source: str, msg: str): self._append(DEBUG, source, msg)

    def _append(self, level: str, source: str, message: str):
        with self._lock:
            self._entries.append(LogEntry(
                ts=time.time(), level=level,
                source=source, message=message
            ))

    # ── Czas ─────────────────────────────────────────────────────────────────

    def uptime(self) -> float:
        """Czas działania systemu w sekundach."""
        return time.time() - self._boot_time

    def uptime_str(self) -> str:
        seconds = int(self.uptime())
        h, rem = divmod(seconds, 3600)
        m, s   = divmod(rem, 60)
        if h:
            return f"{h}h {m:02d}m {s:02d}s"
        if m:
            return f"{m}m {s:02d}s"
        return f"{s}s"

    def boot_time_str(self) -> str:
        return datetime.datetime.fromtimestamp(self._boot_time).strftime("%Y-%m-%d %H:%M:%S")

    def now_str(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Formatowanie ─────────────────────────────────────────────────────────

    def format_status(self, runtime=None) -> str:
        """
        Tabela usług + czas systemowy + opcjonalne statystyki runtime.
        """
        lines = []

        # Nagłówek — czas systemowy
        now    = self.now_str()
        uptime = self.uptime_str()
        boot   = self.boot_time_str()
        lines.append(f"  Czas systemowy : {now}")
        lines.append(f"  Uruchomiony    : {boot}   (uptime: {uptime})")

        # Opcjonalne statystyki z runtime
        if runtime is not None:
            try:
                s = runtime.status_summary()
                epoch = runtime.phi.epoch
                t_vac = runtime.phi.t_vacuum()
                total = sum(s.values())
                lines.append(
                    f"  Φ Epoka        : {epoch}   "
                    f"T_vac: {t_vac:.4f}   "
                    f"Atomów: {total} "
                    f"(HOT:{s['HOT']} WARM:{s['WARM']} COLD:{s['COLD']} TOMB:{s['TOMB']})"
                )
                loop_ok = runtime.is_alive() if hasattr(runtime, 'is_alive') else True
                loop_status = "aktywna" if loop_ok else "MARTWA ⚠️"
                lines.append(f"  Pętla runtime  : {loop_status}")
            except Exception as e:
                lines.append(f"  Runtime        : błąd odczytu — {e}")

        lines.append("")
        lines.append("  USŁUGI:")
        lines.append("  " + "─" * 54)

        with self._lock:
            ordered = [
                self._services[n]
                for n in self._service_order
                if n in self._services
            ]

        # Usługi pogrupowane: najpierw OK, potem DEGRADED, potem FAIL
        for svc in ordered:
            lines.append(svc.format())

        lines.append("  " + "─" * 54)

        # Podsumowanie
        with self._lock:
            counts = {}
            for svc in self._services.values():
                counts[svc.status] = counts.get(svc.status, 0) + 1

        summary_parts = []
        if counts.get(OK):       summary_parts.append(f"✅ {counts[OK]} OK")
        if counts.get(DEGRADED): summary_parts.append(f"⚠️  {counts[DEGRADED]} DEGRADED")
        if counts.get(FAIL):     summary_parts.append(f"❌ {counts[FAIL]} FAIL")
        if counts.get(DISABLED): summary_parts.append(f"⬜ {counts[DISABLED]} DISABLED")
        lines.append("  " + "  ".join(summary_parts))

        return "\n".join(lines)

    def format_log(self, n: int = 30, min_level: str = INFO,
                   use_color: bool = True) -> str:
        """
        Ostatnie n wpisów logu, opcjonalnie filtrowanych po poziomie.
        """
        min_order = _LEVEL_ORDER.get(min_level, 0)
        with self._lock:
            entries = list(self._entries)

        filtered = [
            e for e in entries
            if _LEVEL_ORDER.get(e.level, 0) >= min_order
        ]
        recent = filtered[-n:]

        if not recent:
            return "  (brak wpisów)"

        lines = []
        for e in recent:
            lines.append(e.format(use_color=use_color))
        return "\n".join(lines)

    def format_compact(self) -> str:
        """
        Jednoliniowe podsumowanie dla HUD lub headera.
        """
        with self._lock:
            counts = {}
            for svc in self._services.values():
                counts[svc.status] = counts.get(svc.status, 0) + 1

        parts = []
        if counts.get(OK):       parts.append(f"✅{counts[OK]}")
        if counts.get(DEGRADED): parts.append(f"⚠️{counts[DEGRADED]}")
        if counts.get(FAIL):     parts.append(f"❌{counts[FAIL]}")

        failed = self.failed_services()
        if failed:
            parts.append(f"[FAIL: {', '.join(failed)}]")

        return "  ".join(parts) if parts else "brak usług"


# ─── Singleton ───────────────────────────────────────────────────────────────

SYSLOG = SystemLog()