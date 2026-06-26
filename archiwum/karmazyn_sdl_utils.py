"""
karmazyn_sdl_utils.py — KarmazynOS SDL Utilities v1.0
======================================================
Wspólne narzędzia SDL/display wyciągnięte z duplikatów
w NooEdit.py i AstraEdit.py.

Zawiera:
  _is_sdl_mode()          — wykryj aktywne okno SDL (pygame)
  _find_external_editor() — znajdź zewnętrzny edytor tekstowy
  FileWatcher             — obserwuj zmiany pliku (hash MD5)

Izomorfizm z phi-space:
  FileWatcher ≡ sensor temperatury — wykrywa zmianę stanu zewnętrznego
  _is_sdl_mode ≡ sprawdzenie stanu ekranu (substrat renderowania)
"""

import hashlib
import os
import platform
import shutil
import subprocess
import threading
from typing import Callable, Optional, Tuple


# ── Detekcja środowiska ───────────────────────────────────────────────────────

def is_sdl_mode() -> bool:
    """
    Sprawdź czy jesteśmy w trybie SDL (aktywne okno pygame).

    Zwraca True gdy pygame.display jest zainicjalizowany.
    Używane do wyboru trybu edytora:
      True  → zewnętrzny edytor (SDL zajmuje terminal)
      False → prompt_toolkit TUI (terminal dostępny)
    """
    try:
        import pygame
        return bool(pygame.display.get_init())
    except ImportError:
        return False
    except Exception:
        return False


def find_external_editor() -> Tuple[Optional[list], bool]:
    """
    Znajdź zewnętrzny edytor tekstowy dostępny na platformie.

    Zwraca (args_list, blocking) gdzie:
      args_list — lista argumentów do subprocess.Popen
      blocking  — czy edytor blokuje do zamknięcia (True/False)
      (None, False) — brak edytora

    Kolejność priorytetów:
      Windows: code > notepad++ > notepad (zawsze dostępny)
      macOS:   code --wait > open -W TextEdit
      Linux:   code > gedit/kate/mousepad > xterm+nano
    """
    system = platform.system()

    if system == "Windows":
        for name in ["code", "notepad++", "notepad"]:
            path = shutil.which(name)
            if path:
                return [path], True
        return ["notepad"], True  # notepad zawsze istnieje na Windows

    if system == "Darwin":
        code = shutil.which("code")
        if code:
            return [code, "--wait"], True
        return ["open", "-W", "-a", "TextEdit"], True

    # Linux / inny Unix
    # Priorytet: GUI edytory które otwierają nowe okno
    for name in ["code", "gedit", "kate", "mousepad",
                 "xed", "pluma", "featherpad", "geany"]:
        path = shutil.which(name)
        if path:
            return [path], False  # GUI — proc.wait() nadal działa

    # Fallback: terminal + edytor tekstowy
    for term, flag in [
        ("x-terminal-emulator", "-e"),
        ("xterm",               "-e"),
        ("konsole",             "-e"),
        ("gnome-terminal",      "--"),
        ("xfce4-terminal",      "-x"),
        ("alacritty",           "-e"),
    ]:
        term_path = shutil.which(term)
        if term_path:
            for ed in ["nano", "vim", "vi", "micro", "mcedit"]:
                ed_path = shutil.which(ed)
                if ed_path:
                    return [term_path, flag, ed_path], True

    return None, False


# ── FileWatcher ───────────────────────────────────────────────────────────────

def _file_md5(path: str) -> str:
    """MD5 hash pliku — do wykrywania zmian."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return ""


class FileWatcher:
    """
    Obserwuje plik w tle (osobny wątek daemon).
    Wywołuje callback(path) przy każdej wykrytej zmianie.

    Zmiana jest wykrywana przez porównanie MD5 co `interval` sekund.
    Wątek kończy się automatycznie gdy program się zamknie (daemon=True).

    Izomorfizm z phi-space:
      FileWatcher ≡ sensor który mierzy temperaturę zewnętrznego pliku.
      Każda zmiana to 'touch' — plik staje się HOT z zewnątrz systemu.

    Użycie:
      watcher = FileWatcher("/tmp/edit.py", on_change, interval=0.5)
      watcher.start()
      # ... edytor zewnętrzny działa ...
      watcher.stop()
    """

    def __init__(self, path: str, callback: Callable[[str], None],
                 interval: float = 0.5):
        """
        path     — ścieżka obserwowanego pliku
        callback — fn(path) wywoływana przy każdej zmianie
        interval — czas między sprawdzeniami (sekundy)
        """
        self.path     = path
        self.callback = callback
        self.interval = interval
        self._stop    = threading.Event()
        self._last    = _file_md5(path)
        self._thread  = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"filewatcher-{os.path.basename(path)}"
        )

    def start(self) -> None:
        """Uruchom obserwację w tle."""
        self._thread.start()

    def stop(self) -> None:
        """Zatrzymaj obserwację."""
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            current = _file_md5(self.path)
            if current and current != self._last:
                self._last = current
                try:
                    self.callback(self.path)
                except Exception:
                    pass  # callback nie może zatrzymać watchera