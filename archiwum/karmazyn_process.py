"""
karmazyn_process.py — Warstwa procesów KarmazynOS v1.1
=======================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Tablica procesów + kontrakt procesu. KarmazynOS tworzy WŁASNE procesy.
Proces = jednostka wykonania z:

  - pid                — identyfikator
  - ppid               — rodzic (hierarchia procesów)
  - stan               — NEW → RUNNING ↔ WAITING_IO → TERMINATING → DEAD
                         (oraz ZOMBIE gdy wątek nie chce się zakończyć)
  - ProcessContext     — własne we/wy (stdout→TTY/okno, stdin←kolejka TTY),
                         NIGDY konsola procesu hosta
  - atom wykonania     — proces ma swój atom w phi (S="process"). OS widzi
                         własne procesy jako atomy. RUNNING≈HOT, DEAD≈usuń.
  - uchwyt do kernela  — RUNTIME/phi współdzielony przez wszystkie procesy
  - opcjonalne okno    — aplikacje GUI dostają okno przez WM

Szeregowanie deleguje host (wątki OS → docelowo jądro Linuksa). Nasze jest:
tożsamość (phi), we/wy (ctx), tablica i CYKL ŻYCIA procesu.

── O kończeniu procesów (ważne) ────────────────────────────────────────────
Python nie potrafi siłowo zabić wątku. Dlatego kończenie jest KOOPERATYWNE:
  • kill() przechodzi w TERMINATING, ustawia ctx._alive=False i odblokowuje
    read() (shutdown TTY), po czym DOŁĄCZA wątek (join z timeoutem).
  • Dobrze napisany target sprawdza ctx.alive() w pętli → kończy się →
    _on_exit() ustawia DEAD i sprząta.
  • Target, który tego NIE robi (np. `while True: sleep`), nie zakończy się —
    oznaczamy go ZOMBIE i logujemy. To uczciwy stan, nie udawany DEAD.
KONTRAKT: długo żyjący target MUSI sprawdzać ctx.alive() (patrz terminal_main).

Reużywa: TerminalState (TTY), EventBus (RUNTIME.events), SYSLOG (log), WM (okna).
"""

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

Color = Tuple[int, int, int]
C_OUT = (255, 255, 255)
C_ERR = (255, 80, 80)
C_SYS = (160, 160, 200)

# Stany procesu (mapują się na termodynamikę atomu)
NEW         = "NEW"
RUNNING     = "RUNNING"
WAITING_IO  = "WAITING_IO"   # zablokowany na ctx.read() — czeka na wejście (nie sen CPU)
TERMINATING = "TERMINATING"  # zażądano zakończenia, wątek jeszcze kończy
ZOMBIE      = "ZOMBIE"       # wątek nie zakończył się po join (target nie kooperuje)
DEAD        = "DEAD"

_LIVE_STATES = (NEW, RUNNING, WAITING_IO, TERMINATING)

# Temperatura atomu procesu
T_PROC_RUN = 85.0

# Domyślny czas oczekiwania na zakończenie wątku przy kill
KILL_JOIN_TIMEOUT = 1.0

# Bieżący proces w wątku — pozwala komendzie EXIT zakończyć WŁASNY proces
# (to okno), zamiast kłaść cały system.
_CURRENT = threading.local()

def current_process() -> Optional["Process"]:
    """Proces wykonujący się w bieżącym wątku, lub None (np. wątek główny/konsola)."""
    return getattr(_CURRENT, "proc", None)


def _now() -> float:
    return time.time()


# ─── ProcessContext — we/wy procesu (jak deskryptory) ────────────────────────

class ProcessContext:
    """
    Kontekst we/wy procesu. Aplikacja pisze do `ctx`, nie do świata.

    tty    — TerminalState lub None. stdout→tty.append, stdin←get_input_blocking.
             Bez tty write() jest no-op (NIE pisze do konsoli hosta — celowo).
    window — okno WM lub None (aplikacje GUI).
    kernel — RUNTIME/phi współdzielony.
    table  — ProcessTable (do spawnowania dzieci).
    """

    def __init__(self, pid: int, name: str,
                 kernel: Any = None, table: "ProcessTable" = None,
                 tty: Any = None, window: Any = None):
        self.pid      = pid
        self.name     = name
        self.kernel   = kernel
        self.table    = table
        self.tty      = tty
        self.window   = window
        self._alive   = True
        self._process: Optional["Process"] = None   # uchwyt do właściciela
        self.on_save: Optional[Callable] = None      # hak: zapis pracy przy zakończeniu (przez store)

    # stdout
    def write(self, text: Any, color: Color = C_OUT) -> None:
        if self.tty is not None and text is not None:
            for line in str(text).split("\n"):
                self.tty.append(line, color)
        # brak tty → nic (żadnego wycieku do konsoli hosta)

    # stdin (blokujący odczyt linii) — w trakcie blokady proces jest WAITING_IO
    def read(self) -> Optional[str]:
        if self.tty is None:
            return None
        p = self._process
        if p is not None and p.state == RUNNING:
            p.state = WAITING_IO
        line = self.tty.get_input_blocking()
        if p is not None and p.state == WAITING_IO:
            p.state = RUNNING
        return line

    def alive(self) -> bool:
        if self.tty is not None and getattr(self.tty, "_shutdown", False):
            return False
        return self._alive

    def spawn(self, name: str, target: Callable, **kw) -> "Process":
        if self.table is None:
            raise RuntimeError("ProcessContext bez ProcessTable")
        kw.setdefault("parent", self.pid)
        return self.table.spawn(name, target, **kw)

    # ── Zapis WYNIKU (trwały) — ODRĘBNY od write() (ekran/TTY) ───────────────
    def store(self, key: str, content: Any, S: str = "result",
              T: float = 45.0, program: str = None):
        """
        Zapisuje wynik programu do bąbla-wyniku keyowanego hologramem programu.

        ODRĘBNE od write(): write() idzie na ekran/TTY i jest ULOTNE; store()
        zapisuje trwały wynik w nieśmiertelnym magazynie phi.

        Reguła dostępu (zgodnie z logiką systemu): wynik istnieje tylko w bąblu;
        bąbel jest osiągalny wyłącznie dla programu z właściwym hologramem (genom).
        Atom poza bąblem nie miałby punktu dostępu — byłby geometrycznie nieistotny.

        Trwałość na dysk rideuje tę samą ścieżkę co dokumenty Workspace
        (karmazyn_store → Pole Proca, dedup + szyfrowanie) — bąbel-wynik to
        zwykły bąbel phi, więc save_documents go persystuje. Bez nowej ścieżki.
        """
        phi = self.kernel
        if phi is None:
            return None
        prog = program or self.name
        bub  = phi.open_result_bubble(prog, create=True)
        aid  = f"res::{prog}::{key}"
        txt  = content if isinstance(content, str) else ""
        phi.create_atom(aid, S=S, E=txt, T=T)   # atom dostaje też vector = bind(onto(S),val(E))
        bub.add(aid)
        if txt:
            bub.content = txt
        return bub

    # ── Odczyt WYNIKÓW (punkt dostępu przez hologram programu) ───────────────
    def results(self, program: str = None):
        """
        Bąbel-wynik programu — osiągalny tylko z właściwym hologramem (genom).
        Bez genomu etykieta jest nieobliczalna → None.
        """
        phi = self.kernel
        if phi is None:
            return None
        return phi.open_result_bubble(program or self.name)

    # ── Zapis PRACY przy zakończeniu (realny, atomowy — przez store) ─────────
    def save_work(self) -> bool:
        """
        Woła hak on_save (jeśli ustawiony) — program zapisuje swoją pracę przez
        store() PRZED zakończeniem. Wołane przy zamknięciu okna i przy EXIT.
        Zwraca True jeśli zapis się wykonał. Idempotentne i bezpieczne (wyjątki
        nie blokują zakończenia procesu).
        """
        cb = self.on_save
        if cb is None:
            return False
        try:
            cb()
            return True
        except Exception:
            return False


# ─── Process — jednostka wykonania ───────────────────────────────────────────

class Process:
    """Proces KarmazynOS = wątek OS + tożsamość (atom phi) + ProcessContext."""

    def __init__(self, pid: int, name: str, target: Optional[Callable],
                 ctx: ProcessContext, table: "ProcessTable",
                 parent: Optional[int] = None):
        self.pid     = pid
        self.name    = name
        self.target  = target
        self.ctx     = ctx
        self.table   = table
        self.parent  = parent          # ppid
        self.state   = NEW
        self.atom_id = f"proc::{pid}"
        self.started = _now()
        self._thread: Optional[threading.Thread] = None
        ctx._process = self

    def start(self) -> "Process":
        if self._thread is not None and self._thread.is_alive():
            return self
        self.state = RUNNING
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"proc-{self.pid}-{self.name}")
        self._thread.start()
        return self

    def _run(self) -> None:
        _CURRENT.proc = self
        try:
            if callable(self.target):
                self.target(self.ctx)
        except SystemExit:
            pass
        except Exception as e:
            self.ctx.write(f"[proc {self.name} BLAD] {e}", C_ERR)
        finally:
            _CURRENT.proc = None
            self.table._on_exit(self)

    def request_stop(self) -> None:
        """Poproś proces o zakończenie (kooperatywnie). Nie blokuje."""
        if self.state in (DEAD, ZOMBIE):
            return
        self.state = TERMINATING
        self.ctx._alive = False
        if self.ctx.tty is not None:
            try:
                self.ctx.tty.shutdown()   # odblokuj read()
            except Exception:
                pass

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def uptime(self) -> float:
        return _now() - self.started


# ─── ProcessTable — tablica procesów ─────────────────────────────────────────

class ProcessTable:
    """Tablica procesów. Jeden kernel, wiele procesów. Każdy ma atom w phi."""

    def __init__(self, kernel: Any = None):
        self.kernel = kernel
        self._procs: Dict[int, Process] = {}
        self._pid   = 0
        self._lock  = threading.RLock()

    # ── Tworzenie ─────────────────────────────────────────────────────────────

    def spawn(self, name: str, target: Optional[Callable],
              tty: Any = None, window: Any = None,
              parent: Optional[int] = None) -> Process:
        with self._lock:
            self._pid += 1
            pid = self._pid
        ctx = ProcessContext(pid, name, kernel=self.kernel,
                             table=self, tty=tty, window=window)
        p = Process(pid, name, target, ctx, self, parent=parent)
        with self._lock:
            self._procs[pid] = p
        self._make_atom(p)
        self._emit("process_spawned", p)
        self._log(f"spawn pid={pid} ppid={parent} {name}")
        p.start()
        return p

    # ── Kończenie ──────────────────────────────────────────────────────────────

    def kill(self, pid: int, join_timeout: float = KILL_JOIN_TIMEOUT) -> bool:
        """
        Kooperatywne zakończenie: request_stop + join. Jeśli wątek nie
        zakończy się w join_timeout (target nie sprawdza ctx.alive()) →
        oznacz ZOMBIE. Nie dołącza do samego siebie (uniknięcie deadlocka).
        """
        p = self.get(pid)
        if p is None:
            return False
        p.request_stop()
        th = p._thread
        if th is not None and th is not threading.current_thread():
            th.join(timeout=join_timeout)
            if th.is_alive():
                p.state = ZOMBIE
                self._log(f"zombie pid={pid} {p.name} — wątek nie kończy się "
                          f"(target nie sprawdza ctx.alive())")
        return True

    def kill_tree(self, pid: int, join_timeout: float = KILL_JOIN_TIMEOUT) -> int:
        """Zakończ proces i WSZYSTKICH potomków. Dzieci przed rodzicami."""
        order: List[int] = []
        frontier = [pid]
        seen = set()
        while frontier:
            cur = frontier.pop()
            if cur in seen:
                continue
            seen.add(cur)
            order.append(cur)
            for q in self.list():
                if q.parent == cur and q.pid not in seen:
                    frontier.append(q.pid)
        killed = 0
        for vp in reversed(order):          # liście najpierw
            if self.kill(vp, join_timeout=join_timeout):
                killed += 1
        return killed

    def _on_exit(self, p: Process) -> None:
        """Wołane z wątku procesu po zakończeniu target (reap)."""
        if p.state != ZOMBIE:
            p.state = DEAD
        self._kill_atom(p)
        self._emit("process_exited", p)
        self._log(f"exit  pid={p.pid} {p.name}")
        with self._lock:
            self._procs.pop(p.pid, None)

    def close_all(self) -> None:
        for p in self.list():
            self.kill(p.pid, join_timeout=0.3)

    # ── Zapytania ──────────────────────────────────────────────────────────────

    def get(self, pid: int) -> Optional[Process]:
        with self._lock:
            return self._procs.get(pid)

    def list(self) -> List[Process]:
        with self._lock:
            return list(self._procs.values())

    def count(self) -> int:
        with self._lock:
            return len(self._procs)

    def children(self, pid: int) -> List[Process]:
        return [p for p in self.list() if p.parent == pid]

    def ps(self) -> str:
        procs = sorted(self.list(), key=lambda x: x.pid)
        if not procs:
            return "(brak procesów)"
        rows = ["  PID  PPID  STAN         UP       NAZWA"]
        for p in procs:
            ppid = "-" if p.parent is None else str(p.parent)
            rows.append(f"  {p.pid:<4} {ppid:<5} {p.state:<12} "
                        f"{p.uptime():6.1f}s  {p.name}")
        return "\n".join(rows)

    # ── Atom procesu w phi ─────────────────────────────────────────────────────

    def _make_atom(self, p: Process) -> None:
        k = self.kernel
        if k is not None and hasattr(k, "create_atom"):
            try:
                meta = json.dumps({"pid": p.pid, "name": p.name, "ppid": p.parent})
                k.create_atom(p.atom_id, "process", meta, T_PROC_RUN)
            except Exception:
                pass

    def _kill_atom(self, p: Process) -> None:
        k = self.kernel
        if k is None:
            return
        try:
            if hasattr(k, "delete_atom"):
                k.delete_atom(p.atom_id)
            elif hasattr(k, "matrix") and hasattr(k.matrix, "delete"):
                k.matrix.delete(p.atom_id)
        except Exception:
            pass

    # ── EventBus + log ─────────────────────────────────────────────────────────

    def _emit(self, event: str, p: Process) -> None:
        k = self.kernel
        if k is not None and hasattr(k, "events"):
            try:
                k.events.emit(event, p)
            except Exception:
                pass

    def _log(self, msg: str) -> None:
        try:
            from karmazyn_syslog import SYSLOG
            SYSLOG.info("proc", msg)
        except Exception:
            pass


# ─── Target powłoki terminala (proces sesji) ─────────────────────────────────

def terminal_main(dispatch: Callable[[str], str],
                  banner: Optional[List[Tuple[str, Color]]] = None) -> Callable:
    """
    Zwraca target(ctx) dla procesu powłoki. Sprawdza ctx.alive() w pętli
    (kontrakt kooperatywnego kończenia), czyta stdin z TTY, dispatchuje,
    pisze stdout do TTY. exit kończy TYLKO ten proces.
    """
    def _main(ctx: ProcessContext) -> None:
        if banner:
            for line, color in banner:
                ctx.write(line, color)
        while ctx.alive():
            line = ctx.read()
            if not ctx.alive():
                break
            line = (line or "").strip()
            if not line:
                continue
            if line.lower() in ("exit", "quit"):
                ctx.write(f"[{ctx.name} zakończony]", C_SYS)
                break
            try:
                result = dispatch(line)
                if result:
                    for ln in str(result).split("\n"):
                        ctx.write(ln, C_OUT)
            except SystemExit:
                break
            except Exception as e:
                ctx.write(f"[BLAD] {e}", C_ERR)
    return _main


def default_banner(name: str = "ksh",
                   commands: Optional[List[str]] = None) -> List[Tuple[str, Color]]:
    lines = [(f"KarmazynOS — proces {name}", C_SYS)]
    if commands:
        preview = "  ".join(sorted(commands)[:12])
        lines.append((f"Komendy: {preview}...", C_SYS))
    return lines


# ─── Rejestr globalny (jak get_active dla WM) ────────────────────────────────

_TABLE: Optional[ProcessTable] = None

def set_table(table: ProcessTable) -> None:
    global _TABLE
    _TABLE = table

def get_table() -> Optional[ProcessTable]:
    return _TABLE