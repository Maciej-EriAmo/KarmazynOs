#!/usr/bin/env python3
"""
Nooedit.py — Edytor Bąbli KarmazynOS v5.2
==========================================
Edytor wbudowany w SDL workspace — lewy panel.
Bąbel jest dokumentem: bubble.content to canonical source.

Tryby (auto-detect):
  SDL aktywny → EditorState w lewym panelu SDL
  Terminal    → NooEditTUI (prompt_toolkit)

Architektura:
  NooContext      — łącznik edytor ↔ runtime (bąble + phi-space)
  EditorState     — bufor tekstu z kursorem (w karmazyn_display)
  draw_editor()   — immediate mode renderer (w karmazyn_display)
  BubbleVFS       — szyfrowany backup (w karmazyn_vfs)
  FileWatcher     — obserwacja zmian (w karmazyn_sdl_utils)

Izomorfizm phi-space:
  Edytowany bąbel = HOT atom (T=90 przy edycji, stygnie po zamknięciu)
  VFS backup = persistentna emanacja atomu między sesjami
"""

import contextlib
import hashlib
import io
import os
import pathlib
import subprocess
import sys
import threading
import time
import queue
from typing import Optional

# ── Importy wewnętrzne KarmazynOS ─────────────────────────────────────────────
from karmazyn_vfs import BubbleVFS, vfs_workspace_key
from karmazyn_sdl_utils import FileWatcher, is_sdl_mode, find_external_editor

# Importy SDL — opcjonalne (brak gdy pygame niedostępny)
try:
    from karmazyn_display import EditorState, draw_editor, C_FG
    _SDL_DISPLAY_OK = True
except ImportError:
    EditorState = None
    draw_editor = None
    C_FG        = (200, 200, 200)
    _SDL_DISPLAY_OK = False


def read_text_file(path: str) -> str:
    """Prosta funkcja odczytu."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def write_text_file(path: str, content: str) -> None:
    """Prosta funkcja zapisu."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


@contextlib.contextmanager
def _silent():
    """Tłumi stdout/stderr — dla cichej konsolidacji atomów."""
    with contextlib.redirect_stdout(io.StringIO()), \
         contextlib.redirect_stderr(io.StringIO()):
        yield


class NooContext:
    """
    Łącznik edytor ↔ KarmazynOS.
    Canonical source: bubble.content (nie plik, nie VFS).
    VFS = zaszyfrowany backup na restart.
    """

    def __init__(self, label: str, runtime, content_type: str = "py"):
        self.label        = label
        self.runtime      = runtime  # Oczekiwany obiekt PhiSpace
        self.content_type = content_type
        self.vfs          = BubbleVFS()
        self._last_hash   = ""

    def get_bubble(self):
        return getattr(self.runtime, "_bubbles", {}).get(self.label) if self.runtime else None

    def get_content(self) -> str:
        # 1. Canonical: bąbel
        bubble = self.get_bubble()
        if bubble:
            content = getattr(bubble, "content", "")
            if content and content not in ("bubble_init", "", self.label):
                return content
        
        # 2. Fallback: VFS (zaszyfrowany backup)
        # Używa content_type zgodnie z API z karmazyn_vfs.py
        if self.vfs.has(self.label, self.content_type):
            return self.vfs.load(self.label, self.content_type)
        
        # 3. Domyślny szablon
        lang = {"py":"Python","lua":"Lua","md":"Markdown",
                "txt":"Tekst","karm":"KarmazynScript"}.get(self.content_type, "?")
        return (f"# Babl \'{self.label}\' [{lang}]\n"
                f"# Ctrl+S: zapisz  F5: uruchom  Ctrl+Q: wyjdz\n")

    def push_content(self, new_content: str) -> dict:
        h = hashlib.md5(new_content.encode("utf-8")).hexdigest()
        if h == self._last_hash:
            return {"status": "unchanged"}
        self._last_hash = h

        # 1. Canonical: bąbel dostaje treść bezpośrednio
        bubble = self.get_bubble()
        if bubble is not None:
            bubble.content = new_content

        # 2. Backup: zaszyfrowany VFS (używa .save() i content_type z karmazyn_vfs.py)
        self.vfs.save(self.label, new_content, self.content_type)

        # 3. Konsolidacja atomu (synchronizuje phi-space)
        tmp_id = None
        try:
            tmp_id = f"nooedit_{self.label}_{int(time.time())}"
            with _silent():
                # Zgodne z API PhiSpace
                self.runtime.create_atom(tmp_id, new_content[:256], self.label, T=90.0)
                self.runtime.consolidate(tmp_id, self.label)
                result = {"status": "absorbed"}
        except Exception as e:
            result = {"status": "absorbed", "note": f"konsolidacja: {e}"}
        finally:
            if tmp_id and self.runtime.has_atom(tmp_id):
                try: self.runtime.delete_atom(tmp_id)
                except Exception: pass
        return result

    def run_in_new_bubble(self, content: str, tmp_path: str):
        """Uruchom kod — output trafia do nowego bąbla jako atom."""
        result_label = f"{self.label}_run_{int(time.time())}"
        code_id      = f"code_{result_label}"
        try:
            # Atom z kodem źródłowym (Zgodne z PhiSpace)
            with _silent():
                self.runtime.create_atom(code_id, code_id, content, T=80.0)
                self.runtime.consolidate(code_id, result_label)
                
            # Subprocess
            cmd  = self._get_run_command(tmp_path)
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=30, encoding="utf-8", errors="replace")
            output = proc.stdout + proc.stderr
            
            # Atom z outputem (Pozostawiamy jako artefakt)
            out_id = f"out_{result_label}"
            self.runtime.create_atom(out_id, output[:512] or "(brak wyjscia)", result_label, T=80.0)
            self.runtime.consolidate(out_id, result_label)
            
            return result_label, proc.returncode, output
        except subprocess.TimeoutExpired:
            return result_label, -1, "TIMEOUT"
        except Exception as e:
            return result_label, -1, f"BLAD: {e}"
        finally:
            if self.runtime.has_atom(code_id):
                try: self.runtime.delete_atom(code_id)
                except Exception: pass

    def _get_run_command(self, file_path: str):
        import shutil as _sh
        ext = pathlib.Path(file_path).suffix.lower()
        if ext == ".py":
            return [sys.executable, "-u", file_path]
        if ext in (".lua", ".karm"):
            for c in ("lua","lua5.4","lua5.3","luajit"):
                found = _sh.which(c)
                if found: return [found, file_path]
            raise FileNotFoundError("Brak interpretera Lua")
        if ext in (".sh", ".bash"):
            sh = _sh.which("bash") or _sh.which("sh")
            if sh: return [sh, file_path]
            raise FileNotFoundError("Brak bash/sh")
        return [file_path]


# --- NooEditSDL — tryb zewnętrznego edytora ---

class NooEditSDL:
    """
    Otwiera zewnętrzny edytor w nowym oknie.
    Obserwuje plik przez FileWatcher.
    Callback on_change informuje shell (term_state.append).
    """

    def __init__(self, ctx: NooContext, tmp_path: str,
                 term_state=None):
        self.ctx       = ctx
        self.tmp_path  = tmp_path
        self.term_state = term_state
        self._proc     = None
        self._watcher  = None
        self._done     = threading.Event()

    def _notify(self, msg: str):
        if self.term_state is not None:
            try:
                self.term_state.append(msg, (180, 220, 100))
            except Exception:
                pass

    def _on_file_change(self, path: str):
        """FileWatcher callback — plik zmieniony → zapisz do VFS."""
        try:
            content = read_text_file(path)
            result  = self.ctx.push_content(content)
            status  = result.get("status", "?") if isinstance(result, dict) else str(result)
            self._notify(f"NooEdit: zapisano {self.ctx.label} [{status}]")
        except Exception as e:
            self._notify(f"NooEdit: blad zapisu: {e}")

    def run(self) -> str:
        """
        Otwiera edytor, czeka na zamknięcie, zapisuje finalnie.
        Wywołuj z wątku roboczego (nie main SDL thread).
        """
        editor_args, _wait = find_external_editor()

        if editor_args is None:
            return ("Brak zewnetrznego edytora.\n"
                    f"Edytuj recznie: {self.tmp_path}")

        cmd = editor_args + [self.tmp_path]
        self._notify(f"NooEdit: otwieram {self.ctx.label} w {editor_args[0]}...")

        # FileWatcher — live sync podczas edycji
        self._watcher = FileWatcher(self.tmp_path, self._on_file_change)
        self._watcher.start()

        try:
            self._proc = subprocess.Popen(cmd)
            self._proc.wait()   # czekaj na zamknięcie edytora
        except FileNotFoundError as e:
            if self._watcher: self._watcher.stop()
            return f"Blad uruchomienia edytora: {e}"
        finally:
            if self._watcher: self._watcher.stop()

        # Finalny zapis po zamknięciu
        self._on_file_change(self.tmp_path)
        self._notify(f"NooEdit: {self.ctx.label} zamkniety.")
        return "ok"


# --- TUI (prompt_toolkit) — tylko tryb terminalowy ---

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
    HAS_TUI = False


class NooEditTUI:
    APP_NAME = "NooEdit — KarmazynOS"

    def __init__(self, ctx, tmp_path):
        self.ctx             = ctx
        self.tmp_path        = tmp_path
        self.is_modified     = False
        self.save_queue      = queue.Queue()
        self.last_save_status = "?"
        self.app             = None
        self.save_thread     = threading.Thread(
            target=self._save_worker, daemon=True)
        self.save_thread.start()
        self.search_field = SearchToolbar()
        initial = read_text_file(tmp_path) if os.path.exists(tmp_path) else ""
        self.editor = TextArea(
            text=initial, scrollbar=True, line_numbers=True,
            multiline=True, search_field=self.search_field,
            focus_on_click=True)
        self.editor.buffer.on_text_changed += lambda _: self._on_change()
        self.frame  = Frame(self.editor, title=self._title())
        self.status = Window(
            height=1,
            content=FormattedTextControl(self._status_bar),
            style="class:status")
        self.kb = self._make_kb()

    def _save_worker(self):
        while True:
            item = self.save_queue.get()
            if item is None:
                self.save_queue.task_done(); break
            with _silent():
                try:
                    write_text_file(self.tmp_path, item)
                    result = self.ctx.push_content(item)
                except Exception as e:
                    result = {"status": f"error:{e}"}
            self.last_save_status = result.get("status", "?")
            self.save_queue.task_done()
            self.frame.title = self._title()
            if self.app and hasattr(self.app, 'invalidate'):
                try:
                    if hasattr(self.app, 'call_from_executor'):
                        self.app.call_from_executor(self.app.invalidate)
                    else:
                        self.app.invalidate()
                except Exception: 
                    pass

    def _title(self):
        ct   = {"py":"Python","lua":"Lua","md":"MD",
                "txt":"TXT","karm":"Karm"}.get(self.ctx.content_type, "?")
        mark = "*" if self.is_modified else ""
        return f"{self.APP_NAME} | {self.ctx.label} [{ct}]{mark}"

    def _on_change(self):
        if not self.is_modified:
            self.is_modified = True
            self.frame.title = self._title()

    def _status_bar(self):
        row = self.editor.document.cursor_position_row + 1
        col = self.editor.document.cursor_position_col + 1
        return [("class:status",
                 f" Ln {row}, Col {col} | Ctrl+S: zapisz"
                 f" | F5: uruchom | Ctrl+Q: wyjdz"
                 f" | save: {self.last_save_status} ")]

    def _make_kb(self):
        kb = KeyBindings()

        @kb.add("c-s")
        def _(event):
            self.save_queue.put(self.editor.text)
            self.is_modified     = False
            self.frame.title     = self._title() + " [saving...]"
            event.app.invalidate()

        @kb.add("c-q")
        def _(event):
            if self.is_modified:
                self.save_queue.put(self.editor.text)
            event.app.exit()

        @kb.add("f5")
        def _(event):
            write_text_file(self.tmp_path, self.editor.text)
            app = event.app
            app.suspend_to_background()
            print(f"\n{'='*60}\n  NooEdit F5: {self.ctx.label}\n{'='*60}\n")
            try:
                _, exit_code, output = self.ctx.run_in_new_bubble(
                    self.editor.text, self.tmp_path)
                print(output or "(brak wyjscia)")
                print(f"\n{'='*60}\n  Kod wyjscia: {exit_code}")
            except Exception as e:
                print(f"BLAD: {e}")
            input("\nEnter aby wrocic...")
            app.resume()
            app.invalidate()

        @kb.add("c-f")
        def _(event):
            event.app.layout.focus(self.search_field)

        return kb

    def run(self):
        style  = Style.from_dict({
            "status":      "bg:#1a3a5c #ffffff",
            "frame.label": "#ffffff bold",
            "search":      "bg:cyan #000000",
        })
        layout = Layout(HSplit([self.frame, self.search_field, self.status]))
        app    = Application(
            layout=layout, key_bindings=self.kb,
            full_screen=True, mouse_support=True, style=style)
        self.app = app
        try:
            with patch_stdout(raw=True):
                app.run()
        finally:
            self.save_queue.put(None)
            self.save_thread.join(timeout=1.0)
            self.app = None


# --- Główna komenda ---

def cmd_nooedit(args, runtime=None, term_state=None, display=None):
    if runtime is None:
        return "Brak runtime."
    if not args:
        return "Uzycie: NOOEDIT <label> [--py|--lua|--md|--karm]"

    label = args[0]
    force_type = None
    for a in args[1:]:
        if a.startswith("--"):
            force_type = a[2:]
    if force_type is None:
        ext = label.split(".")[-1] if "." in label else ""
        force_type = ext if ext in ("py","lua","md","txt","karm") else "py"

    if label not in getattr(runtime, "_bubbles", {}):
        try:
            # Zgodnie z PhiSpace
            runtime.create_atom(label, label, "bubble_init", T=90.0)
            runtime.consolidate(label, label)
        except Exception:
            pass

    ctx     = NooContext(label, runtime, force_type)
    content = ctx.get_content()

    # SDL workspace
    try:
        import pygame
        sdl_ok = pygame.display.get_init()
    except ImportError:
        sdl_ok = False

    if sdl_ok and _SDL_DISPLAY_OK:
        import builtins
        if display is None:
            display = getattr(builtins, "_KARMAZYN_DISPLAY", None)
        if display is None:
            display = getattr(runtime, "_display", None)

        if display and getattr(display, "available", False) and getattr(display, "renderer", None):
            renderer = display.renderer
            state    = EditorState(label, content, force_type)
            state.status = "Ctrl+S zapisz | Ctrl+Q wyjdz | F5 uruchom"

            renderer.claim_left(lambda ctx_arg: draw_editor(ctx_arg, state),
                                f"NOOEDIT:{label}")
            renderer.set_editor(state)

            if term_state:
                term_state.append(
                    "NooEdit: " + label + " [" + force_type + "] — edytuj w lewym panelu",
                    (180, 220, 100))

            import subprocess as _sp
            C_OK  = (100, 200, 100)
            C_ERR = (220, 80, 80)
            C_INF = (255, 200, 50)
            C_TXT = (200, 200, 200)

            try:
                while not state._quit:
                    action = state.process_key()

                    if action == "save" or state._save:
                        state._save  = False
                        result = ctx.push_content(state.get_text())
                        status = result.get("status","?") if isinstance(result,dict) else str(result)
                        state.status = "Zapisano [" + status + "] | Ctrl+Q wyjdz | F5 uruchom"
                        if term_state:
                            term_state.append("NooEdit: zapisano " + label, C_OK)

                    elif action == "run" or state._run:
                        state._run   = False
                        tmp = ctx.vfs.materialize(label, state.get_text(), force_type)
                        state.status = "Uruchamianie..."
                        if term_state:
                            term_state.append("NooEdit: uruchamiam " + label + "...", C_INF)
                        try:
                            cmd  = ctx._get_run_command(tmp)
                            proc = _sp.run(cmd, capture_output=True, text=True,
                                           timeout=30, encoding="utf-8", errors="replace")
                            out  = (proc.stdout + proc.stderr).strip()
                            msg  = out if out else "(exit " + str(proc.returncode) + ")"
                            if term_state:
                                for ln in msg.split("\n")[:30]:
                                    term_state.append(ln, C_TXT)
                            state.status = ("exit:" + str(proc.returncode)
                                            + " | Ctrl+S zapisz | Ctrl+Q wyjdz")
                        except Exception as e:
                            if term_state:
                                term_state.append("Blad: " + str(e), C_ERR)
                            state.status = "Blad uruchomienia | Ctrl+Q wyjdz"
            finally:
                renderer.release_left()
                if state.modified:
                    ctx.push_content(state.get_text())
                    if term_state:
                        term_state.append("NooEdit: auto-zapis " + label, C_OK)
            
            # API z karmazyn_vfs.py — używamy content_type (force_type)
            ctx.vfs.cleanup_tmp(label, force_type)
            return "ok"

    # Fallback TUI
    try:
        from prompt_toolkit import Application
        HAS_TUI = True
    except ImportError:
        HAS_TUI = False

    if not HAS_TUI:
        return "Brak SDL display i prompt_toolkit."

    tmp2   = ctx.vfs.materialize(label, content, force_type)
    editor = NooEditTUI(ctx, tmp2)
    editor.run()
    
    # API z karmazyn_vfs.py — używamy content_type (force_type)
    final = ctx.vfs.load(label, force_type)
    if final:
        ctx.push_content(final)
    ctx.vfs.cleanup_tmp(label, force_type)
    return "ok"