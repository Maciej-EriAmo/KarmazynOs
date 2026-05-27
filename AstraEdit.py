#!/usr/bin/env python3
"""
AstraEdit.py — AstraEdit 5.1.1 KarmazynOS Edition (FIX)
========================================================
Edytor plików z integracją phi-space.

FIX v5.1.1:
  - Usunięto martwy kod po return w is_binary_file()
  - Dodano brakującą funkcję _print_status() (używaną w __main__)
"""

import argparse
import json
import os
import pathlib
import queue
import re
import subprocess
import sys
import threading
import time
from typing import Any, Optional, Tuple

# ── Importy wewnętrzne KarmazynOS ─────────────────────────────────────────────
from karmazyn_vfs import BubbleVFS
from karmazyn_sdl_utils import FileWatcher, is_sdl_mode, find_external_editor


def read_text_file_smart(path: str):
    """Wczytaj plik z detekcją kodowania. Zwraca (content, encoding)."""
    if is_binary_file(path):
        raise ValueError("Plik binarny")
    for enc in ("utf-8", "utf-8-sig", "cp1250", "latin-1", "iso-8859-2"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(), "utf-8 (zastępcze)"

def read_text_file(path: str) -> str:
    """Wczytaj plik tekstowy ze smart detekcją kodowania."""
    content, _ = read_text_file_smart(path)
    return content

def write_text_file(path: str, text: str, encoding: str = "utf-8"):
    """Zapisz plik tekstowy."""
    os.makedirs(pathlib.Path(path).parent, exist_ok=True)
    with open(path, "w", encoding=encoding, errors="replace") as f:
        f.write(text)

def _silent():
    """Kontekst tłumiący stdout/stderr."""
    import contextlib, io
    return contextlib.redirect_stdout(io.StringIO())



APP_NAME   = "AstraEdit 5.1 — KarmazynOS Edition"
APP_SHORT  = "AstraEdit"
DEFAULT_FILE = "notatka.txt"
CONFIG_FILE  = __import__("pathlib").Path.home() / ".astraedit_config.json"


class PhiAdapter:
    """
    Cienka warstwa między AstraEdit a runtime KarmazynOS.
    Działa z SanctuaryRuntime, PhiSpace lub bez runtime (fallback).

    Zasada: AstraEdit nie wie nic o phi-space. Wie tylko o PhiAdapter.
    """

    T_OPEN   = 80.0   # plik właśnie otwarty
    T_EDIT   = 92.0   # plik aktywnie edytowany
    T_SAVE   = 70.0   # plik zapisany
    T_CLOSE  = 45.0   # plik zamknięty (stygnie)
    T_RUN    = 95.0   # wynik uruchomienia skryptu

    def __init__(self, runtime=None):
        self._rt  = runtime
        self._phi = self._find_phi(runtime)

    def _find_phi(self, rt):
        if rt is None: return None
        return (getattr(rt, "phi", None) or
                getattr(rt, "matrix", None))

    # ── Atomy plików ─────────────────────────────────────────────────────────

    def _file_atom_id(self, path: str) -> str:
        """Deterministyczne id atomu dla ścieżki pliku."""
        name = pathlib.Path(path).name
        slug = re.sub(r"[^a-z0-9]", "_", name.lower())[:24]
        return f"file.{slug}"

    def file_opened(self, path: str):
        """Plik otwarty — ogrzej lub utwórz atom."""
        self._touch_file_atom(path, self.T_OPEN,
                              f"open:{pathlib.Path(path).name}")

    def file_edited(self, path: str):
        """Plik edytowany — dodaj ciepło."""
        self._touch_file_atom(path, self.T_EDIT, "edit")

    def file_saved(self, path: str):
        """Plik zapisany."""
        self._touch_file_atom(path, self.T_SAVE, "save")

    def file_closed(self, path: str):
        """Plik zamknięty — schłodź atom."""
        self._touch_file_atom(path, self.T_CLOSE, "close")

    def script_output(self, path: str, output: str, exit_code: int) -> str:
        """Zapisz output skryptu jako atom. Zwraca atom_id."""
        if not self._phi or not self._rt: return ""
        atom_id = f"run.{self._file_atom_id(path)}.{int(time.time())}"
        summary = output[:256] if output else f"exit:{exit_code}"
        try:
            self._create_or_update(atom_id, "script_output", summary, self.T_RUN)
        except Exception: pass
        return atom_id

    def hot_files(self, n: int = 10) -> list:
        """Zwraca n najgorętszych plików (ostatnio używanych)."""
        if not self._phi: return []
        try:
            atoms = [a for a in self._phi.matrix.atoms()
                     if getattr(a, "S", "") == "file" and not a.is_dead()]
            atoms.sort(key=lambda a: -a.T)
            return [a.E for a in atoms[:n]]
        except Exception: return []

    def file_temp(self, path: str) -> float:
        """Pobierz aktualną temperaturę atomu pliku."""
        if not self._phi: return 0.0
        try:
            atom = self._phi.matrix.get(self._file_atom_id(path))
            return float(atom.T) if atom else 0.0
        except Exception: return 0.0

    def phi_summary(self) -> str:
        """Krótki status phi-space do status bara."""
        if not self._phi: return ""
        try:
            s = self._phi.matrix.stats()
            return (f"φ HOT:{s.get('HOT',0)} "
                    f"WARM:{s.get('WARM',0)} "
                    f"COLD:{s.get('COLD',0)}")
        except Exception: return ""

    # ── Wewnętrzne ────────────────────────────────────────────────────────────

    def _touch_file_atom(self, path: str, T: float, note: str):
        if not self._phi or not self._rt: return
        atom_id = self._file_atom_id(path)
        E       = str(pathlib.Path(path).resolve())
        try:
            self._create_or_update(atom_id, "file", E, T)
        except Exception: pass

    def _create_or_update(self, atom_id: str, S: str, E: str, T: float):
        phi = self._phi
        if phi.matrix.has(atom_id):
            atom = phi.matrix.get(atom_id)
            if atom:
                if T > atom.T: atom.heat(T - atom.T)
                else:          atom.cool(atom.T - T)
        else:
            if hasattr(self._rt, "create_atom"):
                self._rt.create_atom(atom_id, S, E, T)
            elif hasattr(phi, "create_atom"):
                phi.create_atom(atom_id, S=S, E=E, T=T)


# ── BubbleVFS (z NooEdit) ─────────────────────────────────────────────────────

def is_binary_file(filepath: str) -> bool:
    """Sprawdza czy plik jest binarny (zawiera bajt null w pierwszych 1024B)."""
    try:
        with open(filepath, "rb") as f:
            return b"\x00" in f.read(1024)
    except Exception:
        return False
    # FIX: usunięto martwy kod (fragment write_text_file wklejony po return)

# ── Pygments ──────────────────────────────────────────────────────────────────

try:
    from pygments.lexers import get_lexer_for_filename, TextLexer
    from pygments.util import ClassNotFound
    _HAS_PYGMENTS = True
except ImportError:
    _HAS_PYGMENTS = False
    get_lexer_for_filename = None

def _get_lexer(filename: str):
    if not _HAS_PYGMENTS: return None
    try:    return get_lexer_for_filename(filename)
    except Exception: return TextLexer()


# ── FileWatcher (z NooEdit) ───────────────────────────────────────────────────

class EditorTab:
    """Pojedyncza karta edytora — plik jako atom phi-space."""

    def __init__(self, parent, file_path: str, app):
        self.app           = app
        self.phi           = app.phi            # PhiAdapter
        self.file_path     = str(pathlib.Path(file_path).resolve())
        self.is_modified   = False
        self.file_encoding = "utf-8"
        self.is_readonly   = False
        self._last_edit_t  = 0.0
        self._edit_debounce: Optional[str] = None  # after() id

        self.frame = tk.Frame(parent, bg=app.bg_color)

        container = tk.Frame(self.frame, bg=app.bg_color)
        container.pack(fill="both", expand=True)

        self.line_numbers = tk.Text(
            container, width=4, padx=3, takefocus=0, border=0,
            bg=app.line_num_bg, fg=app.line_num_fg,
            state="disabled", font=("Consolas", 11))
        self.line_numbers.pack(side="left", fill="y")

        self.text_area = scrolledtext.ScrolledText(
            container, wrap="word", undo=True,
            bg=app.bg_color, fg=app.fg_color,
            insertbackground=app.cursor_color,
            selectbackground=app.selection_color,
            font=("Consolas", 11), border=0)
        self.text_area.pack(side="left", fill="both", expand=True)

        self.text_area.vbar.config(command=self._on_scrollbar)
        self.line_numbers.config(yscrollcommand=self.text_area.vbar.set)

        # Tagi kolorowania
        for tag, color in {
            "Keyword":"#569cd6","Name.Builtin":"#dcdcaa",
            "Comment":"#6a9955","String":"#ce9178",
            "Number":"#b5cea8","Operator":"#d4d4d4",
        }.items():
            self.text_area.tag_config(tag, foreground=color)
        self.text_area.tag_config("matching_bracket",
                                  background="#404040", borderwidth=1)

        self.text_area.bind("<<Modified>>",   self._on_modified)
        self.text_area.bind("<KeyRelease>",   self._on_key)
        self.text_area.bind("<Button-1>",
            lambda e: app.root.after(10, self._update_combined))

        self._load_file()
        self.phi.file_opened(self.file_path)

    def _load_file(self):
        if not os.path.exists(self.file_path): return
        if is_binary_file(self.file_path):
            self.text_area.insert("1.0", "# BLAD: Plik binarny\n")
            return
        try:
            content, self.file_encoding = read_text_file_smart(self.file_path)
            self.text_area.insert("1.0", content)
            self._update_syntax()
            if not os.access(self.file_path, os.W_OK):
                self.is_readonly = True
                self.text_area.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Blad", f"Nie mozna wczytac: {e}")
        self._update_line_numbers()

    def _on_scrollbar(self, *args):
        self.text_area.yview(*args)
        self.line_numbers.yview(*args)

    def _on_modified(self, event=None):
        if self.text_area.edit_modified():
            if not self.is_modified:
                self.is_modified = True
                self.app.update_tab_title(self)
            self.text_area.edit_modified(False)
            # Debounce phi heat — max co 2s
            if time.time() - self._last_edit_t > 2.0:
                self._last_edit_t = time.time()
                self.phi.file_edited(self.file_path)
                self.app._refresh_status()

    def _on_key(self, event=None):
        self._update_line_numbers()
        self.app.update_cursor_position()
        self._highlight_brackets()
        t = time.time()
        if t - self._last_edit_t > 1.0:
            self._update_syntax()
            self._last_edit_t = t

    def _update_combined(self):
        self._update_line_numbers()
        self.app.update_cursor_position()

    def _update_line_numbers(self):
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", "end")
        end   = self.text_area.index("end-1c")
        count = int(end.split(".")[0])
        self.line_numbers.insert("1.0", "\n".join(str(i) for i in range(1, count+1)))
        self.line_numbers.config(state="disabled")
        try:
            self.line_numbers.yview_moveto(self.text_area.yview()[0])
        except Exception: pass

    def _highlight_brackets(self):
        self.text_area.tag_remove("matching_bracket", "1.0", tk.END)
        pos = self.text_area.index(tk.INSERT)
        brackets  = {"(":")",  "[":"]",  "{":"}", "<":">"}
        rev       = {v: k for k, v in brackets.items()}
        MAX = 2000
        try:
            cb = self.text_area.get(f"{pos}-1c", pos)
            ca = self.text_area.get(pos, f"{pos}+1c")
        except Exception: return
        if cb in rev: self._find_opening(f"{pos}-1c", cb, rev[cb], MAX)
        elif ca in brackets: self._find_closing(pos, ca, brackets[ca], MAX)

    def _find_closing(self, start, ob, cb, mx):
        count = 1; p = start; n = 0
        while n < mx:
            n += 1; p = f"{p}+1c"
            if self.text_area.compare(p, ">=", tk.END): break
            ch = self.text_area.get(p, f"{p}+1c")
            if ch == ob: count += 1
            elif ch == cb:
                count -= 1
                if count == 0:
                    self.text_area.tag_add("matching_bracket", start, f"{start}+1c")
                    self.text_area.tag_add("matching_bracket", p, f"{p}+1c")
                    break

    def _find_opening(self, start, cb, ob, mx):
        count = 1; p = start; n = 0
        while n < mx:
            n += 1
            if self.text_area.compare(p, "<=", "1.0"): break
            p = f"{p}-1c"
            ch = self.text_area.get(p, f"{p}+1c")
            if ch == cb: count += 1
            elif ch == ob:
                count -= 1
                if count == 0:
                    self.text_area.tag_add("matching_bracket", p, f"{p}+1c")
                    self.text_area.tag_add("matching_bracket", start, f"{start}+1c")
                    break

    def _update_syntax(self):
        if not _HAS_PYGMENTS: return
        content = self.text_area.get("1.0", "end-1c")
        for tag in self.text_area.tag_names():
            if tag not in ("sel", "matching_bracket"):
                self.text_area.tag_remove(tag, "1.0", "end")
        lexer = _get_lexer(self.file_path)
        if not lexer: return
        try:
            li = 1; ci = 0
            for token, text in lexer.get_tokens(content):
                ts = str(token)
                tag = None
                if "Keyword" in ts:    tag = "Keyword"
                elif "Comment" in ts:  tag = "Comment"
                elif "String" in ts:   tag = "String"
                elif "Number" in ts:   tag = "Number"
                elif "Builtin" in ts:  tag = "Name.Builtin"
                si = f"{li}.{ci}"
                lines = text.split("\n")
                if len(lines) > 1:
                    li += len(lines) - 1
                    ci  = len(lines[-1])
                else:
                    ci += len(text)
                ei = f"{li}.{ci}"
                if tag:
                    self.text_area.tag_add(tag, si, ei)
        except Exception: pass

    def save(self) -> bool:
        if self.is_readonly: return False
        try:
            content = self.text_area.get("1.0", "end-1c")
            write_text_file(self.file_path, content, self.file_encoding)
            self.is_modified = False
            self.app.update_tab_title(self)
            self.phi.file_saved(self.file_path)
            self.app._refresh_status()
            return True
        except Exception as e:
            messagebox.showerror("Blad zapisu", str(e))
            return False

    def on_close(self):
        self.phi.file_closed(self.file_path)

    def get_short_name(self) -> str:
        return pathlib.Path(self.file_path).name


try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
    _HAS_TK = True
except ImportError:
    tk     = None
    _HAS_TK = False

class AstraEditGUI:
    """Tryb graficzny — Tkinter z phi-space integration."""

    def __init__(self, file_paths=None, runtime=None):
        self.phi  = PhiAdapter(runtime)
        self._vfs = BubbleVFS()
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} [GUI]")
        self.root.geometry("1200x820")

        # Dark mode
        self.bg_color        = "#1e1e1e"
        self.fg_color        = "#d4d4d4"
        self.cursor_color    = "#ffffff"
        self.selection_color = "#264f78"
        self.line_num_bg     = "#252526"
        self.line_num_fg     = "#858585"
        self.console_bg      = "#111111"
        self.console_fg      = "#cccccc"

        self.autosave_enabled  = True
        self.autosave_interval = 30000
        self.find_window       = None
        self.last_search       = ""
        self.use_regex         = False
        self._tabs: list       = []
        self.process           = None
        self.msg_queue: queue.Queue = queue.Queue()

        self._setup_ui()
        self._setup_menu()
        self._setup_bindings()

        # Otwórz pliki
        if file_paths:
            for fp in file_paths:
                self.open_file(fp)
        else:
            self.new_tab()

        if self.autosave_enabled:
            self._schedule_autosave()

        self.root.after(100, self._process_queue)
        self.root.after(5000, self._phi_tick)  # odświeżanie phi co 5s

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.paned = tk.PanedWindow(
            self.root, orient=tk.VERTICAL, sashwidth=4, bg="#333333")
        self.paned.pack(fill="both", expand=True)

        # Edytor
        ec = tk.Frame(self.paned, bg=self.bg_color)
        self.paned.add(ec, stretch="always", height=520)

        style = ttk.Style(); style.theme_use("default")
        style.configure("TNotebook",     background=self.bg_color, borderwidth=0)
        style.configure("TNotebook.Tab", background="#2d2d2d",
                        foreground=self.fg_color, padding=[10, 5], borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", "#007acc")])

        self.notebook = ttk.Notebook(ec)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<ButtonPress-1>", self._on_tab_click)
        self.notebook.bind("<Button-3>",      self._show_tab_ctx)

        self._tab_ctx = tk.Menu(self.root, tearoff=0,
                                bg=self.bg_color, fg=self.fg_color)
        self._tab_ctx.add_command(label="Zamknij karte",     command=self.close_current_tab)
        self._tab_ctx.add_command(label="Zamknij inne",      command=self._close_other_tabs)
        self._tab_ctx.add_command(label="Zamknij wszystkie", command=self._close_all_tabs)

        # Konsola interaktywna
        cf = tk.Frame(self.paned, bg=self.console_bg)
        self.paned.add(cf, stretch="never", height=260)

        toolbar = tk.Frame(cf, bg="#252526", height=28)
        toolbar.pack(fill="x", side="top")
        tk.Label(toolbar, text="Konsola Interaktywna", bg="#252526", fg="white",
                 font=("Arial", 9, "bold")).pack(side="left", padx=8)
        tk.Button(toolbar, text="Wyczysc", command=self._clear_console,
                  bg="#404040", fg="white", border=0,
                  font=("Arial", 8), padx=8, pady=2).pack(side="right", padx=5, pady=3)
        self.stop_btn = tk.Button(
            toolbar, text="STOP", command=self.stop_process,
            bg="#8b0000", fg="white", border=0,
            font=("Arial", 8, "bold"), state="disabled", padx=8, pady=2)
        self.stop_btn.pack(side="right", padx=5, pady=3)

        self.console_area = scrolledtext.ScrolledText(
            cf, bg=self.console_bg, fg=self.console_fg,
            font=("Consolas", 10), state="disabled", border=0)
        self.console_area.pack(fill="both", expand=True)
        self.console_area.tag_config("stderr", foreground="#ff6b6b")
        self.console_area.tag_config("stdin",  foreground="#00ff00")
        self.console_area.tag_config("info",   foreground="#61afef")

        inp_frame = tk.Frame(cf, bg=self.console_bg, height=30)
        inp_frame.pack(fill="x", side="bottom")
        tk.Label(inp_frame, text=">>> ", bg=self.console_bg, fg="#00ff00",
                 font=("Consolas", 10, "bold")).pack(side="left", padx=5)
        self.input_entry = tk.Entry(
            inp_frame, bg=self.console_bg, fg="white",
            insertbackground="white", font=("Consolas", 10), border=0)
        self.input_entry.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        self.input_entry.bind("<Return>", self._send_input)

        # Status bar — zawiera phi summary
        self.status_var = tk.StringVar(value="Gotowy")
        self.status_bar = tk.Label(
            self.root, textvariable=self.status_var,
            bg="#007acc", fg="white", anchor="w", padx=5, font=("Arial", 9))
        self.status_bar.pack(side="bottom", fill="x")

    def _setup_menu(self):
        mb = tk.Menu(self.root, bg=self.bg_color, fg=self.fg_color)

        # Plik
        fm = tk.Menu(mb, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        fm.add_command(label="Nowa karta  Ctrl+N",      command=self.new_tab)
        fm.add_command(label="Otworz...   Ctrl+O",      command=self._open_dialog)
        fm.add_separator()
        fm.add_command(label="Zapisz      Ctrl+S",      command=self.save_current)
        fm.add_command(label="Zapisz jako F2",          command=self._save_as)
        fm.add_command(label="Zapisz wszystko",         command=self._save_all)
        fm.add_separator()
        self._add_recent_menu(fm)
        fm.add_separator()
        fm.add_command(label="Zamknij karte  Ctrl+W",   command=self.close_current_tab)
        fm.add_command(label="Wyjscie",                 command=self._on_close)
        mb.add_cascade(label="Plik", menu=fm)

        # Edycja
        em = tk.Menu(mb, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        em.add_command(label="Cofnij       Ctrl+Z",     command=self._undo)
        em.add_command(label="Ponow        Ctrl+Y",     command=self._redo)
        em.add_separator()
        em.add_command(label="Znajdz       Ctrl+F",     command=self._show_find)
        em.add_command(label="Zamien       Ctrl+H",     command=self._show_replace)
        em.add_command(label="Idz do linii Ctrl+G",     command=self._goto_line)
        mb.add_cascade(label="Edycja", menu=em)

        # Uruchom
        rm = tk.Menu(mb, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        rm.add_command(label="Uruchom  F5",             command=self._run_file)
        rm.add_command(label="Zatrzymaj",               command=self.stop_process)
        rm.add_separator()
        rm.add_command(label="Wyczysc konsole",         command=self._clear_console)
        mb.add_cascade(label="Uruchom", menu=rm)

        # Phi-space
        pm = tk.Menu(mb, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        pm.add_command(label="Pokaz gorące pliki",  command=self._show_hot_files)
        pm.add_command(label="Status phi-space",    command=self._show_phi_status)
        mb.add_cascade(label="Phi-space", menu=pm)

        # Widok
        vm = tk.Menu(mb, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        self._autosave_var = tk.BooleanVar(value=self.autosave_enabled)
        vm.add_checkbutton(label="Auto-zapisywanie (30s)",
                           variable=self._autosave_var,
                           command=lambda: setattr(self, "autosave_enabled",
                                                   self._autosave_var.get()))
        mb.add_cascade(label="Widok", menu=vm)

        # Pomoc
        hm = tk.Menu(mb, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        hm.add_command(label="Skroty  F1",          command=self._show_help)
        hm.add_command(label="O programie",         command=self._show_about)
        mb.add_cascade(label="Pomoc", menu=hm)

        self.root.config(menu=mb)

    def _setup_bindings(self):
        for key, cmd in [
            ("<Control-n>", self.new_tab),
            ("<Control-o>", self._open_dialog),
            ("<Control-s>", self.save_current),
            ("<Control-w>", self.close_current_tab),
            ("<F2>",        self._save_as),
            ("<F1>",        self._show_help),
            ("<F5>",        self._run_file),
            ("<Control-f>", self._show_find),
            ("<Control-h>", self._show_replace),
            ("<Control-g>", self._goto_line),
            ("<F3>",        self._find_next),
            ("<Control-z>", self._undo),
            ("<Control-y>", self._redo),
        ]:
            self.root.bind(key, lambda e, c=cmd: c())

        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self.update_cursor_position())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Phi-space UI ──────────────────────────────────────────────────────────

    def _refresh_status(self):
        tab = self._get_tab()
        if not tab:
            self.status_var.set(f"Gotowy | {self.phi.phi_summary()}")
            return
        row = col = "?"
        try:
            r, c = tab.text_area.index(tk.INSERT).split(".")
            total = tab.text_area.index("end-1c").split(".")[0]
            row, col = f"{r}/{total}", str(int(c)+1)
        except Exception: pass
        T_str = ""
        T = self.phi.file_temp(tab.file_path)
        if T > 0:
            bar = "▓" * int(T / 10) + "░" * (10 - int(T / 10))
            T_str = f" | φ[{bar}]{T:.0f}°"
        phi = self.phi.phi_summary()
        self.status_var.set(
            f"Ln {row}, Col {col}{T_str}"
            f" | {tab.file_encoding} | {tab.get_short_name()}"
            f" | {phi} | F5:Uruchom F1:Pomoc")

    def _phi_tick(self):
        """Odśwież phi summary w status bar co 5s."""
        self._refresh_status()
        self.root.after(5000, self._phi_tick)

    def _show_hot_files(self):
        hot = self.phi.hot_files(10)
        win = tk.Toplevel(self.root)
        win.title("Gorace pliki (phi-space)")
        win.geometry("600x350")
        win.configure(bg=self.bg_color)
        tk.Label(win, text="Ostatnio uzywane (wg temperatury phi):",
                 bg=self.bg_color, fg=self.fg_color,
                 font=("Arial", 11, "bold")).pack(pady=10, padx=10, anchor="w")
        for path in hot:
            T = self.phi.file_temp(path)
            bar = "▓" * int(T/10) + "░" * (10 - int(T/10))
            txt = f"  [{bar}]{T:3.0f}°  {pathlib.Path(path).name}"
            row = tk.Frame(win, bg=self.bg_color)
            row.pack(fill="x", padx=10, pady=2)
            tk.Label(row, text=txt, bg=self.bg_color, fg="#9cdcfe",
                     font=("Consolas", 10), anchor="w").pack(side="left")
            tk.Button(row, text="Otworz",
                      command=lambda p=path: (self.open_file(p), win.destroy()),
                      bg="#007acc", fg="white", border=0, padx=8).pack(side="right")
        tk.Button(win, text="Zamknij", command=win.destroy,
                  bg="#555", fg="white", padx=15, pady=6, border=0).pack(pady=10)

    def _show_phi_status(self):
        s = self.phi.phi_summary()
        messagebox.showinfo("Phi-space", s or "Runtime niedostepny")

    # ── Zakładki ──────────────────────────────────────────────────────────────

    def new_tab(self, file_path=None):
        if file_path is None:
            file_path = DEFAULT_FILE
            i = 1
            while any(t.file_path == str(pathlib.Path(file_path).resolve())
                      for t in self._tabs):
                file_path = f"notatka_{i}.txt"; i += 1
        tab = EditorTab(self.notebook, file_path, self)
        self._tabs.append(tab)
        self.notebook.add(tab.frame, text=self._tab_title(tab))
        self.notebook.select(tab.frame)
        return tab

    def _tab_title(self, tab) -> str:
        t = tab.get_short_name()
        if tab.is_modified: t = "* " + t
        if tab.is_readonly:  t += " [R]"
        T = self.phi.file_temp(tab.file_path)
        if T >= 70: t = t + " ●"
        return t + "  x"

    def update_tab_title(self, tab):
        try:
            self.notebook.tab(self.notebook.index(tab.frame),
                              text=self._tab_title(tab))
        except Exception: pass

    def _get_tab(self):
        try:
            cur = self.notebook.nametowidget(self.notebook.select())
            for t in self._tabs:
                if t.frame == cur: return t
        except Exception: pass
        return None

    def _on_tab_click(self, event):
        try:
            idx = self.notebook.tk.call(self.notebook._w,"identify","tab",event.x,event.y)
            if idx == "": return
            x, y, w, h = self.notebook.bbox(idx)
            if event.x > x + w - 25:
                frame = self.notebook.nametowidget(self.notebook.tabs()[idx])
                for t in self._tabs:
                    if t.frame == frame: self._close_tab(t); break
        except Exception: pass

    def _show_tab_ctx(self, event):
        try: self._tab_ctx.tk_popup(event.x_root, event.y_root)
        finally: self._tab_ctx.grab_release()

    def _close_tab(self, tab):
        if tab.is_modified:
            self.notebook.select(tab.frame)
            r = messagebox.askyesnocancel(
                "Niezapisane", f"Zapisac {tab.get_short_name()}?")
            if r is None: return
            if r and not tab.save(): return
        tab.on_close()
        self._tabs.remove(tab)
        self.notebook.forget(tab.frame)
        if not self._tabs: self.new_tab()

    def close_current_tab(self):
        t = self._get_tab()
        if t: self._close_tab(t)

    def _close_other_tabs(self):
        cur = self._get_tab()
        if not cur: return
        for t in [x for x in self._tabs if x != cur]:
            self._close_tab(t)

    def _close_all_tabs(self):
        while self._tabs: self._close_tab(self._tabs[0])

    # ── Pliki ─────────────────────────────────────────────────────────────────

    def _open_dialog(self):
        paths = filedialog.askopenfilenames(title="Otworz")
        for p in paths: self.open_file(p)

    def open_file(self, file_path: str):
        file_path = str(pathlib.Path(file_path).resolve())
        for t in self._tabs:
            if t.file_path == file_path:
                self.notebook.select(t.frame); return
        if is_binary_file(file_path):
            messagebox.showerror("Blad", "Plik binarny"); return
        self.new_tab(file_path)
        self._save_recent(file_path)

    def save_current(self):
        t = self._get_tab()
        if t and t.save():
            self.status_var.set(f"Zapisano: {t.get_short_name()}")

    def _save_as(self):
        t = self._get_tab()
        if not t: return
        path = filedialog.asksaveasfilename(
            initialfile=t.get_short_name(),
            initialdir=pathlib.Path(t.file_path).parent)
        if path:
            t.file_path = str(pathlib.Path(path).resolve())
            t.is_readonly = False
            t.text_area.config(state="normal")
            if t.save():
                self.update_tab_title(t)
                self._save_recent(t.file_path)

    def _save_all(self):
        n = sum(1 for t in self._tabs
                if t.is_modified and not t.is_readonly and t.save())
        self.status_var.set(f"Zapisano {n} plikow")

    # ── Uruchamianie ──────────────────────────────────────────────────────────

    def _run_file(self):
        tab = self._get_tab()
        if not tab: return
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Info", "Proces juz dziala."); return
        if not tab.save(): return

        self._clear_console()
        self._log("="*60 + "\n", "info")
        self._log(f"  Uruchamianie: {tab.get_short_name()}\n", "info")
        self._log("="*60 + "\n\n", "info")
        self.stop_btn.config(state="normal", bg="#ff3333")
        self.input_entry.focus()

        threading.Thread(target=self._run_subprocess,
                         args=(tab.file_path,), daemon=True).start()

    def _run_subprocess(self, file_path: str):
        output_lines = []
        try:
            cmd = ([sys.executable, "-u", file_path]
                   if file_path.endswith(".py") else [file_path])
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.PIPE, text=True, bufsize=1,
                cwd=pathlib.Path(file_path).parent)
            threading.Thread(
                target=self._reader,
                args=(self.process.stdout, None, output_lines), daemon=True).start()
            threading.Thread(
                target=self._reader,
                args=(self.process.stderr, "stderr", output_lines), daemon=True).start()
            self.process.wait()
            self.msg_queue.put(("text", f"\n{'='*60}\n  Zakończono (kod: {self.process.returncode})\n{'='*60}\n", "info"))
            # Zapisz output jako atom phi-space
            full_output = "".join(output_lines)
            self.phi.script_output(file_path, full_output, self.process.returncode)
        except Exception as e:
            self.msg_queue.put(("text", f"\nBlad: {e}\n", "stderr"))
        finally:
            self.msg_queue.put(("status", "stopped", None))

    def _reader(self, stream, tag, collector: list):
        try:
            for line in iter(stream.readline, ""):
                if line:
                    collector.append(line)
                    self.msg_queue.put(("text", line, tag))
        except Exception: pass
        finally:
            try: stream.close()
            except Exception: pass

    def _process_queue(self):
        try:
            while True:
                mt, content, tag = self.msg_queue.get_nowait()
                if mt == "text": self._log(content, tag)
                elif mt == "status" and content == "stopped":
                    self.stop_btn.config(state="disabled", bg="#8b0000")
                    self.process = None
        except queue.Empty: pass
        self.root.after(100, self._process_queue)

    def stop_process(self):
        if self.process and self.process.poll() is None:
            self.process.kill()
            self._log("\n Zatrzymano przez uzytkownika.\n", "stderr")
            self.stop_btn.config(state="disabled", bg="#8b0000")
            self.process = None

    def _log(self, text: str, tag=None):
        self.console_area.config(state="normal")
        self.console_area.insert(tk.END, text, tag)
        self.console_area.see(tk.END)
        self.console_area.config(state="disabled")

    def _send_input(self, event):
        text = self.input_entry.get()
        self.input_entry.delete(0, tk.END)
        if not text: return
        if self.process and self.process.poll() is None:
            try:
                self._log(f"{text}\n", "stdin")
                self.process.stdin.write(text + "\n")
                self.process.stdin.flush()
            except Exception as e:
                self._log(f"Blad stdin: {e}\n", "stderr")
        else:
            self._log("Proces nie dziala.\n", "stderr")

    def _clear_console(self):
        self.console_area.config(state="normal")
        self.console_area.delete("1.0", tk.END)
        self.console_area.config(state="disabled")

    # ── Find/Replace ──────────────────────────────────────────────────────────

    def _show_find(self):
        if self.find_window and tk.Toplevel.winfo_exists(self.find_window):
            self.find_window.focus(); return
        self.find_window = w = tk.Toplevel(self.root)
        w.title("Znajdz"); w.geometry("480x150")
        w.configure(bg=self.bg_color); w.transient(self.root)
        tk.Label(w, text="Szukaj:", bg=self.bg_color, fg=self.fg_color).pack(pady=5)
        self.find_entry = tk.Entry(w, width=60, bg=self.line_num_bg,
                                   fg=self.fg_color, insertbackground=self.cursor_color)
        self.find_entry.pack(pady=5, padx=10)
        self.find_entry.insert(0, self.last_search); self.find_entry.focus()
        self.find_entry.select_range(0, tk.END)
        self.regex_var = tk.BooleanVar(value=self.use_regex)
        tk.Checkbutton(w, text="Regex", variable=self.regex_var,
                       bg=self.bg_color, fg=self.fg_color,
                       selectcolor=self.line_num_bg).pack()
        bf = tk.Frame(w, bg=self.bg_color); bf.pack(pady=8)
        tk.Button(bf, text="Znajdz F3", command=self._find_next,
                  bg="#007acc", fg="white", border=0, padx=10, pady=5).pack(side="left", padx=5)
        tk.Button(bf, text="Zamknij", command=w.destroy,
                  bg="#555", fg="white", border=0, padx=10, pady=5).pack(side="left")
        self.find_entry.bind("<Return>", lambda e: self._find_next())
        self.find_entry.bind("<Escape>", lambda e: w.destroy())

    def _show_replace(self):
        if self.find_window and tk.Toplevel.winfo_exists(self.find_window):
            self.find_window.destroy()
        self.find_window = w = tk.Toplevel(self.root)
        w.title("Znajdz i zamien"); w.geometry("480x220")
        w.configure(bg=self.bg_color); w.transient(self.root)
        for lbl in ("Znajdz:", "Zamien na:"):
            tk.Label(w, text=lbl, bg=self.bg_color, fg=self.fg_color).pack(pady=3)
            e = tk.Entry(w, width=60, bg=self.line_num_bg,
                         fg=self.fg_color, insertbackground=self.cursor_color)
            e.pack(pady=3, padx=10)
            if lbl.startswith("Z"):
                self.find_entry   = e; e.insert(0, self.last_search); e.focus()
            else:
                self._replace_entry = e
        self.regex_var = tk.BooleanVar(value=self.use_regex)
        tk.Checkbutton(w, text="Regex", variable=self.regex_var,
                       bg=self.bg_color, fg=self.fg_color,
                       selectcolor=self.line_num_bg).pack()
        bf = tk.Frame(w, bg=self.bg_color); bf.pack(pady=8)
        tk.Button(bf, text="Zamien",
                  command=lambda: self._replace_one(self.find_entry.get(),
                                                    self._replace_entry.get()),
                  bg="#007acc", fg="white", border=0, padx=10, pady=5).pack(side="left", padx=3)
        tk.Button(bf, text="Zamien wszystkie",
                  command=lambda: self._replace_all(self.find_entry.get(),
                                                    self._replace_entry.get()),
                  bg="#0e639c", fg="white", border=0, padx=10, pady=5).pack(side="left", padx=3)
        tk.Button(bf, text="Zamknij", command=w.destroy,
                  bg="#555", fg="white", border=0, padx=10, pady=5).pack(side="left", padx=3)

    def _find_next(self):
        tab = self._get_tab()
        if not tab: return
        pattern = getattr(self, "find_entry", None)
        pattern = pattern.get() if pattern else self.last_search
        if not pattern: return
        self.last_search = pattern
        self.use_regex   = getattr(self, "regex_var", tk.BooleanVar()).get()
        tw = tab.text_area
        start = tw.index(tk.INSERT)
        try:
            start = tw.index(tk.SEL_LAST)
        except tk.TclError: pass
        pos = end_pos = None
        if self.use_regex:
            try:
                for offset, content in [("", tw.get(start, tk.END)),
                                         ("1.0:", tw.get("1.0", tk.END))]:
                    m = re.search(pattern, content, re.IGNORECASE)
                    if m:
                        base_line = int(start.split(".")[0]) if not offset else 1
                        base_col  = int(start.split(".")[1]) if not offset else 0
                        lines_b   = content[:m.start()].count("\n")
                        if lines_b:
                            col = len(content[:m.start()].rsplit("\n",1)[-1])
                        else:
                            col = m.start() + (base_col if not offset else 0)
                        pos     = f"{base_line + lines_b}.{col}"
                        end_pos = f"{pos}+{m.end()-m.start()}c"
                        break
            except re.error as e:
                messagebox.showerror("Blad regex", str(e)); return
        else:
            pos = tw.search(pattern, start, stopindex=tk.END, nocase=True)
            if not pos:
                pos = tw.search(pattern, "1.0", stopindex=tk.END, nocase=True)
            if pos: end_pos = f"{pos}+{len(pattern)}c"
        if pos:
            tw.tag_remove("sel","1.0",tk.END)
            tw.tag_add("sel", pos, end_pos)
            tw.mark_set(tk.INSERT, end_pos)
            tw.see(pos)
            self.status_var.set(f"Znaleziono: linia {pos.split('.')[0]}")
        else:
            self.status_var.set(f"Nie znaleziono: '{pattern}'")

    def _replace_one(self, find_text, replace_text):
        tab = self._get_tab()
        if not tab or not find_text: return
        tw = tab.text_area; self.use_regex = self.regex_var.get()
        try:
            s, e = tw.index(tk.SEL_FIRST), tw.index(tk.SEL_LAST)
            sel = tw.get(s, e)
            ok  = (bool(re.match(find_text, sel, re.IGNORECASE)) if self.use_regex
                   else sel.lower() == find_text.lower())
            if ok:
                repl = (re.sub(find_text, replace_text, sel, flags=re.IGNORECASE)
                        if self.use_regex else replace_text)
                tw.delete(s, e); tw.insert(s, repl)
                self.status_var.set("Zamieniono 1"); self._find_next(); return
        except tk.TclError: pass
        self._find_next()

    def _replace_all(self, find_text, replace_text):
        tab = self._get_tab()
        if not tab or not find_text: return
        tw = tab.text_area; content = tw.get("1.0","end-1c")
        self.use_regex = self.regex_var.get()
        try:
            if self.use_regex:
                new, n = re.subn(find_text, replace_text, content, flags=re.IGNORECASE)
            else:
                new, n = re.compile(re.escape(find_text), re.IGNORECASE).subn(replace_text, content)
            if n == 0:
                messagebox.showinfo("Zamien", f"Nie znaleziono: '{find_text}'"); return
            tw.delete("1.0", tk.END); tw.insert("1.0", new)
            self.status_var.set(f"Zamieniono {n} wystapien")
        except re.error as e:
            messagebox.showerror("Blad regex", str(e))

    # ── Dialogi ───────────────────────────────────────────────────────────────

    def _goto_line(self):
        tab = self._get_tab()
        if not tab: return
        d = tk.Toplevel(self.root); d.title("Idz do linii")
        d.geometry("280x110"); d.configure(bg=self.bg_color); d.transient(self.root)
        tk.Label(d, text="Numer linii:", bg=self.bg_color, fg=self.fg_color).pack(pady=8)
        le = tk.Entry(d, width=20, bg=self.line_num_bg,
                      fg=self.fg_color, insertbackground=self.cursor_color)
        le.pack(pady=4); le.focus()
        def go():
            try:
                n = int(le.get())
                tab.text_area.mark_set(tk.INSERT, f"{n}.0")
                tab.text_area.see(f"{n}.0")
                d.destroy()
            except ValueError: pass
        le.bind("<Return>", lambda e: go())
        bf = tk.Frame(d, bg=self.bg_color); bf.pack(pady=6)
        tk.Button(bf, text="Idz", command=go, bg="#007acc",
                  fg="white", border=0, padx=12, pady=4).pack(side="left", padx=4)
        tk.Button(bf, text="Anuluj", command=d.destroy,
                  bg="#555", fg="white", border=0, padx=12, pady=4).pack(side="left")

    def _undo(self):
        t = self._get_tab()
        if t:
            try: t.text_area.edit_undo()
            except tk.TclError: pass

    def _redo(self):
        t = self._get_tab()
        if t:
            try: t.text_area.edit_redo()
            except tk.TclError: pass

    def update_cursor_position(self):
        self._refresh_status()

    def _show_help(self):
        shortcuts = [
            ("Ctrl+N", "Nowa karta"),  ("Ctrl+O","Otworz"),
            ("Ctrl+S", "Zapisz"),      ("F2","Zapisz jako"),
            ("Ctrl+W", "Zamknij"),     ("F5","Uruchom"),
            ("Ctrl+F", "Znajdz"),      ("F3","Nastepny"),
            ("Ctrl+H", "Zamien"),      ("Ctrl+G","Idz do linii"),
            ("Ctrl+Z", "Cofnij"),      ("Ctrl+Y","Ponow"),
            ("F1",     "Pomoc"),
        ]
        w = tk.Toplevel(self.root); w.title("Pomoc")
        w.geometry("460x420"); w.configure(bg=self.bg_color); w.transient(self.root)
        tk.Label(w, text=APP_NAME, font=("Helvetica",13,"bold"),
                 bg=self.bg_color, fg="white").pack(pady=10)
        f = tk.Frame(w, bg=self.bg_color); f.pack(padx=20, fill="both", expand=True)
        for key, desc in shortcuts:
            r = tk.Frame(f, bg=self.bg_color); r.pack(fill="x", pady=2)
            tk.Label(r, text=key, font=("Consolas",10,"bold"), width=18,
                     anchor="w", bg=self.bg_color, fg="#569cd6").pack(side="left")
            tk.Label(r, text=desc, font=("Helvetica",10),
                     anchor="w", bg=self.bg_color, fg=self.fg_color).pack(side="left")
        tk.Button(w, text="Zamknij", command=w.destroy,
                  bg="#007acc", fg="white", border=0,
                  padx=20, pady=6).pack(pady=12)

    def _show_about(self):
        messagebox.showinfo("O programie",
            f"{APP_NAME}\n\n"
            "Hybrydowy IDE z phi-space integration\n\n"
            "Kazdy plik = atom phi-space\n"
            "Temperatura = czestotliwosc uzycia\n"
            "Output skryptow zapisywany jako atomy\n"
            "VFS z szyfrowaniem AES-256-GCM\n\n"
            "Autor: Maciej Mazur (@drwisz)")

    # ── Recent files (phi-space first) ────────────────────────────────────────

    def _add_recent_menu(self, menu):
        rm = tk.Menu(menu, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        # Najpierw gorące z phi-space
        hot = self.phi.hot_files(5)
        shown = set()
        for fp in hot:
            if os.path.exists(fp) and fp not in shown:
                shown.add(fp)
                T = self.phi.file_temp(fp)
                lbl = f"{pathlib.Path(fp).name}  ({T:.0f}°)"
                rm.add_command(label=lbl,
                               command=lambda p=fp: self.open_file(p))
        # Uzupełnij z pliku config
        for fp in self._load_recent():
            if os.path.exists(fp) and fp not in shown:
                shown.add(fp)
                rm.add_command(label=pathlib.Path(fp).name,
                               command=lambda p=fp: self.open_file(p))
        if not shown:
            rm.add_command(label="(brak)", state="disabled")
        menu.add_cascade(label="Ostatnio otwierane", menu=rm)

    def _load_recent(self) -> list:
        try:
            if CONFIG_FILE.exists():
                return json.load(open(CONFIG_FILE)).\
                    get("recent_files", [])
        except Exception: pass
        return []

    def _save_recent(self, filepath: str):
        try:
            recent = self._load_recent()
            fp = str(pathlib.Path(filepath).resolve())
            if fp in recent: recent.remove(fp)
            recent.insert(0, fp); recent = recent[:10]
            json.dump({"recent_files": recent},
                      open(CONFIG_FILE, "w"), indent=2)
        except Exception: pass

    # ── Auto-save ─────────────────────────────────────────────────────────────

    def _schedule_autosave(self):
        if self.autosave_enabled:
            for t in self._tabs:
                if t.is_modified and not t.is_readonly: t.save()
        self.root.after(self.autosave_interval, self._schedule_autosave)

    # ── Zamknięcie ────────────────────────────────────────────────────────────

    def _on_close(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("Proces dziala", "Zatrzymac i wyjsc?"):
                return
            self.process.kill()
        mod = [t for t in self._tabs if t.is_modified]
        if mod:
            r = messagebox.askyesnocancel(
                "Wyjscie", f"{len(mod)} niezapisanych. Zapisac?")
            if r is None: return
            if r: self._save_all()
        for t in self._tabs: t.on_close()
        self.root.quit()

    def run(self): self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════════
# TRYB TUI — prompt_toolkit
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from prompt_toolkit import Application as _PTApp
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.widgets import TextArea, Frame, SearchToolbar
    from prompt_toolkit.styles import Style
    from prompt_toolkit.patch_stdout import patch_stdout
    _HAS_TUI = True
except ImportError:
    _HAS_TUI = False

if _HAS_TUI:
    class AstraEditTUI:
        """Tryb TUI — prompt_toolkit z phi-space status bar."""

        def __init__(self, file_path: str, runtime=None):
            self.file_path = str(pathlib.Path(file_path).resolve())
            self.phi       = PhiAdapter(runtime)
            self.is_mod    = False
            self.app       = None

            self._search   = SearchToolbar()
            initial        = ""
            if os.path.exists(self.file_path):
                try: initial = read_text_file(self.file_path)
                except Exception: pass

            self.editor = TextArea(
                text=initial, scrollbar=True, line_numbers=True,
                multiline=True, search_field=self._search,
                focus_on_click=True)
            self.editor.buffer.on_text_changed += lambda _: self._on_change()

            self.frame  = Frame(self.editor, title=self._title())
            self.status = Window(
                height=1,
                content=FormattedTextControl(self._status_bar),
                style="class:status")
            self.kb = self._make_kb()
            self.phi.file_opened(self.file_path)

        def _title(self) -> str:
            return (f"{APP_SHORT} | {pathlib.Path(self.file_path).name}"
                    f"{'*' if self.is_mod else ''}")

        def _on_change(self):
            if not self.is_mod:
                self.is_mod = True
                self.frame.title = self._title()
            self.phi.file_edited(self.file_path)

        def _status_bar(self):
            row = self.editor.document.cursor_position_row + 1
            col = self.editor.document.cursor_position_col + 1
            phi = self.phi.phi_summary()
            T   = self.phi.file_temp(self.file_path)
            T_s = f" T:{T:.0f}" if T > 0 else ""
            return [("class:status",
                     f" Ln {row} Col {col}{T_s}"
                     f" | {phi}"
                     f" | Ctrl+S:zapisz F5:uruchom Ctrl+Q:wyjdz ")]

        def _make_kb(self):
            kb = KeyBindings()

            @kb.add("c-s")
            def _(event):
                try:
                    write_text_file(self.file_path, self.editor.text)
                    self.is_mod    = False
                    self.frame.title = self._title()
                    self.phi.file_saved(self.file_path)
                except Exception: pass

            @kb.add("c-q")
            def _(event):
                if self.is_mod:
                    try: write_text_file(self.file_path, self.editor.text)
                    except Exception: pass
                self.phi.file_closed(self.file_path)
                event.app.exit()

            @kb.add("f5")
            def _(event):
                write_text_file(self.file_path, self.editor.text)
                app = event.app
                app.suspend_to_background()
                print(f"\n{'='*60}\n  Uruchamianie: {pathlib.Path(self.file_path).name}\n{'='*60}\n")
                try:
                    cmd = ([sys.executable,"-u",self.file_path]
                           if self.file_path.endswith(".py") else [self.file_path])
                    proc = subprocess.run(cmd, timeout=60)
                    self.phi.script_output(self.file_path, "", proc.returncode)
                    print(f"\n{'='*60}\n  Kod wyjscia: {proc.returncode}")
                except Exception as e:
                    print(f"BLAD: {e}")
                input("\nEnter aby wrocic...")
                app.resume(); app.invalidate()

            @kb.add("c-f")
            def _(event):
                event.app.layout.focus(self._search)

            return kb

        def run(self):
            style = Style.from_dict({
                "status":      "bg:#1a3a5c #ffffff",
                "frame.label": "#ffffff bold",
                "search":      "bg:cyan #000000",
            })
            layout = Layout(HSplit([self.frame, self._search, self.status]))
            app    = _PTApp(layout=layout, key_bindings=self.kb,
                           full_screen=True, mouse_support=True, style=style)
            self.app = app
            with patch_stdout(raw=True):
                app.run()
            self.app = None


# ═══════════════════════════════════════════════════════════════════════════════
# TRYB SDL — zewnętrzny edytor + FileWatcher
# ═══════════════════════════════════════════════════════════════════════════════

class AstraEditSDL:
    """Tryb SDL — otwiera zewnętrzny edytor, obserwuje zmiany, synchronizuje z phi."""

    def __init__(self, file_path: str, runtime=None, term_state=None):
        self.file_path  = str(pathlib.Path(file_path).resolve())
        self.phi        = PhiAdapter(runtime)
        self.term_state = term_state
        self._watcher   = None

    def _notify(self, msg: str):
        if self.term_state:
            try: self.term_state.append(msg, (180, 220, 100))
            except Exception: pass
        else:
            print(msg)

    def _on_change(self, path: str):
        try:
            content = read_text_file(path)
            self.phi.file_edited(path)
            # Opcjonalnie: zapisz do VFS
            vfs   = BubbleVFS()
            label = re.sub(r"[^a-z0-9]", "_",
                           pathlib.Path(path).name.lower())[:24]
            ct    = pathlib.Path(path).suffix.lstrip(".") or "txt"
            if ct in ("py","lua","md","txt","karm"):
                vfs.save(label, content, ct)
            self._notify(f"AstraEdit: zapisano {pathlib.Path(path).name} [{self.phi.phi_summary()}]")
        except Exception as e:
            self._notify(f"AstraEdit: blad: {e}")

    def run(self) -> str:
        editor_args, _ = find_external_editor()
        if editor_args is None:
            return f"Brak zewnetrznego edytora. Plik: {self.file_path}"
        cmd = editor_args + [self.file_path]
        self._notify(f"AstraEdit: otwieram {pathlib.Path(self.file_path).name} w {editor_args[0]}...")
        self.phi.file_opened(self.file_path)
        self._watcher = FileWatcher(self.file_path, self._on_change)
        self._watcher.start()
        try:
            proc = subprocess.Popen(cmd)
            proc.wait()
        except FileNotFoundError as e:
            self._watcher.stop()
            return f"Blad edytora: {e}"
        finally:
            self._watcher.stop()
        self._on_change(self.file_path)   # finalny zapis
        self.phi.file_closed(self.file_path)
        self._notify(f"AstraEdit: zamkniety. {self.phi.phi_summary()}")
        return "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# KOMENDA SHELLA
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_astraedit(args, runtime=None, term_state=None):
    """
    ASTRAEDIT <plik> [--gui|--tui|--sdl]

    Auto-detect:
      SDL aktywny → zewnetrzny edytor (SDL mode)
      X11/Windows → Tkinter GUI
      terminal    → prompt_toolkit TUI
    """
    if not args:
        return "Uzycie: ASTRAEDIT <plik> [--gui|--tui|--sdl]"

    file_path  = args[0]
    force_mode = None
    for a in args[1:]:
        if a in ("--gui", "--tui", "--sdl"):
            force_mode = a[2:]

    # Utwórz plik jeśli nie istnieje
    if not os.path.exists(file_path):
        try:
            os.makedirs(pathlib.Path(file_path).parent, exist_ok=True)
            write_text_file(file_path, "")
        except Exception: pass

    # Auto-detect tryb
    if force_mode is None:
        if is_sdl_mode() or not _HAS_TUI:
            force_mode = "sdl"
        elif _HAS_TK and (os.environ.get("DISPLAY") or
                          os.environ.get("WAYLAND_DISPLAY") or
                          os.name == "nt"):
            force_mode = "gui"
        else:
            force_mode = "tui"

    if force_mode == "sdl":
        ed = AstraEditSDL(file_path, runtime=runtime, term_state=term_state)
        t  = threading.Thread(target=ed.run, daemon=True, name="astra-sdl")
        t.start()
        return f"AstraEdit: otwieram {file_path} w zewnetrznym edytorze..."

    if force_mode == "gui":
        if not _HAS_TK:
            return "Tkinter niedostepny. Uzyj --tui"
        AstraEditGUI([file_path], runtime=runtime).run()
        return "ok"

    # TUI
    if not _HAS_TUI:
        return "prompt_toolkit niedostepny. Uzyj --gui lub --sdl"
    AstraEditTUI(file_path, runtime=runtime).run()
    return "ok"


# ────────────────────────────────────────────────────────────────────
# FIX #3b: Dodana brakująca _print_status (używana w __main__)
# ────────────────────────────────────────────────────────────────────
def _print_status(message: str, level: str = "info"):
    """Wyświetla status z kolorowym prefixem (dla __main__)."""
    prefixes = {
        "info":  f"\033[36m[AstraEdit]\033[0m",
        "warn":  f"\033[33m[AstraEdit WARN]\033[0m",
        "error": f"\033[31m[AstraEdit ERROR]\033[0m",
    }
    prefix = prefixes.get(level, prefixes["info"])
    print(f"{prefix} {message}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("files", nargs="*", help="Pliki do otwarcia")
    parser.add_argument("--gui",    action="store_true")
    parser.add_argument("--tui",    action="store_true")
    parser.add_argument("--sdl",    action="store_true")
    parser.add_argument("--runtime", default=None, help="Sciezka do runtime (opcjonalnie)")
    pargs = parser.parse_args()

    runtime = None
    if pargs.runtime:
        try:
            sys.path.insert(0, os.path.dirname(pargs.runtime))
            from runtime import SanctuaryRuntime
            runtime = SanctuaryRuntime()
        except Exception as e:
            _print_status(f"Runtime niedostepny: {e}", "warn")

    # Wymuś tryb
    if pargs.sdl:    force = "sdl"
    elif pargs.gui:  force = "gui"
    elif pargs.tui:  force = "tui"
    else:
        if is_sdl_mode():
            force = "sdl"
        elif (_HAS_TK and
              (os.environ.get("DISPLAY") or
               os.environ.get("WAYLAND_DISPLAY") or
               os.name == "nt")):
            force = "gui"
        else:
            force = "tui"

    _print_status(f"Tryb: {force.upper()}")

    if force == "sdl":
        for fp in (pargs.files or [DEFAULT_FILE]):
            ed = AstraEditSDL(fp, runtime=runtime)
            ed.run()

    elif force == "gui":
        if not _HAS_TK:
            _print_status("Tkinter niedostepny, przelaczam na TUI", "warn")
            force = "tui"
        else:
            AstraEditGUI(pargs.files or None, runtime=runtime).run()

    if force == "tui":
        if not _HAS_TUI:
            _print_status("prompt_toolkit niedostepny", "error")
            sys.exit(1)
        for fp in (pargs.files or [DEFAULT_FILE]):
            AstraEditTUI(fp, runtime=runtime).run()