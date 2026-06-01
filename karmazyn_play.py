"""
karmazyn_play.py — Odtwarzacz KarmazynOS v1.0
==============================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Odtwarzacz który gra utwory z bąbli, wewnątrz KarmazynOS. Nie wie
nic o atomach ani phi — woła tylko Workspace.open() / .list().

Filozofia (jak każdy odtwarzacz): otwórz utwór, graj. Cała mechanika
przechowywania pod maską. Backend audio wybierany automatycznie.
Odporność na brak (kluczowe):
  Łańcuch wykrywania backendu — bierze pierwszy dostępny:
    1. pygame.mixer   — działa na Termux i Windows, pauza/głośność/seek
    2. ffplay         — zewnętrzny proces (ffmpeg), tylko stop
    3. aplay / mpv / afplay — systemowe, tylko stop
    4. NullBackend    — gdy NIC nie ma: pokazuje utwór, nie pada
  Gdy żaden backend nie gra — odtwarzacz nadal działa jako przeglądarka
  biblioteki (lista, metadane). System nie wywala się przez brak audio.

Hybryda pamięć/temp (jak ustalono):
  małe utwory (< 4 MB) → grane wprost z bajtów (BytesIO / stdin pipe)
  duże utwory          → zrzut do pliku tymczasowego, granie z dysku, sprzątanie

Rozdział testowalności:
  AudioBackend (+ implementacje) — backendy, izolowane
  KarmazynPlayer — logika biblioteki/playlisty na Workspace (testowalna bez audio)

Sterowanie (gdy TTY):
  spacja  — pauza / wznów
  s       — stop
  n / p   — następny / poprzedni w playliście
  + / -   — głośność
  q       — wyjście
"""

import os
import subprocess
import sys
import tempfile
import time
from typing import List, Optional

from karmazyn_app import Workspace, Item


MEM_LIMIT = 4 * 1024 * 1024   # 4 MB — próg pamięć vs plik tymczasowy


# ═══════════════════════════════════════════════════════════════════════════════
# Backendy audio
# ═══════════════════════════════════════════════════════════════════════════════

class AudioBackend:
    """Interfejs backendu. Wszystkie metody bezpieczne — nie rzucają."""

    name = "base"
    can_pause = False
    can_volume = False

    def available(self) -> bool:        return False
    def load(self, data: bytes, kind: str, track: str) -> bool: return False
    def play(self) -> bool:             return False
    def pause(self) -> None:            pass
    def resume(self) -> None:           pass
    def stop(self) -> None:             pass
    def is_playing(self) -> bool:       return False
    def set_volume(self, v: float) -> None: pass
    def cleanup(self) -> None:          pass


class NullBackend(AudioBackend):
    """Brak audio — odtwarzacz nadal działa (info/lista). Nie pada."""
    name = "none"

    def available(self) -> bool:
        return True   # zawsze "dostępny" jako ostatnia deska ratunku

    def load(self, data, kind, track) -> bool:
        self._track = track
        self._size  = len(data)
        return True

    def play(self) -> bool:
        return False  # nie gra, ale nie pada


class PygameBackend(AudioBackend):
    """
    pygame.mixer — preferowany. Pauza, głośność, async.
    Małe pliki z BytesIO, duże z pliku tymczasowego.
    """
    name = "pygame"
    can_pause = True
    can_volume = True

    def __init__(self):
        self._ok      = False
        self._pygame  = None
        self._tmp     = None
        self._playing = False
        self._paused  = False
        self._vol     = 0.8
        try:
            import pygame
            self._pygame = pygame
            pygame.mixer.init()
            self._ok = True
        except Exception:
            self._ok = False

    def available(self) -> bool:
        return self._ok

    def load(self, data: bytes, kind: str, track: str) -> bool:
        if not self._ok:
            return False
        self._cleanup_tmp()
        try:
            if len(data) < MEM_LIMIT:
                import io
                self._pygame.mixer.music.load(io.BytesIO(data))
            else:
                ext = {"audio": ".mp3"}.get(kind, ".bin")
                fd, path = tempfile.mkstemp(prefix="karmazyn_play_", suffix=ext)
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                self._tmp = path
                self._pygame.mixer.music.load(path)
            self._pygame.mixer.music.set_volume(self._vol)
            return True
        except Exception:
            return False

    def play(self) -> bool:
        if not self._ok:
            return False
        try:
            self._pygame.mixer.music.play()
            self._playing = True
            self._paused  = False
            return True
        except Exception:
            return False

    def pause(self) -> None:
        if self._ok and self._playing and not self._paused:
            self._pygame.mixer.music.pause()
            self._paused = True

    def resume(self) -> None:
        if self._ok and self._paused:
            self._pygame.mixer.music.unpause()
            self._paused = False

    def stop(self) -> None:
        if self._ok:
            try: self._pygame.mixer.music.stop()
            except Exception: pass
        self._playing = False
        self._paused  = False

    def is_playing(self) -> bool:
        if not self._ok:
            return False
        try:
            return bool(self._pygame.mixer.music.get_busy())
        except Exception:
            return False

    def set_volume(self, v: float) -> None:
        self._vol = max(0.0, min(1.0, v))
        if self._ok:
            try: self._pygame.mixer.music.set_volume(self._vol)
            except Exception: pass

    def cleanup(self) -> None:
        self.stop()
        self._cleanup_tmp()

    def _cleanup_tmp(self) -> None:
        if self._tmp and os.path.exists(self._tmp):
            try: os.unlink(self._tmp)
            except OSError: pass
        self._tmp = None


class SubprocessBackend(AudioBackend):
    """
    Zewnętrzny odtwarzacz (ffplay/mpv/aplay/afplay) jako proces.
    Tylko stop (kill). Małe → stdin pipe, duże → plik tymczasowy.
    """
    name = "subprocess"

    # (komenda, czy_obsługuje_stdin_pipe)
    _CANDIDATES = [
        (["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet"], True),
        (["mpv", "--no-video", "--really-quiet"],                  True),
        (["afplay"],                                                False),  # macOS
        (["aplay", "-q"],                                           False),  # WAV
        (["paplay"],                                                False),
    ]

    def __init__(self):
        self._cmd    = None
        self._pipe   = False
        self._proc   = None
        self._tmp    = None
        for cmd, pipe in self._CANDIDATES:
            if self._which(cmd[0]):
                self._cmd  = cmd
                self._pipe = pipe
                break

    @staticmethod
    def _which(prog: str) -> bool:
        from shutil import which
        return which(prog) is not None

    def available(self) -> bool:
        return self._cmd is not None

    def load(self, data: bytes, kind: str, track: str) -> bool:
        if self._cmd is None:
            return False
        self._cleanup_tmp()
        self._data = data
        # małe + backend wspiera stdin → pipe; inaczej temp
        if len(data) < MEM_LIMIT and self._pipe:
            self._use_pipe = True
        else:
            self._use_pipe = False
            ext = {"audio": ".mp3"}.get(kind, ".bin")
            fd, path = tempfile.mkstemp(prefix="karmazyn_play_", suffix=ext)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            self._tmp = path
        return True

    def play(self) -> bool:
        if self._cmd is None:
            return False
        try:
            if self._use_pipe:
                # ffplay/mpv czytają z stdin: dodaj wskaźnik stdin
                cmd = list(self._cmd)
                if cmd[0] == "ffplay":
                    cmd += ["-i", "pipe:0"]
                elif cmd[0] == "mpv":
                    cmd += ["-"]
                self._proc = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # zapis bajtów w tle (żeby nie blokować przy dużych)
                import threading
                def _feed():
                    try:
                        self._proc.stdin.write(self._data)
                        self._proc.stdin.close()
                    except Exception:
                        pass
                threading.Thread(target=_feed, daemon=True).start()
            else:
                cmd = list(self._cmd) + [self._tmp]
                self._proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            try: self._proc.terminate()
            except Exception: pass
        self._proc = None

    def is_playing(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def cleanup(self) -> None:
        self.stop()
        self._cleanup_tmp()

    def _cleanup_tmp(self) -> None:
        if self._tmp and os.path.exists(self._tmp):
            try: os.unlink(self._tmp)
            except OSError: pass
        self._tmp = None


def detect_backend() -> AudioBackend:
    """
    Wybierz najlepszy dostępny backend. Zawsze zwraca coś (NullBackend
    jako ostateczność) — odtwarzacz nigdy nie pada przez brak audio.
    """
    pg = PygameBackend()
    if pg.available():
        return pg
    sp = SubprocessBackend()
    if sp.available():
        return sp
    return NullBackend()


# ═══════════════════════════════════════════════════════════════════════════════
# KarmazynPlayer — biblioteka + playlista na Workspace
# ═══════════════════════════════════════════════════════════════════════════════

class KarmazynPlayer:
    """
    Odtwarzacz oparty na Workspace. Biblioteka = dokumenty audio.
    Logika playlisty testowalna bez sprzętu audio.
    """

    def __init__(self, workspace: Workspace, backend: AudioBackend = None):
        self.ws      = workspace
        self.backend = backend if backend is not None else detect_backend()
        self.playlist: List[str] = []
        self.index   = 0
        self.status  = ""

    # ── Biblioteka ─────────────────────────────────────────────────────────────

    def library(self) -> List[dict]:
        """Lista utworów audio w workspace (nie ogrzewa — peek przez list)."""
        return [d for d in self.ws.list() if d["kind"] == "audio"]

    def build_playlist(self, names: Optional[List[str]] = None) -> List[str]:
        """Zbuduj playlistę z podanych nazw lub całej biblioteki audio."""
        if names:
            self.playlist = [n for n in names if self.ws.exists(n)]
        else:
            self.playlist = [d["name"] for d in self.library()]
        self.index = 0
        return self.playlist

    # ── Odtwarzanie pojedynczego utworu ─────────────────────────────────────────

    def load_track(self, name: str) -> Optional[Item]:
        """Załaduj utwór do backendu. Zwraca Item lub None gdy nie audio."""
        item = self.ws.open(name)
        if item is None:
            self.status = f"Nie ma utworu '{name}'"
            return None
        if not item.is_audio:
            self.status = f"'{name}' to nie jest audio ({item.kind})"
            return None
        ok = self.backend.load(item.data, item.kind, name)
        if not ok:
            self.status = f"Nie udało się załadować '{name}' (backend: {self.backend.name})"
        return item

    def play(self, name: str) -> bool:
        item = self.load_track(name)
        if item is None:
            return False
        ok = self.backend.play()
        if ok:
            self.status = f"▶ {name}"
        else:
            # NullBackend lub błąd — pokaż info zamiast grać
            self.status = (f"♪ {name} — {item.size} B "
                           f"(brak działającego audio: {self.backend.name})")
        return ok

    def stop(self) -> None:
        self.backend.stop()
        self.status = "■ stop"

    def toggle_pause(self) -> None:
        if not self.backend.can_pause:
            return
        if getattr(self.backend, "_paused", False):
            self.backend.resume()
            self.status = "▶ wznowiono"
        else:
            self.backend.pause()
            self.status = "❚❚ pauza"

    # ── Nawigacja playlisty ─────────────────────────────────────────────────────

    def current(self) -> Optional[str]:
        if 0 <= self.index < len(self.playlist):
            return self.playlist[self.index]
        return None

    def play_current(self) -> bool:
        name = self.current()
        return self.play(name) if name else False

    def next(self) -> bool:
        if self.index + 1 < len(self.playlist):
            self.index += 1
            return self.play_current()
        self.status = "koniec playlisty"
        return False

    def prev(self) -> bool:
        if self.index > 0:
            self.index -= 1
            return self.play_current()
        return False

    def volume(self, delta: float) -> None:
        cur = getattr(self.backend, "_vol", 0.8)
        self.backend.set_volume(cur + delta)

    def cleanup(self) -> None:
        self.backend.cleanup()

    # ── Pętla interaktywna (gdy TTY) lub odtwarzanie blokujące ──────────────────

    def run_interactive(self, start_name: Optional[str] = None) -> str:
        """
        Pętla sterowania. Używa przenośnego czytnika klawiszy z karmazyn_edit.
        Gdy brak TTY → odtwarza i czeka (lub tylko info gdy NullBackend).
        """
        if start_name:
            self.build_playlist([start_name])
        elif not self.playlist:
            self.build_playlist()

        if not self.playlist:
            return "Brak utworów audio w bibliotece."

        # Czytnik klawiszy współdzielony z edytorem
        try:
            from karmazyn_edit import make_key_reader
            reader = make_key_reader()
        except Exception:
            reader = None

        self.play_current()

        if reader is None:
            # Brak TTY — odtwarzaj playlistę po kolei, czekając
            return self._run_blocking()

        with reader:
            running = True
            while running:
                self._render_now_playing()
                # nieblokujące sprawdzenie końca utworu byłoby lepsze,
                # ale read_key blokuje — akceptujemy sterowanie ręczne
                key = reader.read_key()
                if key == "q" or key == "QUIT":
                    running = False
                elif key == " ":
                    self.toggle_pause()
                elif key == "s":
                    self.stop()
                elif key == "n" or key == "RIGHT":
                    self.next()
                elif key == "p" or key == "LEFT":
                    self.prev()
                elif key == "+":
                    self.volume(+0.1)
                elif key == "-":
                    self.volume(-0.1)
        self.cleanup()
        sys.stdout.write("\n")
        return "ok"

    def _render_now_playing(self) -> None:
        name = self.current() or "?"
        pos  = f"{self.index + 1}/{len(self.playlist)}"
        line = (f"\r♪ [{pos}] {name}  ·  {self.status}  "
                f"(spacja=pauza s=stop n/p=zmiana +/-=głośność q=wyjście)   ")
        sys.stdout.write(line[:120])
        sys.stdout.flush()

    def _run_blocking(self) -> str:
        """Bez TTY: odtwórz playlistę po kolei, czekając na koniec każdego."""
        for i in range(len(self.playlist)):
            self.index = i
            name = self.current()
            ok = self.play(name)
            print(self.status)
            if not ok:
                continue   # NullBackend — tylko info, idź dalej
            # czekaj aż utwór się skończy (z limitem bezpieczeństwa)
            waited = 0.0
            while self.backend.is_playing() and waited < 3600:
                time.sleep(0.2)
                waited += 0.2
        self.cleanup()
        return "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# Komenda powłoki
# ═══════════════════════════════════════════════════════════════════════════════

_WS: Optional[Workspace] = None
_PLAYER: Optional[KarmazynPlayer] = None


def cmd_play(args: List[str], phi=None) -> str:
    """
    PLAY            — lista utworów audio
    PLAY <nazwa>    — odtwórz utwór
    PLAY *          — odtwórz całą bibliotekę (playlista)
    """
    global _WS, _PLAYER
    if _WS is None or (phi is not None and _WS.phi is not phi):
        _WS = Workspace(phi=phi)
        _PLAYER = KarmazynPlayer(_WS)

    if not args:
        lib = _PLAYER.library()
        if not lib:
            return "Brak utworów audio. Dodaj przez zapis pliku audio do dokumentu."
        head = f"Biblioteka (backend audio: {_PLAYER.backend.name}):\n"
        return head + "\n".join(
            f"  {d['name']:24} {d['size']:>8} B" for d in lib)

    if args[0] == "*":
        return _PLAYER.run_interactive()
    return _PLAYER.run_interactive(args[0])


if __name__ == "__main__":
    ws = Workspace()
    player = KarmazynPlayer(ws)
    print(f"Backend audio: {player.backend.name}")
    if len(sys.argv) > 1:
        player.run_interactive(sys.argv[1])
    else:
        lib = player.library()
        print(f"Utwory: {[d['name'] for d in lib] or 'brak'}")