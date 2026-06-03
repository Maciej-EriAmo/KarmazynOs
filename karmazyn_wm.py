#!/usr/bin/env python3
"""
karmazyn_wm.py — Menedżer okien KarmazynOS v1.2.0
====================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Openbox‑style stacking window manager.
Okna swobodnie nachodzące na siebie, przeciąganie,
zmiana rozmiaru (krawędzie/rogi), focus, z‑order, modale.

v1.2.0 – poprawki krytyczne:
- None‑guard dla resize_edge
- clamp pozycji przy resize (N/W)
- normalizacja z-order co klatkę
"""

from typing import Any, Callable, List, Optional, Tuple

TITLE_H       = 24
BORDER        = 2
CLOSE_W       = 20
MIN_W         = 120
MIN_H         = 80
CASCADE       = 28
RESIZE_MARGIN = 6          # szerokość niewidzialnej ramki do chwytania resize


# ═══════════════════════════════════════════════════════════════════════════════
# Okno
# ═══════════════════════════════════════════════════════════════════════════════

class Window:
    _seq = 0

    def __init__(self, title: str, draw_fn: Callable,
                 x: int, y: int, w: int, h: int,
                 key_handler: Optional[Any] = None,
                 closable: bool = True):
        Window._seq += 1
        self.id          = Window._seq
        self.title       = title
        self.draw_fn     = draw_fn
        self.x, self.y   = x, y
        self.w, self.h   = max(MIN_W, w), max(MIN_H, h)
        self.key_handler = key_handler
        self.closable    = closable
        self.z           = self.id
        self.on_body_click: Optional[Callable] = None
        self.modal       = False

    # ── geometria (współrzędne lokalne pulpitu) ────────────────────────────
    def title_rect(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.w, TITLE_H)

    def close_rect(self) -> Tuple[int, int, int, int]:
        return (self.x + self.w - CLOSE_W - 4, self.y + 3, CLOSE_W, TITLE_H - 6)

    def body_rect(self) -> Tuple[int, int, int, int]:
        return (self.x + BORDER, self.y + TITLE_H,
                self.w - 2 * BORDER, self.h - TITLE_H - BORDER)

    def contains(self, lx: int, ly: int) -> bool:
        return (self.x <= lx < self.x + self.w
                and self.y <= ly < self.y + self.h)

    def resize_edge(self, lx: int, ly: int) -> Optional[str]:
        """
        Zwraca kierunek krawędzi/narożnika, jeżeli punkt (lx,ly) leży
        w marginesie zmiany rozmiaru. W przeciwnym razie None.
        """
        m = RESIZE_MARGIN
        x, y, w, h = self.x, self.y, self.w, self.h

        left   = (x <= lx <= x + m)
        right  = (x + w - m <= lx <= x + w)
        top    = (y <= ly <= y + m)
        bottom = (y + h - m <= ly <= y + h)

        if top and left:    return 'nw'
        if top and right:   return 'ne'
        if bottom and left:  return 'sw'
        if bottom and right: return 'se'
        if top:              return 'n'
        if bottom:           return 's'
        if left:             return 'w'
        if right:            return 'e'
        return None

    @staticmethod
    def _in(rect, lx, ly) -> bool:
        rx, ry, rw, rh = rect
        return rx <= lx < rx + rw and ry <= ly < ry + rh


# ═══════════════════════════════════════════════════════════════════════════════
# TerminalKeyHandler – wrapper dla TerminalState
# ═══════════════════════════════════════════════════════════════════════════════

class TerminalKeyHandler:
    def __init__(self, term_state):
        self.term_state = term_state

    def on_key(self, event) -> None:
        self.term_state.push_key(event)


# ═══════════════════════════════════════════════════════════════════════════════
# WindowManager
# ═══════════════════════════════════════════════════════════════════════════════

class WindowManager:
    """Stacking window manager à la Openbox."""

    def __init__(self):
        self.windows: List[Window] = []
        self.focused: Optional[Window] = None
        self._drag:   Optional[Window] = None
        self._drag_dx = 0
        self._drag_dy = 0
        self._cascade_n = 0
        self._panel = None          # ostatni znany panel_rect (pygame.Rect)
        self._t = 0.0               # czas do kursora terminala

        # ── resize ────────────────────────────────────────────────────────
        self._resize: Optional[Window] = None
        self._resize_edge: Optional[str] = None
        self._resize_start_x = 0
        self._resize_start_y = 0
        self._resize_start_w = 0
        self._resize_start_h = 0
        self._resize_start_win_x = 0
        self._resize_start_win_y = 0

        import threading
        self._lock = threading.RLock()
        # Fabryka nowych terminali (sesja + okno). Ustawiana przez
        # start_desktop. None → stary tryb (jeden term_state na display).
        self._spawn_terminal = None

    # ── Cykl życia okien ──────────────────────────────────────────────────

    def open(self, title: str, draw_fn: Callable,
             w: int = 360, h: int = 300,
             key_handler: Optional[Any] = None,
             closable: bool = True) -> Window:
        with self._lock:
            x = 16 + (self._cascade_n % 5) * CASCADE
            y = 16 + (self._cascade_n % 5) * CASCADE
            self._cascade_n += 1
            win = Window(title, draw_fn, x, y, w, h, key_handler, closable)
            self.windows.append(win)
            self.focus(win)
            return win

    def open_terminal(self, term_state) -> Window:
        """Otwórz okno terminala (jak Sakura/URxvt w Openboksie)."""
        def draw_terminal_win(ctx):
            from karmazyn_display import draw_terminal
            draw_terminal(ctx, term_state, self._t)

        win = self.open("ksh", draw_terminal_win,
                        w=720, h=420,
                        key_handler=TerminalKeyHandler(term_state))
        win.x = 60
        win.y = 60
        return win

    def close(self, win: Window) -> None:
        with self._lock:
            if win in self.windows:
                self.windows.remove(win)
            if self.focused is win:
                self.focused = self.windows[-1] if self.windows else None
            if self._drag is win:
                self._drag = None
            if self._resize is win:
                self._resize = None

    def close_by_title(self, title: str) -> bool:
        with self._lock:
            for w in list(self.windows):
                if w.title == title:
                    self.close(w)
                    return True
        return False

    def focus(self, win: Window) -> None:
        with self._lock:
            if win not in self.windows:
                return
            top_z = max((w.z for w in self.windows), default=0)
            win.z = top_z + 1
            self.focused = win

    def _ordered(self) -> List[Window]:
        """Kopia listy okien od spodu do wierzchu (bezpieczna wątkowo)."""
        with self._lock:
            return sorted(self.windows, key=lambda w: w.z)

    def _topmost_at(self, lx: int, ly: int) -> Optional[Window]:
        """Najwyższe okno pod punktem (w przestrzeni pulpitu)."""
        for win in reversed(self._ordered()):
            if win.contains(lx, ly):
                return win
        return None

    # ── Klawiatura ────────────────────────────────────────────────────────

    def wants_keys(self) -> bool:
        return self.focused is not None and self.focused.key_handler is not None

    def on_key(self, event) -> None:
        if self.focused is not None and self.focused.key_handler is not None:
            try:
                self.focused.key_handler.on_key(event)
            except Exception:
                pass

    # ── Mysz – główna logika zdarzeń ──────────────────────────────────────

    def is_dragging(self) -> bool:
        return self._drag is not None

    def _event_kind(self, event) -> Optional[str]:
        k = getattr(event, "kind", None)
        if k:
            return k
        try:
            import pygame
            return {
                pygame.MOUSEBUTTONDOWN: "down",
                pygame.MOUSEBUTTONUP:   "up",
                pygame.MOUSEMOTION:     "motion",
            }.get(event.type)
        except Exception:
            return None

    def on_mouse(self, event, panel_rect) -> bool:
        """
        panel_rect – pygame.Rect opisujący dostępny obszar pulpitu.
        Współrzędne: event.pos to piksele ekranu, przeliczamy na
        współrzędne pulpitu (lx, ly).
        """
        self._panel = panel_rect
        kind = self._event_kind(event)
        if kind is None:
            return False

        px, py = event.pos
        lx = px - panel_rect.x
        ly = py - panel_rect.y

        # ── motion ────────────────────────────────────────────────────────
        if kind == "motion":
            handled = False

            # przeciąganie całego okna
            if self._drag is not None:
                nx = lx - self._drag_dx
                ny = ly - self._drag_dy
                self._drag.x = max(0, min(nx, panel_rect.w - 40))
                self._drag.y = max(0, min(ny, panel_rect.h - TITLE_H))
                handled = True

            # zmiana rozmiaru
            if self._resize is not None:
                edge = self._resize_edge
                # Zabezpieczenie przed None (krytyczne)
                if edge is None:
                    return True

                dx = lx - self._resize_start_x
                dy = ly - self._resize_start_y
                win = self._resize

                if 'e' in edge:
                    new_w = max(MIN_W, self._resize_start_w + dx)
                    win.w = min(new_w, panel_rect.w - win.x)   # nie wychodź poza prawą krawędź
                if 'w' in edge:
                    new_w = max(MIN_W, self._resize_start_w - dx)
                    # clamp lewej krawędzi
                    new_x = self._resize_start_win_x + self._resize_start_w - new_w
                    win.x = max(0, new_x)
                    win.w = self._resize_start_win_x + self._resize_start_w - win.x
                if 's' in edge:
                    new_h = max(MIN_H, self._resize_start_h + dy)
                    win.h = min(new_h, panel_rect.h - win.y)   # nie wychodź poza dolną krawędź
                if 'n' in edge:
                    new_h = max(MIN_H, self._resize_start_h - dy)
                    # clamp górnej krawędzi
                    new_y = self._resize_start_win_y + self._resize_start_h - new_h
                    win.y = max(0, new_y)
                    win.h = self._resize_start_win_y + self._resize_start_h - win.y

                handled = True

            # zmiana kursora przy najechaniu na krawędź (opcjonalne)
            if self._drag is None and self._resize is None:
                win = self._topmost_at(lx, ly)
                if win:
                    edge = win.resize_edge(lx, ly)
                    if edge:
                        cursor_map = {
                            'n':  65282,  # SYSTEM_CURSOR_SIZENS
                            's':  65282,
                            'w':  65280,  # SYSTEM_CURSOR_SIZEWE
                            'e':  65280,
                            'nw': 65284,  # SYSTEM_CURSOR_SIZENWSE
                            'se': 65284,
                            'ne': 65285,  # SYSTEM_CURSOR_SIZENESW
                            'sw': 65285,
                        }
                        try:
                            import pygame
                            pygame.mouse.set_cursor(cursor_map[edge])
                        except Exception:
                            pass
                    else:
                        try:
                            import pygame
                            pygame.mouse.set_cursor(0)  # ARROW
                        except Exception:
                            pass

            return handled

        # ── up ────────────────────────────────────────────────────────────
        if kind == "up":
            if self._drag is not None:
                self._drag = None
                return True
            if self._resize is not None:
                self._resize = None
                self._resize_edge = None
                return True
            return False

        # ── down ──────────────────────────────────────────────────────────
        button = getattr(event, "button", 1)
        if button != 1:
            return False

        # modal – tylko ono dostaje eventy
        modal = self._topmost_modal()
        if modal is not None:
            win = modal if modal.contains(lx, ly) else None
            if win is None:
                return True          # klik poza modalem – konsumujemy
        else:
            win = self._topmost_at(lx, ly)

        if win is None:
            return False

        # 1. Przycisk zamknięcia
        if win.closable and Window._in(win.close_rect(), lx, ly):
            self.close(win)
            return True

        # 2. Krawędź resize? (priorytet przed paskiem tytułu)
        edge = win.resize_edge(lx, ly)
        if edge is not None:
            self.focus(win)
            self._resize = win
            self._resize_edge = edge
            self._resize_start_x = lx
            self._resize_start_y = ly
            self._resize_start_w = win.w
            self._resize_start_h = win.h
            self._resize_start_win_x = win.x
            self._resize_start_win_y = win.y
            return True

        # 3. Pasek tytułu → przeciąganie
        if Window._in(win.title_rect(), lx, ly):
            self.focus(win)
            self._drag = win
            self._drag_dx = lx - win.x
            self._drag_dy = ly - win.y
            return True

        # 4. Ciało → fokus + ew. body_click
        if win.on_body_click is not None:
            bx0, by0, _, _ = win.body_rect()
            if win.on_body_click(lx - bx0, ly - by0):
                return True
        self.focus(win)
        return True

    def _topmost_modal(self) -> Optional[Window]:
        with self._lock:
            modals = [w for w in self.windows if w.modal]
        if not modals:
            return None
        return max(modals, key=lambda w: w.z)

    # ── Rysowanie ─────────────────────────────────────────────────────────

    def attach(self, display) -> bool:
        """Podłącz jako panel boczny (stary tryb)."""
        r = getattr(display, "renderer", None)
        if r is None:
            return False
        r.claim_left(self._draw_all, "OKNA", handler=self)
        return True

    def attach_fullscreen(self, display) -> bool:
        """Przejmij CAŁY ekran (Openbox‑style)."""
        r = getattr(display, "renderer", None)
        if r is None:
            return False
        r.claim_fullscreen(self)
        return True

    def _draw_all(self, ctx) -> None:
        """Rysuje wszystkie okna na podanym kontekście (obszar pulpitu)."""
        try:
            import pygame
            from karmazyn_display import (DrawCtx, C_BG, C_ACCENT, C_FG,
                                          C_STATUS)
        except Exception:
            return

        # Normalizacja z-order co klatkę – zapobiega overflow
        with self._lock:
            for i, w in enumerate(sorted(self.windows, key=lambda w: w.z)):
                w.z = i

        # Tło pulpitu
        ctx.clear((30, 30, 45), alpha=255)

        if not self.windows:
            ctx.text("Pulpit — otwórz okno (PAINT, VIEW, WIN TERM)",
                     C_STATUS, x=ctx.rect.x + 12, y=ctx.rect.y + 12)
            return

        px0, py0 = ctx.rect.x, ctx.rect.y

        for win in self._ordered():
            focused = (win is self.focused)
            wx = px0 + win.x
            wy = py0 + win.y
            win_screen = pygame.Rect(wx, wy, win.w, win.h)

            # Tło + ramka okna
            ctx.box(win_screen, fill=C_BG,
                    outline=C_ACCENT if focused else (90, 40, 40))

            # Pasek tytułu
            tr = pygame.Rect(wx, wy, win.w, TITLE_H)
            ctx.box(tr, fill=(60, 24, 24) if focused else (34, 20, 24))
            ctx.text(win.title[:40], C_FG if focused else C_STATUS,
                     x=wx + 8, y=wy + 4)

            # Przycisk zamknięcia [×]
            if win.closable:
                crx, cry, crw, crh = win.close_rect()
                cr = pygame.Rect(px0 + crx, py0 + cry, crw, crh)
                ctx.box(cr, fill=(120, 30, 30), outline=C_ACCENT)
                ctx.text("×", (230, 230, 230), x=cr.x + 6, y=cr.y + 1)

            # Ciało okna – rysowane na przyciętym obszarze
            bx, by, bw, bh = win.body_rect()
            body_screen = pygame.Rect(px0 + bx, py0 + by, bw, bh)
            if bw > 0 and bh > 0:
                prev_clip = ctx.surface.get_clip()
                ctx.surface.set_clip(body_screen)
                try:
                    body_ctx = DrawCtx(ctx.surface, ctx.font, body_screen)
                    win.draw_fn(body_ctx)
                except Exception:
                    pass
                finally:
                    ctx.surface.set_clip(prev_clip)

    # ── Modal potwierdzenia ───────────────────────────────────────────────

    def confirm_modal(self, message: str, timeout: float = 120.0) -> bool:
        import threading
        ev = threading.Event()
        result = {"v": False}

        BW, BH = 90, 34
        win_w, win_h = 360, 150

        def draw(ctx):
            try:
                import pygame
                from karmazyn_display import C_FG, C_ACCENT
            except Exception:
                return
            r = ctx.rect
            words, line, y = message.split(), "", r.y + 8
            maxch = max(10, r.w // 9)
            for w in words:
                if len(line) + len(w) + 1 > maxch:
                    ctx.text(line, C_FG, x=r.x + 10, y=y); y += 22; line = w
                else:
                    line = (line + " " + w).strip()
            if line:
                ctx.text(line, C_FG, x=r.x + 10, y=y)
            yes_x = r.x + 10
            no_x  = r.x + r.w - BW - 10
            by    = r.y + r.h - BH - 8
            yes = pygame.Rect(yes_x, by, BW, BH)
            no  = pygame.Rect(no_x,  by, BW, BH)
            ctx.box(yes, fill=(40, 90, 40), outline=C_ACCENT, radius=4)
            ctx.box(no,  fill=(90, 40, 40), outline=C_ACCENT, radius=4)
            ctx.text("Tak", C_FG, x=yes.x + 28, y=yes.y + 8)
            ctx.text("Nie", C_FG, x=no.x + 28,  y=no.y + 8)

        def body_click(bx, by):
            body_h = win_h - TITLE_H - BORDER
            body_w = win_w - 2 * BORDER
            yb = body_h - BH - 8
            if yb <= by <= yb + BH:
                if 10 <= bx <= 10 + BW:
                    result["v"] = True; ev.set(); return True
                if body_w - BW - 10 <= bx <= body_w - 10:
                    result["v"] = False; ev.set(); return True
            return False

        win = self.open("Potwierdzenie", draw, w=win_w, h=win_h, closable=False)
        win.modal = True
        win.on_body_click = body_click
        if self._panel is not None:
            win.x = max(0, (self._panel.w - win_w) // 2)
            win.y = max(0, (self._panel.h - win_h) // 3)

        got = ev.wait(timeout)
        self.close(win)
        return result["v"] if got else False


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton, rejestr aktywnego pulpitu, komendy powłoki
# ═══════════════════════════════════════════════════════════════════════════════

_WM: Optional[WindowManager] = None
_ACTIVE: Optional[WindowManager] = None


def get_wm() -> WindowManager:
    global _WM
    if _WM is None:
        _WM = WindowManager()
    return _WM


def set_active(wm: Optional[WindowManager]) -> None:
    global _ACTIVE
    _ACTIVE = wm


def get_active() -> Optional[WindowManager]:
    return _ACTIVE


def start_desktop(display, spawn_terminal=None) -> Optional[WindowManager]:
    """Uruchom tryb okienkowy Openbox‑style (pełny ekran) i otwórz terminal.

    spawn_terminal — opcjonalna fabryka (callable() -> None) tworząca nową
    SESJĘ + okno terminala (model xterm/tmux). Gdy podana, pierwszy terminal
    i WIN TERM idą przez nią (osobny TTY + worker na sesję). Gdy None — stary
    tryb (jeden wspólny term_state).

    Idempotentne: ponowne wywołanie (np. z komendy WIN) nie zeruje fabryki
    ani nie tworzy drugiego pierwszego terminala."""
    wm = get_wm()
    if display is not None and getattr(display, "available", False):
        wm.attach_fullscreen(display)
        if spawn_terminal is not None:
            wm._spawn_terminal = spawn_terminal     # ustaw TYLKO gdy podano
        has_term = any(getattr(w, "title", "") == "ksh" for w in wm.windows)
        if not has_term:                            # pierwszy terminal raz
            if wm._spawn_terminal is not None:
                wm._spawn_terminal()
            else:
                wm.open_terminal(display.term_state)
    set_active(wm)
    return wm


def modal_confirm(reason: str = "") -> bool:
    wm = get_active()
    if wm is None:
        return True
    msg = f"Wykonać zapis — {reason}?" if reason else "Wykonać zapis?"
    return wm.confirm_modal(msg)


def cmd_windows(args: List[str], display=None) -> str:
    if display is not None:
        wm = start_desktop(display)
    else:
        wm = get_wm()
    if not args:
        if not wm.windows:
            return ("Pulpit okienkowy aktywny. Brak okien — otwórz aplikację "
                    "(PAINT, IMG) aby pojawiła się jako okno.")
        return "Okna:\n" + "\n".join(
            f"  {'*' if w is wm.focused else ' '} {w.title} "
            f"({w.w}×{w.h} @ {w.x},{w.y})" for w in wm._ordered())
    if args[0].upper() == "CLOSE" and len(args) > 1:
        title = " ".join(args[1:])
        return f"Zamknięto '{title}'" if wm.close_by_title(title) else f"Brak okna '{title}'"
    if args[0].upper() == "TERM":
        if wm._spawn_terminal is not None:
            wm._spawn_terminal()                  # nowa sesja + okno (model sesji)
            return "Otwarto nowy terminal (nowa sesja)"
        if display and hasattr(display, 'term_state'):
            wm.open_terminal(display.term_state)
        else:
            wm.open_terminal(None)
        return "Otwarto nowy terminal"
    return "Użycie: WIN | WIN CLOSE <tytuł> | WIN TERM"