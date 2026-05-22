#!/usr/bin/env python3
"""
NooEdit.py — Edytor Bąbli KarmazynOS v5.1
===========================================
- Praca na bąblach (Bubble) zamiast plików lokalnych
- Zapis przez BubbleVFS (szyfrowany, .bubbles/content)
- Integracja z runtime (tworzenie atomów, konsolidacja)
- Tryb TUI (prompt_toolkit) i GUI (tkinter) w jednym pliku
- Uruchamianie kodu (F5) w nowym bąblu z konsolą interaktywną
- Poprawki: import shutil, finally dla delete_atom, brak split/filtrowania treści
"""

import sys
import os
import pathlib
import json
import re
import subprocess
import threading
import queue
import time
import hashlib
import hmac as _hmac
import contextlib
import io
import shutil
from typing import Optional, List, Dict, Any

# ---------------- Szyfrowanie VFS ----------------
_VFS_MAGIC = b"BVFS"
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    _VFS_CRYPTO_OK = True
except ImportError:
    _AESGCM = None
    _VFS_CRYPTO_OK = False

def _vfs_key(workspace_key: bytes, label: str) -> bytes:
    return _hmac.new(workspace_key, b"vfs:" + label.encode(), hashlib.sha256).digest()

def _vfs_encrypt(plaintext: bytes, workspace_key: bytes, label: str) -> bytes:
    if not _VFS_CRYPTO_OK:
        return _VFS_MAGIC + b"\x00" * 28 + plaintext
    salt = os.urandom(16)
    nonce = os.urandom(12)
    derived = _hmac.new(_vfs_key(workspace_key, label), salt, hashlib.sha256).digest()
    ct = _AESGCM(derived).encrypt(nonce, plaintext, _VFS_MAGIC + label.encode())
    return _VFS_MAGIC + salt + nonce + ct

def _vfs_decrypt(blob: bytes, workspace_key: bytes, label: str) -> bytes:
    if blob[:4] != _VFS_MAGIC:
        return blob
    salt = blob[4:20]
    nonce = blob[20:32]
    ct = blob[32:]
    if not _VFS_CRYPTO_OK or (salt == b"\x00" * 16 and nonce == b"\x00" * 12):
        return ct
    derived = _hmac.new(_vfs_key(workspace_key, label), salt, hashlib.sha256).digest()
    try:
        return _AESGCM(derived).decrypt(nonce, ct, _VFS_MAGIC + label.encode())
    except Exception as e:
        raise ValueError(f"VFS decrypt failed: {e}")

def _vfs_workspace_key() -> bytes:
    key_path = os.path.join(".bubbles", ".vfskey")
    if os.path.exists(key_path):
        try:
            with open(key_path, "rb") as f:
                raw = f.read()
                if len(raw) == 32:
                    return raw
        except Exception:
            pass
    new_key = os.urandom(32)
    os.makedirs(".bubbles", exist_ok=True)
    with open(key_path, "wb") as f:
        f.write(new_key)
    return new_key

# ---------------- BubbleVFS ----------------
class BubbleVFS:
    TMP_DIR = ".bubbles/tmp"
    CONTENT_DIR = ".bubbles/content"

    def __init__(self):
        os.makedirs(self.TMP_DIR, exist_ok=True)
        os.makedirs(self.CONTENT_DIR, exist_ok=True)

    def materialize(self, label: str, content: str, ext: str = ".txt") -> str:
        path = os.path.join(self.TMP_DIR, f"{label}{ext}")
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            f.write(content)
        return path

    def read_back(self, label: str, ext: str = ".txt") -> str:
        path = os.path.join(self.TMP_DIR, f"{label}{ext}")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        return ""

    def save_content(self, label: str, content: str, ext: str = ".txt") -> None:
        path = os.path.join(self.CONTENT_DIR, f"{label}{ext}")
        key = _vfs_workspace_key()
        blob = _vfs_encrypt(content.encode("utf-8"), key, label)
        with open(path, "wb") as f:
            f.write(blob)

    def load_content(self, label: str, ext: str = ".txt") -> str:
        path = os.path.join(self.CONTENT_DIR, f"{label}{ext}")
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "rb") as f:
                raw = f.read()
            key = _vfs_workspace_key()
            return _vfs_decrypt(raw, key, label).decode("utf-8")
        except Exception:
            return ""

    def has_content(self, label: str, ext: str = ".txt") -> bool:
        return os.path.exists(os.path.join(self.CONTENT_DIR, f"{label}{ext}"))

    def cleanup(self, label: str, ext: str = ".txt") -> None:
        path = os.path.join(self.TMP_DIR, f"{label}{ext}")
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

# ---------------- NooContext (łącznik z runtime) ----------------
class NooContext:
    def __init__(self, label: str, runtime, content_type: str = "py"):
        self.label = label
        self.runtime = runtime
        self.content_type = content_type
        self.vfs = BubbleVFS()
        self._last_hash = ""

    def get_bubble(self):
        return self.runtime._bubbles.get(self.label) if self.runtime else None

    def get_content(self) -> str:
        bubble = self.get_bubble()
        if bubble:
            content = getattr(bubble, "content", "")
            if content:
                return content
        ext_map = {"py": ".py", "lua": ".lua", "md": ".md", "txt": ".txt", "karm": ".karm"}
        ext = ext_map.get(self.content_type, ".txt")
        if self.vfs.has_content(self.label, ext):
            return self.vfs.load_content(self.label, ext)
        lang = {"py": "Python", "lua": "Lua", "md": "Markdown", "txt": "Tekst", "karm": "KarmazynScript"}.get(self.content_type, "?")
        return f"# Babl '{self.label}' [{lang}]\n# Ctrl+S: zapisz  F5: uruchom  Ctrl+Q: wyjdz\n"

    def push_content(self, new_content: str) -> dict:
        bubble = self.get_bubble()
        if bubble is None:
            return {"status": "error", "reason": "bubble_not_found"}
        h = hashlib.md5(new_content.encode("utf-8")).hexdigest()
        if h == self._last_hash:
            return {"status": "unchanged"}
        self._last_hash = h
        bubble.content = new_content
        ext_map = {"py": ".py", "lua": ".lua", "md": ".md", "txt": ".txt", "karm": ".karm"}
        ext = ext_map.get(self.content_type, ".txt")
        self.vfs.save_content(self.label, new_content, ext)
        tmp_id = None
        try:
            tmp_id = f"nooedit_{self.label}_{int(time.time())}"
            atom = self.runtime.create_atom(tmp_id, new_content[:256], self.label, T=90.0)
            if hasattr(self.runtime, "consolidate_to_bubble"):
                result = self.runtime.consolidate_to_bubble(atom, bubble)
            else:
                self.runtime.consolidate(tmp_id)
                result = {"status": "absorbed"}
        except Exception as e:
            result = {"status": "absorbed", "note": f"consolidation failed: {e}"}
        finally:
            if tmp_id and self.runtime.has_atom(tmp_id):
                try:
                    self.runtime.delete_atom(tmp_id)
                except:
                    pass
        return result

    def run_in_new_bubble(self, content: str, tmp_path: str):
        result_label = f"{self.label}_run_{int(time.time())}"
        tmp_id = None
        try:
            code_label = f"code_{result_label}"
            self.runtime.write(code_label, code_label, content, 1.0)
            self.runtime.consolidate(code_label)
            tmp_id = code_label
            cmd = self._get_run_command(tmp_path)
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                  encoding="utf-8", errors="replace")
            output = proc.stdout + proc.stderr
            out_id = f"out_{result_label}"
            self.runtime.create_atom(out_id, output[:512] if output else "(brak wyjścia)", result_label, T=80.0)
            return result_label, proc.returncode, output
        except subprocess.TimeoutExpired:
            return result_label, -1, "TIMEOUT"
        except Exception as e:
            return result_label, -1, f"BŁĄD: {e}"
        finally:
            if tmp_id and self.runtime.has_atom(tmp_id):
                try:
                    self.runtime.delete_atom(tmp_id)
                except:
                    pass

    def _get_run_command(self, file_path: str):
        ext = pathlib.Path(file_path).suffix.lower()
        if ext == ".py":
            return [sys.executable, "-u", file_path]
        if ext in (".lua", ".karm"):
            for cand in ("lua", "lua5.4", "lua5.3", "luajit"):
                if shutil.which(cand):
                    return [cand, file_path]
            raise FileNotFoundError("Brak interpretera Lua")
        return [file_path]

# ---------------- Część TUI (prompt_toolkit) ----------------
HAS_TUI = False
try:
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.widgets import TextArea, Frame, SearchToolbar
    from prompt_toolkit.styles import Style
    from prompt_toolkit.patch_stdout import patch_stdout
    HAS_TUI = True
except ImportError:
    pass

if HAS_TUI:
    class NooEditTUI:
        APP_NAME = "NooEdit — KarmazynOS (TUI)"

        def __init__(self, ctx: NooContext, tmp_path: str):
            self.ctx = ctx
            self.tmp_path = tmp_path
            self.is_modified = False
            self.save_queue = queue.Queue()
            self.last_save_status = "?"
            self.app = None
            self.save_thread = threading.Thread(target=self._save_worker, daemon=True)
            self.save_thread.start()

            self.search_field = SearchToolbar()
            initial = ""
            if os.path.exists(tmp_path):
                with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
                    initial = f.read()

            self.editor = TextArea(
                text=initial,
                scrollbar=True,
                line_numbers=True,
                multiline=True,
                search_field=self.search_field,
                focus_on_click=True
            )
            self.editor.buffer.on_text_changed += lambda _: self._on_change()
            self.frame = Frame(self.editor, title=self._title())
            self.status = Window(
                height=1,
                content=FormattedTextControl(self._status_bar),
                style="class:status"
            )
            self.kb = self._make_kb()

        def _save_worker(self):
            while True:
                item = self.save_queue.get()
                if item is None:
                    self.save_queue.task_done()
                    break
                text = item
                try:
                    with open(self.tmp_path, "w", encoding="utf-8", errors="replace") as f:
                        f.write(text)
                    result = self.ctx.push_content(text)
                except Exception as e:
                    result = {"status": f"error:{e}"}
                self.last_save_status = result.get("status", "?")
                self.save_queue.task_done()
                self.frame.title = self._title()
                if self.app is not None:
                    try:
                        self.app.invalidate()
                    except Exception:
                        pass

        def _title(self):
            ct = {'py':'Python','lua':'Lua','md':'MD','txt':'TXT','karm':'Karm'}.get(self.ctx.content_type, '?')
            mark = "*" if self.is_modified else ""
            return f"{self.APP_NAME} | Babl: {self.ctx.label} [{ct}]{mark}"

        def _on_change(self):
            if not self.is_modified:
                self.is_modified = True
                self.frame.title = self._title()

        def _status_bar(self):
            row = self.editor.document.cursor_position_row + 1
            col = self.editor.document.cursor_position_col + 1
            return [("class:status", f" Ln {row}, Col {col} | Ctrl+S: zapisz | F5: uruchom | Ctrl+Q: wyjdz | save: {self.last_save_status} ")]

        def _make_kb(self):
            kb = KeyBindings()

            @kb.add("c-s")
            def _(event):
                self.save_queue.put(self.editor.text)
                self.is_modified = False
                self.frame.title = self._title() + " [saving...]"
                event.app.invalidate()

            @kb.add("c-q")
            def _(event):
                if self.is_modified:
                    self.save_queue.put(self.editor.text)
                self.save_queue.put(None)
                event.app.exit()

            @kb.add("f5")
            def _(event):
                # Zapisz przed uruchomieniem
                with open(self.tmp_path, "w", encoding="utf-8", errors="replace") as f:
                    f.write(self.editor.text)
                app = event.app
                app.suspend_to_background()
                print(f"\n{'='*60}")
                print(f"  NooEdit F5: {self.ctx.label}")
                print(f"{'='*60}\n")
                try:
                    result_label, exit_code, output = self.ctx.run_in_new_bubble(self.editor.text, self.tmp_path)
                    print(output or "(brak wyjścia)")
                    print(f"\n{'='*60}")
                    print(f"  Kod wyjścia: {exit_code}")
                    print(f"  Wynik w Bablu: {result_label}")
                except Exception as e:
                    print(f"BŁĄD: {e}")
                input("\nEnter aby wrócić...")
                app.resume()
                app.invalidate()

            @kb.add("c-f")
            def _(event):
                event.app.layout.focus(self.search_field)

            return kb

        def run(self):
            style = Style.from_dict({
                "status": "bg:#1a3a5c #ffffff",
                "frame.label": "#ffffff bold",
                "search": "bg:cyan #000000"
            })
            layout = Layout(HSplit([self.frame, self.search_field, self.status]))
            app = Application(
                layout=layout,
                key_bindings=self.kb,
                full_screen=True,
                mouse_support=True,
                style=style
            )
            self.app = app
            with patch_stdout(raw=True):
                app.run()
            self.app = None

# ---------------- Część GUI (tkinter) ----------------
HAS_GUI = False
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk
    HAS_GUI = True
except ImportError:
    pass

if HAS_GUI:
    class NooEditGUI:
        APP_NAME = "NooEdit — KarmazynOS (GUI)"

        def __init__(self, ctx: NooContext, tmp_path: str):
            self.ctx = ctx
            self.tmp_path = tmp_path
            self.is_modified = False
            self.root = tk.Tk()
            self.root.title(f"{self.APP_NAME} – {ctx.label}")
            self.root.geometry("1000x700")
            self.root.configure(bg="#1e1e1e")

            # Dark mode colors
            self.bg_color = "#1e1e1e"
            self.fg_color = "#d4d4d4"
            self.cursor_color = "#ffffff"
            self.selection_color = "#264f78"
            self.line_num_bg = "#252526"
            self.line_num_fg = "#858585"
            self.console_bg = "#111111"
            self.console_fg = "#cccccc"

            # Auto-save
            self.autosave_enabled = True
            self.autosave_interval = 30000

            # State for subprocess
            self.process = None
            self.msg_queue = queue.Queue()

            self.setup_ui()
            self.setup_menu()
            self.setup_bindings()

            # Load content
            self.load_content()

            # Auto-save timer
            if self.autosave_enabled:
                self.schedule_autosave()

            self.root.after(100, self.process_queue)

        def setup_ui(self):
            # PanedWindow (podział: edytor + konsola)
            self.paned = tk.PanedWindow(self.root, orient=tk.VERTICAL, sashwidth=4, bg="#333333")
            self.paned.pack(fill="both", expand=True)

            # Edytor (góra)
            editor_frame = tk.Frame(self.paned, bg=self.bg_color)
            self.paned.add(editor_frame, stretch="always", height=500)

            # Kontener z numeracją linii i polem tekstowym
            container = tk.Frame(editor_frame, bg=self.bg_color)
            container.pack(fill="both", expand=True)

            self.line_numbers = tk.Text(
                container, width=4, padx=3, takefocus=0, border=0,
                bg=self.line_num_bg, fg=self.line_num_fg,
                state="disabled", font=("Consolas", 11)
            )
            self.line_numbers.pack(side="left", fill="y")

            self.text_area = scrolledtext.ScrolledText(
                container, wrap="word", undo=True,
                bg=self.bg_color, fg=self.fg_color,
                insertbackground=self.cursor_color,
                selectbackground=self.selection_color,
                font=("Consolas", 11), border=0
            )
            self.text_area.pack(side="left", fill="both", expand=True)

            self.text_area.vbar.config(command=self.on_scrollbar)
            self.line_numbers.config(yscrollcommand=self.text_area.vbar.set)

            # Tagi kolorowania składni (proste)
            tags = {
                "Keyword": "#569cd6", "Name.Builtin": "#dcdcaa",
                "Comment": "#6a9955", "String": "#ce9178",
                "Number": "#b5cea8", "Operator": "#d4d4d4",
                "Punctuation": "#d4d4d4", "Name": "#9cdcfe"
            }
            for tag, color in tags.items():
                self.text_area.tag_config(tag, foreground=color)

            # Konsola (dół)
            console_frame = tk.Frame(self.paned, bg=self.console_bg)
            self.paned.add(console_frame, stretch="never", height=250)

            # Pasek narzędzi konsoli
            toolbar = tk.Frame(console_frame, bg="#252526", height=28)
            toolbar.pack(fill="x", side="top")
            tk.Label(toolbar, text="📟 Konsola interaktywna", bg="#252526", fg="white",
                     font=("Arial", 9, "bold")).pack(side="left", padx=8)

            self.stop_btn = tk.Button(
                toolbar, text="⬛ STOP", command=self.stop_process,
                bg="#8b0000", fg="white", border=0, font=("Arial", 8, "bold"),
                state="disabled", padx=8, pady=2
            )
            self.stop_btn.pack(side="right", padx=5, pady=3)

            tk.Button(toolbar, text="🗑 Wyczyść", command=self.clear_console,
                      bg="#404040", fg="white", border=0, font=("Arial", 8),
                      padx=8, pady=2).pack(side="right", padx=5, pady=3)

            self.console_area = scrolledtext.ScrolledText(
                console_frame, bg=self.console_bg, fg=self.console_fg,
                font=("Consolas", 10), state="disabled", border=0
            )
            self.console_area.pack(fill="both", expand=True)
            self.console_area.tag_config("stderr", foreground="#ff6b6b")
            self.console_area.tag_config("stdin", foreground="#00ff00")
            self.console_area.tag_config("info", foreground="#61afef")

            # Pasek wprowadzania (input)
            input_frame = tk.Frame(console_frame, bg=self.console_bg, height=30)
            input_frame.pack(fill="x", side="bottom")
            tk.Label(input_frame, text=">>> ", bg=self.console_bg, fg="#00ff00",
                     font=("Consolas", 10, "bold")).pack(side="left", padx=5)
            self.input_entry = tk.Entry(
                input_frame, bg=self.console_bg, fg="white",
                insertbackground="white", font=("Consolas", 10),
                border=0, relief="flat"
            )
            self.input_entry.pack(side="left", fill="x", expand=True, padx=5, pady=5)
            self.input_entry.bind("<Return>", self.send_input)

            # Status bar
            self.status_var = tk.StringVar(value="Gotowy | F5: Uruchom | F1: Pomoc")
            self.status_bar = tk.Label(
                self.root, textvariable=self.status_var,
                bg="#007acc", fg="white", anchor="w", padx=5, font=("Arial", 9)
            )
            self.status_bar.pack(side="bottom", fill="x")

        def setup_menu(self):
            menubar = tk.Menu(self.root, bg="#1e1e1e", fg="#d4d4d4")
            filemenu = tk.Menu(menubar, tearoff=0, bg="#1e1e1e", fg="#d4d4d4")
            filemenu.add_command(label="Zapisz (Ctrl+S)", command=self.save)
            filemenu.add_separator()
            filemenu.add_command(label="Zamknij", command=self.on_close)
            menubar.add_cascade(label="Plik", menu=filemenu)

            runmenu = tk.Menu(menubar, tearoff=0, bg="#1e1e1e", fg="#d4d4d4")
            runmenu.add_command(label="▶ Uruchom (F5)", command=self.run_script)
            runmenu.add_command(label="⬛ Zatrzymaj", command=self.stop_process)
            runmenu.add_separator()
            runmenu.add_command(label="🗑 Wyczyść konsolę", command=self.clear_console)
            menubar.add_cascade(label="Uruchom", menu=runmenu)

            helpmenu = tk.Menu(menubar, tearoff=0, bg="#1e1e1e", fg="#d4d4d4")
            helpmenu.add_command(label="Skróty (F1)", command=self.show_help)
            helpmenu.add_command(label="O programie", command=self.show_about)
            menubar.add_cascade(label="Pomoc", menu=helpmenu)

            self.root.config(menu=menubar)

        def setup_bindings(self):
            self.root.bind("<Control-s>", lambda e: self.save())
            self.root.bind("<F5>", lambda e: self.run_script())
            self.root.bind("<F1>", lambda e: self.show_help())
            self.text_area.bind("<<Modified>>", self.on_modified)
            self.text_area.bind("<KeyRelease>", self.on_key_release)
            self.text_area.bind("<Button-1>", lambda e: self.update_line_numbers())

        def on_scrollbar(self, *args):
            self.text_area.yview(*args)
            self.line_numbers.yview(*args)

        def on_modified(self, event=None):
            if self.text_area.edit_modified():
                if not self.is_modified:
                    self.is_modified = True
                    self.update_title()
                self.text_area.edit_modified(False)

        def on_key_release(self, event=None):
            self.update_line_numbers()

        def update_line_numbers(self):
            self.line_numbers.config(state="normal")
            self.line_numbers.delete("1.0", "end")
            end_index = self.text_area.index("end-1c")
            line_count = int(end_index.split('.')[0])
            nums = "\n".join(str(i) for i in range(1, line_count + 1))
            self.line_numbers.insert("1.0", nums)
            self.line_numbers.config(state="disabled")
            try:
                first_visible = self.text_area.yview()[0]
                self.line_numbers.yview_moveto(first_visible)
            except:
                pass

        def load_content(self):
            content = self.ctx.get_content()
            self.text_area.insert("1.0", content)
            self.is_modified = False
            self.update_title()
            self.update_line_numbers()

        def save(self):
            content = self.text_area.get("1.0", "end-1c")
            result = self.ctx.push_content(content)
            if result.get("status") in ("absorbed", "unchanged"):
                self.is_modified = False
                self.update_title()
                self.status_var.set(f"Zapisano: {self.ctx.label}")
                return True
            else:
                messagebox.showerror("Błąd zapisu", str(result))
                return False

        def update_title(self):
            mark = "*" if self.is_modified else ""
            self.root.title(f"{self.APP_NAME} – {self.ctx.label}{mark}")

        def run_script(self):
            if self.process and self.process.poll() is None:
                messagebox.showinfo("Info", "Proces już działa. Użyj STOP.")
                return
            if not self.save():
                return
            self.clear_console()
            self.log_to_console(f"{'='*60}\n", "info")
            self.log_to_console(f"  Uruchamianie: {self.ctx.label}\n", "info")
            self.log_to_console(f"{'='*60}\n\n", "info")
            self.stop_btn.config(state="normal", bg="#ff3333")
            threading.Thread(target=self._run_subprocess, daemon=True).start()

        def _run_subprocess(self):
            tmp_path = self.tmp_path
            try:
                cmd = self.ctx._get_run_command(tmp_path)
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    cwd=pathlib.Path(tmp_path).parent
                )
                threading.Thread(target=self._reader, args=(self.process.stdout, None), daemon=True).start()
                threading.Thread(target=self._reader, args=(self.process.stderr, "stderr"), daemon=True).start()
                self.process.wait()
                self.msg_queue.put(("text", f"\n{'='*60}\n", "info"))
                self.msg_queue.put(("text", f"  Zakończono (kod wyjścia: {self.process.returncode})\n", "info"))
                self.msg_queue.put(("text", f"{'='*60}\n", "info"))
            except Exception as e:
                self.msg_queue.put(("text", f"\n❌ Błąd: {e}\n", "stderr"))
            finally:
                self.msg_queue.put(("status", "stopped", None))

        def _reader(self, stream, tag):
            try:
                for line in iter(stream.readline, ''):
                    if line:
                        self.msg_queue.put(("text", line, tag))
            except:
                pass
            finally:
                try:
                    stream.close()
                except:
                    pass

        def process_queue(self):
            try:
                while True:
                    typ, content, tag = self.msg_queue.get_nowait()
                    if typ == "text":
                        self.log_to_console(content, tag)
                    elif typ == "status" and content == "stopped":
                        self.stop_btn.config(state="disabled", bg="#8b0000")
                        self.process = None
            except queue.Empty:
                pass
            self.root.after(100, self.process_queue)

        def log_to_console(self, text, tag=None):
            self.console_area.config(state="normal")
            self.console_area.insert(tk.END, text, tag)
            self.console_area.see(tk.END)
            self.console_area.config(state="disabled")

        def send_input(self, event):
            text = self.input_entry.get()
            self.input_entry.delete(0, tk.END)
            if not text:
                return
            if self.process and self.process.poll() is None:
                try:
                    self.log_to_console(f"{text}\n", "stdin")
                    self.process.stdin.write(text + "\n")
                    self.process.stdin.flush()
                except Exception as e:
                    self.log_to_console(f"❌ Błąd: {e}\n", "stderr")
            else:
                self.log_to_console("⚠ Proces nie działa.\n", "stderr")

        def stop_process(self):
            if self.process and self.process.poll() is None:
                self.process.kill()
                self.log_to_console("\n⚠ Proces zatrzymany przez użytkownika.\n", "stderr")
                self.stop_btn.config(state="disabled", bg="#8b0000")
                self.process = None

        def clear_console(self):
            self.console_area.config(state="normal")
            self.console_area.delete("1.0", tk.END)
            self.console_area.config(state="disabled")

        def schedule_autosave(self):
            if self.autosave_enabled and self.is_modified:
                self.save()
            self.root.after(self.autosave_interval, self.schedule_autosave)

        def show_help(self):
            help_win = tk.Toplevel(self.root)
            help_win.title("Pomoc")
            help_win.geometry("400x300")
            help_win.configure(bg="#1e1e1e")
            txt = tk.Text(help_win, bg="#1e1e1e", fg="#d4d4d4", wrap="word")
            txt.pack(fill="both", expand=True)
            txt.insert("1.0",
                "Skróty klawiszowe:\n\n"
                "Ctrl+S – Zapisz\n"
                "F5     – Uruchom kod\n"
                "F1     – Ta pomoc\n\n"
                "Kod uruchamiany jest w nowym bąblu.\n"
                "Konsola obsługuje stdin (wpisz i Enter)."
            )
            txt.config(state="disabled")
            tk.Button(help_win, text="Zamknij", command=help_win.destroy).pack(pady=5)

        def show_about(self):
            messagebox.showinfo("O programie",
                f"{self.APP_NAME}\n\n"
                "Edytor bąbli KarmazynOS.\n"
                "Pracuje bezpośrednio na Bąblach (Bubble).\n"
                "Wspiera Python, Lua, Markdown, tekst zwykły i KarmScript.\n"
                "Wersja 5.1 – integracja z runtime i VFS.")

        def on_close(self):
            if self.is_modified:
                resp = messagebox.askyesnocancel("Wyjście", "Zapisać zmiany?")
                if resp is None:
                    return
                if resp:
                    if not self.save():
                        return
            self.root.quit()

        def run(self):
            self.root.mainloop()

# ---------------- Komenda shella ----------------
def cmd_nooedit(args, runtime=None):
    if not runtime:
        return "Brak runtime."
    if not args:
        return "Użycie: NOOEDIT <label> [--py|--lua|--md|--karm]"
    label = args[0]
    force_type = None
    for a in args[1:]:
        if a.startswith("--"):
            force_type = a[2:]
    if force_type is None:
        ext = label.split(".")[-1] if "." in label else ""
        force_type = ext if ext in ("py", "lua", "md", "txt", "karm") else "py"
    if label not in runtime._bubbles:
        runtime.write(label, label, "bubble_init", 1.0)
        runtime.consolidate(label)
    ctx = NooContext(label, runtime, force_type)
    content = ctx.get_content()
    ext_map = {"py": ".py", "lua": ".lua", "md": ".md", "txt": ".txt", "karm": ".karm"}
    ext = ext_map.get(force_type, ".txt")
    tmp_path = ctx.vfs.materialize(label, content, ext)

    # Preferencja: GUI jeśli dostępne i mamy DISPLAY, w przeciwnym razie TUI
    use_gui = False
    if HAS_GUI and (os.environ.get("DISPLAY") or os.name == 'nt'):
        use_gui = True

    if use_gui and HAS_GUI:
        editor = NooEditGUI(ctx, tmp_path)
        editor.run()
    elif HAS_TUI:
        editor = NooEditTUI(ctx, tmp_path)
        editor.run()
    else:
        return "Brak obsługi TUI lub GUI (zainstaluj prompt_toolkit lub tkinter)."

    if hasattr(editor, "save_queue"):
        editor.save_queue.join()
    final_content = ctx.vfs.read_back(label, ext)
    if final_content:
        ctx.push_content(final_content)
        ctx.vfs.cleanup(label, ext)
    return "ok"

if __name__ == "__main__":
    print("NooEdit v5.1 – uruchom przez shell KarmazynOS: NOOEDIT <label>")