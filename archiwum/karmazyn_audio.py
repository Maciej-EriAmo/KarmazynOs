"""
karmazyn_audio.py — Daemon Audio KarmazynOS v1.2
=================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Zarządza odtwarzaczem audio (mpv) przez JSON IPC socket.
Metadane ICY → atomy phi-space. Aktualny utwór = HOT, poprzedni stygnie.

Zmiany v1.2 (poprawki drugiej recenzji):
  BUG 1 — _push_event(): rolling buffer zamiast put_nowait() który zabija watek
           przy queue.Full. Stary event wypada, nowy zawsze wchodzi.
  BUG 2 — send(): streaming parser — buf = lines[-1] zachowuje niepelna linie
           zamiast probowac parsowac polowe JSON-a przy split(b"\\n").
  BUG 3 — _on_track_change(): _track modyfikowany pod self._lock.
           Race condition: now_playing()/status_str() czytaly _track bez locka.
  BUG 4 — shutdown(): join() watkow po stop() z timeout=1.0 kazdy.
           Poprzednio watki mogly dalej dzialac po shutdown().
  BUG 5 — _normalize_title() + debounce PO normalizacji.
           ICY moze rotowac whitespace, reklamy co sekunde — lawina atomow.

Zmiany v1.1:
  - _stop_process(): process.wait() POZA lockiem — deadlock fix.

Platforma:
  Linux/Termux: mpv --input-ipc-server=/tmp/karmazyn_mpv.sock
  Instalacja:   pkg install mpv  (Termux) | apt install mpv (Debian)
"""

import json
import os
import platform
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

IS_WINDOWS = platform.system() == "Windows"
IS_TERMUX  = "com.termux" in os.environ.get("PREFIX", "")

IPC_SOCK_PATH    = "/tmp/karmazyn_mpv.sock"
META_POLL_S      = 2.0
WATCHDOG_S       = 3.0
IPC_TIMEOUT_S    = 1.5
IPC_CONNECT_WAIT = 0.2
IPC_CONNECT_MAX  = 25
T_TRACK_HOT      = 90.0
T_TRACK_RECENT   = 50.0


# ─── Normalizacja tytulu ICY ─────────────────────────────────────────────────

def _normalize_title(raw: str) -> str:
    """
    BUG FIX v1.2 (BUG 5): normalizuje tytul ICY przed debounce.
    "Artist - Track " != "Artist - Track" bez normalizacji → nowy atom.
    Collapse whitespace: "Artist  -  Track" → "Artist - Track".
    """
    if not raw:
        return ""
    return " ".join(raw.strip().split())


# ─── Wykrywanie mpv ───────────────────────────────────────────────────────────

def find_mpv() -> Optional[str]:
    return shutil.which("mpv")


def mpv_supports_ipc() -> bool:
    mpv = find_mpv()
    if not mpv:
        return False
    try:
        r = subprocess.run([mpv, "--version"], capture_output=True,
                           text=True, timeout=3)
        m = re.search(r"mpv (\d+)\.(\d+)", r.stdout)
        if m:
            return (int(m.group(1)), int(m.group(2))) >= (0, 17)
        return True
    except Exception:
        return False


# ─── Model danych ─────────────────────────────────────────────────────────────

@dataclass
class TrackInfo:
    title:    str   = ""
    station:  str   = ""
    url:      str   = ""
    start_ts: float = field(default_factory=time.time)
    atom_id:  str   = ""

    def age_s(self) -> float:
        return time.time() - self.start_ts


# ─── IPC komunikacja z mpv ────────────────────────────────────────────────────

class MpvIPC:
    """
    Klient JSON IPC dla mpv przez Unix domain socket.
    mpv musi byc uruchomiony z --input-ipc-server=<sciezka>.

    BUG FIX v1.2 (BUG 2): streaming parser w send().
    buf = lines[-1] zachowuje niepelna linie miedzy porcjami recv().
    Wczesniej split(b"\\n") probowal parsowac uszkodzony fragment
    gdy recv() zwrocilo polowe JSON-a — cicha utrata odpowiedzi.
    """

    def __init__(self, sock_path: str = IPC_SOCK_PATH):
        self.sock_path   = sock_path
        self._lock       = threading.Lock()
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def send(self, command: list,
             timeout: float = IPC_TIMEOUT_S) -> Optional[Any]:
        if IS_WINDOWS:
            return None
        with self._lock:
            try:
                with socket.socket(socket.AF_UNIX,
                                   socket.SOCK_STREAM) as s:
                    s.settimeout(timeout)
                    s.connect(self.sock_path)
                    rid = self._next_id()
                    msg = json.dumps({
                        "command": command, "request_id": rid,
                    }) + "\n"
                    s.sendall(msg.encode("utf-8"))

                    buf      = b""
                    deadline = time.time() + timeout
                    while time.time() < deadline:
                        try:
                            chunk = s.recv(4096)
                        except socket.timeout:
                            break
                        if not chunk:
                            break

                        buf  += chunk
                        # BUG FIX v1.2: streaming parser.
                        # lines[-1] = potencjalnie niepelna linia — zostaje
                        # w buf do nastepnego recv(). Parsujemy tylko lines[:-1].
                        lines = buf.split(b"\n")
                        buf   = lines[-1]

                        for line in lines[:-1]:
                            if not line.strip():
                                continue
                            try:
                                resp = json.loads(line)
                                if resp.get("request_id") == rid:
                                    if resp.get("error") == "success":
                                        return resp.get("data")
                                    return None
                            except json.JSONDecodeError:
                                pass

            except (ConnectionRefusedError, FileNotFoundError,
                    socket.timeout, OSError):
                pass
        return None

    def is_alive(self) -> bool:
        try:
            return (self.send(["get_property", "playback-time"],
                              timeout=0.5) is not None)
        except Exception:
            return False

    def get_property(self, prop: str) -> Optional[Any]:
        return self.send(["get_property", prop])

    def set_property(self, prop: str, value: Any) -> bool:
        return self.send(["set_property", prop, value]) is not None

    def get_title(self) -> Optional[str]:
        for prop in ("media-title", "icy-title",
                     "metadata/by-key/icy-StreamTitle", "filename"):
            val = self.get_property(prop)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        return None

    def get_volume(self) -> int:
        v = self.get_property("volume")
        return int(v) if v is not None else -1

    def set_volume(self, vol: int) -> bool:
        return self.set_property("volume", max(0, min(100, vol)))

    def pause(self) -> bool:
        paused = self.get_property("pause")
        if paused is None:
            return False
        return self.set_property("pause", not paused)

    def is_paused(self) -> bool:
        return bool(self.get_property("pause"))

    def stop(self) -> bool:
        return self.send(["stop"]) is not None

    def get_duration(self) -> Optional[float]:
        return self.get_property("duration")

    def get_playback_time(self) -> Optional[float]:
        return self.get_property("playback-time")

    def get_metadata(self) -> Dict[str, str]:
        raw = self.get_property("metadata")
        if isinstance(raw, dict):
            return {k.lower(): str(v) for k, v in raw.items()}
        return {}


# ─── Daemon Audio ─────────────────────────────────────────────────────────────

class AudioDaemon:
    """
    Daemon audio KarmazynOS z mpv IPC.
    ICY metadata → atomy phi-space (aktualny utwar = HOT, poprzedni stygnie).
    """

    def __init__(self, runtime,
                 sock_path: str = IPC_SOCK_PATH,
                 volume: int = 80):
        self.runtime   = runtime
        self.sock_path = sock_path
        self._volume   = volume
        self._ipc:     Optional[MpvIPC] = None
        self._process: Optional[subprocess.Popen] = None
        self._current_url:     str = ""
        self._current_station: str = ""
        self._track:           Optional[TrackInfo] = None
        self._prev_title:      str = ""
        self._lock             = threading.Lock()
        self._running          = False
        self._meta_thread:     Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._events:          queue.Queue = queue.Queue(maxsize=100)

        self._mpv_path = find_mpv()
        self._has_ipc  = mpv_supports_ipc() if self._mpv_path else False
        self._use_ipc  = self._has_ipc and not IS_WINDOWS

    # ── Status ────────────────────────────────────────────────────────────────

    def capabilities(self) -> Dict[str, Any]:
        return {
            "mpv_path": self._mpv_path,
            "has_ipc":  self._has_ipc,
            "use_ipc":  self._use_ipc,
            "platform": platform.system(),
            "termux":   IS_TERMUX,
            "volume":   self._volume,
            "playing":  self.is_playing(),
            "paused":   self.is_paused(),
        }

    def is_playing(self) -> bool:
        with self._lock:
            if self._process is None:
                return False
            return self._process.poll() is None

    def is_paused(self) -> bool:
        if not self._use_ipc or self._ipc is None:
            return False
        return self._ipc.is_paused()

    def now_playing(self) -> Optional[TrackInfo]:
        """
        BUG FIX v1.2 (BUG 3): czytaj _track pod lockiem.
        Race z _on_track_change() ktory zapisuje _track.title/_track.atom_id.
        GIL chroni przed korupcja, ale nie przed niespojnoscia logiczna.
        """
        if not self.is_playing():
            return None
        with self._lock:
            return self._track

    # ── Odtwarzanie ───────────────────────────────────────────────────────────

    def play(self, url: str, station_name: str = "",
             volume: int = None) -> Tuple[bool, str]:
        if self._mpv_path is None:
            return False, ("Brak mpv. Zainstaluj:\n"
                           "  Termux: pkg install mpv\n"
                           "  Debian: apt install mpv")

        vol = volume if volume is not None else self._volume
        self._stop_process()

        if not IS_WINDOWS and os.path.exists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass

        cmd = self._build_cmd(url, vol)

        with self._lock:
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._current_url     = url
                self._current_station = station_name or url.split("/")[-1][:30]
                self._track           = TrackInfo(
                    title   = self._current_station,
                    station = self._current_station,
                    url     = url,
                )
                self._prev_title = ""   # reset debounce przy nowej stacji
            except FileNotFoundError:
                return False, f"Nie znaleziono mpv: {self._mpv_path}"
            except Exception as e:
                return False, f"Blad uruchamiania: {e}"

        if self._use_ipc:
            self._ipc = MpvIPC(self.sock_path)
            self._wait_for_ipc()
            self._ipc.set_volume(vol)

        if not self._running:
            self._running = True
            self._start_threads()

        self._log(f"Odtwarzam: {self._current_station} [{url[:50]}]")
        return True, f"Odtwarzam: {self._current_station}"

    def _build_cmd(self, url: str, vol: int) -> List[str]:
        cmd = [
            self._mpv_path,
            "--no-video", "--quiet",
            f"--volume={vol}",
            "--term-status-msg=",
            "--cache=yes",
            "--cache-secs=10",
            "--demuxer-max-bytes=50MiB",
        ]
        if self._use_ipc:
            cmd.append(f"--input-ipc-server={self.sock_path}")
        cmd.append(url)
        return cmd

    def _wait_for_ipc(self) -> bool:
        if IS_WINDOWS or not self._use_ipc:
            return False
        for _ in range(IPC_CONNECT_MAX):
            if os.path.exists(self.sock_path) and self._ipc.is_alive():
                return True
            time.sleep(IPC_CONNECT_WAIT)
        return False

    def stop(self) -> str:
        station = self._current_station
        if self._use_ipc and self._ipc:
            self._ipc.stop()
            time.sleep(0.2)
        self._stop_process()
        self._cool_current_track()
        return "Zatrzymano." + (f" (bylo: {station})" if station else "")

    def _stop_process(self) -> None:
        """
        BUG FIX v1.1: process.wait() POZA lockiem.
        Wyciagnij proc z locka → zwolnij lock → czekaj poza lockiem.
        """
        with self._lock:
            proc = self._process
            self._process         = None
            self._current_url     = ""
            self._current_station = ""

        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def pause_toggle(self) -> str:
        if not self._use_ipc or self._ipc is None:
            return "Pauza niedostepna (brak IPC). Wymagany mpv >= 0.17."
        if not self.is_playing():
            return "Nic nie gra."
        self._ipc.pause()
        state = "Pauza" if self._ipc.is_paused() else "Wznowiono"
        return f"{state}: {self._current_station}"

    def volume(self, vol: int) -> str:
        vol = max(0, min(100, vol))
        self._volume = vol
        if self._use_ipc and self._ipc and self.is_playing():
            self._ipc.set_volume(vol)
            actual = self._ipc.get_volume()
            return f"Glosnosc: {actual}%"
        return f"Glosnosc: {vol}% (aktywna przy nastepnym play)"

    def shutdown(self) -> None:
        """
        BUG FIX v1.2 (BUG 4): join() watkow po stop().
        Poprzednio: _running=False, ale watki dalej mogly dzialac.
        Teraz: join(timeout=1.0) — czekaj az watki skonczą iteracje.
        daemon=True wciaz chroni przed wiszacym procesem przy exit().
        """
        self._running = False
        self.stop()
        for t in (self._meta_thread, self._watchdog_thread):
            if t is not None and t.is_alive():
                t.join(timeout=1.0)

    # ── Watki ─────────────────────────────────────────────────────────────────

    def _start_threads(self) -> None:
        self._meta_thread = threading.Thread(
            target=self._meta_loop, daemon=True,
            name="karmazyn-audio-meta",
        )
        self._meta_thread.start()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True,
            name="karmazyn-audio-watchdog",
        )
        self._watchdog_thread.start()

    def _meta_loop(self) -> None:
        """
        Watek metadanych. Odpytuje mpv o tytul ICY co META_POLL_S sekund.
        BUG FIX v1.2 (BUG 5): normalizacja + debounce po normalizacji.
        Bez normalizacji: kazdej drobna zmiana whitespace = nowy atom.
        """
        while self._running:
            time.sleep(META_POLL_S)
            if not self.is_playing():
                continue
            if not self._use_ipc or self._ipc is None:
                continue
            try:
                raw_title = self._ipc.get_title()
                if raw_title is None:
                    continue
                norm = _normalize_title(raw_title)
                if not norm or norm == self._prev_title:
                    continue   # debounce — ten sam tytul po normalizacji
                self._prev_title = norm
                self._on_track_change(norm)
            except Exception:
                pass

    def _on_track_change(self, new_title: str) -> None:
        """
        Wywoływane gdy zmienia sie tytul ICY (po normalizacji).
        BUG FIX v1.2 (BUG 3): _track modyfikowany pod self._lock.
        """
        self._cool_current_track()

        ts      = int(time.time())
        atom_id = f"track_{ts}"

        with self._lock:
            station = self._current_station

        try:
            if not self.runtime.matrix.has_atom(atom_id):
                self.runtime.create_atom(
                    atom_id, new_title[:64], station, T_TRACK_HOT,
                )
        except Exception:
            pass

        # BUG FIX v1.2 (BUG 3): zapis pod lockiem
        with self._lock:
            if self._track is not None:
                self._track.title   = new_title
                self._track.atom_id = atom_id

        self._log(f"ICY: {new_title}")
        self._push_event(("track_change", new_title, station))

    def _cool_current_track(self) -> None:
        with self._lock:
            track = self._track
        if track and track.atom_id:
            try:
                atom = self.runtime.get_atom(track.atom_id)
                if atom:
                    atom.T     = T_TRACK_RECENT
                    atom.state = "WARM"
            except Exception:
                pass

    def _watchdog_loop(self) -> None:
        """Watchdog: czysci stan gdy mpv zakonczy sie sam."""
        while self._running:
            time.sleep(WATCHDOG_S)
            with self._lock:
                proc = self._process
            if proc is not None and proc.poll() is not None:
                with self._lock:
                    if self._process is proc:
                        self._process         = None
                        self._current_url     = ""
                        self._current_station = ""
                self._cool_current_track()
                self._log("mpv zakonczyl dzialanie")
                self._push_event(("stopped", "", ""))

    # ── Kolejka zdarzen ───────────────────────────────────────────────────────

    def _push_event(self, event: tuple) -> None:
        """
        BUG FIX v1.2 (BUG 1): rolling buffer zamiast put_nowait().

        put_nowait() przy pelnej kolejce rzuca queue.Full ktory wylatywal
        z _meta_loop lub _watchdog_loop — cichy crash watku, daemon
        bez monitorowania metadanych az do restartu.

        Rolling buffer: wyrzuc najstarszy event, wstaw nowy.
        Najnowsze zdarzenie zawsze wchodzi kosztem najstarszego.
        """
        try:
            self._events.put_nowait(event)
        except queue.Full:
            try:
                self._events.get_nowait()   # wyrzuc najstarszy
            except queue.Empty:
                pass
            try:
                self._events.put_nowait(event)
            except queue.Full:
                pass   # ekstremalny edge case — porzuc event

    def drain_events(self) -> List[tuple]:
        events = []
        while not self._events.empty():
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return events

    def _log(self, msg: str) -> None:
        try:
            from sys_registry import REGISTRY
            REGISTRY.log("EVENT", msg, service="audio")
        except Exception:
            pass

    # ── Status ────────────────────────────────────────────────────────────────

    def status_str(self) -> str:
        cap = self.capabilities()
        lines = [
            f"mpv:       {cap['mpv_path'] or 'nie znaleziono'}",
            f"IPC:       {'aktywne' if cap['use_ipc'] else 'niedostepne'}",
            f"Platforma: {cap['platform']}"
            + (" (Termux)" if cap["termux"] else ""),
            f"Glosnosc:  {cap['volume']}%",
        ]
        if cap["playing"]:
            # BUG FIX v1.2 (BUG 3): czytaj _track pod lockiem
            with self._lock:
                t = self._track
            if t:
                lines.append(f"Gra:       {t.station}")
                if t.title != t.station:
                    lines.append(f"Utwar:     {t.title}")
                lines.append(f"URL:       {t.url[:60]}")
                lines.append(f"Czas:      {t.age_s():.0f}s")
            if cap["paused"]:
                lines.append("Stan:      PAUZA")
            if self._use_ipc and self._ipc:
                vol = self._ipc.get_volume()
                if vol >= 0:
                    lines.append(f"Glosnosc:  {vol}% (mpv)")
        else:
            lines.append("Stan:      zatrzymane")
        return "\n".join(lines)


# ─── Komenda shella ───────────────────────────────────────────────────────────

def cmd_audio(args, daemon: AudioDaemon) -> str:
    """
    AUDIO STATUS          — stan daemona
    AUDIO PAUSE           — pauza/wznow (wymaga IPC)
    AUDIO VOL <0-100>     — glosnosc
    AUDIO STOP            — zatrzymaj
    AUDIO INFO            — metadane ICY aktualnego utworu
    AUDIO EVENTS          — ostatnie zdarzenia z kolejki
    """
    if not args or args[0].upper() == "STATUS":
        return daemon.status_str()

    sub = args[0].upper()

    if sub == "PAUSE":
        return daemon.pause_toggle()

    if sub == "VOL":
        if len(args) < 2:
            return f"Glosnosc: {daemon._volume}%"
        try:
            return daemon.volume(int(args[1]))
        except ValueError:
            return "AUDIO VOL <0-100>"

    if sub == "STOP":
        return daemon.stop()

    if sub == "INFO":
        t = daemon.now_playing()
        if t is None:
            return "Nic nie gra."
        lines = [
            f"Stacja: {t.station}",
            f"Utwar:  {t.title}",
            f"URL:    {t.url}",
            f"Czas:   {t.age_s():.0f}s",
            f"Atom:   {t.atom_id or 'brak'}",
        ]
        if daemon._use_ipc and daemon._ipc:
            meta = daemon._ipc.get_metadata()
            if meta:
                lines.append("Metadane mpv:")
                for k, v in list(meta.items())[:8]:
                    lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    if sub == "EVENTS":
        events = daemon.drain_events()
        if not events:
            return "Brak nowych zdarzen audio."
        lines = []
        for ev in events:
            if ev[0] == "track_change":
                lines.append(f"track_change: {ev[1]} @ {ev[2]}")
            elif ev[0] == "stopped":
                lines.append("stopped")
            else:
                lines.append(str(ev))
        return "\n".join(lines)

    return cmd_audio([], daemon)