#!/usr/bin/env python3
"""
karmazyn_fm.py — KarmazynOS File Manager v1.0
==============================================
Maciej Mazur, Warsaw 2026

Menedżer plików TUI (curses) zintegrowany z phi-space KarmazynOS.
Działa na Termux, NUC, Chromebook — bez SDL, bez X11.

Układ:
  ┌──────────────────┬──────────────────┐
  │   Panel lewy     │   Panel prawy    │
  │   (filesystem)   │   (fs / phi)     │
  ├──────────────────┴──────────────────┤
  │   Pasek statusu + komendy F-key     │
  └─────────────────────────────────────┘

Klawiszologia:
  Tab / ←→      przełącz panel
  ↑↓ / jk       nawigacja
  Enter          wejdź do katalogu / otwórz plik
  Space          zaznacz plik
  Backspace      katalog wyżej
  F3             podgląd (view)
  F4             edytuj (NooEdit / $EDITOR)
  F5             kopiuj
  F6             przenieś / zmień nazwę
  F7             utwórz katalog
  F8             usuń
  F10 / q        wyjście
  Ctrl+A         utwórz atom phi-space z zaznaczonego pliku
  Ctrl+P         przełącz prawy panel: fs ↔ phi-space
  Ctrl+S         zapisz/sync bubble VFS
  /              szukaj w bieżącym katalogu

Integracja phi-space:
  - Pliki .soul wyświetlane innym kolorem (BubbleVFS)
  - Prawy panel może pokazywać atomy phi-space (T, state)
  - Otwierany plik → atom touch() (rejestruje aktywność)
  - Ctrl+A → tworzy atom z pliku (S=filename, E=path, T=60)

Rejestracja w shell.py:
  reg("FM", cmd_fm, "File Manager TUI (mc-style)", category="system")
"""

import curses
import os
import shutil
import stat
import subprocess
import sys
import time
from typing import Any, List, Optional, Tuple


# ── Importy KarmazynOS (graceful) ─────────────────────────────────────────────

try:
    from karmazyn_phi import PhiSpace
    _PHI_AVAILABLE = True
except ImportError:
    _PHI_AVAILABLE = False

try:
    from karmazyn_vfs import BubbleVFS
    _VFS_AVAILABLE = True
except ImportError:
    _VFS_AVAILABLE = False

try:
    from karmazyn_syslog import SystemLog
    REGISTRY = SystemLog()
except ImportError:
    class _MinLog:
        def log(self, *a, **kw): pass
        def register(self, *a, **kw): pass
    REGISTRY = _MinLog()


# ── Stałe ─────────────────────────────────────────────────────────────────────

VERSION       = "KFM-1.0"
ATOM_T_FILE   = 60.0     # T atomu tworzonego z pliku
ATOM_T_OPEN   = 75.0     # T po otwarciu pliku (touch)
SORT_NAME     = 0
SORT_SIZE     = 1
SORT_DATE     = 2
SORT_EXT      = 3


def _atom_id(path: str) -> str:
    """
    Kanoniczny atom_id dla pliku — SHA1 pełnej ścieżki.
    [FIX] Stary format file.{name.replace('.','_')} powodował kolizje:
    /home/a/test.txt i /tmp/test.txt → ten sam atom_id!
    SHA1(path) jest unikalny per ścieżka bezwzględna.
    """
    import hashlib as _hl
    hid = _hl.sha1(os.path.abspath(path).encode()).hexdigest()[:12]
    return f"file.{hid}"


# ── Unicode width ───────────────────────────────────────────────────────────────
try:
    from wcwidth import wcswidth as _wcswidth
    def _strwidth(s: str) -> int:
        """Prawdziwa szerokość terminalowa — obsługa CJK, emoji."""
        w = _wcswidth(s)
        return w if w >= 0 else len(s)
except ImportError:
    def _strwidth(s: str) -> int:   # fallback: ASCII width
        return len(s)


# ── Kolory ────────────────────────────────────────────────────────────────────

C_NORMAL      = 1
C_DIR         = 2
C_SOUL        = 3   # .soul pliki BubbleVFS
C_MARKED      = 4   # zaznaczone pliki
C_ACTIVE      = 5   # aktywny panel (border)
C_INACTIVE    = 6   # nieaktywny panel
C_STATUS      = 7   # pasek statusu
C_HOT         = 8   # atom HOT (T>70)
C_WARM        = 9   # atom WARM
C_COLD        = 10  # atom COLD
C_HEADER      = 11  # nagłówek panelu
C_EXEC        = 12  # pliki wykonywalne
C_ERROR       = 13  # błędy


def _init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()
    bg = -1
    curses.init_pair(C_NORMAL,   curses.COLOR_WHITE,   bg)
    curses.init_pair(C_DIR,      curses.COLOR_CYAN,    bg)
    curses.init_pair(C_SOUL,     curses.COLOR_MAGENTA, bg)
    curses.init_pair(C_MARKED,   curses.COLOR_YELLOW,  bg)
    curses.init_pair(C_ACTIVE,   curses.COLOR_WHITE,   curses.COLOR_BLUE)
    curses.init_pair(C_INACTIVE, curses.COLOR_WHITE,   bg)
    curses.init_pair(C_STATUS,   curses.COLOR_BLACK,   curses.COLOR_CYAN)
    curses.init_pair(C_HOT,      curses.COLOR_RED,     bg)
    curses.init_pair(C_WARM,     curses.COLOR_YELLOW,  bg)
    curses.init_pair(C_COLD,     curses.COLOR_BLUE,    bg)
    curses.init_pair(C_HEADER,   curses.COLOR_BLACK,   curses.COLOR_CYAN)
    curses.init_pair(C_EXEC,     curses.COLOR_GREEN,   bg)
    curses.init_pair(C_ERROR,    curses.COLOR_RED,     bg)


# ─────────────────────────────────────────────────────────────────────────────
# FileEntry — jeden plik/katalog w panelu
# ─────────────────────────────────────────────────────────────────────────────

class FileEntry:
    __slots__ = ("name", "path", "is_dir", "size", "mtime",
                 "is_soul", "is_exec", "marked", "atom_T", "atom_state")

    def __init__(self, name: str, path: str):
        self.name       = name
        self.path       = path
        self.marked     = False
        self.atom_T     = None
        self.atom_state = None

        try:
            st          = os.stat(path)
            self.is_dir = stat.S_ISDIR(st.st_mode)
            self.size   = st.st_size
            self.mtime  = st.st_mtime
            self.is_exec= bool(st.st_mode & 0o111) and not self.is_dir
        except OSError:
            self.is_dir = False
            self.size   = 0
            self.mtime  = 0.0
            self.is_exec= False

        self.is_soul = name.endswith(".soul")

    def color(self) -> int:
        if self.marked:   return C_MARKED
        if self.is_dir:   return C_DIR
        if self.is_soul:  return C_SOUL
        if self.is_exec:  return C_EXEC
        if self.atom_T is not None:
            if   self.atom_T > 70: return C_HOT
            elif self.atom_T > 30: return C_WARM
            else:                  return C_COLD
        return C_NORMAL

    def size_str(self) -> str:
        if self.is_dir: return "<DIR>"
        s = self.size
        for unit in ("B","K","M","G"):
            if s < 1024: return f"{s:5.0f}{unit}"
            s /= 1024
        return f"{s:5.1f}T"

    def mtime_str(self) -> str:
        try:
            return time.strftime("%d.%m %H:%M", time.localtime(self.mtime))
        except Exception:
            return "           "


# ─────────────────────────────────────────────────────────────────────────────
# Panel — jeden panel plików
# ─────────────────────────────────────────────────────────────────────────────

class Panel:
    """Jeden panel (lewy lub prawy). Może być w trybie 'fs' lub 'phi'."""

    def __init__(self, path: str = ".", mode: str = "fs"):
        self.path     = os.path.abspath(path)
        self.mode     = mode     # "fs" lub "phi"
        self.entries: List[FileEntry] = []
        self.cursor   = 0
        self.offset   = 0
        self.sort     = SORT_NAME
        self.sort_rev = False
        self.filter   = ""
        self._phi     = None
        self.refresh()

    def set_phi(self, phi) -> None:
        self._phi = phi

    def refresh(self) -> None:
        if self.mode == "phi":
            self._load_phi()
        else:
            self._load_fs()

    def _load_fs(self) -> None:
        entries = []
        # Katalog nadrzędny
        if self.path != "/":
            parent = os.path.dirname(self.path)
            e      = FileEntry("..", parent)
            e.is_dir = True
            entries.append(e)

        MAX_ENTRIES = 5000   # lazy: powyżej tego sort tylko top
        try:
            names = os.listdir(self.path)
        except PermissionError:
            self.entries = entries
            return

        # Filtr
        if self.filter:
            names = [n for n in names if self.filter.lower() in n.lower()]

        # Lazy: ogranicz przy bardzo dużych katalogach
        is_truncated = len(names) > MAX_ENTRIES
        if is_truncated and not self.filter:
            names = names[:MAX_ENTRIES]

        for name in names:
            full = os.path.join(self.path, name)
            entries.append(FileEntry(name, full))

        # Wzbogać o informacje phi-space jeśli dostępne
        if self._phi:
            self._enrich_phi(entries)

        # Sortowanie: katalogi pierwsze
        dirs  = [e for e in entries if e.is_dir  and e.name != ".."]
        files = [e for e in entries if not e.is_dir]
        dotdot= [e for e in entries if e.name == ".."]

        key_fn = {
            SORT_NAME: lambda e: e.name.lower(),
            SORT_SIZE: lambda e: e.size,
            SORT_DATE: lambda e: e.mtime,
            SORT_EXT:  lambda e: os.path.splitext(e.name)[1].lower(),
        }.get(self.sort, lambda e: e.name.lower())

        dirs.sort( key=key_fn, reverse=self.sort_rev)
        files.sort(key=key_fn, reverse=self.sort_rev)

        self.entries = dotdot + dirs + files
        if is_truncated:
            trunc_e           = FileEntry.__new__(FileEntry)
            trunc_e.name      = f'... (ograniczono do {MAX_ENTRIES} wpisów)'
            trunc_e.path      = self.path
            trunc_e.is_dir    = False
            trunc_e.is_soul   = False
            trunc_e.is_exec   = False
            trunc_e.marked    = False
            trunc_e.size      = 0
            trunc_e.mtime     = 0.0
            trunc_e.atom_T    = None
            trunc_e.atom_state= None
            self.entries.append(trunc_e)
        self._clamp_cursor()

    def _load_phi(self) -> None:
        """Tryb phi — pokaż atomy phi-space jako wpisy."""
        entries = []
        if self._phi is None:
            self.entries = entries
            return
        try:
            atoms = self._phi.matrix.atoms()
        except Exception:
            self.entries = entries
            return

        for a in atoms:
            T     = float(getattr(a, "T",     0))
            state = str(getattr(a,  "state",  "?"))
            name  = str(getattr(a,  "id",     "?"))
            S     = str(getattr(a,  "S",      ""))
            path  = str(getattr(a,  "E",      ""))

            e         = FileEntry.__new__(FileEntry)
            e.name    = name
            e.path    = path or name
            e.is_dir  = False
            e.is_soul = False
            e.is_exec = False
            e.marked  = False
            e.size    = 0
            e.mtime   = 0.0
            e.atom_T  = T
            e.atom_state = state
            entries.append(e)

        if self.filter:
            entries = [e for e in entries if self.filter.lower() in e.name.lower()]
        # [FIX] filtr działa też w trybie phi
        # Sortuj po T malejąco (gorące na górze)
        entries.sort(key=lambda e: (-(e.atom_T or 0), e.name))  # [FIX] stabilny
        self.entries = entries
        self._clamp_cursor()

    def _enrich_phi(self, entries: List[FileEntry]) -> None:
        """Dodaj dane phi-space do wpisów fs."""
        if not self._phi: return
        try:
            # [FIX] indeksuj po atom_id (SHA1 path) — nie po nazwie
            atoms = {str(getattr(a,"id","")): a
                     for a in self._phi.matrix.atoms()}
        except Exception:
            return
        for e in entries:
            key = _atom_id(e.path)   # SHA1 pełnej ścieżki
            if key in atoms:
                a            = atoms[key]
                e.atom_T     = float(getattr(a, "T",     0))
                e.atom_state = str(getattr(a,   "state", ""))

    def _clamp_cursor(self) -> None:
        n = len(self.entries)
        if n == 0:
            self.cursor = self.offset = 0
            return
        self.cursor = max(0, min(self.cursor, n - 1))

    def move(self, delta: int) -> None:
        self.cursor = max(0, min(self.cursor + delta, len(self.entries) - 1))

    def current(self) -> Optional[FileEntry]:
        if not self.entries or self.cursor >= len(self.entries):
            return None
        return self.entries[self.cursor]

    def marked_entries(self) -> List[FileEntry]:
        return [e for e in self.entries if e.marked]

    def toggle_mark(self) -> None:
        e = self.current()
        if e and e.name != "..":
            e.marked = not e.marked
            self.move(1)

    def cd(self, path: str) -> bool:
        path = os.path.abspath(path)
        if os.path.isdir(path):
            self.path   = path
            self.cursor = 0
            self.offset = 0
            self.filter = ""
            for e in self.entries: e.marked = False  # [FIX]
            self.refresh()
            return True
        return False

    def toggle_sort(self) -> None:
        self.sort = (self.sort + 1) % 4
        self.refresh()

    def toggle_phi_mode(self) -> None:
        self.mode = "phi" if self.mode == "fs" else "fs"
        self.cursor = 0
        self.offset = 0
        self.refresh()


# ─────────────────────────────────────────────────────────────────────────────
# Renderer — rysuje UI przez curses
# ─────────────────────────────────────────────────────────────────────────────

class Renderer:

    def __init__(self, scr):
        self.scr  = scr
        self.h, self.w = scr.getmaxyx()

    def resize(self) -> None:
        self.h, self.w = self.scr.getmaxyx()

    def draw(self, left: Panel, right: Panel,
             active: int, status: str, cmdline: str) -> None:
        self.scr.erase()
        self.h, self.w = self.scr.getmaxyx()
        mid = self.w // 2

        self._draw_panel(left,  0,     mid,          active == 0)
        self._draw_panel(right, mid+1, self.w-mid-1, active == 1)
        self._draw_divider(mid)
        self._draw_fkeys(self.h - 2)
        self._draw_status(self.h - 1, status, cmdline)
        self.scr.refresh()

    def _draw_panel(self, panel: Panel, x: int, w: int, is_active: bool) -> None:
        h          = self.h - 2  # minus fkeys i status
        border_col = curses.color_pair(C_ACTIVE) if is_active else curses.color_pair(C_INACTIVE)
        head_col   = curses.color_pair(C_HEADER)

        # Nagłówek
        mode_tag = "[PHI]" if panel.mode == "phi" else ""
        title    = f" {panel.path} {mode_tag}"
        if len(title) > w - 2: title = "…" + title[-(w-3):]
        self._put(0, x, title.ljust(w), head_col)

        # Kolumny: name  size  date
        col_date = 11
        col_size = 6
        col_name = max(4, w - col_size - col_date - 2)

        header = (f"{'Nazwa':<{col_name}} {'Rozmiar':>{col_size}} {'Data':>{col_date}}")
        self._put(1, x, header[:w].ljust(w), head_col | curses.A_BOLD)

        # Dostosuj offset do kursora
        visible = max(1, h - 3)  # [FIX] guard: h<3 dawało crash
        if h < 4: return          # za małe okno
        if panel.cursor < panel.offset:
            panel.offset = panel.cursor
        elif panel.cursor >= panel.offset + visible:
            panel.offset = panel.cursor - visible + 1

        # Wpisy
        for row, idx in enumerate(range(panel.offset,
                                        min(panel.offset + visible,
                                            len(panel.entries)))):
            e      = panel.entries[idx]
            is_cur = (idx == panel.cursor)
            col    = curses.color_pair(e.color())

            if is_active and is_cur:
                col = col | curses.A_REVERSE

            # Nazwa
            name = e.name
            if e.is_dir and e.name != "..":
                name = "/" + name

            if panel.mode == "phi" and e.atom_T is not None:
                # W trybie phi: pokaż T i state
                t_str   = f"T={e.atom_T:5.1f}"
                st_str  = (e.atom_state or "")[:4]
                s_str   = f"{t_str} {st_str}"
                col_phi = w - len(s_str) - 1
                name_w  = max(1, col_phi - 1)
                line    = f"{name[:name_w]:<{name_w}} {s_str}"
            else:
                name_w  = col_name
                sz_str  = e.size_str()
                dt_str  = e.mtime_str()
                line    = f"{name[:name_w]:<{name_w}} {sz_str:>{col_size}} {dt_str:>{col_date}}"

            self._put(row + 2, x, line[:w].ljust(w), col)

        # Scrollbar
        if len(panel.entries) > visible and visible > 2:
            sb_h   = max(1, visible * visible // max(1, len(panel.entries)))
            sb_pos = (panel.offset * (visible - sb_h)) // max(1, len(panel.entries) - visible)
            for r in range(visible):
                ch = "█" if sb_pos <= r < sb_pos + sb_h else "│"
                try:
                    if x + w - 1 < self.w:
                        self.scr.addch(r + 2, x + w - 1,
                                       ch, curses.color_pair(C_INACTIVE))
                except curses.error:
                    pass

        # Ramka dolna z info
        if h - 1 >= 2:
            n_marked = sum(1 for e in panel.entries if e.marked)
            info = (f" {len(panel.entries)} wpisów"
                    + (f" [{n_marked} zaznaczonych]" if n_marked else ""))
            self._put(h - 1, x, info[:w].ljust(w), border_col)

    def _draw_divider(self, x: int) -> None:
        col = curses.color_pair(C_INACTIVE)
        for y in range(self.h - 2):
            try:
                self.scr.addch(y, x, "│", col)
            except curses.error:
                pass

    def _draw_fkeys(self, y: int) -> None:
        fkeys = [
            ("F3", "Podgląd"), ("F4", "Edytuj"), ("F5", "Kopiuj"),
            ("F6", "Przenieś"), ("F7", "MkDir"), ("F8", "Usuń"),
            ("^A", "Atom"), ("^P", "Phi"), ("F10", "Wyjście"),
        ]
        col_key  = curses.color_pair(C_ACTIVE)   | curses.A_BOLD
        col_desc = curses.color_pair(C_STATUS)
        x = 0
        for key, desc in fkeys:
            if x >= self.w: break
            key_str  = key
            desc_str = desc + " "
            try:
                self.scr.addstr(y, x, key_str,  col_key)
                x += len(key_str)
                self.scr.addstr(y, x, desc_str, col_desc)
                x += len(desc_str)
            except curses.error:
                break

    def _draw_status(self, y: int, status: str, cmdline: str) -> None:
        col = curses.color_pair(C_STATUS)
        if cmdline:
            line = f"/{cmdline}"
        else:
            e = status
            line = e if e else " KarmazynOS FM " + VERSION
        try:
            _w = max(1, self.w-1)
            self.scr.addstr(y, 0, line[:_w].ljust(_w), col)  # [FIX] w==0
        except curses.error:
            pass

    def _put(self, y: int, x: int, text: str, attr: int) -> None:
        try:
            self.scr.addstr(y, x, text, attr)
        except curses.error:
            pass

    def dialog(self, prompt: str, default: str = "") -> Optional[str]:
        """Prosty dialog wejścia w dolnej części ekranu."""
        h, w = self.scr.getmaxyx()
        y    = h // 2
        x    = w // 4
        dw   = w // 2
        col  = curses.color_pair(C_HEADER) | curses.A_BOLD

        # Ramka
        try:
            self.scr.addstr(y-1, x, "┌" + "─"*(dw-2) + "┐", col)
            self.scr.addstr(y,   x, f"│ {prompt[:dw-4]:<{dw-4}} │", col)
            self.scr.addstr(y+1, x, f"│ {default[:dw-4]:<{dw-4}} │", col)
            self.scr.addstr(y+2, x, "└" + "─"*(dw-2) + "┘", col)
        except curses.error:
            pass
        self.scr.refresh()

        # Wejście
        curses.echo()
        curses.curs_set(1)
        try:
            read_w = max(1, dw - 4)   # [FIX] guard: dw<=4
            self.scr.move(y+1, x+2)
            buf = self.scr.getstr(read_w).decode("utf-8", errors="replace")
            return buf.strip() or default or None
        except Exception:
            return None
        finally:
            curses.noecho()
            curses.curs_set(0)

    def confirm(self, msg: str) -> bool:
        """Tak/Nie dialog."""
        h, w = self.scr.getmaxyx()
        y    = h // 2
        col  = curses.color_pair(C_ERROR) | curses.A_BOLD
        line = f" {msg} [T/N] "
        try:
            self.scr.addstr(y, max(0, (w - len(line))//2), line, col)
        except curses.error:
            pass
        self.scr.refresh()
        while True:
            ch = self.scr.getch()
            if ch in (ord("t"), ord("T"), ord("y"), ord("Y")): return True
            if ch in (ord("n"), ord("N"), 27, ord("q")):       return False

    def show_text(self, title: str, lines: List[str]) -> None:
        """Podgląd tekstu (F3)."""
        h, w = self.scr.getmaxyx()
        offset = 0
        col    = curses.color_pair(C_NORMAL)
        head   = curses.color_pair(C_HEADER) | curses.A_BOLD
        while True:
            self.scr.erase()
            self._put(0, 0, f" {title[:w-4]} — q=wyjście ↑↓ PgUp/Dn ".ljust(w), head)
            for row in range(1, h-1):
                idx = offset + row - 1
                if idx < len(lines):
                    self._put(row, 0, lines[idx][:w-1].ljust(w-1), col)
            self._put(h-1, 0,
                      f" Linia {offset+1}/{len(lines)} ".ljust(w),
                      curses.color_pair(C_STATUS))
            self.scr.refresh()
            ch = self.scr.getch()
            if ch in (ord("q"), ord("Q"), 27, curses.KEY_F10): break
            elif ch == curses.KEY_UP:    offset = max(0, offset - 1)
            elif ch == curses.KEY_DOWN:  offset = min(max(0, len(lines)-h+2), offset+1)
            elif ch == curses.KEY_PPAGE: offset = max(0, offset - (h-2))
            elif ch == curses.KEY_NPAGE: offset = min(max(0, len(lines)-h+2), offset+(h-2))
            elif ch == curses.KEY_HOME:  offset = 0
            elif ch == curses.KEY_END:   offset = max(0, len(lines)-h+2)


# ─────────────────────────────────────────────────────────────────────────────
# FM — główna klasa menedżera plików
# ─────────────────────────────────────────────────────────────────────────────

class FM:
    """
    KarmazynOS File Manager.

    Użycie:
        fm = FM(phi=RUNTIME, bubbles=BUBBLES)
        fm.run()
    """

    def __init__(self,
                 phi:     Any = None,
                 bubbles: Any = None,
                 start:   str = "."):
        self.phi     = phi
        self.bubbles = bubbles
        self.left    = Panel(start)
        self.right   = Panel(os.path.expanduser("~"))
        self.left.set_phi(phi)
        self.right.set_phi(phi)
        self.active  = 0      # 0=lewy, 1=prawy
        self.status  = ""
        self.cmdline = ""     # szukanie
        self._searching = False

    @property
    def _cur_panel(self) -> Panel:
        return self.left if self.active == 0 else self.right

    @property
    def _other_panel(self) -> Panel:
        return self.right if self.active == 0 else self.left

    # ── Główna pętla ──────────────────────────────────────────────────────────

    def run(self) -> None:
        curses.wrapper(self._main)

    def emit(self, event: str, data: dict = None) -> None:
        """
        Prosty event bus — log zdarzenia FM do REGISTRY.
        Przyszłość: scheduler, AI, GUI mogą subskrybować.
        emit('file.open', {'path': ..., 'atom_id': ...})
        emit('atom.touch', {'id': ..., 'T': ...})
        emit('bubble.sync', {'count': ...})
        """
        try:
            REGISTRY.log("EVENT", str(data or {}), service=f"fm.{event}")
        except Exception:
            pass

    def _main(self, scr) -> None:
        curses.curs_set(0)
        curses.noecho()
        scr.keypad(True)
        _init_colors()
        rnd = Renderer(scr)

        self.left.refresh()
        self.right.refresh()

        while True:
            rnd.draw(self.left, self.right, self.active,
                     self.status, self.cmdline)
            self.status = ""

            try:
                ch = scr.getch()
            except KeyboardInterrupt:
                break
            if ch == -1: continue  # [FIX] ERR przy timeout — ignoruj

            if self._searching:
                if ch in (27, curses.KEY_F3):       # ESC — anuluj szukanie
                    self._searching = False
                    self.cmdline    = ""
                    self._cur_panel.filter = ""
                    self._cur_panel.refresh()
                elif ch in (10, 13):                # Enter — zatwierdź
                    self._searching = False
                    self.cmdline    = ""
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    self.cmdline    = self.cmdline[:-1]
                    self._cur_panel.filter = self.cmdline
                    self._cur_panel.refresh()
                elif 32 <= ch < 127:
                    self.cmdline   += chr(ch)
                    self._cur_panel.filter = self.cmdline
                    self._cur_panel.refresh()
                continue

            # ── Nawigacja ─────────────────────────────────────────────────────
            if ch == curses.KEY_UP   or ch == ord("k"): self._cur_panel.move(-1)
            elif ch == curses.KEY_DOWN or ch == ord("j"): self._cur_panel.move(1)
            elif ch == curses.KEY_PPAGE: self._cur_panel.move(-10)
            elif ch == curses.KEY_NPAGE: self._cur_panel.move(10)
            elif ch == curses.KEY_HOME:  self._cur_panel.cursor = 0
            elif ch == curses.KEY_END:
                self._cur_panel.cursor = max(0, len(self._cur_panel.entries)-1)

            # ── Przełączenie panelu ───────────────────────────────────────────
            elif ch == ord("\t") or ch == curses.KEY_LEFT or ch == curses.KEY_RIGHT:
                self.active = 1 - self.active

            # ── Wejście / otwieranie ──────────────────────────────────────────
            elif ch in (10, 13, curses.KEY_ENTER):
                self._action_enter(rnd, scr)

            # ── Katalog wyżej ─────────────────────────────────────────────────
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if self._cur_panel.mode == "fs":
                    parent = os.path.dirname(self._cur_panel.path)
                    self._cur_panel.cd(parent)

            # ── Zaznaczanie ───────────────────────────────────────────────────
            elif ch == ord(" "):
                self._cur_panel.toggle_mark()

            # ── F-keys ────────────────────────────────────────────────────────
            elif ch == curses.KEY_F3:    self._action_view(rnd)
            elif ch == curses.KEY_F4:    self._action_edit(scr)
            elif ch == curses.KEY_F5:    self._action_copy(rnd)
            elif ch == curses.KEY_F6:    self._action_move(rnd)
            elif ch == curses.KEY_F7:    self._action_mkdir(rnd)
            elif ch == curses.KEY_F8:    self._action_delete(rnd)
            elif ch == curses.KEY_F10:   break
            elif ch == ord("q"):         break

            # ── Ctrl kombinacje ───────────────────────────────────────────────
            elif ch == 1:   # Ctrl+A — utwórz atom
                self._action_create_atom(rnd)
            elif ch == 16:  # Ctrl+P — przełącz phi mode
                self._cur_panel.toggle_phi_mode()
                mode = "phi-space" if self._cur_panel.mode == "phi" else "filesystem"
                self.status = f"Panel: tryb {mode}"
            elif ch == 19:  # Ctrl+S — zapisz/sync
                self._action_sync(rnd)
            elif ch == ord("r"):         # odśwież
                self.left.refresh()
                self.right.refresh()
            elif ch == ord("s"):         # zmień sortowanie
                self._cur_panel.toggle_sort()
                sort_names = ["nazwa", "rozmiar", "data", "rozszerzenie"]
                self.status = f"Sortowanie: {sort_names[self._cur_panel.sort]}"

            # ── Szukanie ──────────────────────────────────────────────────────
            elif ch == ord("/"):
                self._searching = True
                self.cmdline    = ""

            # ── Resize ────────────────────────────────────────────────────────
            elif ch == curses.KEY_RESIZE:
                rnd.resize()
                for p in (self.left, self.right):
                    p._clamp_cursor(); p.offset = 0  # [FIX] reset offset

    # ── Akcje ─────────────────────────────────────────────────────────────────

    def _action_enter(self, rnd: Renderer, scr) -> None:
        e = self._cur_panel.current()
        if not e: return

        if self._cur_panel.mode == "phi":
            # W trybie phi — pokaż info o atomie
            if e.atom_T is not None:
                info = [
                    f"Atom:  {e.name}",
                    f"T:     {e.atom_T:.2f}",
                    f"State: {e.atom_state}",
                    f"S:     {e.path}",
                ]
                rnd.show_text(f"Atom: {e.name}", info)
            return

        if e.is_dir:
            self._cur_panel.cd(e.path)
        else:
            # Otwórz plik — touch atom w phi-space
            self._touch_atom(e)
            self._action_view(rnd)

    def _action_view(self, rnd: Renderer) -> None:
        e = self._cur_panel.current()
        if not e or e.is_dir: return
        MAX_PREVIEW = 512 * 1024   # 512 KB — większe pliki obcinaj
        try:
            with open(e.path, encoding="utf-8", errors="replace") as f:
                content = f.read(MAX_PREVIEW)
            truncated = os.path.getsize(e.path) > MAX_PREVIEW
            if e.is_soul:
                import json as _j
                pretty = []
                for rl in content.splitlines():
                    if not rl.strip(): continue
                    try: pretty.extend(_j.dumps(_j.loads(rl), ensure_ascii=False, indent=2).splitlines()); pretty.append('─'*40)
                    except: pretty.append(rl)
                lines = pretty or ['(pusty .soul)']
            else:
                lines = content.splitlines()
                if not lines: lines = ['(pusty plik)']
            if truncated:
                lines.append("")
                lines.append(f"--- OBCIĘTO (plik > {MAX_PREVIEW//1024}KB) ---")
            rnd.show_text(e.name, lines)
            self._touch_atom(e)
        except Exception as ex:
            self.status = f"Błąd odczytu: {ex}"

    def _action_edit(self, scr) -> None:
        e = self._cur_panel.current()
        if not e or e.is_dir: return

        # Spróbuj NooEdit → EDITOR → nano → vi
        editors = []
        try:
            from Nooedit import cmd_nooedit
            editors.append(("nooedit", lambda: cmd_nooedit([e.path], runtime=self.phi)))
        except ImportError:
            pass

        ext_editor = os.environ.get("EDITOR", "")
        if ext_editor:
            editors.append((ext_editor, lambda ed=ext_editor: subprocess.call([ed, e.path])))
        for fallback in ("nano", "vi", "vim"):
            editors.append((fallback, lambda ed=fallback: subprocess.call([ed, e.path])))

        name, fn = editors[0]
        curses.def_prog_mode()   # zapamiętaj tryb curses
        curses.endwin()          # oddaj terminal edytorowi
        try:
            fn()
        except Exception:
            pass
        finally:
            curses.reset_prog_mode()  # [FIX] przywróć tryb curses
            scr.clear()
            scr.refresh()
            self._cur_panel.refresh()
            self._touch_atom(e)

    def _action_copy(self, rnd: Renderer) -> None:
        sources = self._cur_panel.marked_entries()
        if not sources:
            e = self._cur_panel.current()
            if e and e.name != "..":
                sources = [e]
        if not sources: return

        dest = rnd.dialog("Kopiuj do:", self._other_panel.path)
        if not dest: return

        count = errors = 0
        for e in sources:
            try:
                dst = os.path.join(dest, e.name)
                if e.is_dir:
                    try:
                        shutil.copytree(e.path, dst, dirs_exist_ok=True)
                    except TypeError:  # Python < 3.8
                        if os.path.exists(dst): shutil.rmtree(dst)
                        shutil.copytree(e.path, dst)
                else:
                    shutil.copy2(e.path, dst)
                count += 1
            except Exception as ex:
                errors += 1
                self.status = f"Błąd: {ex}"

        self.status = f"Skopiowano: {count}" + (f" (błędów: {errors})" if errors else "")
        self.left.refresh()
        self.right.refresh()

    def _action_move(self, rnd: Renderer) -> None:
        sources = self._cur_panel.marked_entries()
        if not sources:
            e = self._cur_panel.current()
            if e and e.name != "..":
                sources = [e]
        if not sources: return

        if len(sources) == 1:
            dest = rnd.dialog("Nowa nazwa / katalog docelowy:", sources[0].path)
        else:
            dest = rnd.dialog("Przenieś do:", self._other_panel.path)
        if not dest: return

        count = errors = 0
        for e in sources:
            try:
                if len(sources) == 1 and not os.path.isdir(dest):
                    shutil.move(e.path, dest)
                else:
                    shutil.move(e.path, os.path.join(dest, e.name))
                count += 1
            except Exception as ex:
                errors += 1
                self.status = f"Błąd: {ex}"

        self.status = f"Przeniesiono: {count}" + (f" (błędów: {errors})" if errors else "")
        self.left.refresh()
        self.right.refresh()

    def _action_mkdir(self, rnd: Renderer) -> None:
        name = rnd.dialog("Nowy katalog:", "")
        if not name: return
        path = os.path.join(self._cur_panel.path, name)
        try:
            os.makedirs(path, exist_ok=True)
            self.status = f"Utworzono: {path}"
            self._cur_panel.refresh()
        except Exception as ex:
            self.status = f"Błąd: {ex}"

    def _action_delete(self, rnd: Renderer) -> None:
        sources = self._cur_panel.marked_entries()
        if not sources:
            e = self._cur_panel.current()
            if e and e.name != "..":
                sources = [e]
        if not sources: return

        names = ", ".join(e.name for e in sources[:3])
        if len(sources) > 3: names += f" + {len(sources)-3} więcej"

        if not rnd.confirm(f"Usuń: {names}?"):
            return

        count = errors = 0
        for e in sources:
            try:
                if os.path.islink(e.path):
                    os.unlink(e.path)   # [FIX] symlink→dir: rmtree usuwa cel!
                elif e.is_dir:
                    shutil.rmtree(e.path)
                else:
                    os.remove(e.path)
                count += 1
            except Exception as ex:
                errors += 1
                self.status = f"Błąd: {ex}"

        self.status = f"Usunięto: {count}" + (f" (błędów: {errors})" if errors else "")
        self.left.refresh()
        self.right.refresh()

    def _action_create_atom(self, rnd: Renderer) -> None:
        """Ctrl+A — utwórz atom phi-space z zaznaczonego pliku."""
        if not self.phi:
            self.status = "Brak phi-space."
            return
        e = self._cur_panel.current()
        if not e or e.name == "..": return

        atom_id = _atom_id(e.path)
        try:
            existing = self.phi.get_atom(atom_id)
            if existing:
                existing.T = min(getattr(existing,"T_max",100.0),
                                 float(existing.T) + 10)
                try: existing.touch()
                except Exception: pass
                self.status = f"Atom zaktualizowany: {atom_id} T={existing.T:.1f}"
            else:
                a = self.phi.create_atom(
                    atom_id,
                    S=e.name,
                    E=e.path,
                    T=ATOM_T_FILE)
                self.status = f"Atom utworzony: {atom_id} T={ATOM_T_FILE}"
            REGISTRY.log("INFO", f"FM atom: {atom_id}", service="fm")
            self.left.refresh()
            self.right.refresh()
        except Exception as ex:
            self.status = f"Błąd atom: {ex}"

    def _action_sync(self, rnd: Renderer) -> None:
        """Ctrl+S — sync BubbleVFS."""
        if not self.bubbles:
            self.status = "Brak BubbleVFS."
            return
        try:
            bubbles = self.bubbles.list_bubbles()
            self.status = f"BubbleVFS: {len(bubbles)} bąbli aktywnych"
        except Exception as ex:
            self.status = f"Sync błąd: {ex}"

    def _touch_atom(self, e: FileEntry) -> None:
        """Rejestruj dostęp do pliku jako touch() na atomie phi-space."""
        if not self.phi or not e: return
        atom_id = _atom_id(e.path)
        try:
            a = self.phi.get_atom(atom_id)
            if a:
                a.T = min(float(getattr(a,"T_max",100.0)), ATOM_T_OPEN)
                try: a.touch()
                except Exception: pass
                self.emit("atom.touch",
                          {"id": atom_id, "T": a.T, "path": e.path})
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Komenda shella
# ─────────────────────────────────────────────────────────────────────────────

def cmd_fm(args, runtime=None, bubbles=None, **_kw) -> str:
    """
    FM [ścieżka]   — uruchom menedżer plików
    FM .           — bieżący katalog
    FM ~           — katalog domowy
    """
    start = args[0] if args else os.getcwd()
    start = os.path.expanduser(start)
    if not os.path.isdir(start):
        return f"Brak katalogu: {start}"

    fm = FM(phi=runtime, bubbles=bubbles, start=start)
    try:
        fm.run()
    except Exception as e:
        return f"FM błąd: {e}"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Punkt wejścia
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="KarmazynOS File Manager")
    ap.add_argument("path", nargs="?", default=os.getcwd(),
                    help="Katalog startowy")
    opt = ap.parse_args()

    phi     = None
    bubbles = None

    if _PHI_AVAILABLE:
        try:
            phi = PhiSpace()
        except Exception:
            pass
    if _VFS_AVAILABLE:
        try:
            bubbles = BubbleVFS()
        except Exception:
            pass

    fm = FM(phi=phi, bubbles=bubbles, start=opt.path)
    fm.run()