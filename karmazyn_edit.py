"""
karmazyn_edit.py — Edytor tekstu KarmazynOS v1.0
=================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Edytor który działa NA BĄBLACH, wewnątrz KarmazynOS. Bez plików
tymczasowych, bez zewnętrznych bibliotek (tylko stdlib), bez wiedzy
o tym jak system jest zbudowany.

Filozofia (jak Notatnik / TextEdit):
  Użytkownik widzi: nazwę dokumentu i pole tekstu.
  NIE widzi: atomów, bąbli, phi-space, temperatur.
  Otwiera, pisze, zapisuje. Koniec.

Cała maszyneria w karmazyn_app.Workspace (warstwa-pod-maską).
Edytor woła tylko ws.open() / ws.save() / ws.list().

Przenośność:
  Wejście klawiatury: termios/tty (Unix/Termux) lub msvcrt (Windows).
  Wyświetlanie: ANSI escape (Windows Terminal + Termux to wspierają).
  Gdy brak interaktywnego TTY → tryb liniowy (zawsze działa).

Rozdział testowalności:
  EditBuffer  — czysta logika bufora tekstu (kursor, wstaw, usuń) — testowalna
  BubbleEditor— pętla TTY + render ANSI (cienka powłoka wokół EditBuffer)

Sterowanie (tryb pełnoekranowy):
  strzałki      — ruch kursora
  Enter         — nowa linia
  Backspace     — usuń znak
  Ctrl+S        — zapisz do dokumentu
  Ctrl+Q        — wyjście (pyta o zapis gdy są zmiany)
  Ctrl+K        — usuń linię
  Home / End    — początek / koniec linii
"""

import os
import sys
from typing import List, Optional, Tuple

from karmazyn_app import Workspace, Item


# ═══════════════════════════════════════════════════════════════════════════════
# EditBuffer — czysta logika bufora (testowalna bez TTY)
# ═══════════════════════════════════════════════════════════════════════════════

class EditBuffer:
    """
    Bufor tekstu: lista linii + pozycja kursora (row, col).
    Cała logika edycji tu — bez I/O, w pełni testowalna.
    """

    def __init__(self, text: str = ""):
        self.set_text(text)
        self.modified = False

    def set_text(self, text: str) -> None:
        self.lines: List[str] = text.split("\n") if text else [""]
        if not self.lines:
            self.lines = [""]
        self.row = 0
        self.col = 0
        self.modified = False

    def get_text(self) -> str:
        return "\n".join(self.lines)

    # ── Ruch kursora ──────────────────────────────────────────────────────────

    def _clamp(self) -> None:
        self.row = max(0, min(self.row, len(self.lines) - 1))
        self.col = max(0, min(self.col, len(self.lines[self.row])))

    def move_left(self) -> None:
        if self.col > 0:
            self.col -= 1
        elif self.row > 0:
            self.row -= 1
            self.col = len(self.lines[self.row])

    def move_right(self) -> None:
        if self.col < len(self.lines[self.row]):
            self.col += 1
        elif self.row < len(self.lines) - 1:
            self.row += 1
            self.col = 0

    def move_up(self) -> None:
        if self.row > 0:
            self.row -= 1
            self.col = min(self.col, len(self.lines[self.row]))

    def move_down(self) -> None:
        if self.row < len(self.lines) - 1:
            self.row += 1
            self.col = min(self.col, len(self.lines[self.row]))

    def home(self) -> None:
        self.col = 0

    def end(self) -> None:
        self.col = len(self.lines[self.row])

    # ── Edycja ────────────────────────────────────────────────────────────────

    def insert(self, ch: str) -> None:
        line = self.lines[self.row]
        self.lines[self.row] = line[:self.col] + ch + line[self.col:]
        self.col += len(ch)
        self.modified = True

    def newline(self) -> None:
        line  = self.lines[self.row]
        left  = line[:self.col]
        right = line[self.col:]
        self.lines[self.row] = left
        self.lines.insert(self.row + 1, right)
        self.row += 1
        self.col = 0
        self.modified = True

    def backspace(self) -> None:
        if self.col > 0:
            line = self.lines[self.row]
            self.lines[self.row] = line[:self.col - 1] + line[self.col:]
            self.col -= 1
            self.modified = True
        elif self.row > 0:
            prev_len = len(self.lines[self.row - 1])
            self.lines[self.row - 1] += self.lines[self.row]
            del self.lines[self.row]
            self.row -= 1
            self.col = prev_len
            self.modified = True

    def delete(self) -> None:
        """Delete pod kursorem (forward delete)."""
        line = self.lines[self.row]
        if self.col < len(line):
            self.lines[self.row] = line[:self.col] + line[self.col + 1:]
            self.modified = True
        elif self.row < len(self.lines) - 1:
            self.lines[self.row] += self.lines[self.row + 1]
            del self.lines[self.row + 1]
            self.modified = True

    def kill_line(self) -> None:
        """Usuń bieżącą linię."""
        if len(self.lines) == 1:
            self.lines[0] = ""
            self.col = 0
        else:
            del self.lines[self.row]
            self.row = min(self.row, len(self.lines) - 1)
            self.col = min(self.col, len(self.lines[self.row]))
        self.modified = True

    def stats(self) -> dict:
        text = self.get_text()
        return {
            "lines": len(self.lines),
            "chars": len(text),
            "row":   self.row + 1,
            "col":   self.col + 1,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Wejście klawiatury — przenośne (Unix/Termux + Windows)
# ═══════════════════════════════════════════════════════════════════════════════

# Logiczne klawisze (zwracane przez read_key)
K_UP, K_DOWN, K_LEFT, K_RIGHT = "UP", "DOWN", "LEFT", "RIGHT"
K_HOME, K_END, K_DEL          = "HOME", "END", "DEL"
K_ENTER, K_BACKSPACE, K_TAB   = "ENTER", "BACKSPACE", "TAB"
K_SAVE, K_QUIT, K_KILL        = "SAVE", "QUIT", "KILL"
K_OPEN, K_LIST                = "OPEN", "LIST"


class _KeyReaderUnix:
    """Czytnik klawiszy dla Unix/Termux przez termios."""

    def __init__(self):
        import termios, tty
        self._termios = termios
        self._tty     = tty
        self._fd      = sys.stdin.fileno()
        self._old     = None

    def __enter__(self):
        self._old = self._termios.tcgetattr(self._fd)
        self._tty.setraw(self._fd)
        return self

    def __exit__(self, *a):
        if self._old:
            self._termios.tcsetattr(self._fd, self._termios.TCSADRAIN, self._old)

    def read_key(self) -> str:
        ch = sys.stdin.read(1)
        o  = ord(ch)
        if o == 13 or o == 10:  return K_ENTER
        if o == 127 or o == 8:  return K_BACKSPACE
        if o == 9:              return K_TAB
        if o == 19:             return K_SAVE   # Ctrl+S
        if o == 17:             return K_QUIT   # Ctrl+Q
        if o == 11:             return K_KILL   # Ctrl+K
        if o == 15:             return K_OPEN   # Ctrl+O
        if o == 12:             return K_LIST   # Ctrl+L
        if o == 27:             # sekwencja escape
            seq = sys.stdin.read(1)
            if seq == '[':
                code = sys.stdin.read(1)
                return {
                    'A': K_UP, 'B': K_DOWN, 'C': K_RIGHT, 'D': K_LEFT,
                    'H': K_HOME, 'F': K_END,
                }.get(code, self._extended(code))
            return "ESC"
        if o < 32:              return None      # inne ctrl — ignoruj
        return ch

    def _extended(self, code: str) -> Optional[str]:
        # np. ESC[3~ = Delete, ESC[1~ = Home
        if code.isdigit():
            tail = sys.stdin.read(1)  # zwykle '~'
            return {'3': K_DEL, '1': K_HOME, '4': K_END}.get(code)
        return None


class _KeyReaderWindows:
    """Czytnik klawiszy dla Windows przez msvcrt."""

    def __init__(self):
        import msvcrt
        self._m = msvcrt

    def __enter__(self): return self
    def __exit__(self, *a): pass

    def read_key(self) -> str:
        ch = self._m.getwch()
        o  = ord(ch)
        if o == 13:  return K_ENTER
        if o == 8:   return K_BACKSPACE
        if o == 9:   return K_TAB
        if o == 19:  return K_SAVE
        if o == 17:  return K_QUIT
        if o == 11:  return K_KILL
        if o == 15:  return K_OPEN
        if o == 12:  return K_LIST
        if ch in ('\x00', '\xe0'):   # klawisz specjalny — drugi bajt
            ch2 = self._m.getwch()
            return {
                'H': K_UP, 'P': K_DOWN, 'K': K_LEFT, 'M': K_RIGHT,
                'G': K_HOME, 'O': K_END, 'S': K_DEL,
            }.get(ch2)
        if o < 32:   return None
        return ch


def make_key_reader():
    """Zwraca odpowiedni czytnik klawiszy dla platformy lub None."""
    if os.name == "nt":
        try:
            return _KeyReaderWindows()
        except Exception:
            return None
    else:
        try:
            import termios  # noqa
            if sys.stdin.isatty():
                return _KeyReaderUnix()
        except Exception:
            pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# BubbleEditor — pełnoekranowy edytor ANSI
# ═══════════════════════════════════════════════════════════════════════════════

class BubbleEditor:
    """
    Edytor dokumentu bąblowego. Cienka powłoka wokół EditBuffer + Workspace.
    Render przez ANSI escape. Wejście przez przenośny czytnik klawiszy.
    """

    def __init__(self, workspace: Workspace, name: str):
        self.ws   = workspace
        self.name = name
        item = workspace.open(name)
        if item is not None and item.is_text:
            self.buf = EditBuffer(item.text or "")
        else:
            self.buf = EditBuffer("")   # nowy dokument
        self.status_msg = ""
        self._running   = False
        self._top       = 0   # pierwsza widoczna linia (scroll)

    # ── Render ────────────────────────────────────────────────────────────────

    def _term_size(self) -> Tuple[int, int]:
        try:
            sz = os.get_terminal_size()
            return sz.columns, sz.lines
        except OSError:
            return 80, 24

    def _render(self) -> None:
        cols, rows = self._term_size()
        text_rows = rows - 2   # nagłówek + status

        # scroll vertical
        if self.buf.row < self._top:
            self._top = self.buf.row
        elif self.buf.row >= self._top + text_rows:
            self._top = self.buf.row - text_rows + 1

        out = []
        out.append("\033[2J\033[H")   # czyść + kursor na górę

        # nagłówek
        flag = "*" if self.buf.modified else " "
        head = f" KarmazynOS · {self.name}{flag}"
        out.append(f"\033[7m{head:<{cols}}\033[0m\r\n")

        # linie tekstu
        for i in range(text_rows):
            li = self._top + i
            if li < len(self.buf.lines):
                line = self.buf.lines[li]
                if len(line) > cols:
                    line = line[:cols - 1] + "›"
                out.append(line + "\r\n")
            else:
                out.append("\033[90m~\033[0m\r\n")

        # status bar
        st = self.buf.stats()
        info = (f" {st['row']}:{st['col']}  "
                f"{st['lines']} lin  {st['chars']} zn  "
                f"^S zapisz  ^Q wyjdź  ^O otwórz  ^L lista")
        if self.status_msg:
            info = f" {self.status_msg}"
            self.status_msg = ""
        out.append(f"\033[7m{info[:cols]:<{cols}}\033[0m")

        # ustaw kursor na rzeczywistą pozycję
        cur_row = self.buf.row - self._top + 2   # +1 nagłówek, +1 do 1-index
        cur_col = self.buf.col + 1
        out.append(f"\033[{cur_row};{cur_col}H")

        sys.stdout.write("".join(out))
        sys.stdout.flush()

    # ── Zapis ─────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        self.ws.save(self.name, self.buf.get_text())
        self.buf.modified = False
        self.status_msg = f"Zapisano '{self.name}'"

    # ── Pętla ─────────────────────────────────────────────────────────────────

    def run(self) -> str:
        reader = make_key_reader()
        if reader is None:
            # Brak interaktywnego TTY → tryb liniowy
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
        b = self.buf
        if key is None:
            return
        if   key == K_UP:        b.move_up()
        elif key == K_DOWN:      b.move_down()
        elif key == K_LEFT:      b.move_left()
        elif key == K_RIGHT:     b.move_right()
        elif key == K_HOME:      b.home()
        elif key == K_END:       b.end()
        elif key == K_ENTER:     b.newline()
        elif key == K_BACKSPACE: b.backspace()
        elif key == K_DEL:       b.delete()
        elif key == K_TAB:       b.insert("    ")
        elif key == K_KILL:      b.kill_line()
        elif key == K_SAVE:      self._save()
        elif key == K_OPEN:      self._prompt_open(reader)
        elif key == K_LIST:      self._show_list(reader)
        elif key == K_QUIT:
            if b.modified:
                self.status_msg = "Niezapisane zmiany! ^S zapisz, ^Q ponownie wyjdź"
                # druga próba wyjścia wychodzi mimo zmian
                self._render()
                k2 = reader.read_key()
                if k2 == K_QUIT:
                    self._running = False
                elif k2 == K_SAVE:
                    self._save()
                    self._running = False
            else:
                self._running = False
        elif isinstance(key, str) and len(key) == 1 and key >= " ":
            b.insert(key)

    def _prompt_open(self, reader) -> None:
        """Otwórz inny dokument (zapisuje bieżący jeśli zmieniony)."""
        if self.buf.modified:
            self._save()
        name = self._read_line(reader, "Otwórz dokument: ")
        if name:
            item = self.ws.open(name) or self.ws.save(name, "")
            self.name = name
            self.buf = EditBuffer(item.text if (item and item.is_text) else "")
            self._top = 0
            self.status_msg = f"Otwarto '{name}'"

    def _show_list(self, reader) -> None:
        docs = self.ws.list()
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.write("Dokumenty:\r\n\r\n")
        for d in docs:
            sys.stdout.write(f"  {d['name']:20} [{d['kind']}] {d['size']}B\r\n")
        sys.stdout.write("\r\nKlawisz aby wrócić...")
        sys.stdout.flush()
        reader.read_key()

    def _read_line(self, reader, prompt: str) -> str:
        """Prosty input jednoliniowy w trybie raw (do nazw dokumentów)."""
        sys.stdout.write(f"\033[{self._term_size()[1]};1H\033[7m\033[K{prompt}\033[0m")
        sys.stdout.flush()
        chars = []
        while True:
            k = reader.read_key()
            if k == K_ENTER:
                break
            elif k == K_BACKSPACE:
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
            elif isinstance(k, str) and len(k) == 1 and k >= " ":
                chars.append(k)
                sys.stdout.write(k)
            sys.stdout.flush()
        return "".join(chars).strip()

    # ── Fallback liniowy (gdy brak TTY) ──────────────────────────────────────

    def _run_line_mode(self) -> str:
        """
        Tryb liniowy gdy brak interaktywnego TTY (potoki, niektóre środowiska).
        Polecenia jak w 'ed': p=pokaż, a=dopisz, w=zapisz, q=wyjdź.
        """
        print(f"[KarmazynOS edytor liniowy] dokument: {self.name}")
        print("Polecenia: p(okaż) a(dopisz linie, '.' kończy) "
              "d N(usuń linię) w(zapisz) q(wyjdź)")
        while True:
            try:
                cmd = input("· ").strip()
            except EOFError:
                break
            if not cmd:
                continue
            c = cmd[0].lower()
            if c == "q":
                if self.buf.modified:
                    print("Niezapisane zmiany. 'w' zapisz albo 'q' ponownie.")
                    if input("· ").strip().lower() == "q":
                        break
                else:
                    break
            elif c == "w":
                self._save()
                print(f"Zapisano '{self.name}'.")
            elif c == "p":
                for i, ln in enumerate(self.buf.lines, 1):
                    print(f"{i:4} {ln}")
            elif c == "a":
                print("(wpisuj linie, '.' w nowej linii kończy)")
                while True:
                    try:
                        ln = input()
                    except EOFError:
                        break
                    if ln == ".":
                        break
                    # Nowy dokument zaczyna od [""] — pierwszy dopisek
                    # zastępuje pustą linię zamiast zostawiać wiodący pusty wiersz.
                    if self.buf.lines == [""]:
                        self.buf.lines[0] = ln
                    else:
                        self.buf.lines.append(ln)
                    self.buf.modified = True
            elif c == "d":
                parts = cmd.split()
                if len(parts) == 2 and parts[1].isdigit():
                    idx = int(parts[1]) - 1
                    if 0 <= idx < len(self.buf.lines):
                        del self.buf.lines[idx]
                        self.buf.modified = True
                        if not self.buf.lines:
                            self.buf.lines = [""]
            else:
                print("Nieznane polecenie.")
        return "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# Punkt wejścia / komenda powłoki
# ═══════════════════════════════════════════════════════════════════════════════

_WS: Optional[Workspace] = None


def cmd_edit(args: List[str], phi=None) -> str:
    """
    Komenda powłoki: EDIT <nazwa>
    Współdzieli phi-space z resztą systemu jeśli podane.
    """
    global _WS
    if _WS is None or (phi is not None and _WS.phi is not phi):
        _WS = Workspace(phi=phi)

    if not args:
        docs = _WS.list()
        if not docs:
            return "Brak dokumentów. Użyj: EDIT <nazwa>"
        return "Dokumenty:\n" + "\n".join(
            f"  {d['name']:20} [{d['kind']}] {d['size']}B" for d in docs)

    name = args[0]
    editor = BubbleEditor(_WS, name)
    return editor.run()


if __name__ == "__main__":
    # Tryb samodzielny — własny Workspace (do testów / użycia bez powłoki)
    ws = Workspace()
    if len(sys.argv) > 1:
        ed = BubbleEditor(ws, sys.argv[1])
        ed.run()
    else:
        print("Użycie: python3 karmazyn_edit.py <nazwa_dokumentu>")