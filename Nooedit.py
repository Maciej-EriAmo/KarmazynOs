"""
NooEdit.py — Edytor KarmazynOS
===============================
Adaptacja AstraEdit 4.6 dla modelu fundamentalnego KarmazynOS.

Filozofia:
  Plik na dysku = projekcja Babla.
  Edytor pracuje na projekcji.
  Zapis = push projekcji z powrotem do Babla przez rezonans.
  F5 = uruchomienie kodu w NOWYM Bablu Workspace.

Typy treści — wykrywane automatycznie z przestrzeni phi Babla:
  logic + knowledge  → .py   (kod Python)
  creation + logic   → .lua  (skrypt Lua / KarmazynScript)
  creation + being   → .md   (tekst, notatki, poezja)
  chaos dominant     → .txt  (surowy tekst)
  default            → .py

Tryby uruchomienia:
  python NooEdit.py                          — samodzielnie (plik)
  python NooEdit.py <plik>                   — otworz plik
  from nooedit import open_bubble            — z shella KarmazynOS

Wymagania:
  prompt_toolkit   (TUI)
  tkinter          (GUI)
  AstraEdit.pyw    (silnik edytora — musi byc w tym samym katalogu)
"""

import os
import sys
import pathlib
import subprocess
import time
import json
import hashlib
import threading
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from runtime import SanctuaryRuntime

# ─── Wspolne funkcje I/O (zachowane z AstraEdit) ─────────────────────────────

def is_binary_file(filepath):
    try:
        with open(filepath, 'rb') as f:
            return b'\0' in f.read(1024)
    except Exception:
        return False

def read_text_file_smart(path):
    if is_binary_file(path):
        raise ValueError("Plik binarny")
    for enc in ['utf-8', 'utf-8-sig', 'cp1250', 'latin-1']:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(), "utf-8(replace)"

def read_text_file(path):
    content, _ = read_text_file_smart(path)
    return content

def write_text_file(path, text, encoding='utf-8'):
    with open(path, "w", encoding=encoding, errors="replace") as f:
        f.write(text)

# ─── Wykrywanie typu tresci z przestrzeni phi ─────────────────────────────────

PHI_AXES = [
    "joy", "sadness", "fear", "anger", "love", "disgust",
    "surprise", "acceptance", "logic", "knowledge", "time",
    "creation", "being", "space", "chaos",
]

PHI_LOGIC    = PHI_AXES.index("logic")
PHI_KNOWLEDGE = PHI_AXES.index("knowledge")
PHI_CREATION = PHI_AXES.index("creation")
PHI_BEING    = PHI_AXES.index("being")
PHI_CHAOS    = PHI_AXES.index("chaos")

CONTENT_TYPE_MAP = {
    "py":   ("Python",        ".py"),
    "lua":  ("Lua/KarmScript", ".lua"),
    "md":   ("Tekst/Notatki", ".md"),
    "txt":  ("Surowy tekst",  ".txt"),
    "karm": ("KarmazynScript", ".karm"),
}


def detect_content_type(phi_vec=None, label: str = "") -> str:
    """
    Wykrywa typ tresci Babla na podstawie wektora phi.
    Zwraca klucz: 'py' | 'lua' | 'md' | 'txt' | 'karm'
    """
    import numpy as np

    # Hint z nazwy etykiety
    label_low = label.lower()
    for ext in ('.py', '.lua', '.md', '.txt', '.karm'):
        if label_low.endswith(ext):
            return ext[1:]

    if any(k in label_low for k in ('kod', 'code', 'skrypt', 'script', 'func')):
        return 'py'
    if any(k in label_low for k in ('notatk', 'note', 'tekst', 'text', 'pism', 'poem')):
        return 'md'
    if any(k in label_low for k in ('lua', 'karm')):
        return 'lua'

    if phi_vec is None:
        return 'py'

    vec = np.array(phi_vec, dtype=float)

    logic_score    = vec[PHI_LOGIC] + vec[PHI_KNOWLEDGE]
    creation_score = vec[PHI_CREATION] + vec[PHI_BEING]
    chaos_score    = vec[PHI_CHAOS]

    # Chaos dominuje → surowy tekst
    if chaos_score > 0.4:
        return 'txt'

    # Logika > kreatywnosc → kod
    if logic_score > creation_score:
        if vec[PHI_CREATION] > 0.2:
            return 'karm'  # logika + kreatywnosc = KarmazynScript
        return 'py'

    # Kreatywnosc dominuje → tekst/notatki
    return 'md'


# ─── BubbleVFS — wirtualny system plikow dla Babli ────────────────────────────

class BubbleVFS:
    """
    Wirtualny system plikow dla Babli.
    Dwa katalogi:
      .bubbles/tmp/      — pliki tymczasowe do edycji (czyszczone po zapisie)
      .bubbles/content/  — trwaly magazyn tresci Babli (persystuje miedzy sesjami)
    """

    TMP_DIR     = ".bubbles/tmp"
    CONTENT_DIR = ".bubbles/content"

    def __init__(self):
        os.makedirs(self.TMP_DIR,     exist_ok=True)
        os.makedirs(self.CONTENT_DIR, exist_ok=True)

    def materialize(self, label: str, content: str,
                    content_type: str = 'py') -> str:
        """Zapisuje zawartosc do pliku tymczasowego. Zwraca sciezke."""
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        path = os.path.join(self.TMP_DIR, f"{label}{ext}")
        write_text_file(path, content)
        return path

    def read_back(self, label: str, content_type: str = 'py') -> str:
        """Czyta zawartosc pliku tymczasowego po edycji."""
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        path = os.path.join(self.TMP_DIR, f"{label}{ext}")
        if os.path.exists(path):
            return read_text_file(path)
        return ""

    def save_content(self, label: str, content: str,
                     content_type: str = 'py') -> str:
        """
        Trwaly zapis tresci Babla do .bubbles/content/.
        Ten plik persystuje miedzy sesjami — to jest zrodlo prawdy dla NooEdit.
        """
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        path = os.path.join(self.CONTENT_DIR, f"{label}{ext}")
        write_text_file(path, content)
        return path

    def load_content(self, label: str,
                     content_type: str = 'py') -> str:
        """Wczytuje trwala tresc Babla z .bubbles/content/."""
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        path = os.path.join(self.CONTENT_DIR, f"{label}{ext}")
        if os.path.exists(path):
            return read_text_file(path)
        return ""

    def has_content(self, label: str, content_type: str = 'py') -> bool:
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        return os.path.exists(
            os.path.join(self.CONTENT_DIR, f"{label}{ext}")
        )

    def cleanup(self, label: str, content_type: str = 'py'):
        """Usuwa plik tymczasowy po synchronizacji."""
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        path = os.path.join(self.TMP_DIR, f"{label}{ext}")
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


# ─── NooContext — kontekst edycji w KarmazynOS ────────────────────────────────

class NooContext:
    """
    Kontekst jednej sesji edycji Babla w NooEdit.
    Lacznik miedzy edytorem a runtimem KarmazynOS.
    """

    def __init__(self, label: str, runtime: 'SanctuaryRuntime',
                 content_type: str = 'py'):
        self.label        = label
        self.runtime      = runtime
        self.content_type = content_type
        self.vfs          = BubbleVFS()
        self._last_hash   = ""

    def get_bubble(self):
        return self.runtime._bubbles.get(self.label)

    def get_content(self) -> str:
        """
        Pobiera zawartosc Babla jako tekst.
        Kolejnosc:
          1. .bubbles/content/<label>.<ext>  — trwaly magazyn NooEdit
          2. bubble.content                  — fallback (skrot z absorb)
          3. Pusty szablon z komentarzem
        """
        # 1. Trwaly magazyn NooEdit
        if self.vfs.has_content(self.label, self.content_type):
            return self.vfs.load_content(self.label, self.content_type)

        # 2. Fallback: bubble.content (krótki string z absorb)
        bubble = self.get_bubble()
        if bubble is not None:
            content = getattr(bubble, 'content', '')
            noise   = {'bubble_init', self.label, 'Tekst', ''}
            parts   = [p.strip() for p in content.split()
                       if p.strip() not in noise]
            if parts:
                return '\n'.join(parts)

        # 3. Pusty szablon
        lang = CONTENT_TYPE_MAP.get(self.content_type, ("?", ""))[0]
        return (f"# Babl '{self.label}' [{lang}]\n"
                f"# Ctrl+S: zapisz  F5: uruchom  Ctrl+Q: wyjdz\n")

    def push_content(self, new_content: str) -> dict:
        """
        Zapisuje nowa zawartosc Babla.
        Dwa miejsca zapisu:
          1. .bubbles/content/<label>.<ext>  — pelna tresc (persystuje)
          2. bubble.content                  — skrot (pierwsze 256 zn) dla phi-space
        """
        bubble = self.get_bubble()
        if bubble is None:
            return {"status": "error", "reason": "bubble_not_found"}

        h = hashlib.md5(new_content.encode('utf-8')).hexdigest()
        if h == self._last_hash:
            return {"status": "unchanged"}
        self._last_hash = h

        # 1. Zapisz pelna tresc do magazynu
        self.vfs.save_content(self.label, new_content, self.content_type)

        # 2. Zaktualizuj bubble.content (skrot dla phi-space)
        atom_id = f"edit_{self.label}_{int(time.time())}"
        try:
            atom = self.runtime.create_atom(
                atom_id,
                new_content[:256],
                self.label,
                T=90.0
            )
            bubble.absorb(atom)
            bubble.update_psi([atom])
            # Atom byl tylko nosnikiem tresci — teraz zanika
            try:
                self.runtime.delete_atom(atom_id)
            except Exception:
                pass
            return {"status": "absorbed", "atom": atom_id}
        except Exception as e:
            # Magazyn zapisany — atom to bonus, nie blokuj
            return {"status": "absorbed", "note": str(e)}

    def run_in_new_bubble(self, content: str,
                          tmp_path: str) -> Optional[str]:
        """
        F5: uruchamia kod w NOWYM Bablu Workspace.
        Wynik wykonania trafia do nowego Babla.
        Zwraca etykiete nowego Babla lub None przy bledzie.
        """
        # Nowy Babl na wyniki
        result_label = f"{self.label}_run_{int(time.time())}"

        try:
            from karmazyn_core import BubbleMode
            from core.phi_math import PhiPhysics

            # Tworzymy Babl Workspace dla wynikow
            self.runtime.write(result_label, result_label, "run_output", 1.0)
            self.runtime.consolidate(result_label)
            rb = self.runtime._bubbles.get(result_label)
            if rb:
                rb.mode = BubbleMode.WORKSPACE

            # Uruchomienie kodu — przechwyc stdout
            ext = CONTENT_TYPE_MAP.get(self.content_type, ("", ".py"))[1]
            cmd = _get_run_command(tmp_path)

            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=30, encoding='utf-8', errors='replace'
            )
            output = proc.stdout + proc.stderr

            # Wynik → Atom → nowy Babl
            out_id = f"out_{result_label}"
            self.runtime.create_atom(
                out_id,
                output[:512] if output else "(brak wyjscia)",
                result_label,
                T=80.0
            )
            if rb:
                out_atom = self.runtime.get_atom(out_id)
                if out_atom:
                    self.runtime.consolidate_to_bubble(out_atom, rb)

            return result_label, proc.returncode, output

        except subprocess.TimeoutExpired:
            return result_label, -1, "TIMEOUT: skrypt przekroczyl 30s"
        except Exception as e:
            return result_label, -1, f"BLAD: {e}"


def _get_run_command(file_path: str):
    """Zwraca komende uruchomienia dla danego pliku."""
    import shutil
    ext = pathlib.Path(file_path).suffix.lower()

    if ext == '.py':
        return [sys.executable, "-u", file_path]
    if ext in ('.lua', '.karm'):
        for candidate in ('lua', 'lua5.4', 'lua5.3', 'luajit'):
            found = shutil.which(candidate)
            if found:
                return [found, file_path]
        raise FileNotFoundError("Brak interpretera Lua w PATH.")
    if ext in ('.sh', '.bash'):
        shell = shutil.which('bash') or shutil.which('sh')
        if shell:
            return [shell, file_path]
        raise FileNotFoundError("Brak bash/sh.")
    return [file_path]


# ─── NooEditTUI ───────────────────────────────────────────────────────────────

try:
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit, Window, FloatContainer, Float
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.widgets import (TextArea, Frame, Dialog,
                                        Button, Label, SearchToolbar)
    from prompt_toolkit.styles import Style
    try:
        from prompt_toolkit.lexers import PygmentsLexer
        from pygments.lexers import get_lexer_for_filename
        from pygments.util import ClassNotFound
        from pygments.token import Token as PygToken
        HAS_PYGMENTS = True
    except ImportError:
        HAS_PYGMENTS = False
        PygmentsLexer = None
        get_lexer_for_filename = None
    HAS_TUI = True
except ImportError:
    HAS_TUI = False


class NooEditTUI:
    """
    NooEdit w trybie TUI (prompt_toolkit).
    Zapisuje do Babla zamiast do pliku.
    F5 tworzy nowy Babl z wynikiem.
    """

    APP_NAME = "NooEdit — KarmazynOS"

    def __init__(self, ctx: NooContext, tmp_path: str):
        if not HAS_TUI:
            raise ImportError("Brak prompt_toolkit. Zainstaluj: pip install prompt_toolkit")

        self.ctx      = ctx
        self.tmp_path = tmp_path
        self.is_modified = False

        self.search_field = SearchToolbar()

        lexer = None
        if HAS_PYGMENTS and get_lexer_for_filename:
            try:
                lex_inst = get_lexer_for_filename(tmp_path)
                lexer = PygmentsLexer(lex_inst.__class__)
            except Exception:
                pass

        initial = read_text_file(tmp_path) if os.path.exists(tmp_path) else ""

        self.editor = TextArea(
            text=initial, scrollbar=True, line_numbers=True,
            lexer=lexer, multiline=True,
            search_field=self.search_field, focus_on_click=True
        )
        self.editor.buffer.on_text_changed += lambda _: self._on_change()
        self.frame  = Frame(self.editor, title=self._title())
        self.status = Window(
            height=1,
            content=FormattedTextControl(self._status_bar),
            style="class:status"
        )
        self.kb = self._make_kb()

    def _title(self) -> str:
        ct   = CONTENT_TYPE_MAP.get(self.ctx.content_type, ("?", ""))[0]
        mark = "*" if self.is_modified else ""
        return f"{self.APP_NAME} | Babl: {self.ctx.label} [{ct}]{mark}"

    def _on_change(self):
        if not self.is_modified:
            self.is_modified = True
            self.frame.title  = self._title()

    def _status_bar(self):
        row = self.editor.document.cursor_position_row + 1
        col = self.editor.document.cursor_position_col + 1
        return [("class:status",
                 f" Ln {row}, Col {col} | "
                 f"Ctrl+S: zapisz do Babla | F5: uruchom w nowym Bablu | "
                 f"Ctrl+Q: wyjdz | Babl: {self.ctx.label} ")]

    def _save_to_bubble(self):
        """Ctrl+S — push tresci do Babla."""
        write_text_file(self.tmp_path, self.editor.text)
        result = self.ctx.push_content(self.editor.text)
        self.is_modified = False
        self.frame.title = self._title()
        status = result.get("status", "?")
        return status

    def _make_kb(self):
        kb = KeyBindings()

        @kb.add("c-s")
        def _(event):
            status = self._save_to_bubble()
            # Krotka informacja w tytule
            self.frame.title = (
                f"{self._title()} [zapisano → Babl]"
                if status in ("absorbed", "unchanged")
                else f"{self._title()} [odrzucono: {status}]"
            )

        @kb.add("c-q")
        def _(event):
            if self.is_modified:
                self._save_to_bubble()
            event.app.exit()

        @kb.add("f5")
        def _(event):
            self._run_in_bubble(event.app)

        @kb.add("c-f")
        def _(event):
            event.app.layout.focus(self.search_field)

        return kb

    def _run_in_bubble(self, app):
        """F5 — uruchom kod, wynik do nowego Babla Workspace."""
        # Najpierw zapisz
        write_text_file(self.tmp_path, self.editor.text)

        app.suspend_to_background()
        print(f"\n{'='*60}")
        print(f"  NooEdit F5: {self.ctx.label}")
        print(f"  Wyniki traca do nowego Babla Workspace...")
        print(f"{'='*60}\n")

        try:
            result_label, exit_code, output = self.ctx.run_in_new_bubble(
                self.editor.text, self.tmp_path
            )
            print(output or "(brak wyjscia)")
            print(f"\n{'='*60}")
            print(f"  Kod wyjscia: {exit_code}")
            print(f"  Wynik zapisany w Bablu: {result_label}")
            print(f"{'='*60}")
        except Exception as e:
            print(f"BLAD: {e}")

        input("\nEnter aby wrocic do edytora...")
        app.resume()

    def run(self):
        style = Style.from_dict({
            "status":      "bg:#1a3a5c #ffffff",
            "frame.label": "#ffffff bold",
            "search":      "bg:cyan #000000"
        })
        layout = Layout(FloatContainer(
            HSplit([self.frame, self.search_field, self.status]),
            floats=[]
        ))
        Application(
            layout=layout,
            key_bindings=self.kb,
            full_screen=True,
            mouse_support=True,
            style=style
        ).run()


# ─── NooEditGUI ───────────────────────────────────────────────────────────────

try:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk
    HAS_GUI = True
except ImportError:
    HAS_GUI = False
    tk = None


class NooEditGUI:
    """
    NooEdit w trybie GUI (Tkinter).
    Zapisuje do Babla zamiast do pliku.
    F5 tworzy nowy Babl Workspace z wynikiem.
    """

    APP_NAME = "NooEdit — KarmazynOS"

    BG_COLOR        = "#1e1e1e"
    FG_COLOR        = "#d4d4d4"
    CURSOR_COLOR    = "#ffffff"
    SELECTION_COLOR = "#264f78"
    LINE_NUM_BG     = "#252526"
    LINE_NUM_FG     = "#858585"
    STATUS_BG       = "#1a3a5c"

    def __init__(self, ctx: NooContext, tmp_path: str):
        if not HAS_GUI:
            raise ImportError("Brak tkinter.")

        self.ctx         = ctx
        self.tmp_path    = tmp_path
        self.is_modified = False
        self.process     = None

        self.root = tk.Tk()
        self.root.title(self._title())
        self.root.geometry("1100x750")
        self.root.configure(bg=self.BG_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._load_content()
        self._build_menu()
        self._bind_keys()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Toolbar
        tb = tk.Frame(self.root, bg="#2d2d2d", height=32)
        tb.pack(fill="x")

        for label, cmd in [
            ("Zapisz do Babla (Ctrl+S)", self._save_to_bubble),
            (f"Uruchom w nowym Bablu (F5)", self._run_in_bubble),
            ("Zamknij (Ctrl+Q)", self._on_close),
        ]:
            tk.Button(
                tb, text=label, command=cmd,
                bg="#007acc", fg="white", relief="flat",
                padx=10, pady=4, font=("Consolas", 9)
            ).pack(side="left", padx=2, pady=3)

        # Etykieta Babla
        ct = CONTENT_TYPE_MAP.get(self.ctx.content_type, ("?", ""))[0]
        tk.Label(
            tb,
            text=f"  Babl: {self.ctx.label} [{ct}]",
            bg="#2d2d2d", fg="#569cd6",
            font=("Consolas", 10, "bold")
        ).pack(side="left", padx=10)

        # Obszar edycji
        editor_frame = tk.Frame(self.root, bg=self.BG_COLOR)
        editor_frame.pack(fill="both", expand=True)

        self.line_numbers = tk.Text(
            editor_frame, width=4, padx=3, takefocus=0,
            border=0, bg=self.LINE_NUM_BG, fg=self.LINE_NUM_FG,
            state="disabled", font=("Consolas", 11)
        )
        self.line_numbers.pack(side="left", fill="y")

        self.text_area = scrolledtext.ScrolledText(
            editor_frame, wrap="word", undo=True,
            bg=self.BG_COLOR, fg=self.FG_COLOR,
            insertbackground=self.CURSOR_COLOR,
            selectbackground=self.SELECTION_COLOR,
            font=("Consolas", 11), border=0
        )
        self.text_area.pack(side="left", fill="both", expand=True)

        # Konsola wyjscia
        out_frame = tk.Frame(self.root, bg="#0a0a0a", height=160)
        out_frame.pack(fill="x")
        out_frame.pack_propagate(False)

        tk.Label(
            out_frame,
            text="Wyjscie (Babl wynikow):",
            bg="#0a0a0a", fg="#569cd6",
            font=("Consolas", 9, "bold")
        ).pack(anchor="w", padx=4, pady=2)

        self.output_area = scrolledtext.ScrolledText(
            out_frame, wrap="word",
            bg="#0a0a0a", fg="#9cdcfe",
            font=("Consolas", 10), border=0, height=7
        )
        self.output_area.pack(fill="both", expand=True, padx=4, pady=2)

        # Statusbar
        self.status_var = tk.StringVar(value="Gotowy")
        tk.Label(
            self.root, textvariable=self.status_var,
            bg=self.STATUS_BG, fg="white",
            font=("Consolas", 9), anchor="w", padx=6
        ).pack(fill="x", side="bottom")

        # Bindingi
        self.text_area.bind("<<Modified>>", self._on_modified)
        self.text_area.bind("<KeyRelease>", lambda e: self._update_line_numbers())

    def _build_menu(self):
        mb = tk.Menu(self.root, bg="#2d2d2d", fg="white", tearoff=0)
        fm = tk.Menu(mb, bg="#2d2d2d", fg="white", tearoff=0)
        fm.add_command(label="Zapisz do Babla  Ctrl+S",
                       command=self._save_to_bubble)
        fm.add_command(label="Uruchom w nowym Bablu  F5",
                       command=self._run_in_bubble)
        fm.add_separator()
        fm.add_command(label="Zamknij  Ctrl+Q", command=self._on_close)
        mb.add_cascade(label="Plik", menu=fm)
        self.root.config(menu=mb)

    def _bind_keys(self):
        self.root.bind("<Control-s>", lambda e: self._save_to_bubble())
        self.root.bind("<Control-q>", lambda e: self._on_close())
        self.root.bind("<F5>",        lambda e: self._run_in_bubble())

    def _title(self) -> str:
        ct   = CONTENT_TYPE_MAP.get(self.ctx.content_type, ("?", ""))[0]
        mark = " *" if self.is_modified else ""
        return f"{self.APP_NAME} | {self.ctx.label} [{ct}]{mark}"

    # ── Tresc ─────────────────────────────────────────────────────────────────

    def _load_content(self):
        content = read_text_file(self.tmp_path) if os.path.exists(self.tmp_path) else ""
        self.text_area.insert("1.0", content)
        self._update_line_numbers()
        self.text_area.edit_modified(False)

    def _on_modified(self, event=None):
        if self.text_area.edit_modified():
            if not self.is_modified:
                self.is_modified = True
                self.root.title(self._title())
            self.text_area.edit_modified(False)

    def _update_line_numbers(self):
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", "end")
        end = self.text_area.index("end-1c")
        n   = int(end.split('.')[0])
        self.line_numbers.insert("1.0", "\n".join(str(i) for i in range(1, n+1)))
        self.line_numbers.config(state="disabled")

    # ── Operacje KarmazynOS ───────────────────────────────────────────────────

    def _save_to_bubble(self):
        """Ctrl+S — push do Babla przez rezonans."""
        content = self.text_area.get("1.0", "end-1c")
        write_text_file(self.tmp_path, content)
        result  = self.ctx.push_content(content)
        self.is_modified = False
        self.root.title(self._title())

        status = result.get("status", "?")
        if status == "absorbed":
            self.status_var.set(f"Zapisano do Babla '{self.ctx.label}'")
        elif status == "unchanged":
            self.status_var.set("Bez zmian")
        elif status == "reflected":
            coh = result.get("coherence", 0)
            self.status_var.set(
                f"Odrzucono — Babl odrzucil tresc (koherencja={coh:.3f}). "
                f"Sprobuj BUBBLE TICK {self.ctx.label} w shellu."
            )
        else:
            self.status_var.set(f"Status: {status}")

    def _run_in_bubble(self):
        """F5 — uruchom w nowym Bablu Workspace (w osobnym watku)."""
        content = self.text_area.get("1.0", "end-1c")
        write_text_file(self.tmp_path, content)

        self.output_area.delete("1.0", "end")
        self.output_area.insert("end", f"Uruchamianie '{self.ctx.label}'...\n")
        self.status_var.set("Uruchamianie...")

        def run_thread():
            try:
                result_label, exit_code, output = self.ctx.run_in_new_bubble(
                    content, self.tmp_path
                )
                def update_ui():
                    try:
                        self.output_area.delete("1.0", "end")
                        self.output_area.insert("end", output or "(brak wyjscia)")
                        self.output_area.insert(
                            "end",
                            f"\n{'─'*40}\n"
                            f"Kod wyjscia: {exit_code}\n"
                            f"Wynik w Bablu: {result_label}\n"
                        )
                        self.output_area.see("end")
                        self.status_var.set(
                            f"Zakonczone (kod={exit_code}). "
                            f"Wynik w Bablu: {result_label}"
                        )
                    except RuntimeError:
                        pass  # Okno juz zamkniete

                try:
                    self.root.after(0, update_ui)
                except RuntimeError:
                    pass  # Tkinter mainloop nie dziala
            except Exception as e:
                try:
                    self.root.after(0, lambda: self.status_var.set(f"Blad: {e}"))
                except RuntimeError:
                    pass

        threading.Thread(target=run_thread, daemon=True).start()

    def _on_close(self):
        if self.is_modified:
            if messagebox.askyesno("Wyjscie", "Zapisac zmiany do Babla?"):
                self._save_to_bubble()
        self.root.quit()

    def run(self):
        self.root.mainloop()


# ─── Publiczne API dla shell.py ───────────────────────────────────────────────

def open_bubble(label: str, runtime: 'SanctuaryRuntime',
                force_type: Optional[str] = None,
                mode: str = "tui") -> str:
    """
    Otwiera Babl w NooEdit.
    Wywolywane z shella: NOOEDIT <label>

    label      — etykieta Babla
    runtime    — SanctuaryRuntime
    force_type — wymusz typ: 'py'|'lua'|'md'|'txt'|'karm'
    mode       — 'auto'|'gui'|'tui'

    Zwraca: 'ok' lub komunikat bledu
    """
    # Stworz Babl jesli nie istnieje
    if label not in runtime._bubbles:
        runtime.write(label, label, "bubble_init", 1.0)
        runtime.consolidate(label)

    bubble = runtime._bubbles.get(label)
    if bubble is None:
        return f"Nie mozna otworzyc Babla '{label}'"

    # Wykryj typ tresci
    phi_vec = bubble.phi1.signature.tolist() if bubble.phi1 else None
    ctype   = force_type or detect_content_type(phi_vec, label)

    # Stworz kontekst
    ctx = NooContext(label, runtime, ctype)

    # Materializuj Babl do pliku tymczasowego
    content  = ctx.get_content()
    tmp_path = ctx.vfs.materialize(label, content, ctype)

    ct_name = CONTENT_TYPE_MAP.get(ctype, ("?", ""))[0]
    print(f"NooEdit: {label} [{ct_name}] -> {tmp_path}")

    # Wybierz tryb — domyslnie TUI (terminal), GUI tylko gdy jawnie zadane
    if mode == "gui":
        use_gui = HAS_GUI
    else:
        use_gui = False

    if use_gui and HAS_GUI:
        NooEditGUI(ctx, tmp_path).run()
    elif HAS_TUI:
        NooEditTUI(ctx, tmp_path).run()
    else:
        return "Brak prompt_toolkit i tkinter. Zainstaluj jedno z nich."

    # Po zamknieciu edytora: synchronizuj plik tymczasowy z Bablem
    final_content = ctx.vfs.read_back(label, ctype)
    if final_content:
        result = ctx.push_content(final_content)
        # Usun tylko plik tymczasowy — content store (.bubbles/content/) zostaje
        ctx.vfs.cleanup(label, ctype)

    return "ok"


# ─── Komenda shella ───────────────────────────────────────────────────────────

def cmd_nooedit(args, runtime=None) -> str:
    """
    Komenda NOOEDIT dla shell.py.
    Rejestracja: reg("NOOEDIT", lambda a: cmd_nooedit(a, RUNTIME), ...)

    NOOEDIT <label>           -- otworz Babl w NooEdit
    NOOEDIT <label> --gui     -- wymus GUI
    NOOEDIT <label> --tui     -- wymus TUI
    NOOEDIT <label> --py      -- wymus typ Python
    NOOEDIT <label> --lua     -- wymus typ Lua
    NOOEDIT <label> --md      -- wymus typ Markdown
    """
    if runtime is None:
        return "Brak runtime. Zarejestruj NOOEDIT z lambda."

    # Rozdziel etykiete od flag
    label      = None
    mode       = "tui"
    force_type = None

    for arg in args:
        if arg == "--gui":        mode = "gui"
        elif arg == "--tui":      mode = "tui"
        elif arg == "--py":       force_type = "py"
        elif arg == "--lua":      force_type = "lua"
        elif arg == "--md":       force_type = "md"
        elif arg == "--karm":     force_type = "karm"
        elif arg == "--txt":      force_type = "txt"
        elif not arg.startswith("--"):
            label = arg

    if label is None:
        return "Uzycie: NOOEDIT <label> [--gui|--tui] [--py|--lua|--md|--karm]"

    return open_bubble(label, runtime, force_type=force_type, mode=mode)


# ─── Standalone (bez KarmazynOS) ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NooEdit — KarmazynOS Editor")
    parser.add_argument("files", nargs="*", help="Pliki do otwarcia")
    parser.add_argument("--gui",  action="store_true")
    parser.add_argument("--tui",  action="store_true")
    parsed = parser.parse_args()

    # Tryb standalone — klasyczny edytor plikow
    use_gui = bool(parsed.gui or (
        not parsed.tui and HAS_GUI and (
            os.environ.get("DISPLAY") or
            os.environ.get("WAYLAND_DISPLAY") or
            os.name == 'nt'
        )
    ))

    file_path = parsed.files[0] if parsed.files else "notatka.txt"

    print(f"NooEdit standalone: {file_path}")

    # Standalone: uzywamy oryginalnych klas AstraEdit
    # (brak runtime → dzialamy jak zwykly edytor)
    class _StandaloneCtx:
        label        = pathlib.Path(file_path).name
        content_type = detect_content_type(None, file_path)
        def push_content(self, c): return {"status": "file"}
        def run_in_new_bubble(self, c, p):
            cmd = _get_run_command(p)
            r   = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return f"[standalone_run]", r.returncode, r.stdout + r.stderr

    ctx          = _StandaloneCtx()
    ctx.vfs      = BubbleVFS()
    ctx.runtime  = None

    if use_gui and HAS_GUI:
        NooEditGUI(ctx, file_path).run()
    elif HAS_TUI:
        NooEditTUI(ctx, file_path).run()
    else:
        print("Brak tkinter i prompt_toolkit.")
        sys.exit(1)