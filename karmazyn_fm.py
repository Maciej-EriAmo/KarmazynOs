#!/usr/bin/env python3
"""
karmazyn_fm.py — KarmazynOS File Manager v2.7 (Fix #8)
=======================================================
Menedżer plików TUI z wieloma ontologiami (fs, phi, bbl) oraz wyszukiwaniem semantycznym.
Skrót Ctrl+F otwiera okno wyszukiwania i przełącza panel w tryb SEARCH.

Poprawki v2.7:
  - Fix #8: import_files_to_bubble() używa peek_atom() aby uniknąć podwójnego
    podgrzewania atomów przy sprawdzaniu istnienia (get_atom → touch).
  - artefakty przy tworzeniu plików/katalogów – wymuszony synchroniczny refresh
  - tworzenie bąbla możliwe tylko w trybie BBL, komunikat gdy zły tryb
  - import plików do bąbla – walidacja trybów źródła i celu, czytelny komunikat
  - bezpieczeństwo wątkowe (lock w Panel), metadane odświeżane w pętli głównej
  - Enter w filtrze nie otwiera pliku, Esc czyści filtr
  - FIX: PhiAtomCache nie wymaga już _atoms_dict (działa z każdą implementacją phi)
  - FIX: PhiEntry.delete bezpieczniej wywołuje usunięcie atomu
"""

import curses
import os
import shutil
import stat
import subprocess
import sys
import time
import threading
import queue
from typing import Any, List, Optional, Tuple, Dict
from abc import ABC, abstractmethod

# ── Importy KarmazynOS ─────────────────────────────────────────────────────────
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
VERSION       = "KFM-2.7"
ATOM_T_FILE   = 60.0
ATOM_T_OPEN   = 75.0
SORT_NAME     = 0
SORT_SIZE     = 1
SORT_DATE     = 2
SORT_EXT      = 3

MODE_FS       = "fs"
MODE_PHI      = "phi"
MODE_BBL      = "bbl"
MODE_SEARCH   = "search"

CACHE_REFRESH = 5.0

def _atom_id(path: str) -> str:
    import hashlib as _hl
    hid = _hl.sha1(os.path.abspath(path).encode()).hexdigest()[:12]
    return f"file.{hid}"

# ── Unicode width ───────────────────────────────────────────────────────────
try:
    from wcwidth import wcswidth as _wcswidth
    def _strwidth(s: str) -> int:
        w = _wcswidth(s)
        return w if w >= 0 else len(s)
except ImportError:
    def _strwidth(s: str) -> int:
        return len(s)

# ── Kolory ────────────────────────────────────────────────────────────────────
C_NORMAL      = 1
C_DIR         = 2
C_SOUL        = 3
C_MARKED      = 4
C_ACTIVE      = 5
C_INACTIVE    = 6
C_STATUS      = 7
C_HOT         = 8
C_WARM        = 9
C_COLD        = 10
C_HEADER      = 11
C_EXEC        = 12
C_ERROR       = 13

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

# ── Model danych ────────────────────────────────────────────────────────────
class Entry(ABC):
    __slots__ = ("marked",)
    def __init__(self): self.marked = False
    @abstractmethod
    def name(self) -> str: pass
    @abstractmethod
    def path(self) -> str: pass
    @abstractmethod
    def is_dir(self) -> bool: pass
    @abstractmethod
    def size_str(self) -> str: pass
    @abstractmethod
    def mtime_str(self) -> str: pass
    @abstractmethod
    def color(self) -> int: pass
    @abstractmethod
    def open(self, fm: "FM", rnd: "Renderer") -> None: pass
    @abstractmethod
    def delete(self, fm: "FM", rnd: "Renderer") -> bool: pass

class FsEntry(Entry):
    __slots__ = ("_name", "_path", "_is_dir", "_size", "_mtime", "_is_exec", "_is_soul", "atom_T", "atom_state")
    def __init__(self, name: str, path: str):
        super().__init__()
        self._name = name
        self._path = path
        self.atom_T = None
        self.atom_state = None
        try:
            st = os.stat(path)
            self._is_dir = stat.S_ISDIR(st.st_mode)
            self._size = st.st_size
            self._mtime = st.st_mtime
            self._is_exec = bool(st.st_mode & 0o111) and not self._is_dir
        except OSError:
            self._is_dir = False
            self._size = 0
            self._mtime = 0.0
            self._is_exec = False
        self._is_soul = name.endswith(".soul")
    def name(self) -> str: return self._name
    def path(self) -> str: return self._path
    def is_dir(self) -> bool: return self._is_dir
    def size_str(self) -> str:
        if self._is_dir: return "<DIR>"
        s = self._size
        for unit in ("B","K","M","G"):
            if s < 1024: return f"{s:5.0f}{unit}"
            s /= 1024
        return f"{s:5.1f}T"
    def mtime_str(self) -> str:
        try: return time.strftime("%d.%m %H:%M", time.localtime(self._mtime))
        except: return "           "
    def color(self) -> int:
        if self.marked: return C_MARKED
        if self._is_dir: return C_DIR
        if self._is_soul: return C_SOUL
        if self._is_exec: return C_EXEC
        return C_NORMAL
    def open(self, fm: "FM", rnd: "Renderer") -> None:
        if self._is_dir: fm._cur_panel.cd(self._path)
        else:
            fm._touch_atom(self._path)
            fm._action_view_file(self._path, rnd)
    def delete(self, fm: "FM", rnd: "Renderer") -> bool:
        try:
            if os.path.islink(self._path): os.unlink(self._path)
            elif self._is_dir: shutil.rmtree(self._path)
            else: os.remove(self._path)
            return True
        except Exception as e:
            fm.status = f"Błąd usuwania: {e}"
            return False

class PhiEntry(Entry):
    __slots__ = ("_id", "_T", "_state", "_S", "_E", "_similarity")
    def __init__(self, atom_id: str, T: float, state: str, S: str, E: str, similarity: float = 0.0):
        super().__init__()
        self._id = atom_id
        self._T = T
        self._state = state
        self._S = S
        self._E = E
        self._similarity = similarity
    def name(self) -> str: return self._id
    def path(self) -> str: return self._E or self._id
    def is_dir(self) -> bool: return False
    def size_str(self) -> str: return f"{self._similarity:.2f}" if self._similarity else ""
    def mtime_str(self) -> str: return ""
    def color(self) -> int:
        if self.marked: return C_MARKED
        if self._T > 70: return C_HOT
        if self._T > 30: return C_WARM
        return C_COLD
    def open(self, fm: "FM", rnd: "Renderer") -> None:
        info = [f"Atom: {self._id}", f"T: {self._T:.2f}", f"State: {self._state}", f"S: {self._S}", f"E: {self._E}"]
        rnd.show_text(f"Atom: {self._id}", info)
    def delete(self, fm: "FM", rnd: "Renderer") -> bool:
        if fm.phi:
            try:
                if hasattr(fm.phi, 'delete_atom'):
                    fm.phi.delete_atom(self._id)
                elif hasattr(fm.phi, 'matrix') and hasattr(fm.phi.matrix, 'delete'):
                    fm.phi.matrix.delete(self._id)
                return True
            except Exception as e:
                fm.status = f"Błąd usuwania atomu: {e}"
        return False

class BubbleEntry(Entry):
    __slots__ = ("_name", "_bid", "_atom_count", "_size")
    def __init__(self, name: str, bid: str, atom_count: int, size: int):
        super().__init__()
        self._name = name
        self._bid = bid
        self._atom_count = atom_count
        self._size = size
    def name(self) -> str: return self._name
    def path(self) -> str: return self._bid
    def is_dir(self) -> bool: return True
    def size_str(self) -> str: return f"{self._atom_count} at"
    def mtime_str(self) -> str: return ""
    def color(self) -> int:
        if self.marked: return C_MARKED
        return C_DIR
    def open(self, fm: "FM", rnd: "Renderer") -> None:
        fm._cur_panel.current_bubble_id = self._bid
        fm._cur_panel.cursor = fm._cur_panel.offset = 0
        fm._cur_panel.refresh()
    def delete(self, fm: "FM", rnd: "Renderer") -> bool:
        if fm.bubbles:
            try:
                fm.bubbles.delete_bubble(self._bid)
                return True
            except Exception as e:
                fm.status = f"Błąd usuwania bąbla: {e}"
        return False

# ── PhiAtomCache (bezpieczna dla każdej implementacji phi) ──────────────────
class PhiAtomCache:
    def __init__(self, phi):
        self.phi = phi
        self._cache: Dict[str, Tuple[float, str, str, str]] = {}
        self._last_version = -1

    def _get_atoms(self):
        if hasattr(self.phi, 'get_all_atoms'):
            return self.phi.get_all_atoms()
        if hasattr(self.phi, '_atoms_dict'):
            return list(self.phi._atoms_dict.values())
        if hasattr(self.phi, 'matrix') and hasattr(self.phi.matrix, 'atoms'):
            return self.phi.matrix.atoms()
        return []

    def refresh(self, force=False):
        current_version = getattr(self.phi, '_cache_version', 0)
        if force or current_version != self._last_version:
            new_cache = {}
            for atom in self._get_atoms():
                aid = str(getattr(atom, 'id', id(atom)))
                new_cache[aid] = (
                    float(getattr(atom, "T", 0)),
                    str(getattr(atom, "state", "WARM")),
                    str(getattr(atom, "S", "")),
                    str(getattr(atom, "E", ""))
                )
            self._cache = new_cache
            self._last_version = current_version

    def get(self, atom_id: str):
        return self._cache.get(atom_id)

    def get_all(self):
        return list(self._cache.items())

# ── Panel ────────────────────────────────────────────────────────────────────
class Panel:
    def __init__(self, path: str = ".", mode: str = MODE_FS):
        self.path = os.path.abspath(path)
        self.mode = mode
        self.entries: List[Entry] = []
        self.cursor = 0
        self.offset = 0
        self.sort = SORT_NAME
        self.sort_rev = False
        self.filter = ""
        self._phi = None
        self._bubbles = None
        self.current_bubble_id = None
        self._atom_cache = None
        self._loading = False
        self._load_queue = queue.Queue()
        self._search_results = None
        self._lock = threading.Lock()
        self.last_import_errors = []   # FIX v2.1: diagnostyka importu do bąbli

    def set_phi(self, phi) -> None:
        self._phi = phi
        if phi:
            self._atom_cache = PhiAtomCache(phi)

    def set_bubbles(self, bubbles) -> None:
        self._bubbles = bubbles

    def refresh(self, async_load=True):
        if self.mode == MODE_PHI:
            self._load_phi()
        elif self.mode == MODE_BBL:
            if self.current_bubble_id is None: self._load_bubble_list()
            else: self._load_bubble_content()
        elif self.mode == MODE_SEARCH:
            self._load_search_results()
        else:
            if async_load: self._load_fs_async()
            else: self._load_fs_sync()
        self._clamp_cursor()

    def _load_search_results(self):
        entries = []
        if self._search_results:
            for sim, atom in self._search_results:
                e = PhiEntry(atom.id, atom.T, atom.state, atom.S, atom.E, sim)
                entries.append(e)
        with self._lock:
            self.entries = entries

    def _restore_cursor(self, old_name: Optional[str]):
        if old_name is not None:
            for i, e in enumerate(self.entries):
                if e.name() == old_name:
                    self.cursor = i
                    break
        self._clamp_cursor()

    def _load_fs_sync(self):
        entries = self._build_fs_entries()
        self._enrich_phi(entries)
        with self._lock:
            self.entries = entries

    def _load_fs_async(self):
        if self._loading: return
        self._loading = True
        def loader():
            try:
                entries = self._build_fs_entries()
                self._load_queue.put(("fs_loaded", entries))
            except Exception as e:
                self._load_queue.put(("fs_error", str(e)))
            finally:
                self._loading = False
        threading.Thread(target=loader, daemon=True).start()

    def _build_fs_entries(self) -> List[FsEntry]:
        entries = []
        if self.path != "/":
            parent = os.path.dirname(self.path)
            entries.append(FsEntry("..", parent))
        try: names = os.listdir(self.path)
        except PermissionError: return entries
        if self.filter: names = [n for n in names if self.filter.lower() in n.lower()]
        for name in names:
            full = os.path.join(self.path, name)
            entries.append(FsEntry(name, full))
        dirs = [e for e in entries if e.is_dir() and e.name() != ".."]
        files = [e for e in entries if not e.is_dir()]
        dotdot = [e for e in entries if e.name() == ".."]
        key_fn = {
            SORT_NAME: lambda e: e.name().lower(),
            SORT_SIZE: lambda e: getattr(e, "_size", 0),
            SORT_DATE: lambda e: getattr(e, "_mtime", 0),
            SORT_EXT:  lambda e: os.path.splitext(e.name())[1].lower(),
        }.get(self.sort, lambda e: e.name().lower())
        dirs.sort(key=key_fn, reverse=self.sort_rev)
        files.sort(key=key_fn, reverse=self.sort_rev)
        return dotdot + dirs + files

    def _enrich_phi(self, entries: List[Entry]) -> None:
        if not self._phi or not self._atom_cache: return
        self._atom_cache.refresh()
        for e in entries:
            if isinstance(e, FsEntry) and not e.is_dir():
                data = self._atom_cache.get(_atom_id(e.path()))
                if data: e.atom_T, e.atom_state, _, _ = data
                else: e.atom_T = e.atom_state = None

    def _load_phi(self):
        entries = []
        if self._phi is None:
            with self._lock:
                self.entries = entries
            return
        if self._atom_cache:
            self._atom_cache.refresh()
            for aid, (T, state, S, E) in self._atom_cache.get_all():
                if self.filter and self.filter.lower() not in aid.lower(): continue
                entries.append(PhiEntry(aid, T, state, S, E))
        entries.sort(key=lambda e: (-getattr(e, "_T", 0), e.name()))
        with self._lock:
            self.entries = entries

    def _load_bubble_list(self):
        entries = []
        if self._bubbles is None:
            with self._lock:
                self.entries = entries
            return
        try: bubbles = self._bubbles.list_bubbles()
        except: return
        for b in bubbles:
            name = b.get("label", b.get("name", "?"))
            if self.filter and self.filter.lower() not in name.lower(): continue
            entries.append(BubbleEntry(name, b.get("id", ""), b.get("active_atoms", 0), b.get("size_bytes", 0)))
        entries.sort(key=lambda e: e.name().lower())
        with self._lock:
            self.entries = entries

    def _load_bubble_content(self):
        entries = []
        if self._bubbles is None or self.current_bubble_id is None:
            with self._lock:
                self.entries = entries
            return
        try: atoms = self._bubbles.get_active_atoms(self.current_bubble_id)
        except: return
        for a in atoms:
            aid = a.get("id") if isinstance(a, dict) else getattr(a, "id", "")
            if self.filter and self.filter.lower() not in aid.lower(): continue
            S = a.get("S") if isinstance(a, dict) else getattr(a, "S", "")
            T = a.get("T") if isinstance(a, dict) else getattr(a, "T", 0)
            state = a.get("state") if isinstance(a, dict) else getattr(a, "state", "")
            entries.append(PhiEntry(aid, T, state, S, aid))
        entries.sort(key=lambda e: -getattr(e, "_T", 0))
        with self._lock:
            self.entries = entries

    def refresh_metadata(self):
        if self.mode == MODE_FS and self._atom_cache:
            self._atom_cache.refresh()
            with self._lock:
                for e in self.entries:
                    if isinstance(e, FsEntry) and not e.is_dir():
                        data = self._atom_cache.get(_atom_id(e.path()))
                        if data: e.atom_T, e.atom_state, _, _ = data
                        else: e.atom_T = e.atom_state = None
        elif self.mode == MODE_PHI and self._atom_cache:
            self._load_phi()

    def _clamp_cursor(self):
        n = len(self.entries)
        if n == 0:
            self.cursor = self.offset = 0
            return
        self.cursor = max(0, min(self.cursor, n - 1))

    def move(self, delta: int):
        self.cursor = max(0, min(self.cursor + delta, len(self.entries) - 1))

    def current(self) -> Optional[Entry]:
        if not self.entries or self.cursor >= len(self.entries): return None
        return self.entries[self.cursor]

    def marked_entries(self) -> List[Entry]:
        return [e for e in self.entries if e.marked]

    def toggle_mark(self):
        e = self.current()
        if e and e.name() != "..":
            e.marked = not e.marked
            self.move(1)

    def cd(self, path: str) -> bool:
        if self.mode == MODE_BBL:
            if self.current_bubble_id is None:
                e = self.current()
                if e and e.is_dir():
                    self.current_bubble_id = e.path()
                    self.cursor = self.offset = 0
                    self.filter = ""
                    self.refresh()
                    return True
            return False
        else:
            path = os.path.abspath(path)
            if os.path.isdir(path):
                self.path = path
                self.cursor = self.offset = 0
                self.filter = ""
                for e in self.entries: e.marked = False
                self.refresh()
                return True
            return False

    def cd_up(self) -> bool:
        if self.mode == MODE_BBL:
            if self.current_bubble_id is not None:
                self.current_bubble_id = None
                self.cursor = self.offset = 0
                self.filter = ""
                self.refresh()
                return True
            return False
        else:
            return self.cd(os.path.dirname(self.path))

    def toggle_sort(self):
        self.sort = (self.sort + 1) % 4
        self.refresh(async_load=False)

    def toggle_mode(self):
        if self.mode == MODE_FS: self.mode = MODE_PHI
        elif self.mode == MODE_PHI: self.mode = MODE_BBL
        elif self.mode == MODE_BBL: self.mode = MODE_FS
        else: self.mode = MODE_FS
        self.current_bubble_id = None
        self._search_results = None
        self.cursor = self.offset = 0
        self.refresh()

    def create_bubble(self, name: str) -> bool:
        if not self._bubbles: return False
        try:
            self._bubbles.create_bubble(name)
            self.refresh()
            return True
        except: return False

    def delete_current_bubble(self, fm, rnd) -> bool:
        if self.mode != MODE_BBL or self.current_bubble_id is not None: return False
        e = self.current()
        if e and e.is_dir(): return e.delete(fm, rnd)
        return False

    # ── Fix v2.1: import_files_to_bubble – błędy widoczne, weryfikacja zapisu ──
    def import_files_to_bubble(self, files: List[str]) -> int:
        """Importuje pliki do aktywnego bąbla.

        FIX: poprzednia wersja miała `except Exception: continue` które połykało
        WSZYSTKIE błędy po cichu — zły zapis bez żadnego komunikatu, count mógł
        rosnąć mimo braku faktycznego zapisu (fałszywy sukces).

        Teraz:
          - sprawdza phi i bubbles z jasnym komunikatem
          - błędy są zbierane i raportowane przez self.last_import_errors
          - count rośnie TYLKO po potwierdzonym zapisie (weryfikacja w bąblu)
        """
        self.last_import_errors = []

        if self._bubbles is None:
            self.last_import_errors.append("Brak backendu bąbli (bubbles=None)")
            return 0
        if self.current_bubble_id is None:
            self.last_import_errors.append("Żaden bąbel nie jest otwarty")
            return 0
        if self._phi is None:
            self.last_import_errors.append(
                "Brak phi-space (phi=None) — nie można utworzyć atomów")
            return 0

        count = 0
        for path in files:
            atom_id = _atom_id(path)
            try:
                if not os.path.exists(path):
                    self.last_import_errors.append(f"{os.path.basename(path)}: plik nie istnieje")
                    continue

                # Sprawdź istnienie atomu BEZ touch (peek_atom / matrix.get)
                existing = None
                if hasattr(self._phi, 'peek_atom'):
                    existing = self._phi.peek_atom(atom_id)
                elif hasattr(self._phi, 'matrix') and hasattr(self._phi.matrix, 'get'):
                    existing = self._phi.matrix.get(atom_id)

                if not existing:
                    created = self._phi.create_atom(
                        atom_id, S=os.path.basename(path), E=path, T=ATOM_T_FILE)
                    # Weryfikacja: czy atom faktycznie powstał i ma E?
                    if created is None and not (
                        self._phi.peek_atom(atom_id)
                        if hasattr(self._phi, 'peek_atom') else True
                    ):
                        self.last_import_errors.append(
                            f"{os.path.basename(path)}: create_atom nie zwrócił atomu")
                        continue

                # Import do bąbla — import_to_bubble czyta treść z atom.E
                self._bubbles.import_to_bubble(self.current_bubble_id, atom_id, self._phi)

                # WERYFIKACJA: czy atom faktycznie trafił do bąbla?
                if hasattr(self._bubbles, 'get_active_atoms'):
                    active = {a.get('id') for a in
                              self._bubbles.get_active_atoms(self.current_bubble_id)}
                    if atom_id not in active:
                        self.last_import_errors.append(
                            f"{os.path.basename(path)}: zapis nie potwierdzony w bąblu")
                        continue

                count += 1
            except Exception as e:
                self.last_import_errors.append(
                    f"{os.path.basename(path)}: {type(e).__name__}: {e}")
                continue

        self.refresh()
        return count

    def export_atom_from_bubble(self, atom_id: str, dest_path: str) -> bool:
        if self._bubbles is None or self._phi is None: return False
        try:
            atom = self._phi.get_atom(atom_id)
            if not atom: return False
            E = str(getattr(atom, "E", ""))
            if os.path.exists(E): shutil.copy2(E, dest_path)
            else:
                with open(dest_path, "w") as f:
                    f.write(f"Atom: {atom_id}\nE: {E}\nS: {getattr(atom,'S','')}")
            return True
        except: return False

    def delete_atom_from_bubble(self, atom_id: str) -> bool:
        if self._bubbles is None or self.current_bubble_id is None: return False
        try:
            self._bubbles.remove_from_bubble(self.current_bubble_id, atom_id)
            self.refresh()
            return True
        except: return False

# ── Renderer ─────────────────────────────────────────────────────────────────
class Renderer:
    def __init__(self, scr):
        self.scr = scr
        self.h, self.w = scr.getmaxyx()

    def resize(self):
        self.h, self.w = self.scr.getmaxyx()

    def draw(self, left: Panel, right: Panel, active: int, status: str, cmdline: str):
        self.scr.erase()
        self.h, self.w = self.scr.getmaxyx()
        mid = self.w // 2
        self._draw_panel(left, 0, mid, active == 0)
        self._draw_panel(right, mid+1, self.w-mid-1, active == 1)
        self._draw_divider(mid)
        self._draw_fkeys(self.h - 2)
        self._draw_status(self.h - 1, status, cmdline)
        self.scr.refresh()

    def _draw_panel(self, panel: Panel, x: int, w: int, is_active: bool):
        h = self.h - 2
        border_col = curses.color_pair(C_ACTIVE) if is_active else curses.color_pair(C_INACTIVE)
        head_col = curses.color_pair(C_HEADER)
        mode_tag = ""
        if panel.mode == MODE_PHI: mode_tag = "[PHI]"
        elif panel.mode == MODE_BBL:
            mode_tag = f"[BBL:{panel.current_bubble_id[:8]}]" if panel.current_bubble_id else "[BBL]"
        elif panel.mode == MODE_SEARCH:
            mode_tag = "[SEARCH]"
        title = f" {panel.path} {mode_tag}"
        if len(title) > w - 2:
            if w > 3: title = "…" + title[-(w-3):]
            else: title = title[:max(0, w-2)]
        self._put(0, x, title.ljust(w), head_col)
        col_date = 11
        col_size = 6
        col_name = max(4, w - col_size - col_date - 2)
        header = f"{'Nazwa':<{col_name}} {'Rozmiar':>{col_size}} {'Data':>{col_date}}"
        self._put(1, x, header[:w].ljust(w), head_col | curses.A_BOLD)
        visible = max(1, h - 3)
        if h < 4: return
        with panel._lock:
            entries = panel.entries[:]
        if panel.cursor < panel.offset: panel.offset = panel.cursor
        elif panel.cursor >= panel.offset + visible: panel.offset = panel.cursor - visible + 1
        for row, idx in enumerate(range(panel.offset, min(panel.offset + visible, len(entries)))):
            e = entries[idx]
            col = curses.color_pair(e.color())
            if is_active and idx == panel.cursor: col = col | curses.A_REVERSE
            name = "/" + e.name() if e.is_dir() and e.name() != ".." else e.name()
            if panel.mode == MODE_PHI and hasattr(e, "_T"):
                s_str = f"T={e._T:5.1f} {(e._state[:4] if hasattr(e, '_state') else '')}"
                name_w = max(1, w - len(s_str) - 1 - 1)
                line = f"{name[:name_w]:<{name_w}} {s_str}"
            elif panel.mode == MODE_SEARCH and hasattr(e, "_similarity") and e._similarity:
                sim_str = f"sim={e._similarity:.2f}"
                name_w = max(1, w - len(sim_str) - 1 - 1)
                line = f"{name[:name_w]:<{name_w}} {sim_str}"
            else:
                name_w = col_name
                line = f"{name[:name_w]:<{name_w}} {e.size_str():>{col_size}} {e.mtime_str():>{col_date}}"
            self._put(row+2, x, line[:w].ljust(w), col)
        if len(entries) > visible and visible > 2:
            sb_h = max(1, visible * visible // max(1, len(entries)))
            sb_pos = (panel.offset * (visible - sb_h)) // max(1, len(entries) - visible)
            for r in range(visible):
                try:
                    if x + w - 1 < self.w:
                        self.scr.addch(r+2, x+w-1, "█" if sb_pos <= r < sb_pos + sb_h else "│", curses.color_pair(C_INACTIVE))
                except curses.error: pass
        if h - 1 >= 2:
            n_marked = sum(1 for e in entries if e.marked)
            info = f" {len(entries)} wpisów" + (f" [{n_marked} zaznaczonych]" if n_marked else "")
            self._put(h-1, x, info[:w].ljust(w), border_col)

    def _draw_divider(self, x: int):
        for y in range(self.h - 2):
            try: self.scr.addch(y, x, "│", curses.color_pair(C_INACTIVE))
            except curses.error: pass

    def _draw_fkeys(self, y: int):
        fkeys = [("F3","Podgląd"),("F4","Edytuj"),("F5","Kopiuj"),("F6","Przenieś"),
                 ("F7","MkDir/Bąbel"),("F8","Usuń"),("^A","Atom"),("^P","Tryb"),("^F","Szukaj"),("F10","Wyjście")]
        x = 0
        for key, desc in fkeys:
            if x >= self.w: break
            try:
                self.scr.addstr(y, x, key, curses.color_pair(C_ACTIVE) | curses.A_BOLD)
                x += len(key)
                self.scr.addstr(y, x, desc + " ", curses.color_pair(C_STATUS))
                x += len(desc) + 1
            except curses.error: break

    def _draw_status(self, y: int, status: str, cmdline: str):
        line = f"/{cmdline}" if cmdline else (status if status else f" KarmazynOS FM {VERSION}")
        try: self.scr.addstr(y, 0, line[:max(1, self.w-1)].ljust(max(1, self.w-1)), curses.color_pair(C_STATUS))
        except curses.error: pass

    def _put(self, y, x, text, attr):
        try: self.scr.addstr(y, x, text, attr)
        except curses.error: pass

    def dialog(self, prompt: str, default: str = "") -> Optional[str]:
        h, w = self.scr.getmaxyx()
        y, x, dw = h // 2, w // 4, w // 2
        col = curses.color_pair(C_HEADER) | curses.A_BOLD
        try:
            self.scr.addstr(y-1, x, "┌" + "─"*(dw-2) + "┐", col)
            self.scr.addstr(y,   x, f"│ {prompt[:dw-4]:<{dw-4}} │", col)
            self.scr.addstr(y+1, x, f"│ {default[:dw-4]:<{dw-4}} │", col)
            self.scr.addstr(y+2, x, "└" + "─"*(dw-2) + "┘", col)
        except curses.error: pass
        self.scr.refresh()
        curses.echo()
        curses.curs_set(1)
        try:
            self.scr.move(y+1, x+2)
            return self.scr.getstr(max(1, dw - 4)).decode("utf-8", errors="replace").strip() or default or None
        except Exception: return None
        finally:
            curses.noecho()
            curses.curs_set(0)

    def confirm(self, msg: str) -> bool:
        h, w = self.scr.getmaxyx()
        line = f" {msg} [T/N] "
        try: self.scr.addstr(h // 2, max(0, (w - len(line))//2), line, curses.color_pair(C_ERROR) | curses.A_BOLD)
        except curses.error: pass
        self.scr.refresh()
        while True:
            ch = self.scr.getch()
            if ch in (ord("t"), ord("T"), ord("y"), ord("Y")): return True
            if ch in (ord("n"), ord("N"), 27, ord("q")): return False

    def show_text(self, title: str, lines: List[str]):
        h, w = self.scr.getmaxyx()
        offset = 0
        while True:
            self.scr.erase()
            self._put(0, 0, f" {title[:w-4]} — q=wyjście ↑↓ PgUp/Dn ".ljust(w), curses.color_pair(C_HEADER) | curses.A_BOLD)
            for row in range(1, h-1):
                idx = offset + row - 1
                if idx < len(lines): self._put(row, 0, lines[idx][:w-1].ljust(w-1), curses.color_pair(C_NORMAL))
            self._put(h-1, 0, f" Linia {offset+1}/{len(lines)} ".ljust(w), curses.color_pair(C_STATUS))
            self.scr.refresh()
            ch = self.scr.getch()
            if ch in (ord("q"), ord("Q"), 27, curses.KEY_F10): break
            elif ch == curses.KEY_UP: offset = max(0, offset-1)
            elif ch == curses.KEY_DOWN: offset = min(max(0, len(lines)-h+2), offset+1)
            elif ch == curses.KEY_PPAGE: offset = max(0, offset-(h-2))
            elif ch == curses.KEY_NPAGE: offset = min(max(0, len(lines)-h+2), offset+(h-2))
            elif ch == curses.KEY_HOME: offset = 0
            elif ch == curses.KEY_END: offset = max(0, len(lines)-h+2)

# ── FM ──────────────────────────────────────────────────────────────────────
class FM:
    def __init__(self, phi: Any = None, bubbles: Any = None, start: str = "."):
        self.phi = phi
        self.bubbles = bubbles
        self.left = Panel(start)
        self.right = Panel(os.path.expanduser("~"))
        self.left.set_phi(phi); self.right.set_phi(phi)
        self.left.set_bubbles(bubbles); self.right.set_bubbles(bubbles)
        self.active = 0
        self.status = ""
        self.cmdline = ""
        self._searching = False
        self._last_metadata_refresh = 0.0

    @property
    def _cur_panel(self) -> Panel: return self.left if self.active == 0 else self.right
    @property
    def _other_panel(self) -> Panel: return self.right if self.active == 0 else self.left

    def run(self) -> None:
        curses.wrapper(self._main)

    def emit(self, event: str, data: dict = None):
        try: REGISTRY.log("EVENT", str(data or {}), service=f"fm.{event}")
        except: pass

    def _main(self, scr):
        curses.curs_set(0)
        curses.noecho()
        scr.keypad(True)
        scr.timeout(100)
        _init_colors()
        rnd = Renderer(scr)
        self.left.refresh()
        self.right.refresh()
        need_redraw = True
        self._last_metadata_refresh = time.monotonic()
        while True:
            for panel in (self.left, self.right):
                try:
                    while True:
                        msg = panel._load_queue.get_nowait()
                        if msg[0] == "fs_loaded":
                            old_name = panel.current().name() if panel.current() else None
                            panel._enrich_phi(msg[1])
                            with panel._lock:
                                panel.entries = msg[1]
                            panel._restore_cursor(old_name)
                            need_redraw = True
                        elif msg[0] == "fs_error":
                            self.status = f"Błąd ładowania: {msg[1]}"
                            need_redraw = True
                except queue.Empty: pass

            now = time.monotonic()
            if now - self._last_metadata_refresh >= CACHE_REFRESH:
                self.left.refresh_metadata()
                self.right.refresh_metadata()
                self._last_metadata_refresh = now
                need_redraw = True

            if need_redraw:
                rnd.draw(self.left, self.right, self.active, self.status, self.cmdline)
                self.status = ""
                need_redraw = False
            ch = scr.getch()
            if ch == -1: continue
            need_redraw = True
            if ch == curses.KEY_RESIZE:
                rnd.resize()
                for p in (self.left, self.right): p._clamp_cursor(); p.offset = 0
                continue
            if self._searching:
                if self._handle_search(ch, rnd):
                    need_redraw = True
                    continue
                else:
                    self._searching = False
            if ch == 27 and not self._searching:
                self._cur_panel.filter = ""
                self._cur_panel.refresh()
                self.status = "Filtr wyczyszczony"
                continue
            if ch == curses.KEY_UP or ch == ord("k"): self._cur_panel.move(-1)
            elif ch == curses.KEY_DOWN or ch == ord("j"): self._cur_panel.move(1)
            elif ch == curses.KEY_PPAGE: self._cur_panel.move(-10)
            elif ch == curses.KEY_NPAGE: self._cur_panel.move(10)
            elif ch == curses.KEY_HOME: self._cur_panel.cursor = 0
            elif ch == curses.KEY_END: self._cur_panel.cursor = max(0, len(self._cur_panel.entries)-1)
            elif ch == ord("\t") or ch == curses.KEY_LEFT or ch == curses.KEY_RIGHT: self.active = 1 - self.active
            elif ch in (10,13,curses.KEY_ENTER): self._action_enter(rnd)
            elif ch in (curses.KEY_BACKSPACE, 127, 8): self._cur_panel.cd_up()
            elif ch == ord(" "): self._cur_panel.toggle_mark()
            elif ch == curses.KEY_F3: self._action_view(rnd)
            elif ch == curses.KEY_F4: self._action_edit()
            elif ch == curses.KEY_F5: self._action_copy(rnd)
            elif ch == curses.KEY_F6: self._action_move(rnd)
            elif ch == curses.KEY_F7: self._action_mkdir(rnd)
            elif ch == curses.KEY_F8: self._action_delete(rnd)
            elif ch == curses.KEY_F10 or ch == ord("q"): break
            elif ch == 1:  # Ctrl+A
                self._action_create_atom(rnd)
            elif ch == 16: # Ctrl+P
                self._cur_panel.toggle_mode()
                self.status = f"Tryb: {self._cur_panel.mode}"
            elif ch == 19: # Ctrl+S
                self._action_sync()
            elif ch == 14: # Ctrl+N
                self._action_new_bubble(rnd)
            elif ch == 4:  # Ctrl+D
                self._action_delete_bubble(rnd)
            elif ch == 9:  # Ctrl+I
                self._action_import_to_bubble(rnd)
            elif ch == 5:  # Ctrl+E
                self._action_export_from_bubble(rnd)
            elif ch == curses.KEY_DC: # Delete
                self._action_delete_atom_from_bubble(rnd)
            elif ch == 6:  # Ctrl+F
                self._action_search(rnd)
            elif ch == ord("r"):
                self.left.refresh(False); self.right.refresh(False); self.status = "Odświeżono"
            elif ch == ord("s"):
                self._cur_panel.toggle_sort()
                sort_names = ["nazwa", "rozmiar", "data", "rozszerzenie"]
                self.status = f"Sortowanie {sort_names[self._cur_panel.sort]}"
            elif ch == ord("/"):
                self._searching = True
                self.cmdline = ""

    def _handle_search(self, ch, rnd) -> bool:
        if ch in (27, curses.KEY_F3):
            self._searching = False
            self.cmdline = ""
            self._cur_panel.filter = ""
            self._cur_panel.refresh()
            return True
        elif ch in (10, 13):
            self._searching = False
            self.cmdline = ""
            return True
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            self.cmdline = self.cmdline[:-1]
            self._cur_panel.filter = self.cmdline
            self._cur_panel.refresh()
            return True
        elif 32 <= ch < 127:
            self.cmdline += chr(ch)
            self._cur_panel.filter = self.cmdline
            self._cur_panel.refresh()
            return True
        else:
            self._searching = False
            return False

    def _action_enter(self, rnd):
        e = self._cur_panel.current()
        if e: e.open(self, rnd)

    def _action_view(self, rnd):
        e = self._cur_panel.current()
        if e and not e.is_dir():
            if isinstance(e, FsEntry): self._action_view_file(e.path(), rnd)
            elif isinstance(e, PhiEntry): e.open(self, rnd)

    def _action_view_file(self, path: str, rnd: Renderer):
        try:
            with open(path, encoding="utf-8", errors="replace") as f: content = f.read(512 * 1024)
            rnd.show_text(os.path.basename(path), content.splitlines() or ['(pusty plik)'])
            self._touch_atom(path)
        except Exception as ex: self.status = f"Błąd odczytu: {ex}"

    def _action_edit(self):
        e = self._cur_panel.current()
        if not e or e.is_dir(): return
        path = e.path()
        ed = os.environ.get("EDITOR", "vi")
        if not shutil.which(ed) and ed != "vi":
            ed = "vi" if shutil.which("vi") else "nano"
        curses.def_prog_mode(); curses.endwin()
        try: subprocess.call([ed, path])
        except: pass
        finally:
            curses.reset_prog_mode(); curses.update_lines_cols()
            self._cur_panel.refresh(); self._touch_atom(path)

    def _action_copy(self, rnd):
        sources = self._cur_panel.marked_entries()
        if not sources:
            e = self._cur_panel.current()
            if e and e.name() != "..": sources = [e]
        if not sources: return

        # FIX v2.1: jeśli DRUGI panel to otwarty bąbel (MODE_BBL wewnątrz bąbla),
        # F5 kopiuje pliki DO bąbla zamiast tylko na filesystem.
        # Poprzednio F5 jawnie pomijał bąble (if not isinstance(e, FsEntry): continue)
        # → "brak możliwości kopiowania do bąbli".
        other = self._other_panel
        if other.mode == MODE_BBL and other.current_bubble_id is not None:
            paths = [e.path() for e in sources
                     if isinstance(e, FsEntry) and not e.is_dir()]
            if not paths:
                self.status = "Do bąbla można kopiować tylko pliki (nie katalogi)."
                return
            count = other.import_files_to_bubble(paths)
            errs = getattr(other, 'last_import_errors', [])
            if errs:
                self.status = (f"Skopiowano do bąbla: {count}/{len(paths)}  "
                               f"(błąd: {errs[0]})")
            else:
                self.status = f"Skopiowano do bąbla: {count} plików"
            self.left.refresh(); self.right.refresh()
            return

        # Standardowe kopiowanie na filesystem
        dest = rnd.dialog("Kopiuj do:", other.path)
        if not dest: return
        count = errors = 0
        last_err = ""
        for e in sources:
            if not isinstance(e, FsEntry):
                continue
            try:
                dst = os.path.join(dest, e.name())
                if e.is_dir(): shutil.copytree(e.path(), dst, dirs_exist_ok=True)
                else: shutil.copy2(e.path(), dst)
                count += 1
            except Exception as ex:
                errors += 1
                last_err = str(ex)
        self.status = f"Skopiowano: {count}" + (
            f" (błędów: {errors}: {last_err})" if errors else "")
        self.left.refresh(); self.right.refresh()

    def _action_move(self, rnd):
        sources = self._cur_panel.marked_entries()
        if not sources:
            e = self._cur_panel.current()
            if e and e.name() != "..": sources = [e]
        if not sources: return
        if len(sources) == 1 and isinstance(sources[0], FsEntry):
            dest = rnd.dialog("Nowa nazwa / katalog docelowy:", sources[0].path())
        else:
            dest = rnd.dialog("Przenieś do:", self._other_panel.path)
        if not dest: return
        count = errors = 0
        for e in sources:
            if not isinstance(e, FsEntry): continue
            try:
                src = e.path()
                dst = dest if len(sources) == 1 and not os.path.isdir(dest) else os.path.join(dest, e.name())
                shutil.move(src, dst)
                count += 1
            except Exception as ex:
                errors += 1
                self.status = f"Błąd: {ex}"
        self.status = f"Przeniesiono: {count}" + (f" (błędów: {errors})" if errors else "")
        self.left.refresh(); self.right.refresh()

    def _action_mkdir(self, rnd):
        panel = self._cur_panel
        if panel.mode == MODE_BBL and panel.current_bubble_id is None:
            name = rnd.dialog("Nowy bąbel:", "")
            if name and panel.create_bubble(name):
                self.status = f"Utworzono bąbel: {name}"
            elif name:
                self.status = "Nie udało się utworzyć bąbla"
        elif panel.mode == MODE_BBL:
            self.status = "Jesteś wewnątrz bąbla. Wyjdź (Backspace) aby utworzyć nowy bąbel."
        else:
            name = rnd.dialog("Nowy katalog:", "")
            if name:
                try:
                    os.makedirs(os.path.join(panel.path, name), exist_ok=True)
                    panel.refresh(async_load=False)
                    self.status = f"Utworzono katalog: {name}"
                except Exception as e:
                    self.status = f"Błąd: {e}"

    def _action_delete(self, rnd):
        e = self._cur_panel.current()
        if e and not (e.is_dir() and e.name() == "..") and rnd.confirm(f"Usuń {e.name()}?"):
            if e.delete(self, rnd):
                self._cur_panel.refresh(async_load=False)
                self.status = f"Usunięto: {e.name()}"

    def _action_create_atom(self, rnd):
        e = self._cur_panel.current()
        if self.phi and e and isinstance(e, FsEntry) and not e.is_dir():
            aid = _atom_id(e.path())
            if not self.phi.get_atom(aid):
                self.phi.create_atom(aid, S=e.name(), E=e.path(), T=ATOM_T_FILE)
            self.left.refresh(); self.right.refresh()

    def _action_sync(self):
        self.left.refresh(); self.right.refresh(); self.status = "Zsynchronizowano"

    def _action_new_bubble(self, rnd):
        if self._cur_panel.mode == MODE_BBL:
            name = rnd.dialog("Nazwa bąbla:", "")
            if name: self._cur_panel.create_bubble(name)

    def _action_delete_bubble(self, rnd):
        e = self._cur_panel.current()
        if self._cur_panel.mode == MODE_BBL and not self._cur_panel.current_bubble_id and e and rnd.confirm("Usuń bąbel?"):
            self._cur_panel.delete_current_bubble(self, rnd); self._cur_panel.refresh()

    def _action_import_to_bubble(self, rnd):
        dest_panel = self._cur_panel if self._cur_panel.mode == MODE_BBL else self._other_panel
        src_panel = self._other_panel if dest_panel == self._cur_panel else self._cur_panel

        if dest_panel.mode != MODE_BBL or dest_panel.current_bubble_id is None:
            self.status = "Cel musi być otwartym bąblem (tryb BBL, wejdź do bąbla)."
            return
        if src_panel.mode != MODE_FS:
            self.status = "Źródło plików musi być w trybie FS (zwykły katalog)."
            return

        selected = src_panel.marked_entries()
        if not selected:
            cur = src_panel.current()
            if cur and cur.name() != "..":
                selected = [cur]
        paths = [e.path() for e in selected if isinstance(e, FsEntry) and not e.is_dir()]
        if not paths:
            self.status = "Nie wybrano plików."
            return
        count = dest_panel.import_files_to_bubble(paths)
        errs = getattr(dest_panel, 'last_import_errors', [])
        if errs:
            self.status = (f"Zaimportowano {count}/{len(paths)} do bąbla  "
                           f"(błąd: {errs[0]})")
        else:
            self.status = f"Zaimportowano {count} plików do bąbla"
        src_panel.refresh(async_load=False)
        dest_panel.refresh()

    def _action_export_from_bubble(self, rnd):
        e = self._cur_panel.current()
        if e and not e.is_dir():
            dest_dir = self._other_panel.path if self._other_panel.mode == MODE_FS else os.getcwd()
            dest = rnd.dialog("Eksportuj:", os.path.join(dest_dir, e.name()))
            if dest and self._cur_panel.export_atom_from_bubble(e.name(), dest):
                self.status = f"Eksportowano: {dest}"

    def _action_delete_atom_from_bubble(self, rnd):
        e = self._cur_panel.current()
        if e and not e.is_dir() and rnd.confirm(f"Usuń atom {e.name()} z bąbla?"):
            if self._cur_panel.delete_atom_from_bubble(e.name()):
                self.status = f"Usunięto atom: {e.name()}"

    def _action_search(self, rnd):
        query = rnd.dialog("Szukaj:", "")
        if not query:
            return
        self.status = f"Szukam: {query}..."
        try:
            from karmazyn_karmindb import KarminDatabase
            db = KarminDatabase(self.phi)
            results = db.search(query, limit=50)
            valid_results = []
            for item in results:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    sim, atom = item
                    if hasattr(atom, 'id') and hasattr(atom, 'T'):
                        valid_results.append((float(sim), atom))
            self._cur_panel.mode = MODE_SEARCH
            self._cur_panel._search_results = valid_results
            self._cur_panel.cursor = 0
            self._cur_panel.offset = 0
            self._cur_panel.refresh()
            self.status = f"Znaleziono {len(valid_results)} wyników dla '{query}'"
        except ImportError:
            self.status = "Brak karmazyn_karmindb – wyszukiwanie niedostępne"
        except Exception as e:
            self.status = f"Błąd wyszukiwania: {e}"

    def _touch_atom(self, path: str):
        if self.phi:
            try:
                a = self.phi.get_atom(_atom_id(path))
                if a:
                    a.T = min(100.0, float(a.T) + 10)
                    a.touch()
            except: pass

def cmd_fm(args, runtime=None, bubbles=None, **_kw) -> str:
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

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=os.getcwd())
    opt = ap.parse_args()
    phi = None
    bubbles = None
    if _PHI_AVAILABLE:
        try: phi = PhiSpace()
        except: pass
    if _VFS_AVAILABLE:
        try: bubbles = BubbleVFS()
        except: pass
    FM(phi, bubbles, opt.path).run()