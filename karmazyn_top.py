#!/usr/bin/env python3
"""
karmazyn_top.py — KarmazynOS Thermal Monitor v1.0
==================================================
Maciej Mazur, Warsaw 2026

Monitor termodynamiczny phi-space w czasie rzeczywistym.
Odpowiednik htop — ale zamiast CPU/RAM pokazuje ciepło atomów.

Filozofia:
  Każde obliczenie zostawia ślad termiczny.
  Nie możesz ukryć aktywności bez generowania ciepła.
  Słownik phi-space jest pasywnym detektorem — anomalia widoczna
  bez żadnego aktywnego audytu, bez IDS, bez logowania.

Widoki (Tab):
  HOT    — mapa ciepła (atomy sortowane po T)
  DELTA  — zmiany temperatury (kto ruszał atomy ostatnio)
  ANOMAL — skoki T bez właściciela (potencjalnie nieautoryzowane)
  HIST   — historia temperatury wybranego atomu
  CLUST  — ciepło klastra (wiele węzłów)

Detekcja anomalii:
  Anomalia = atom którego T wzrosło o > ANOMALY_DELTA w < ANOMALY_WINDOW sekund
  bez zarejestrowanego właściciela (touch() z identyfikatorem).
  Prawidłowe programy rejestrują dostęp przez shell.py → reg() → touch().
  Nieautoryzowany dostęp bezpośrednio do phi-space → skok bez właściciela.

Rejestracja w shell.py:
  reg("TOP", cmd_top, "Monitor termiczny phi-space", category="system")

Użycie standalone:
  python3 karmazyn_top.py
  python3 karmazyn_top.py --anomaly-only
  python3 karmazyn_top.py --interval 0.5
"""

import curses
import os
import sys
import time
import threading
import collections
import statistics
from typing import Any, Dict, List, Optional, Tuple


# ── Importy KarmazynOS ────────────────────────────────────────────────────────

try:
    from karmazyn_phi import PhiSpace
    _PHI_AVAILABLE = True
except ImportError:
    _PHI_AVAILABLE = False

try:
    from karmazyn_syslog import SystemLog
    REGISTRY = SystemLog()
except ImportError:
    class _MinLog:
        def log(self, *a, **kw): pass
        def register(self, *a, **kw): pass
    REGISTRY = _MinLog()


# ── Stałe ─────────────────────────────────────────────────────────────────────

VERSION         = "KTOP-1.0"
DEFAULT_INTERVAL= 1.0       # s — częstość odświeżania
HISTORY_LEN     = 60        # próbek historii T per atom
ANOMALY_DELTA   = 15.0      # °T — skok uznawany za anomalię
ANOMALY_WINDOW  = 5.0       # s — okno czasowe skoku
TOMBSTONE_T     = 2.0       # T poniżej której atom jest "zimny/martwy"

# Kolory
C_HOT    = 1
C_WARM   = 2
C_COLD   = 3
C_TOMB   = 4
C_ANOM   = 5   # anomalia
C_HEADER = 6
C_STATUS = 7
C_SELECT = 8
C_DELTA_UP   = 9
C_DELTA_DOWN = 10
C_CLUSTER    = 11


def _init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()
    bg = -1
    curses.init_pair(C_HOT,        curses.COLOR_RED,     bg)
    curses.init_pair(C_WARM,       curses.COLOR_YELLOW,  bg)
    curses.init_pair(C_COLD,       curses.COLOR_CYAN,    bg)
    curses.init_pair(C_TOMB,       curses.COLOR_BLACK,   bg)
    curses.init_pair(C_ANOM,       curses.COLOR_WHITE,   curses.COLOR_RED)
    curses.init_pair(C_HEADER,     curses.COLOR_BLACK,   curses.COLOR_CYAN)
    curses.init_pair(C_STATUS,     curses.COLOR_BLACK,   curses.COLOR_GREEN)
    curses.init_pair(C_SELECT,     curses.COLOR_BLACK,   curses.COLOR_YELLOW)
    curses.init_pair(C_DELTA_UP,   curses.COLOR_RED,     bg)
    curses.init_pair(C_DELTA_DOWN, curses.COLOR_BLUE,    bg)
    curses.init_pair(C_CLUSTER,    curses.COLOR_MAGENTA, bg)


def _T_color(T: float) -> int:
    if T > 70:  return C_HOT
    if T > 30:  return C_WARM
    if T > 2:   return C_COLD
    return C_TOMB


def _T_bar(T: float, T_max: float = 100.0, width: int = 20) -> str:
    """Pasek temperatury ASCII."""
    pct    = max(0.0, min(1.0, T / max(1.0, T_max)))
    filled = int(pct * width)
    chars  = "░▒▓█"
    # Gradient: im gorętszy tym pełniejszy blok
    bar = "█" * filled + "░" * (width - filled)
    return bar


def _spark(history: List[float], width: int = 10) -> str:
    """Mini sparkline z historii T."""
    if not history: return " " * width
    blocks = " ▁▂▃▄▅▆▇█"
    mn, mx = min(history), max(history)
    rng    = max(1.0, mx - mn)
    result = ""
    step   = max(1, len(history) // width)
    sampled = history[-width*step::step][-width:]
    for v in sampled:
        idx = int((v - mn) / rng * (len(blocks) - 1))
        result += blocks[idx]
    return result.ljust(width)


# ─────────────────────────────────────────────────────────────────────────────
# TouchRegistry — rejestr właścicieli (kto ostatnio dotknął atom)
# ─────────────────────────────────────────────────────────────────────────────

class TouchRegistry:
    """
    Rejestr ostatnich touch() per atom.
    Programy rejestrowane przez shell.py wywołują:
        TOUCH_REGISTRY.register(atom_id, owner='nooedit', pid=os.getpid())

    Anomalia = atom nagrzał się ale TOUCH_REGISTRY nie ma wpisu
    w ostatnim ANOMALY_WINDOW → nieautoryzowany dostęp.

    [FIX 5] Prawdziwy owner tracking zamiast S/E heurystyki.
    """

    def __init__(self):
        self._entries: Dict[str, dict] = {}   # atom_id → {owner, pid, session, ts}
        self._lock = threading.Lock()

    def register(self, atom_id: str, owner: str,
                 pid: int = 0, session: str = "") -> None:
        """Zarejestruj dotknięcie atomu przez właściciela."""
        with self._lock:
            self._entries[atom_id] = {
                "owner":   owner,
                "pid":     pid or os.getpid(),
                "session": session,
                "ts":      time.monotonic(),
            }

    def get(self, atom_id: str) -> Optional[dict]:
        """Pobierz ostatni zarejestrowany touch."""
        with self._lock:
            return self._entries.get(atom_id)

    def is_recent(self, atom_id: str,
                   window: float = ANOMALY_WINDOW) -> bool:
        """Czy atom był legalnie dotknięty w oknie czasowym?"""
        entry = self.get(atom_id)
        if not entry: return False
        return (time.monotonic() - entry["ts"]) < window

    def owner_of(self, atom_id: str) -> str:
        entry = self.get(atom_id)
        return entry["owner"] if entry else ""


# Globalny singleton — importowany przez shell.py, FM, NooEdit itd.
TOUCH_REGISTRY = TouchRegistry()


# ─────────────────────────────────────────────────────────────────────────────
# AtomSnapshot — migawka stanu atomu
# ─────────────────────────────────────────────────────────────────────────────

class AtomSnapshot:
    __slots__ = ("id", "T", "T_max", "S", "E", "state", "age",
                 "ts", "delta_T", "is_anomaly", "owner")

    def __init__(self, atom: Any, prev: Optional["AtomSnapshot"] = None):
        self.id    = str(getattr(atom, "id",    "?"))
        self.T     = float(getattr(atom, "T",    0.0))
        self.T_max = float(getattr(atom, "T_max",100.0))
        self.S     = str(getattr(atom,   "S",    ""))
        self.E     = str(getattr(atom,   "E",    ""))
        self.state = str(getattr(atom,   "state","?"))
        self.age   = int(getattr(atom,   "age",  0))
        self.ts    = time.monotonic()

        # Delta względem poprzedniej migawki
        if prev is not None:
            self.delta_T    = self.T - prev.T
            dt              = self.ts - prev.ts
            # [FIX 4] anomalia = wysoki delta LUB wysoki Z-score
            # Z-score jest przekazywany zewnętrznie z PhiMonitor._zscore()
            # Fallback: raw delta gdy za mało historii
            raw_anom        = abs(self.delta_T) > ANOMALY_DELTA and dt < ANOMALY_WINDOW
            # [FIX 5] anomalia silniejsza gdy brak legalnego touch() w rejestrze
            no_legal_touch  = raw_anom and not TOUCH_REGISTRY.is_recent(
                str(getattr(atom, 'id', '')), ANOMALY_WINDOW)
            self.is_anomaly = raw_anom   # Z-score nadpisywany przez monitor
            if no_legal_touch:
                self.is_anomaly = True   # brak rejestracji → zawsze anomalia
        else:
            self.delta_T    = 0.0
            self.is_anomaly = False

        # [FIX 5] prawdziwy właściciel z TouchRegistry (nie heurystyka S/E)
        reg_owner = TOUCH_REGISTRY.owner_of(str(getattr(atom, 'id', '')))
        self.owner = reg_owner or self.S or self.E or ""


# ─────────────────────────────────────────────────────────────────────────────
# HeatPropagation — graf propagacji ciepła między atomami
# ─────────────────────────────────────────────────────────────────────────────

class HeatPropagation:
    """
    Graf propagacji ciepła między atomami.

    Ciepło przepływa po zdefiniowanych krawędziach:
      nooedit → parser → bubble.math → cluster.cache

    Pozwala wykryć:
      - semantyczne bottlenecki (atom gorący ale downstream zimny)
      - rezonans (ciepło krąży w pętli)
      - martwe klastry (ciepło nie dociera do celu)

    Krawędzie rejestrowane przez programy:
      HEAT_GRAPH.add_edge('nooedit', 'bubble.current', weight=0.3)
    """

    def __init__(self):
        # graf: source_id → {target_id: weight (0-1)}
        self._edges: Dict[str, Dict[str, float]] = {}
        self._lock  = threading.Lock()

    def add_edge(self, src: str, dst: str, weight: float = 0.2) -> None:
        """Dodaj krawędź propagacji ciepła."""
        with self._lock:
            self._edges.setdefault(src, {})[dst] = max(0.0, min(1.0, weight))

    def remove_edge(self, src: str, dst: str) -> None:
        with self._lock:
            if src in self._edges:
                self._edges[src].pop(dst, None)

    def propagate(self, phi: Any, decay: float = 0.05) -> int:
        """
        Jeden krok propagacji ciepła.
        Źródło traci: weight * T.
        Cel zyskuje: weight * T * (1 - decay).
        Zwraca liczbę przeniesionych jednostek ciepła.
        """
        transferred = 0
        with self._lock:
            edges = dict(self._edges)
        for src_id, targets in edges.items():
            try:
                src_atom = phi.get_atom(src_id)
                if src_atom is None: continue
                src_T = float(getattr(src_atom, 'T', 0))
                if src_T < 5.0: continue   # za zimny — nie propaguje
                for dst_id, weight in targets.items():
                    dst_atom = phi.get_atom(dst_id)
                    if dst_atom is None: continue
                    # Ciepło przepływa od gorącego do zimniejszego
                    dst_T    = float(getattr(dst_atom, 'T', 0))
                    if src_T <= dst_T: continue   # już wyrównane
                    delta    = (src_T - dst_T) * weight * (1.0 - decay)
                    if delta < 0.1: continue
                    try:
                        dst_atom.T = min(float(getattr(dst_atom,'T_max',100)), dst_T + delta)
                        TOUCH_REGISTRY.register(
                            dst_id, owner=f"heat.{src_id}", session="propagation")
                    except Exception:
                        pass
                    transferred += 1
            except Exception:
                pass
        return transferred

    def edges(self) -> List[Tuple[str, str, float]]:
        with self._lock:
            return [(s, d, w)
                    for s, targets in self._edges.items()
                    for d, w in targets.items()]


# Globalny graf propagacji
HEAT_GRAPH = HeatPropagation()


# ─────────────────────────────────────────────────────────────────────────────
# PhiMonitor — wątek zbierający dane
# ─────────────────────────────────────────────────────────────────────────────

class PhiMonitor:
    """
    Wątek tła: co INTERVAL sekund pobiera snapshot phi-space.
    Przechowuje historię T dla każdego atomu i wykrywa anomalie.
    """

    def __init__(self, phi: Any, interval: float = DEFAULT_INTERVAL):
        self.phi      = phi
        self.interval = interval

        # Bieżące snapshoty: atom_id → AtomSnapshot
        self.current:  Dict[str, AtomSnapshot] = {}
        # Poprzednie snapshoty do delta
        self._prev:    Dict[str, AtomSnapshot] = {}
        # Historia T: atom_id → deque[float]
        self.history:  Dict[str, collections.deque] = collections.defaultdict(
            lambda: collections.deque(maxlen=HISTORY_LEN))
        # Anomalie: lista (ts, AtomSnapshot)
        self.anomalies: List[Tuple[float, AtomSnapshot]] = []
        # Statystyki zbiorcze
        self.stats     = {"hot": 0, "warm": 0, "cold": 0, "tomb": 0, "total": 0}
        self.last_scan = 0.0

        self._lock    = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "PhiMonitor":
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, daemon=True, name="phi-monitor")
        self._thread.start()
        return self

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        # [FIX 3] stabilny timer — bez driftu przy wolnych skanach
        next_tick = time.monotonic()
        while self._running:
            try:
                self._scan()
            except Exception:
                pass
            next_tick += self.interval
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)

    def _zscore(self, atom_id: str, T: float) -> float:
        """Z-score T względem historii atomu — mniej false positives niż raw delta."""
        hist = list(self.history.get(atom_id, []))
        if len(hist) < 5:
            return 0.0   # za mało próbek — nie oceniaj
        try:
            mu  = statistics.mean(hist)
            sig = statistics.stdev(hist)
            return (T - mu) / max(0.1, sig)
        except Exception:
            return 0.0

    def _scan(self) -> None:
        # Propaguj ciepło po grafie przed skanem
        try:
            HEAT_GRAPH.propagate(self.phi)
        except Exception:
            pass
        try:
            atoms = self.phi.matrix.atoms()
        except Exception:
            return

        new_current = {}
        hot = warm = cold = tomb = 0

        for a in atoms:
            aid  = str(getattr(a, "id", ""))
            if not aid: continue

            prev = self._prev.get(aid)
            snap = AtomSnapshot(a, prev)
            # [FIX 4] Z-score PRZED dodaniem do historii (żeby nie zaburzić)
            zscore = self._zscore(aid, snap.T)
            if abs(zscore) > 3.0:   # 3σ — klasyczny próg statystyczny
                snap.is_anomaly = True
            new_current[aid] = snap

            # Historia — po Z-score
            self.history[aid].append(snap.T)

            # Anomalia
            if snap.is_anomaly:
                with self._lock:
                    self.anomalies.append((time.monotonic(), snap))
                    # Ogranicz historię anomalii do 100
                    if len(self.anomalies) > 100:
                        self.anomalies.pop(0)

            # Statystyki
            T = snap.T
            if T > 70:   hot  += 1
            elif T > 30: warm += 1
            elif T > 2:  cold += 1
            else:        tomb += 1

        with self._lock:
            self._prev    = dict(self.current)  # [FIX] shallow copy — nie shared ref
            self.current  = new_current
            # [FIX 2] GC historii — usuń rekordy martwych atomów
            dead_ids = set(self.history.keys()) - set(new_current.keys())
            for dead in dead_ids:
                del self.history[dead]
            self.stats    = {
                "hot": hot, "warm": warm, "cold": cold,
                "tomb": tomb, "total": len(new_current),
            }
            self.last_scan = time.monotonic()

    def snapshots(self) -> List[AtomSnapshot]:
        with self._lock:
            return list(self.current.values())

    def get_history(self, atom_id: str) -> List[float]:
        return list(self.history.get(atom_id, []))

    def get_anomalies(self) -> List[Tuple[float, AtomSnapshot]]:
        with self._lock:
            return list(self.anomalies)

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self.stats)


# ─────────────────────────────────────────────────────────────────────────────
# KTop — interfejs curses
# ─────────────────────────────────────────────────────────────────────────────

VIEWS = ["HOT", "DELTA", "ANOMAL", "HIST", "CLUST"]

class KTop:
    """
    KarmazynOS Thermal Monitor — interfejs curses.

    Użycie:
        top = KTop(phi_space)
        top.run()
    """

    def __init__(self,
                 phi:      Any,
                 interval: float = DEFAULT_INTERVAL,
                 cluster:  Any   = None):
        self.phi      = phi
        self.cluster  = cluster
        self.monitor  = PhiMonitor(phi, interval)
        self.view     = 0         # indeks VIEWS
        self.cursor   = 0
        self.paused   = False
        self.sort_key = "T"       # T | delta | id | state
        self.sort_rev = True
        self.filter   = ""
        self._searching = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        self.monitor.start()
        try:
            curses.wrapper(self._main)
        finally:
            self.monitor.stop()

    def _main(self, scr) -> None:
        curses.curs_set(0)
        curses.noecho()
        scr.keypad(True)
        scr.timeout(int(self.monitor.interval * 1000))
        _init_colors()
        h, w = scr.getmaxyx()

        while True:
            if not self.paused:
                scr.erase()
                h, w = scr.getmaxyx()
                self._draw(scr, h, w)
                scr.refresh()

            ch = scr.getch()
            if ch == -1: continue

            if self._searching:
                self._handle_search(ch, scr)
                continue

            if ch in (ord("q"), ord("Q"), 27,
                      curses.KEY_F10):        break
            elif ch == ord("\t"):             self.view = (self.view + 1) % len(VIEWS)
            elif ch == curses.KEY_UP   or ch == ord("k"): self._move(-1)
            elif ch == curses.KEY_DOWN or ch == ord("j"): self._move(1)
            elif ch == curses.KEY_PPAGE:      self._move(-10)
            elif ch == curses.KEY_NPAGE:      self._move(10)
            elif ch == ord(" "):              self.paused = not self.paused
            elif ch == ord("s"):              self._cycle_sort()
            elif ch == ord("r"):              self.sort_rev = not self.sort_rev
            elif ch == ord("/"):
                self._searching = True
                self.filter     = ""
            elif ch == ord("i"):
                self.view = VIEWS.index("HIST")
            elif ch == ord("a"):
                self.view = VIEWS.index("ANOMAL")
            elif ch == curses.KEY_RESIZE:
                h, w = scr.getmaxyx()

    def _handle_search(self, ch: int, scr) -> None:
        if ch in (27, curses.KEY_F3, 10, 13):
            self._searching = False
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            self.filter = self.filter[:-1]
        elif 32 <= ch < 127:
            self.filter += chr(ch)

    def _move(self, delta: int) -> None:
        snaps = self._filtered_sorted()
        self.cursor = max(0, min(self.cursor + delta, len(snaps) - 1))

    # ── Rysunek ───────────────────────────────────────────────────────────────

    def _draw(self, scr, h: int, w: int) -> None:
        view_name = VIEWS[self.view]
        self._draw_header(scr, h, w, view_name)
        if   view_name == "HOT":    self._draw_hot(scr, h, w)
        elif view_name == "DELTA":  self._draw_delta(scr, h, w)
        elif view_name == "ANOMAL": self._draw_anomal(scr, h, w)
        elif view_name == "HIST":   self._draw_hist(scr, h, w)
        elif view_name == "CLUST":  self._draw_clust(scr, h, w)
        self._draw_footer(scr, h, w)

    def _draw_header(self, scr, h: int, w: int, view: str) -> None:
        stats  = self.monitor.get_stats()
        tabs   = "  ".join(
            f"[{v}]" if v == view else f" {v} "
            for v in VIEWS)
        line1  = (f" KarmazynOS φ-top {VERSION}"
                  f"  HOT:{stats['hot']} WARM:{stats['warm']}"
                  f" COLD:{stats['cold']} TOMB:{stats['tomb']}"
                  f"  Σ={stats['total']}")
        self._put(scr, 0, 0, line1.ljust(w), curses.color_pair(C_HEADER) | curses.A_BOLD)
        self._put(scr, 1, 0, f"  {tabs}".ljust(w), curses.color_pair(C_STATUS))
        if self.filter:
            filt = f"  Filtr: /{self.filter}/"
            self._put(scr, 1, w - len(filt) - 1, filt, curses.color_pair(C_ANOM))
        if self.paused:
            self._put(scr, 0, w - 10, " PAUZA  ", curses.color_pair(C_ANOM))

    def _draw_hot(self, scr, h: int, w: int) -> None:
        """Mapa ciepła — główny widok."""
        snaps  = self._filtered_sorted()
        # Kolumna header
        bar_w  = min(20, w // 4)
        sp_w   = min(10, w // 8)
        id_w   = max(10, w - bar_w - sp_w - 30)
        hdr    = (f"  {'ID':<{id_w}} {'T':>6}  {'Bar':<{bar_w}}"
                  f" {'Spark':<{sp_w}} {'State':<6} {'S'}")
        self._put(scr, 2, 0, hdr[:w].ljust(w),
                  curses.color_pair(C_HEADER))

        visible = h - 5
        offset  = max(0, self.cursor - visible + 1) if self.cursor >= visible else 0

        for row, snap in enumerate(snaps[offset:offset + visible]):
            y   = row + 3
            idx = row + offset
            col = curses.color_pair(_T_color(snap.T))
            if snap.is_anomaly:
                col = curses.color_pair(C_ANOM)
            if idx == self.cursor:
                col = col | curses.A_REVERSE

            hist   = self.monitor.get_history(snap.id)
            bar    = _T_bar(snap.T, snap.T_max, bar_w)
            spark  = _spark(hist, sp_w)
            anom_m = "!!" if snap.is_anomaly else "  "
            line   = (f"{anom_m}{snap.id[:id_w]:<{id_w}}"
                      f" {snap.T:6.1f}  {bar} {spark}"
                      f" {snap.state[:6]:<6} {snap.S[:10]}")
            self._put(scr, y, 0, line[:w].ljust(w), col)

    def _draw_delta(self, scr, h: int, w: int) -> None:
        """Widok delta — kto i o ile zmienił T."""
        snaps = sorted(
            self._filtered_sorted(),
            key=lambda s: abs(s.delta_T),
            reverse=True)

        hdr = f"  {'ID':<30} {'T':>7} {'ΔT':>8} {'Trend':<12} {'Owner'}"
        self._put(scr, 2, 0, hdr[:w].ljust(w), curses.color_pair(C_HEADER))

        visible = h - 5
        for row, snap in enumerate(snaps[:visible]):
            y      = row + 3
            dT     = snap.delta_T
            col    = (curses.color_pair(C_DELTA_UP)   if dT > 0.5
                      else curses.color_pair(C_DELTA_DOWN) if dT < -0.5
                      else curses.color_pair(C_COLD))
            if abs(dT) > ANOMALY_DELTA:
                col = curses.color_pair(C_ANOM) | curses.A_BOLD

            # Trend strzałkowy
            if   dT >  5: trend = "↑↑↑ GRZEJE"
            elif dT >  1: trend = "↑   rośnie"
            elif dT < -5: trend = "↓↓↓ STYGNIE"
            elif dT < -1: trend = "↓   spada"
            else:          trend = "─   stabilne"

            sign = "+" if dT >= 0 else ""
            line = (f"  {snap.id[:30]:<30}"
                    f" {snap.T:7.1f} {sign}{dT:7.1f}"
                    f" {trend:<12} {snap.owner[:20]}")
            self._put(scr, y, 0, line[:w].ljust(w), col)

    def _draw_anomal(self, scr, h: int, w: int) -> None:
        """
        Widok anomalii — skoki T bez właściciela.
        Serce detekcji nieautoryzowanego dostępu.
        """
        anomalies = self.monitor.get_anomalies()
        anomalies.sort(key=lambda x: x[0], reverse=True)

        title = (f"  DETEKCJA ANOMALII TERMICZNYCH"
                 f"  (skok > {ANOMALY_DELTA}°T w < {ANOMALY_WINDOW}s)")
        self._put(scr, 2, 0, title[:w].ljust(w),
                  curses.color_pair(C_ANOM) | curses.A_BOLD)

        hdr = f"  {'Czas temu':>10} {'Atom ID':<28} {'ΔT':>8} {'T':>7} {'Właściciel'}"
        self._put(scr, 3, 0, hdr[:w].ljust(w), curses.color_pair(C_HEADER))

        if not anomalies:
            self._put(scr, 5, 2,
                      "Brak anomalii termicznych. Phi-space stabilne.",
                      curses.color_pair(C_COLD))
            return

        visible = h - 6
        now     = time.monotonic()
        for row, (ts, snap) in enumerate(anomalies[:visible]):
            y      = row + 4
            ago    = now - ts
            ago_s  = f"{ago:.1f}s temu" if ago < 60 else f"{ago/60:.1f}m temu"
            dT     = snap.delta_T
            sign   = "+" if dT >= 0 else ""
            owner  = snap.owner or "(brak właściciela — PODEJRZANE)"
            col    = (curses.color_pair(C_ANOM)
                      if not snap.owner
                      else curses.color_pair(C_WARM))
            line   = (f"  {ago_s:>10} {snap.id[:28]:<28}"
                      f" {sign}{dT:7.1f} {snap.T:7.1f} {owner[:30]}")
            self._put(scr, y, 0, line[:w].ljust(w), col)

    def _draw_hist(self, scr, h: int, w: int) -> None:
        """Historia temperatury wybranego atomu — wykres ASCII."""
        snaps = self._filtered_sorted()
        if not snaps or self.cursor >= len(snaps):
            self._put(scr, 3, 2, "Brak danych.", curses.color_pair(C_COLD))
            return

        snap  = snaps[self.cursor]
        hist  = self.monitor.get_history(snap.id)
        title = f"  Historia: {snap.id}  T={snap.T:.1f}  State={snap.state}"
        self._put(scr, 2, 0, title[:w].ljust(w), curses.color_pair(C_HEADER))

        if not hist:
            self._put(scr, 4, 2, "Brak historii.", curses.color_pair(C_COLD))
            return

        # Wykres słupkowy T w czasie
        chart_h = h - 7
        chart_w = min(w - 10, len(hist))
        mn, mx  = min(hist), max(hist)
        rng     = max(1.0, mx - mn)

        # Rysuj oś Y po lewej
        for row in range(chart_h):
            T_val = mx - (row / max(1, chart_h - 1)) * rng
            label = f"{T_val:5.1f} │"
            col   = curses.color_pair(_T_color(T_val))
            self._put(scr, row + 3, 0, label, col)

        # Rysuj słupki
        hist_slice = list(hist)[-chart_w:]
        for col_idx, T_val in enumerate(hist_slice):
            bar_h = int((T_val - mn) / rng * chart_h)
            for row in range(chart_h):
                y    = 3 + chart_h - 1 - row
                x    = 7 + col_idx
                fill = row < bar_h
                ch   = "█" if fill else " "
                c    = curses.color_pair(_T_color(T_val)) if fill else 0
                try:
                    scr.addch(y, x, ch, c)
                except curses.error:
                    pass

        # Oś X i statystyki
        ax_y = 3 + chart_h
        self._put(scr, ax_y, 7, "└" + "─" * chart_w, curses.color_pair(C_COLD))
        self._put(scr, ax_y + 1, 7,
                  f"min={mn:.1f}  max={mx:.1f}  teraz={snap.T:.1f}  "
                  f"próbek={len(hist)}",
                  curses.color_pair(C_STATUS))

    def _draw_clust(self, scr, h: int, w: int) -> None:
        """Ciepło klastra — mapa węzłów."""
        title = "  MAPA TERMICZNA KLASTRA"
        self._put(scr, 2, 0, title.ljust(w),
                  curses.color_pair(C_HEADER) | curses.A_BOLD)

        if self.cluster is None:
            self._put(scr, 4, 2,
                      "Klaster niedostępny. Uruchom: CLUSTER START",
                      curses.color_pair(C_COLD))
            self._put(scr, 5, 2,
                      "Lokalny węzeł:",
                      curses.color_pair(C_COLD))
            stats = self.monitor.get_stats()
            self._draw_node_bar(scr, 6, "lokalny",
                                stats["hot"], stats["warm"],
                                stats["cold"], stats["total"], w)
            return

        # Z klastra
        try:
            heatmap = self.cluster.heatmap()
        except Exception as e:
            self._put(scr, 4, 2, f"Błąd klastra: {e}",
                      curses.color_pair(C_ANOM))
            return

        hdr = f"  {'Węzeł':<14} {'HOT':>4} {'WARM':>4} {'COLD':>4} {'load':>6}  Mapa"
        self._put(scr, 3, 0, hdr[:w].ljust(w), curses.color_pair(C_HEADER))

        for row, node in enumerate(heatmap[:h - 6]):
            y = row + 4
            self._draw_node_bar(
                scr, y,
                node.get("node_id", "?")[:12],
                node.get("hot",  0),
                node.get("warm", 0),
                node.get("cold", 0),
                node.get("total", node.get("hot",0) + node.get("warm",0) + node.get("cold",0)),
                w,
                is_local=node.get("local", False),
                alive=node.get("alive", True),
            )

    def _draw_node_bar(self, scr, y: int, label: str,
                       hot: int, warm: int, cold: int, total: int,
                       w: int, is_local: bool = False,
                       alive: bool = True) -> None:
        """Pasek termiczny dla jednego węzła."""
        bar_total = max(1, hot + warm + cold)
        bar_w     = min(30, w - 40)
        h_w = int(hot  / bar_total * bar_w)
        w_w = int(warm / bar_total * bar_w)
        c_w = bar_w - h_w - w_w

        bar = ("█" * h_w +
               "▒" * w_w +
               "░" * c_w)
        marker = "◄" if is_local else " "
        status = " OK" if alive else " OFFLINE"
        load   = hot / max(1, bar_total)
        line   = (f"  {marker}{label:<12}"
                  f" {hot:4} {warm:4} {cold:4}"
                  f" {load:5.0%}  [{bar}]{status}")

        col = (curses.color_pair(C_CLUSTER) if is_local
               else curses.color_pair(C_HOT) if load > 0.7
               else curses.color_pair(C_WARM) if alive
               else curses.color_pair(C_TOMB))
        self._put(scr, y, 0, line[:w].ljust(w), col)

    def _draw_footer(self, scr, h: int, w: int) -> None:
        keys = ("Tab=widok  ↑↓=kursor  s=sort  r=rev  "
                "Space=pauza  /=filtr  i=hist  a=anomalie  q=wyjście")
        sort_info = f"Sort: {self.sort_key} {'↓' if self.sort_rev else '↑'}"
        status    = f" {sort_info}  interval={self.monitor.interval:.1f}s "
        self._put(scr, h - 2, 0, keys[:w].ljust(w), curses.color_pair(C_STATUS))
        self._put(scr, h - 1, 0, status[:w].ljust(w), curses.color_pair(C_HEADER))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _put(self, scr, y: int, x: int, text: str, attr: int = 0) -> None:
        try:
            scr.addstr(y, x, text, attr)
        except curses.error:
            pass

    def _filtered_sorted(self) -> List[AtomSnapshot]:
        snaps = self.monitor.snapshots()
        if self.filter:
            fl    = self.filter.lower()
            snaps = [s for s in snaps
                     if fl in s.id.lower()
                     or fl in s.S.lower()
                     or fl in s.E.lower()]
        key_fn = {
            "T":     lambda s: s.T,
            "delta": lambda s: abs(s.delta_T),
            "id":    lambda s: s.id,
            "state": lambda s: s.state,
        }.get(self.sort_key, lambda s: s.T)
        return sorted(snaps, key=key_fn, reverse=self.sort_rev)

    def _cycle_sort(self) -> None:
        keys = ["T", "delta", "id", "state"]
        idx  = keys.index(self.sort_key) if self.sort_key in keys else 0
        self.sort_key = keys[(idx + 1) % len(keys)]


# ─────────────────────────────────────────────────────────────────────────────
# Komenda shella
# ─────────────────────────────────────────────────────────────────────────────

def cmd_top(args, runtime=None, cluster=None, **_kw) -> str:
    """
    TOP [--interval <s>] [--anomaly-only]
    Monitor termiczny phi-space w czasie rzeczywistym.
    """
    if runtime is None:
        return "Brak runtime."

    interval     = DEFAULT_INTERVAL
    anomaly_only = False

    i = 0
    while i < len(args):
        if args[i] in ("--interval", "-i") and i + 1 < len(args):
            try: interval = float(args[i+1]); i += 1
            except ValueError: pass
        elif args[i] == "--anomaly-only":
            anomaly_only = True
        i += 1

    top = KTop(runtime, interval=interval, cluster=cluster)
    if anomaly_only:
        top.view = VIEWS.index("ANOMAL")

    try:
        top.run()
    except Exception as e:
        return f"TOP błąd: {e}"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Standalone
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="KarmazynOS Thermal Monitor")
    ap.add_argument("--interval",     type=float, default=DEFAULT_INTERVAL,
                    help=f"Interwał odświeżania w sekundach (domyślnie {DEFAULT_INTERVAL})")
    ap.add_argument("--anomaly-only", action="store_true",
                    help="Startuj w widoku anomalii")
    ap.add_argument("--demo",         action="store_true",
                    help="Demo z syntetycznymi atomami")
    opt = ap.parse_args()

    if opt.demo:
        # Demo — syntetyczne phi-space
        import math, random

        class _MockAtom:
            def __init__(self, id, S="", T=50.0, state="WARM"):
                self.id    = id;  self.S = S;   self.E  = ""
                self.T     = T;   self.state = state
                self.T_max = 100.0; self.age = 0
            def touch(self): pass

        class _MockPhi:
            def __init__(self):
                self._atoms = [
                    _MockAtom("shell.init",       "sys",    85.0, "HOT"),
                    _MockAtom("program.nooedit",  "editor", 72.0, "HOT"),
                    _MockAtom("bubble.alpha",     "doc",    55.0, "WARM"),
                    _MockAtom("file.karmazyn_phi","source", 48.0, "WARM"),
                    _MockAtom("program.luneta",   "browser",30.0, "WARM"),
                    _MockAtom("sys.scheduler",    "sys",    20.0, "COLD"),
                    _MockAtom("bubble.archive",   "doc",     8.0, "COLD"),
                    _MockAtom("old.session",      "",        1.0, "TOMB"),
                ]
                self.matrix = type("M", (), {"atoms": lambda s: self._atoms})()

            def get_atom(self, id):
                return next((a for a in self._atoms if a.id == id), None)

        phi = _MockPhi()

        # Wątek symulujący zmiany T
        def _simulate():
            import random, time
            while True:
                for a in phi._atoms:
                    noise = random.gauss(0, 0.5)
                    a.T   = max(0, min(a.T_max, a.T + noise - 0.1))
                # Symuluj anomalię co ~15s
                if random.random() < 0.07:
                    victim = random.choice(phi._atoms)
                    victim.T = min(victim.T_max, victim.T + random.uniform(20, 35))
                time.sleep(opt.interval)

        threading.Thread(target=_simulate, daemon=True).start()

    elif _PHI_AVAILABLE:
        phi = PhiSpace()
    else:
        print("Brak karmazyn_phi — uruchom z --demo")
        sys.exit(1)

    cluster = None
    try:
        from karmazyn_cluster import _CLUSTER_INSTANCE
        cluster = _CLUSTER_INSTANCE
    except ImportError:
        pass

    top = KTop(phi, interval=opt.interval, cluster=cluster)
    if opt.anomaly_only:
        top.view = VIEWS.index("ANOMAL")
    top.run()