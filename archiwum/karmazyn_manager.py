"""
karmazyn_manager.py — Zarządca dokumentów KarmazynOS v1.0
==========================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Zarządca który pokazuje dokumenty z bąbli i pozwala nimi zarządzać.
Hub systemu: otwiera tekst w edytorze, audio w odtwarzaczu.

Filozofia (jak menedżer plików / Finder): lista pozycji, akcje na nich.
Użytkownik widzi nazwy, typy, rozmiary. NIE widzi atomów ani phi.

Cała mechanika w karmazyn_app.Workspace. Zarządca woła tylko
ws.list() / ws.open() / ws.delete() / ws.rename().

Przenośność: ten sam czytnik klawiszy co edytor (termios/msvcrt),
fallback do trybu liniowego gdy brak TTY.

Sterowanie (tryb pełnoekranowy):
  ↑ / ↓        — wybór pozycji
  Enter        — otwórz (tekst→edytor, audio→odtwarzacz, reszta→info)
  d            — usuń (z potwierdzeniem)
  r            — zmień nazwę
  i            — szczegóły
  n            — nowy dokument tekstowy
  q            — wyjście
"""

import os
import sys
import time
from typing import List, Optional

from karmazyn_app import Workspace, Item


# ─── Formatowanie ─────────────────────────────────────────────────────────────

def _human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n/1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n/1024/1024:.1f} MB"
    return f"{n/1024/1024/1024:.1f} GB"


def _human_time(ts: float) -> str:
    if not ts:
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return "—"


_KIND_ICON = {
    "text":   "✎",   # dokument tekstowy
    "audio":  "♪",   # utwór
    "image":  "▦",   # obraz
    "binary": "▪",   # dane
}


# ═══════════════════════════════════════════════════════════════════════════════
# KarmazynManager
# ═══════════════════════════════════════════════════════════════════════════════

class KarmazynManager:
    """
    Zarządca dokumentów. Cienka powłoka nad Workspace.
    Render ANSI, wejście przez przenośny czytnik klawiszy.
    """

    def __init__(self, workspace: Workspace):
        self.ws       = workspace
        self.items: List[dict] = []
        self.sel      = 0
        self.status   = ""
        self._running = False
        self.refresh()

    def refresh(self) -> None:
        self.items = self.ws.list()
        if self.sel >= len(self.items):
            self.sel = max(0, len(self.items) - 1)

    # ── Render ────────────────────────────────────────────────────────────────

    def _term_size(self):
        try:
            sz = os.get_terminal_size()
            return sz.columns, sz.lines
        except OSError:
            return 80, 24

    def _render(self) -> None:
        cols, rows = self._term_size()
        out = ["\033[2J\033[H"]

        head = f" KarmazynOS · Dokumenty ({len(self.items)})"
        out.append(f"\033[7m{head:<{cols}}\033[0m\r\n")

        list_rows = rows - 3
        top = max(0, self.sel - list_rows + 1) if self.sel >= list_rows else 0

        if not self.items:
            out.append("\r\n  \033[90m(brak dokumentów — 'n' tworzy nowy)\033[0m\r\n")
        else:
            for i in range(top, min(top + list_rows, len(self.items))):
                d    = self.items[i]
                icon = _KIND_ICON.get(d["kind"], "▪")
                name = d["name"][:32]
                size = _human_size(d["size"])
                when = _human_time(d.get("updated", 0))
                line = f" {icon} {name:<33} {size:>9}  {when}"
                if i == self.sel:
                    out.append(f"\033[7m{line[:cols]:<{cols}}\033[0m\r\n")
                else:
                    out.append(f"{line[:cols]}\r\n")

        # status bar
        info = (" Enter otwórz  n nowy  d usuń  r zmień nazwę  i info  q wyjście")
        if self.status:
            info = f" {self.status}"
            self.status = ""
        out.append(f"\033[{rows};1H\033[7m{info[:cols]:<{cols}}\033[0m")

        sys.stdout.write("".join(out))
        sys.stdout.flush()

    # ── Akcje ─────────────────────────────────────────────────────────────────

    def _selected_name(self) -> Optional[str]:
        if 0 <= self.sel < len(self.items):
            return self.items[self.sel]["name"]
        return None

    def _open_selected(self, reader) -> None:
        name = self._selected_name()
        if name is None:
            return
        d = self.items[self.sel]
        kind = d["kind"]

        if kind == "text":
            self._launch_editor(name, reader)
        elif kind == "audio":
            self._launch_player(name, reader)
        else:
            self._show_info(name, reader)
        self.refresh()

    def _launch_editor(self, name: str, reader) -> None:
        """Otwórz dokument w edytorze (współdzieli ten sam Workspace/phi)."""
        try:
            from karmazyn_edit import BubbleEditor
        except ImportError:
            self.status = "Edytor niedostępny (brak karmazyn_edit)"
            return
        # zwolnij terminal raw na czas edytora
        self._suspend_raw(reader)
        editor = BubbleEditor(self.ws, name)
        editor.run()
        self._resume_raw(reader)

    def _launch_player(self, name: str, reader) -> None:
        """Odtwórz utwór (współdzieli Workspace/phi)."""
        try:
            from karmazyn_play import KarmazynPlayer
        except ImportError:
            self.status = "Odtwarzacz niedostępny (brak karmazyn_play)"
            return
        self._suspend_raw(reader)
        player = KarmazynPlayer(self.ws)
        player.run_interactive(name)
        self._resume_raw(reader)

    def _show_info(self, name: str, reader) -> None:
        item = self.ws.open(name)
        vers = self.ws.versions(name)
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.write(f"Szczegóły: {name}\r\n\r\n")
        if item:
            sys.stdout.write(f"  Typ:      {item.kind}\r\n")
            sys.stdout.write(f"  Rozmiar:  {_human_size(item.size)}\r\n")
            sys.stdout.write(f"  Zmieniony:{_human_time(item.updated)}\r\n")
            sys.stdout.write(f"  Wersje:   {len(vers)}\r\n")
            if item.is_text and item.text:
                preview = item.text[:200].replace("\n", " ")
                sys.stdout.write(f"\r\n  Podgląd: {preview}...\r\n")
        sys.stdout.write("\r\nKlawisz aby wrócić...")
        sys.stdout.flush()
        reader.read_key()

    def _delete_selected(self, reader) -> None:
        name = self._selected_name()
        if name is None:
            return
        self.status = f"Usunąć '{name}'? (t/n)"
        self._render()
        k = reader.read_key()
        if k in ("t", "T", "y", "Y"):
            self.ws.delete(name)
            self.status = f"Usunięto '{name}'"
            self.refresh()
        else:
            self.status = "Anulowano"

    def _rename_selected(self, reader) -> None:
        name = self._selected_name()
        if name is None:
            return
        new = self._read_line(reader, f"Nowa nazwa dla '{name}': ")
        if new and new != name:
            if self.ws.exists(new):
                self.status = f"'{new}' już istnieje"
            else:
                self.ws.rename(name, new)
                self.status = f"Zmieniono na '{new}'"
                self.refresh()

    def _new_document(self, reader) -> None:
        name = self._read_line(reader, "Nazwa nowego dokumentu: ")
        if not name:
            return
        if self.ws.exists(name):
            self.status = f"'{name}' już istnieje"
            return
        self.ws.save(name, "")
        self.refresh()
        # ustaw selekcję na nowy i otwórz w edytorze
        for i, d in enumerate(self.items):
            if d["name"] == name:
                self.sel = i
                break
        self._launch_editor(name, reader)
        self.refresh()

    # ── Pomocnicze wejście ───────────────────────────────────────────────────

    def _read_line(self, reader, prompt: str) -> str:
        cols, rows = self._term_size()
        sys.stdout.write(f"\033[{rows};1H\033[7m\033[K{prompt}\033[0m")
        sys.stdout.flush()
        chars = []
        while True:
            k = reader.read_key()
            if k == "ENTER":
                break
            elif k == "BACKSPACE":
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
            elif isinstance(k, str) and len(k) == 1 and k >= " ":
                chars.append(k)
                sys.stdout.write(k)
            sys.stdout.flush()
        return "".join(chars).strip()

    def _suspend_raw(self, reader) -> None:
        """Wyjdź z trybu raw przed uruchomieniem pod-aplikacji."""
        try:
            reader.__exit__(None, None, None)
        except Exception:
            pass

    def _resume_raw(self, reader) -> None:
        """Wróć do trybu raw po pod-aplikacji."""
        try:
            reader.__enter__()
        except Exception:
            pass

    # ── Pętla ─────────────────────────────────────────────────────────────────

    def run(self) -> str:
        try:
            from karmazyn_edit import make_key_reader
        except ImportError:
            make_key_reader = lambda: None
        reader = make_key_reader()
        if reader is None:
            return self._run_line_mode()

        self._running = True
        with reader:
            while self._running:
                self._render()
                key = reader.read_key()
                self._handle(key, reader)
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        return "ok"

    def _handle(self, key, reader) -> None:
        if key == "UP":
            self.sel = max(0, self.sel - 1)
        elif key == "DOWN":
            self.sel = min(len(self.items) - 1, self.sel + 1) if self.items else 0
        elif key == "ENTER":
            self._open_selected(reader)
        elif key in ("d", "D"):
            self._delete_selected(reader)
        elif key in ("r", "R"):
            self._rename_selected(reader)
        elif key in ("i", "I"):
            name = self._selected_name()
            if name:
                self._show_info(name, reader)
        elif key in ("n", "N"):
            self._new_document(reader)
        elif key in ("q", "Q", "QUIT"):
            self._running = False

    # ── Fallback liniowy ───────────────────────────────────────────────────────

    def _run_line_mode(self) -> str:
        print("[KarmazynOS zarządca]")
        print("Polecenia: l(ista) o NAZWA(otwórz) d NAZWA(usuń) "
              "r STARA NOWA(zmień) i NAZWA(info) q(wyjdź)")
        while True:
            try:
                cmd = input("» ").strip()
            except EOFError:
                break
            if not cmd:
                continue
            parts = cmd.split()
            c = parts[0].lower()

            if c == "q":
                break
            elif c == "l":
                self.refresh()
                if not self.items:
                    print("  (brak dokumentów)")
                for d in self.items:
                    icon = _KIND_ICON.get(d["kind"], "▪")
                    print(f"  {icon} {d['name']:<24} {d['kind']:<7} "
                          f"{_human_size(d['size']):>9}")
            elif c == "o" and len(parts) >= 2:
                name = " ".join(parts[1:])
                item = self.ws.open(name)
                if item is None:
                    print(f"  Nie ma '{name}'")
                elif item.is_text:
                    try:
                        from karmazyn_edit import BubbleEditor
                        BubbleEditor(self.ws, name).run()
                    except ImportError:
                        print("  Edytor niedostępny")
                elif item.is_audio:
                    try:
                        from karmazyn_play import KarmazynPlayer
                        KarmazynPlayer(self.ws).run_interactive(name)
                    except ImportError:
                        print("  Odtwarzacz niedostępny")
                else:
                    print(f"  {name}: {item.kind}, {_human_size(item.size)}")
            elif c == "d" and len(parts) >= 2:
                name = " ".join(parts[1:])
                if self.ws.delete(name):
                    print(f"  Usunięto '{name}'")
                else:
                    print(f"  Nie ma '{name}'")
            elif c == "r" and len(parts) >= 3:
                self.ws.rename(parts[1], parts[2])
                print(f"  {parts[1]} → {parts[2]}")
            elif c == "i" and len(parts) >= 2:
                name = " ".join(parts[1:])
                item = self.ws.open(name)
                if item:
                    print(f"  {name}: {item.kind}, {_human_size(item.size)}, "
                          f"{_human_time(item.updated)}, "
                          f"{len(self.ws.versions(name))} wersji")
                else:
                    print(f"  Nie ma '{name}'")
            else:
                print("  Nieznane polecenie")
        return "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# Komenda powłoki
# ═══════════════════════════════════════════════════════════════════════════════

_WS: Optional[Workspace] = None


def cmd_manager(args: List[str], phi=None) -> str:
    """
    FILES / DOCS — otwórz zarządcę dokumentów.
    Współdzieli phi-space z resztą systemu.
    """
    global _WS
    if _WS is None or (phi is not None and _WS.phi is not phi):
        _WS = Workspace(phi=phi)
    mgr = KarmazynManager(_WS)
    return mgr.run()


if __name__ == "__main__":
    ws = Workspace()
    KarmazynManager(ws).run()