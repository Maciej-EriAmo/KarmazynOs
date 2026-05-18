"""
sys_registry.py - KarmazynOS Service Registry & System Log v1.1
================================================================
Centralny punkt rejestracji uslug, logowania zdarzen i pomiaru czasu.

v1.1: Dodano usluge 'clock' (czas systemowy) rejestrowana przy starcie.
"""

import time
import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class ServiceStatus:
    OK       = "ok"
    FAILED   = "failed"
    MISSING  = "missing"
    DEGRADED = "degraded"


@dataclass
class ServiceRecord:
    name:          str
    status:        str
    message:       str   = ""
    version:       str   = ""
    registered_at: float = field(default_factory=time.time)


@dataclass
class LogEntry:
    timestamp: float
    level:     str
    service:   str
    message:   str


class SystemRegistry:
    """
    Singleton rejestru uslug KarmazynOS.
    Zero zaleznosci od reszty systemu - bezpieczny do pierwszego importu.
    Runtime wstrzykiwany po inicjalizacji przez set_runtime().
    """

    _STATUS_ICON = {
        ServiceStatus.OK:       "OK  ",
        ServiceStatus.FAILED:   "FAIL",
        ServiceStatus.MISSING:  "----",
        ServiceStatus.DEGRADED: "WARN",
    }

    def __init__(self):
        self.boot_time: float = time.time()
        self._services: Dict[str, ServiceRecord] = {}
        self._log:      List[LogEntry]           = []
        self._runtime   = None
        self._start_epoch:       int   = 0
        self._epoch_sample_time: float = time.time()

        # Czas systemowy jako pierwsza usluga — rejestrowana przy tworzeniu singletona
        boot_str = datetime.datetime.fromtimestamp(self.boot_time).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self._services["clock"] = ServiceRecord(
            name="clock", status=ServiceStatus.OK,
            version=boot_str,
            registered_at=self.boot_time,
        )
        self._log.append(LogEntry(
            timestamp=self.boot_time,
            level="INFO",
            service="clock",
            message=f"Start systemu: {boot_str}",
        ))

    def set_runtime(self, runtime):
        self._runtime            = runtime
        self._epoch_sample_time  = time.time()
        try:
            self._start_epoch = runtime.phi.epoch
        except Exception:
            pass

        def _on_vacuum_decay(atom):
            self.log("EVENT", f"Vacuum decay: {atom.id}", "runtime")
        def _on_mission_started(m):
            self.log("INFO", f"Misja: {m.get('nazwa','?')}", "mission")
        def _on_mission_won(data):
            self.log("INFO", f"Misja wygrana czas={data.get('czas',0):.0f}s", "mission")
        def _on_mission_lost(data):
            self.log("WARN", f"Misja przegrana: {data.get('powod','?')}", "mission")

        try:
            runtime.events.on("vacuum_decay",    _on_vacuum_decay)
            runtime.events.on("mission_started", _on_mission_started)
            runtime.events.on("mission_won",     _on_mission_won)
            runtime.events.on("mission_lost",    _on_mission_lost)
        except Exception as e:
            self.log("WARN", f"Nie udalo sie podpiac eventow runtime: {e}", "registry")

    def register(self, name: str, status: str,
                 message: str = "", version: str = ""):
        self._services[name] = ServiceRecord(
            name=name, status=status,
            message=message, version=version,
        )
        level = {
            ServiceStatus.OK:       "INFO",
            ServiceStatus.DEGRADED: "WARN",
            ServiceStatus.MISSING:  "WARN",
            ServiceStatus.FAILED:   "ERROR",
        }.get(status, "INFO")
        detail = version or message or status
        self.log(level, f"[{status.upper()}] {detail}", service=name)

    def log(self, level: str, message: str, service: str = "system"):
        self._log.append(LogEntry(
            timestamp=time.time(),
            level=level.upper(),
            service=service,
            message=message,
        ))

    def clear_log(self):
        self._log.clear()

    def get_log(self, n: int = 40,
                level: Optional[str] = None) -> List[LogEntry]:
        entries = self._log
        if level:
            lvl     = level.upper()
            entries = [e for e in entries if e.level == lvl]
        return entries[-n:]

    def uptime_str(self) -> str:
        delta = time.time() - self.boot_time
        h = int(delta // 3600)
        m = int((delta % 3600) // 60)
        s = int(delta % 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    def epoch_rate(self) -> Optional[float]:
        if self._runtime is None:
            return None
        try:
            current_epoch = self._runtime.phi.epoch
            elapsed       = time.time() - self._epoch_sample_time
            if elapsed < 0.1:
                return None
            return (current_epoch - self._start_epoch) / elapsed
        except Exception:
            return None

    def current_time_str(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def startup_report(self) -> List[str]:
        """Zwraca linie raportu startowego dla gfx.draw_frame()."""
        lines = []

        # Czas systemowy — wyrozniamy jako naglowek raportu
        boot_dt = datetime.datetime.fromtimestamp(self.boot_time)
        lines.append(f"Start: {boot_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        lines.append("USLUGI")
        if not self._services:
            lines.append("  (brak zarejestrowanych uslug)")
        else:
            name_w = max(len(s.name) for s in self._services.values()) + 2
            for svc in self._services.values():
                icon   = self._STATUS_ICON.get(svc.status, "?   ")
                detail = svc.version or svc.message or ""
                lines.append(f"  [{icon}] {svc.name.ljust(name_w)}{detail}")

        ok_count   = sum(1 for s in self._services.values()
                         if s.status == ServiceStatus.OK)
        deg_count  = sum(1 for s in self._services.values()
                         if s.status == ServiceStatus.DEGRADED)
        fail_count = len(self._services) - ok_count - deg_count

        lines.append("")
        summary = f"{ok_count} OK"
        if deg_count:  summary += f"  {deg_count} WARN"
        if fail_count: summary += f"  {fail_count} MISSING/FAIL"
        lines.append(summary)

        return lines

    def format_status(self) -> str:
        """Pelny live status dla komendy STATUS."""
        lines = []
        now = self.current_time_str()
        lines.append(f"Czas:     {now}")
        lines.append(f"Uptime:   {self.uptime_str()}")

        if self._runtime:
            try:
                epoch = self._runtime.phi.epoch
                tvac  = self._runtime.phi.t_vacuum()
                s     = self._runtime.status_summary()
                rate  = self.epoch_rate()

                lines.append("")
                lines.append("RUNTIME")
                rate_str = f"  ({rate:.1f} ep/s)" if rate else ""
                lines.append(f"  Epoka Fi:   {epoch}{rate_str}")
                lines.append(f"  T_vacuum:   {tvac:.4f} bit")
                lines.append(f"  Atomy:      "
                              f"HOT={s['HOT']}  WARM={s['WARM']}  "
                              f"COLD={s['COLD']}  TOMB={s['TOMB']}")
                alive = (self._runtime.is_alive()
                         if hasattr(self._runtime, 'is_alive') else "?")
                lines.append(f"  Petla:      {'aktywna' if alive else 'MARTWA'}")
                hss_ok = getattr(self._runtime, '_hss_available', False)
                lines.append(f"  HSS:        {'aktywny' if hss_ok else 'niedostepny'}")
            except Exception as e:
                lines.append(f"  (blad odczytu runtime: {e})")

        lines.append("")
        lines.append("USLUGI")
        if not self._services:
            lines.append("  (brak)")
        else:
            name_w = max(len(s.name) for s in self._services.values()) + 2
            for svc in self._services.values():
                icon   = self._STATUS_ICON.get(svc.status, "?   ")
                detail = svc.version or svc.message or ""
                lines.append(f"  [{icon}] {svc.name.ljust(name_w)}{detail}")

        errors = [e for e in self._log if e.level == "ERROR"]
        warns  = [e for e in self._log if e.level == "WARN"]
        lines.append("")
        lines.append(f"Log:  {len(self._log)} wpisow  "
                     f"({len(errors)} bledow  {len(warns)} ostrzezen)")

        return "\n".join(lines)

    def format_log(self, n: int = 40, level: Optional[str] = None) -> str:
        entries = self.get_log(n, level)
        if not entries:
            return "(brak wpisow)" + (f" dla poziomu {level}" if level else "")
        lines = []
        for e in entries:
            dt  = datetime.datetime.fromtimestamp(e.timestamp).strftime("%H:%M:%S")
            svc = e.service[:16].ljust(16)
            lines.append(f"[{dt}] {e.level:<5} [{svc}] {e.message}")
        return "\n".join(lines)


# Singleton
REGISTRY = SystemRegistry()