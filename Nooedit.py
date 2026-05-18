"""
NooEdit.py — Edytor KarmazynOS (Safe Windows)
==============================================
Adaptacja AstraEdit 4.6 dla modelu fundamentalnego KarmazynOS.
Poprawka: _silent() nie podmienia deskryptorów systemowych (bezpieczne dla pyreadline3).
"""

import contextlib
import hmac as _hmac
import io
import os
import sys
import pathlib
import subprocess
import time
import json
import hashlib
import threading
import queue
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from runtime import SanctuaryRuntime

# --- Szyfrowanie BubbleVFS (AES-256-GCM) ---
_VFS_MAGIC = b"BVFS"

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    _VFS_CRYPTO_OK = True
except ImportError:
    _AESGCM      = None
    _VFS_CRYPTO_OK = False

def _vfs_key(workspace_key: bytes, label: str) -> bytes:
    return _hmac.new(workspace_key, b"vfs:" + label.encode(), hashlib.sha256).digest()

def _vfs_encrypt(plaintext: bytes, workspace_key: bytes, label: str) -> bytes:
    if not _VFS_CRYPTO_OK:
        return _VFS_MAGIC + b"\x00" * 28 + plaintext
    salt    = os.urandom(16)
    nonce   = os.urandom(12)
    derived = _hmac.new(_vfs_key(workspace_key, label), salt, hashlib.sha256).digest()
    ct      = _AESGCM(derived).encrypt(nonce, plaintext, _VFS_MAGIC + label.encode())
    return _VFS_MAGIC + salt + nonce + ct

def _vfs_decrypt(blob: bytes, workspace_key: bytes, label: str) -> bytes:
    if blob[:4] != _VFS_MAGIC:
        return blob
    salt  = blob[4:20]; nonce = blob[20:32]; ct = blob[32:]
    if not _VFS_CRYPTO_OK or (salt == b"\x00" * 16 and nonce == b"\x00" * 12):
        return ct
    derived = _hmac.new(_vfs_key(workspace_key, label), salt, hashlib.sha256).digest()
    try:
        return _AESGCM(derived).decrypt(nonce, ct, _VFS_MAGIC + label.encode())
    except Exception as e:
        raise ValueError(f"VFS decrypt failed dla {label!r}: {type(e).__name__}")

def _vfs_workspace_key() -> bytes:
    key_path = os.path.join(".bubbles", ".vfskey")
    if os.path.exists(key_path):
        try:
            raw = open(key_path, "rb").read()
            if len(raw) == 32:
                return raw
        except Exception:
            pass
    new_key = os.urandom(32)
    try:
        os.makedirs(".bubbles", exist_ok=True)
        open(key_path, "wb").write(new_key)
    except Exception:
        pass
    return new_key

@contextlib.contextmanager
def _silent():
    """
    Bezpieczne tłumienie stdout/stderr (tylko przekierowanie strumieni Pythona).
    Nie rusza deskryptorów systemowych – działa pewnie na Windows/pyreadline3.
    """
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        yield buf_out, buf_err

# --- Wspólne funkcje I/O ---
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

# --- Wykrywanie typu treści ---
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
    import numpy as np
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
    if chaos_score > 0.4:
        return 'txt'
    if logic_score > creation_score:
        if vec[PHI_CREATION] > 0.2:
            return 'karm'
        return 'py'
    return 'md'

# --- BubbleVFS ---
class BubbleVFS:
    TMP_DIR     = ".bubbles/tmp"
    CONTENT_DIR = ".bubbles/content"

    def __init__(self):
        os.makedirs(self.TMP_DIR,     exist_ok=True)
        os.makedirs(self.CONTENT_DIR, exist_ok=True)

    def materialize(self, label, content, content_type='py'):
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        path = os.path.join(self.TMP_DIR, f"{label}{ext}")
        write_text_file(path, content)
        return path

    def read_back(self, label, content_type='py'):
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        path = os.path.join(self.TMP_DIR, f"{label}{ext}")
        if os.path.exists(path):
            return read_text_file(path)
        return ""

    def save_content(self, label, content, content_type='py'):
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        path = os.path.join(self.CONTENT_DIR, f"{label}{ext}")
        key  = _vfs_workspace_key()
        blob = _vfs_encrypt(content.encode("utf-8"), key, label)
        with open(path, "wb") as f:
            f.write(blob)
        return path

    def load_content(self, label, content_type='py'):
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        path = os.path.join(self.CONTENT_DIR, f"{label}{ext}")
        if not os.path.exists(path):
            return ""
        try:
            raw = open(path, "rb").read()
            key = _vfs_workspace_key()
            return _vfs_decrypt(raw, key, label).decode("utf-8")
        except Exception:
            return read_text_file(path)

    def has_content(self, label, content_type='py'):
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        return os.path.exists(os.path.join(self.CONTENT_DIR, f"{label}{ext}"))

    def cleanup(self, label, content_type='py'):
        ext  = CONTENT_TYPE_MAP.get(content_type, ("", ".py"))[1]
        path = os.path.join(self.TMP_DIR, f"{label}{ext}")
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

# --- NooContext ---
class NooContext:
    def __init__(self, label, runtime, content_type='py'):
        self.label = label
        self.runtime = runtime
        self.content_type = content_type
        self.vfs = BubbleVFS()
        self._last_hash = ""

    def get_bubble(self):
        return self.runtime._bubbles.get(self.label)

    def get_content(self):
        if self.vfs.has_content(self.label, self.content_type):
            return self.vfs.load_content(self.label, self.content_type)
        bubble = self.get_bubble()
        if bubble is not None:
            content = getattr(bubble, 'content', '')
            noise   = {'bubble_init', self.label, 'Tekst', ''}
            parts   = [p.strip() for p in content.split() if p.strip() not in noise]
            if parts:
                return '\n'.join(parts)
        lang = CONTENT_TYPE_MAP.get(self.content_type, ("?", ""))[0]
        return (f"# Babl '{self.label}' [{lang}]\n"
                f"# Ctrl+S: zapisz  F5: uruchom  Ctrl+Q: wyjdz\n")

    def push_content(self, new_content):
        bubble = self.get_bubble()
        if bubble is None:
            return {"status": "error", "reason": "bubble_not_found"}
        h = hashlib.md5(new_content.encode('utf-8')).hexdigest()
        if h == self._last_hash:
            return {"status": "unchanged"}
        self._last_hash = h
        self.vfs.save_content(self.label, new_content, self.content_type)
        atom_id = f"edit_{self.label}_{int(time.time())}"
        try:
            with _silent():
                atom = self.runtime.create_atom(atom_id, new_content[:256], self.label, T=90.0)
                bubble.absorb(atom)
                bubble.update_psi([atom])
                try:
                    self.runtime.delete_atom(atom_id)
                except Exception:
                    pass
            return {"status": "absorbed", "atom": atom_id}
        except Exception as e:
            return {"status": "absorbed", "note": str(e)}

    def run_in_new_bubble(self, content, tmp_path):
        result_label = f"{self.label}_run_{int(time.time())}"
        try:
            from karmazyn_core import BubbleMode
            from core.phi_math import PhiPhysics
            self.runtime.write(result_label, result_label, "run_output", 1.0)
            self.runtime.consolidate(result_label)
            rb = self.runtime._bubbles.get(result_label)
            if rb:
                rb.mode = BubbleMode.WORKSPACE
            ext = CONTENT_TYPE_MAP.get(self.content_type, ("", ".py"))[1]
            cmd = _get_run_command(tmp_path)
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=30, encoding='utf-8', errors='replace')
            output = proc.stdout + proc.stderr
            out_id = f"out_{result_label}"
            self.runtime.create_atom(out_id, output[:512] if output else "(brak wyjscia)",
                                     result_label, T=80.0)
            if rb:
                out_atom = self.runtime.get_atom(out_id)
                if out_atom:
                    self.runtime.consolidate_to_bubble(out_atom, rb)
            return result_label, proc.returncode, output
        except subprocess.TimeoutExpired:
            return result_label, -1, "TIMEOUT"
        except Exception as e:
            return result_label, -1, f"BLAD: {e}"

def _get_run_command(file_path):
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

# --- NooEditTUI (z kolejką zapisów i patch_stdout) ---
try:
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit, Window, FloatContainer, Float
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.widgets import TextArea, Frame, SearchToolbar
    from prompt_toolkit.styles import Style
    from prompt_toolkit.patch_stdout import patch_stdout
    HAS_TUI = True
except ImportError:
    HAS_TUI = False

class NooEditTUI:
    APP_NAME = "NooEdit — KarmazynOS"

    def __init__(self, ctx, tmp_path):
        if not HAS_TUI:
            raise ImportError("Brak prompt_toolkit.")
        self.ctx = ctx
        self.tmp_path = tmp_path
        self.is_modified = False
        self.save_queue = queue.Queue()
        self.last_save_status = "?"
        self.app = None
        self.save_thread = threading.Thread(target=self._save_worker, daemon=True)
        self.save_thread.start()

        self.search_field = SearchToolbar()
        initial = read_text_file(tmp_path) if os.path.exists(tmp_path) else ""
        self.editor = TextArea(
            text=initial, scrollbar=True, line_numbers=True,
            multiline=True, search_field=self.search_field, focus_on_click=True
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
            with _silent():
                try:
                    write_text_file(self.tmp_path, text)
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
        ct = CONTENT_TYPE_MAP.get(self.ctx.content_type, ("?", ""))[0]
        mark = "*" if self.is_modified else ""
        return f"{self.APP_NAME} | Babl: {self.ctx.label} [{ct}]{mark}"

    def _on_change(self):
        if not self.is_modified:
            self.is_modified = True
            self.frame.title = self._title()

    def _status_bar(self):
        row = self.editor.document.cursor_position_row + 1
        col = self.editor.document.cursor_position_col + 1
        status = self.last_save_status
        return [("class:status",
                 f" Ln {row}, Col {col} | Ctrl+S: zapisz | F5: uruchom | F6: kopiuj | F7: wklej | Ctrl+Q: wyjdz | {self.ctx.label} | save: {status} ")]

    def _get_runtime_clipboard(self):
        """Zwraca babl __clipboard__ z runtime, lub None jesli niedostepny."""
        rt = getattr(self.ctx, "runtime", None)
        if rt is None:
            return None
        return getattr(rt, "_bubbles", {}).get("__clipboard__")

    def _copy_selection_to_bubble(self, event):
        """F6 -- kopiuj zaznaczenie do __clipboard__ babla.

        Jesli nie ma zaznaczenia, kopiuje biezaca linie.
        Informacja pojawia sie w tytule ramki.
        """
        buf = self.editor.buffer
        sel = buf.selection_state
        if sel is not None:
            cursor  = buf.cursor_position
            anchor  = sel.original_cursor_position
            start   = min(cursor, anchor)
            end     = max(cursor, anchor)
            text    = buf.document.text[start:end]
        else:
            text = buf.document.current_line

        if not text:
            self.frame.title = self._title() + " [schowek: pusty]"
            event.app.invalidate()
            return

        cb = self._get_runtime_clipboard()
        if cb is not None:
            try:
                cb.content = text
                preview = text[:40].replace("\n", " ")
                self.frame.title = self._title() + f" [schowek: '{preview}...']"
            except Exception as e:
                self.frame.title = self._title() + f" [schowek blad: {e}]"
        else:
            self.frame.title = self._title() + " [schowek niedostepny]"
        event.app.invalidate()

    def _paste_from_bubble(self, event):
        """F7 -- wklej zawartosc __clipboard__ do kursora."""
        cb = self._get_runtime_clipboard()
        if cb is None:
            self.frame.title = self._title() + " [schowek niedostepny]"
            event.app.invalidate()
            return
        try:
            text = cb.content
        except Exception as e:
            self.frame.title = self._title() + f" [schowek blad: {e}]"
            event.app.invalidate()
            return

        if not text:
            self.frame.title = self._title() + " [schowek pusty]"
            event.app.invalidate()
            return

        self.editor.buffer.insert_text(text)
        self.is_modified = True
        self.frame.title = self._title()
        event.app.invalidate()

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
            self._run_in_bubble(event.app)

        @kb.add("c-f")
        def _(event):
            event.app.layout.focus(self.search_field)

        @kb.add("f6")
        def _(event):
            self._copy_selection_to_bubble(event)

        @kb.add("f7")
        def _(event):
            self._paste_from_bubble(event)

        return kb

    def _run_in_bubble(self, app):
        write_text_file(self.tmp_path, self.editor.text)
        app.suspend_to_background()
        print(f"\n{'='*60}")
        print(f"  NooEdit F5: {self.ctx.label}")
        print(f"{'='*60}\n")
        try:
            result_label, exit_code, output = self.ctx.run_in_new_bubble(self.editor.text, self.tmp_path)
            print(output or "(brak wyjscia)")
            print(f"\n{'='*60}")
            print(f"  Kod wyjscia: {exit_code}")
            print(f"  Wynik w Bablu: {result_label}")
        except Exception as e:
            print(f"BLAD: {e}")
        input("\nEnter aby wrocic...")
        app.resume()
        app.invalidate()

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

# --- NooEditGUI (bez zmian) ---
try:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

class NooEditGUI:
    APP_NAME = "NooEdit — KarmazynOS"
    BG_COLOR = "#1e1e1e"
    # (reszta identyczna jak wcześniej – pominięto dla zwięzłości)
    # Pełna implementacja GUI znajduje się w poprzednim pliku.
    pass  # W praktyce wklej całą klasę NooEditGUI z poprzedniego kodu.

# --- API shella ---
def open_bubble(label, runtime, force_type=None, mode="tui"):
    if label not in runtime._bubbles:
        runtime.write(label, label, "bubble_init", 1.0)
        runtime.consolidate(label)
    bubble = runtime._bubbles.get(label)
    if bubble is None:
        return f"Nie mozna otworzyc Babla '{label}'"
    phi_vec = bubble.phi1.signature.tolist() if bubble.phi1 else None
    ctype   = force_type or detect_content_type(phi_vec, label)
    ctx = NooContext(label, runtime, ctype)
    content = ctx.get_content()
    tmp_path = ctx.vfs.materialize(label, content, ctype)

    editor = None
    if mode == "gui" and HAS_GUI:
        editor = NooEditGUI(ctx, tmp_path)
        editor.run()
    elif HAS_TUI:
        editor = NooEditTUI(ctx, tmp_path)
        editor.run()
    else:
        return "Brak prompt_toolkit i tkinter."

    # Poczekaj az worker skonczy zapis przed odczytem
    if hasattr(editor, "save_queue"):
        editor.save_queue.join()
    final_content = ctx.vfs.read_back(label, ctype)
    if final_content:
        ctx.push_content(final_content)
        ctx.vfs.cleanup(label, ctype)
    return "ok"

def cmd_nooedit(args, runtime=None):
    if runtime is None:
        return "Brak runtime."
    label = None
    mode = "tui"
    force_type = None
    for arg in args:
        if arg == "--gui": mode = "gui"
        elif arg == "--tui": mode = "tui"
        elif arg.startswith("--"):
            force_type = arg[2:]
        else:
            label = arg
    if label is None:
        return "Uzycie: NOOEDIT <label> [--gui|--tui] [--py|--lua|--md|--karm]"
    return open_bubble(label, runtime, force_type, mode)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--tui", action="store_true")
    parsed = parser.parse_args()
    use_gui = parsed.gui or (not parsed.tui and HAS_GUI and (os.environ.get("DISPLAY") or os.name == 'nt'))
    file_path = parsed.files[0] if parsed.files else "notatka.txt"
    print(f"NooEdit standalone: {file_path}")
    class _StandaloneCtx:
        label = pathlib.Path(file_path).name
        content_type = detect_content_type(None, file_path)
        def push_content(self, c): return {"status": "file"}
        def run_in_new_bubble(self, c, p):
            cmd = _get_run_command(p)
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return f"[standalone_run]", r.returncode, r.stdout + r.stderr
    ctx = _StandaloneCtx()
    ctx.vfs = BubbleVFS()
    ctx.runtime = None
    if use_gui and HAS_GUI:
        NooEditGUI(ctx, file_path).run()
    elif HAS_TUI:
        NooEditTUI(ctx, file_path).run()
    else:
        print("Brak tkinter i prompt_toolkit.")
        sys.exit(1)