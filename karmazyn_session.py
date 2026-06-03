"""
karmazyn_session.py — Sesje terminala KarmazynOS v1.0
======================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Wzorzec multipleksera terminala (jak xterm/tmux/PTY) — nic nowego, to
standard każdego systemu okienkowego. Każde okno terminala to osobna
SESJA:

    Sesja = wirtualny TTY (TerminalState) + wątek workera

Wszystkie sesje dzielą JEDEN kernel (RUNTIME/phi) — jeden system, wiele
terminali, jak wiele xterm na jednym Linuksie. Shell i komendy piszą do
TerminalState swojej sesji, NIGDY do konsoli procesu (sys.stdout/stdin).
Dzięki temu konsola startowa po starcie pulpitu milczy, a zamknięcie
jednego okna terminala kończy TYLKO tę sesję, nie cały system.

Reużywa istniejących klocków KarmazynOS:
  TerminalState (karmazyn_display) — wirtualny TTY (bufor linii + kolejka
                                     klawiszy karmiona zdarzeniami SDL)
  process_command (shell)          — dyspozytor komend, wspólny dla sesji

Nie zawiera I/O konsoli (print/input/msvcrt) — to celowe. W trybie
okienkowym żadne wyjście nie idzie do konsoli procesu.
"""

import threading
from typing import Callable, List, Optional, Tuple

from karmazyn_display import TerminalState

Color = Tuple[int, int, int]
C_RESULT = (255, 255, 255)
C_STATUS = (160, 160, 200)
C_ACCENT = (180, 60, 60)
C_ERROR  = (255, 80, 80)


class Session:
    """
    Pojedyncza sesja terminala: wirtualny TTY + wątek workera.

    dispatch — callable(line:str) -> str: wykonuje komendę i zwraca wynik
               (np. shell.process_command). Wspólny dla wszystkich sesji,
               więc wszystkie operują na tym samym kernelu.
    term     — TerminalState tej sesji (jeśli None, tworzony nowy). Okno
               terminala renderuje TEN obiekt i karmi jego kolejkę klawiszy.
    """
    _seq = 0

    def __init__(self, dispatch: Callable[[str], str],
                 term: Optional[TerminalState] = None,
                 name: Optional[str] = None,
                 banner: Optional[List[Tuple[str, Color]]] = None):
        Session._seq += 1
        self.id      = Session._seq
        self.name    = name or f"ksh-{self.id}"
        self.dispatch = dispatch
        self.term    = term if term is not None else TerminalState()
        self.banner  = banner
        self._thread: Optional[threading.Thread] = None

    # ── Cykl życia ─────────────────────────────────────────────────────────────

    def start(self) -> "Session":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name=f"session-{self.id}")
        self._thread.start()
        return self

    def stop(self) -> None:
        """Zakończ sesję (odblokowuje workera czekającego na input)."""
        self.term.shutdown()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Pętla workera (zamiast globalnego shell_worker) ──────────────────────

    def _loop(self) -> None:
        t = self.term
        if self.banner:
            for line, color in self.banner:
                t.append(line, color)
        while not t._shutdown:
            line = t.get_input_blocking()
            if t._shutdown:                 # rozróżnij shutdown od pustego Enter
                break
            line = (line or "").strip()
            if not line:
                continue                    # pusty Enter NIE kończy sesji
            if line.lower() in ("exit", "quit"):
                t.append(f"[sesja {self.name} zakończona]", C_STATUS)
                t.shutdown()
                break
            try:
                result = self.dispatch(line)
                if result:
                    for ln in str(result).split("\n"):
                        t.append(ln, C_RESULT)
            except SystemExit:
                t.shutdown()
                break
            except Exception as e:
                t.append(f"[BLAD] {e}", C_ERROR)


class SessionManager:
    """
    Rejestr sesji. Jeden dyspozytor (kernel), wiele sesji.
    Tworzy sesje, śledzi je, kończy. Pierwszą sesję (na głównym
    TerminalState display) traktujemy jak każdą inną.
    """

    def __init__(self, dispatch: Callable[[str], str]):
        self.dispatch  = dispatch
        self.sessions: List[Session] = []
        self._lock     = threading.Lock()

    def new_session(self, term: Optional[TerminalState] = None,
                    name: Optional[str] = None,
                    banner: Optional[List[Tuple[str, Color]]] = None) -> Session:
        s = Session(self.dispatch, term=term, name=name, banner=banner)
        with self._lock:
            self.sessions.append(s)
        s.start()
        return s

    def close_session(self, s: Session) -> None:
        s.stop()
        with self._lock:
            if s in self.sessions:
                self.sessions.remove(s)

    def close_all(self) -> None:
        with self._lock:
            sess = list(self.sessions)
        for s in sess:
            s.stop()

    def count(self) -> int:
        with self._lock:
            return len(self.sessions)


# Domyślny baner sesji (zwięzły — pełny baner boot idzie raz do konsoli)
def default_banner(commands: Optional[List[str]] = None) -> List[Tuple[str, Color]]:
    lines = [("KarmazynOS — sesja terminala", C_ACCENT)]
    if commands:
        preview = "  ".join(sorted(commands)[:12])
        lines.append((f"Komendy: {preview}...", C_STATUS))
    return lines
