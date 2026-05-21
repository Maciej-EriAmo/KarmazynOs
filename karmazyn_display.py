"""
karmazyn_display.py — KarmazynOS Display v1.0
==============================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Immediate Mode renderer na SDL2/pygame.
Filozofia: stan żyje w phi-space i strukturach danych,
UI to deterministyczna funkcja stanu czytana każdą klatkę.

Jeden wątek SDL (main), shell w workerze — bez zmiany logiki shella.
Graceful degradation: cały system działa bez X11/pygame.

Architektura:
  TerminalState    — bufor I/O terminala (thread-safe)
  LogoState        — stan żółwia + przyrostowy canvas (O(1) blit)
  DrawCtx          — narzędzia rysowania, bez własnego stanu
  draw_terminal()  — czysta funkcja (ctx, state, t) → None
  draw_logo()      — czysta funkcja (ctx, state) → None
  draw_phi_map()   — czysta funkcja (ctx, List[Atom]) → None
  ImmediateRenderer— render loop, 60fps, SDL w main thread
  KarmazynDisplay  — fasada: init/bind/run/available

Integracja:
  display = KarmazynDisplay()
  display.init()
  display.bind_phi(phi_space)   # live phi-map
  display.run(shell_worker)     # shell w worker thread

Wydajność (zmierzona na SDL dummy):
  full redraw 3 widoki: ~0.93 ms/frame
  60fps budget: 16.7 ms → 94% wolne na logikę systemu
"""

import math
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# ─── Graceful degradation bez pygame ─────────────────────────────────────────

try:
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame
    PYGAME_OK = True
except ImportError:
    PYGAME_OK = False

# ─── Stałe layoutu ───────────────────────────────────────────────────────────

W, H       = 1280, 800
FPS        = 60
FONT_SIZE  = 16

# Kolory — jeden zestaw dla całego systemu
C_BG     = (12,  12,  20)
C_FG     = (200, 200, 200)
C_ACCENT = (180, 60,  60)   # karmazynowy — akcenty, prompt, obramowania
C_HOT    = (255, 80,  40)   # czerwony — T >= 70
C_WARM   = (60,  160, 255)  # niebieski — T 30-70
C_COLD   = (40,  80,  140)  # ciemny — T < 30
C_TURTLE = (100, 220, 100)  # zielony — żółw
C_TRAIL  = (50,  120, 50)   # ciemniejszy zielony — ślad
C_GRID   = (20,  20,  35)   # siatka phi-map


# ─── TerminalState ────────────────────────────────────────────────────────────

class TerminalState:
    """
    Stan terminala — żyje poza warstwą UI.
    Shell worker modyfikuje przez append() i get_input_blocking().
    Render czyta przez snapshot() bez blokowania.

    Jeden lock. Jeden queue. Zero kopii stanu w widgetach.
    """

    MAX_LINES = 500

    def __init__(self):
        self.prompt:     str              = "ksh> "
        self.input_buf:  str              = ""
        self._lines:     List[Tuple[str, Tuple[int,int,int]]] = []
        self._lock:      threading.Lock   = threading.Lock()
        self._key_queue: queue.Queue      = queue.Queue()
        self._shutdown:  bool             = False   # sygnał zamknięcia

    def shutdown(self) -> None:
        """Sygnalizuje workerowi żeby zakończył get_input_blocking()."""
        self._shutdown = True
        self._key_queue.put("")   # odblokuj jeśli czeka

    # ── API dla shell workera (worker thread) ─────────────────────────────────

    def append(self, text: str,
               color: Tuple[int,int,int] = C_FG) -> None:
        """Dopisz linie. Bezpieczne z każdego wątku."""
        with self._lock:
            for line in str(text).split("\n"):
                self._lines.append((line, color))
            if len(self._lines) > self.MAX_LINES:
                self._lines = self._lines[-self.MAX_LINES:]

    def get_input_blocking(self) -> str:
        """
        Blokuje worker thread aż do Enter lub sygnału shutdown.
        Timeout 100ms — worker nie blokuje się na wieczność
        gdy SDL zamknie okno. Zwraca '' przy shutdown.
        """
        self.append(self.prompt, C_ACCENT)
        while not self._shutdown:
            try:
                return self._key_queue.get(timeout=0.1)
            except queue.Empty:
                continue
        return ""   # sentinel — poinformuj shell o zamknięciu

    # ── API dla SDL event loop (main thread) ──────────────────────────────────

    def push_key(self, event: "pygame.event.Event") -> None:
        """Przetwarza KEYDOWN. Wywołuj tylko z main thread."""
        if not PYGAME_OK:
            return
        if event.key == pygame.K_RETURN:
            line            = self.input_buf
            self.input_buf  = ""
            self._key_queue.put(line)
        elif event.key == pygame.K_BACKSPACE:
            self.input_buf = self.input_buf[:-1]
        elif event.key == pygame.K_UP:
            pass   # TODO: historia — Faza 3
        elif event.unicode and event.unicode.isprintable():
            self.input_buf += event.unicode

    # ── API dla renderera (main thread, read-only) ────────────────────────────

    def snapshot(self) -> Tuple[List[Tuple[str, Tuple]], str]:
        """Zwraca kopię linii i input_buf. Nie modyfikuje stanu."""
        with self._lock:
            return list(self._lines), self.input_buf


# ─── LogoState ────────────────────────────────────────────────────────────────

class LogoState:
    """
    Stan żółwia LOGO + przyrostowy canvas.

    THREADING MODEL (fix Windows freeze):
      Worker thread: add_segment() → tylko enqueue do _seg_queue
      Main thread:   flush_segments() → draw na pygame.Surface

    pygame.Surface NIE jest thread-safe.
    Rysowanie z worker thread = undefined behavior na Windows/DirectX.
    Queue jest thread-safe bez dodatkowego locka.
    """

    SCALE = 3

    def __init__(self):
        self.x:           float              = 0.0
        self.y:           float              = 0.0
        self.heading:     float              = 0.0
        self.pendown:     bool               = True
        self._canvas:     Optional["pygame.Surface"] = None
        self._w:          int                = 0
        self._h:          int                = 0
        self._seg_queue:  queue.Queue        = queue.Queue()
        self._state_lock: threading.Lock     = threading.Lock()

    def init_canvas(self, w: int, h: int) -> None:
        """Wywołaj z main thread po pygame.init()."""
        if not PYGAME_OK:
            return
        self._w      = w
        self._h      = h
        self._canvas = pygame.Surface((w, h))
        self._canvas.fill(C_BG)

    def world_to_px(self, lx: float, ly: float) -> Tuple[int, int]:
        return (int(self._w // 2 + lx * self.SCALE),
                int(self._h // 2 - ly * self.SCALE))

    # ── Worker thread — nie dotyka Surface ───────────────────────────────────

    def add_segment(self, x0: float, y0: float,
                    x1: float, y1: float) -> None:
        """Worker: tylko enqueue. Nigdy nie rysuje bezpośrednio."""
        self._seg_queue.put((x0, y0, x1, y1))

    def set_turtle(self, x: float, y: float,
                   heading: float, pendown: bool) -> None:
        with self._state_lock:
            self.x       = x
            self.y       = y
            self.heading = heading % 360.0
            self.pendown = pendown

    def clear(self) -> None:
        """Worker: enqueue sygnał czyszczenia."""
        self._seg_queue.put(("CLEAR",))

    # ── Main thread — rysuje na Surface ──────────────────────────────────────

    def flush_segments(self) -> int:
        """
        Main thread: opróżnij kolejkę i narysuj na canvas.
        Wywołuj z render_frame() przed draw_logo().
        Zwraca liczbę przetworzonych elementów.
        """
        if self._canvas is None:
            return 0
        count = 0
        try:
            while True:
                item = self._seg_queue.get_nowait()
                if item[0] == "CLEAR":
                    self._canvas.fill(C_BG)
                else:
                    x0, y0, x1, y1 = item
                    pygame.draw.line(
                        self._canvas, C_TRAIL,
                        self.world_to_px(x0, y0),
                        self.world_to_px(x1, y1), 1)
                count += 1
        except queue.Empty:
            pass
        return count

    def snapshot(self) -> Tuple[float, float, float, bool,
                                Optional["pygame.Surface"]]:
        with self._state_lock:
            return (self.x, self.y, self.heading,
                    self.pendown, self._canvas)
# ─── DrawCtx ─────────────────────────────────────────────────────────────────

class DrawCtx:
    """
    Narzędzia rysowania — kursor pozycji, font, surface.
    Przekazywany do funkcji draw_*. Nie przechowuje stanu UI.
    """

    def __init__(self, surface: "pygame.Surface",
                 font:    "pygame.font.Font",
                 rect:    "pygame.Rect"):
        self.surface = surface
        self.font    = font
        self.rect    = rect
        self._line_h = font.get_height() + 2

    def text(self, txt: str,
             color: Tuple[int,int,int] = C_FG,
             x: Optional[int] = None,
             y: Optional[int] = None) -> "pygame.Rect":
        sx = x if x is not None else self.rect.x
        sy = y if y is not None else self.rect.y
        s  = self.font.render(str(txt), True, color)
        self.surface.blit(s, (sx, sy))
        return s.get_rect(topleft=(sx, sy))

    def line(self, p0: Tuple, p1: Tuple,
             color: Tuple = C_FG, w: int = 1) -> None:
        pygame.draw.line(self.surface, color, p0, p1, w)

    def box(self, r: "pygame.Rect",
            fill: Optional[Tuple] = None,
            outline: Optional[Tuple] = None,
            radius: int = 0) -> None:
        if fill:
            pygame.draw.rect(self.surface, fill,    r, 0, radius)
        if outline:
            pygame.draw.rect(self.surface, outline, r, 1, radius)

    def polygon(self, pts: List[Tuple], color: Tuple) -> None:
        pygame.draw.polygon(self.surface, color, pts)

    def clear(self, color: Tuple = C_BG) -> None:
        self.surface.fill(color, self.rect)


# ─── Czyste funkcje rysowania ─────────────────────────────────────────────────

def _T_to_color(T: float) -> Tuple[int,int,int]:
    """Temperatura atomu → kolor. Spójne z karmazyn_atom.state_for_T."""
    t = max(0.0, min(1.0, T / 100.0))
    if t >= 0.7:
        r = int(255 * t)
        g = int(80  * (1 - t))
        return (r, g, 40)
    if t >= 0.3:
        return (60, int(160 * t), 255)
    return (40, 80, int(140 * t + 40))


def draw_terminal(ctx: DrawCtx,
                  state: TerminalState,
                  t: float) -> None:
    """
    Terminal — czysta funkcja (ctx, state, t) → None.
    t = czas od startu dla kursora migającego.
    """
    r = ctx.rect
    ctx.clear()
    ctx.box(r, outline=C_ACCENT)

    line_h  = ctx._line_h
    visible = max(1, (r.h - 8) // line_h - 1)
    lines, input_buf = state.snapshot()

    y = r.y + 4
    for text, color in lines[-visible:]:
        ctx.text(text, color, x=r.x + 6, y=y)
        y += line_h

    # Input z migającym kursorem
    cursor  = "|" if int(t * 2) % 2 == 0 else " "
    inp_txt = state.prompt + input_buf + cursor
    ctx.text(inp_txt, C_ACCENT, x=r.x + 6, y=y)


def draw_logo(ctx: DrawCtx, state: LogoState) -> None:
    """
    Logo canvas — czysta funkcja (ctx, state) → None.
    O(1): jeden blit kanwy + trójkąt żółwia.
    """
    r = ctx.rect
    x, y, heading, pendown, canvas = state.snapshot()

    # Blit przyrostowego canvasu (O(1) niezależnie od liczby segmentów)
    if canvas is not None:
        ctx.surface.blit(canvas, r.topleft)
    else:
        ctx.clear()

    ctx.box(r, outline=C_ACCENT)

    # Żółw — trójkąt kierunkowy
    sx, sy = state.world_to_px(x, y)
    # Uwzględnij offset panelu
    sx += r.x - state._w // 2 + r.w // 2
    sy += r.y - state._h // 2 + r.h // 2

    h_r   = math.radians(heading)
    size  = 9
    pts   = [
        (sx + int(size * math.cos(h_r)),
         sy - int(size * math.sin(h_r))),
        (sx + int(size * 0.45 * math.cos(h_r + 2.4)),
         sy - int(size * 0.45 * math.sin(h_r + 2.4))),
        (sx + int(size * 0.45 * math.cos(h_r - 2.4)),
         sy - int(size * 0.45 * math.sin(h_r - 2.4))),
    ]
    ctx.polygon(pts, C_TURTLE)

    # Pendown indicator — małe kółko przy żółwiu
    if not pendown:
        pygame.draw.circle(ctx.surface, C_ACCENT, (sx, sy), 4, 1)


def draw_phi_map(ctx: DrawCtx,
                 atoms: List[Any],
                 highlight_id: Optional[str] = None) -> None:
    """
    Phi-space heatmapa — czysta funkcja (ctx, List[Atom]) → None.
    Przyjmuje karmazyn_atom.Atom lub duck-typing dict z id/T/state.
    Temperatura → kolor (HOT=czerwony, COLD=niebieski).
    Atomy TOMB — niewidoczne (spójne z GC).
    """
    r = ctx.rect
    ctx.surface.fill(C_GRID, r)
    ctx.box(r, outline=(40, 20, 20))

    # Nagłówek
    ctx.text(f"φ-space  {len(atoms)} atomów",
             C_ACCENT, x=r.x + 6, y=r.y + 4)

    if not atoms:
        ctx.text("brak atomów", C_COLD, x=r.x + 8, y=r.y + 28)
        return

    # Pobierz T i id z Atom lub dict
    def _get(a, key, default):
        if isinstance(a, dict):
            return a.get(key, default)
        return getattr(a, key, default)

    # Sortuj wg T malejąco, pomiń TOMB
    visible = [a for a in atoms
               if _get(a, "state", "WARM") != "TOMB"
               and _get(a, "T", 50) >= 2.0]
    visible.sort(key=lambda a: -_get(a, "T", 50))
    visible = visible[:120]   # max 120 atomów w widoku

    cols    = max(1, (r.w - 12) // 115)
    cell_w  = (r.w - 12) // cols
    cell_h  = 30
    top     = r.y + 22

    for idx, atom in enumerate(visible):
        col_i = idx % cols
        row_i = idx // cols
        ax    = r.x + 6 + col_i * cell_w
        ay    = top + row_i * (cell_h + 3)

        if ay + cell_h > r.bottom - 4:
            break   # nie wyjdź poza panel

        T      = float(_get(atom, "T", 50))
        atom_id = str(_get(atom, "id", "?"))
        color  = _T_to_color(T)
        is_hot = T >= 70.0
        cell   = pygame.Rect(ax, ay, cell_w - 4, cell_h)

        # Tło komórki — HOT dostaje glow (jaśniejsze obramowanie)
        ctx.box(cell, fill=color,
                outline=(min(255, color[0]+60),
                         min(255, color[1]+40),
                         min(255, color[2]+40)) if is_hot else C_BG,
                radius=3)

        # Podświetlenie klikniętego atomu
        if highlight_id and atom_id == highlight_id:
            ctx.box(cell, outline=(255, 255, 100), radius=3)

        # Etykieta — skrócone id + T
        label = f"{atom_id[:11]}  {T:4.0f}°"
        # Kontrast tekstu: jasny na ciemnym tle
        text_c = (230, 230, 230) if T < 50 else (20, 20, 20)
        ctx.text(label, text_c, x=ax + 4, y=ay + 7)


def draw_hud(surface: "pygame.Surface",
             font:       "pygame.font.Font",
             stats:      Dict[str, Any],
             t:          float,
             close_rect: Optional[List] = None) -> None:
    """
    HUD — pasek statusu + przycisk [×] zamknięcia.
    close_rect: mutable list[Rect] — renderer przechowuje pozycję przycisku.
    """
    _cr_ref = close_rect

    r = pygame.Rect(0, 0, W, 22)
    surface.fill((8, 8, 16), r)

    uptime = f"{t:.0f}s"
    hot    = stats.get("HOT",  0)
    warm   = stats.get("WARM", 0)
    cold   = stats.get("COLD", 0)
    tick   = stats.get("tick", 0)

    parts = [
        (f" KarmazynOS  ", C_ACCENT),
        (f"HOT:{hot} ",    C_HOT),
        (f"WARM:{warm} ",  C_WARM),
        (f"COLD:{cold} ",  C_COLD),
        (f"tick:{tick}  ", C_FG),
        (f"up:{uptime}",   (100, 100, 100)),
        (f"  ESC/Ctrl+Q = zamknij", (70, 70, 70)),
    ]
    x = 4
    for text, color in parts:
        s = font.render(text, True, color)
        surface.blit(s, (x, 3))
        x += s.get_width()

    # Przycisk [×] — prawy górny róg
    btn_w = 28
    _new_cr = pygame.Rect(W - btn_w - 2, 1, btn_w, 20)
    if _cr_ref is not None:
        if _cr_ref: _cr_ref[0] = _new_cr
        else: _cr_ref.append(_new_cr)
    pygame.draw.rect(surface, (120, 30, 30), _new_cr, 0, 3)
    pygame.draw.rect(surface, C_ACCENT,      _new_cr, 1, 3)
    lbl = font.render("×", True, (220, 220, 220))
    surface.blit(lbl, (_new_cr.x + (_new_cr.w - lbl.get_width()) // 2,
                        _new_cr.y + 2))

    # Linia oddzielająca HUD od paneli
    pygame.draw.line(surface, C_ACCENT, (0, 21), (W, 21), 1)


def draw_dividers(surface: "pygame.Surface") -> None:
    """Pionowe i poziome linie podziału layoutu."""
    pygame.draw.line(surface, C_ACCENT,
                     (W//2, 22), (W//2, H), 1)
    pygame.draw.line(surface, (40, 20, 20),
                     (W//2, H//2), (W, H//2), 1)


# ─── ImmediateRenderer ────────────────────────────────────────────────────────

class ImmediateRenderer:
    """
    Render loop — SDL w main thread, 60fps.
    Każda klatka: clear → draw_all(state) → flip.
    Jeden wątek roboczy dla shella.

    Stan który czyta:
      term_state  — terminal I/O
      logo_state  — żółw + canvas
      phi_ref     — opcjonalna referencja do PhiSpace (live)
      _phi_atoms  — lista dict gdy phi_ref=None (demo)
      _highlight  — id atomu do podświetlenia (kliknięcie)
    """

    HUD_H = 22   # piksele HUD na górze

    def __init__(self,
                 screen:     "pygame.Surface",
                 font:       "pygame.font.Font",
                 term_state: TerminalState,
                 logo_state: LogoState):
        self.screen     = screen
        self.font       = font
        self.term_state = term_state
        self.logo_state = logo_state
        self.phi_ref    = None   # PhiSpace — podpinany przez bind_phi()
        self._phi_atoms: List[Dict] = []
        self._highlight: Optional[str] = None
        self._clock      = pygame.time.Clock()
        self._t0         = time.monotonic()
        self._tick_n     = 0
        self._close_rect: List = []   # [pygame.Rect] — pozycja przycisku ×
        self._tick_fn:   Optional[Callable] = None  # fizyka: phi.tick()
        self._last_phys  = 0.0        # ostatni czas wywołania tick_fn

    def _make_ctx(self, rect: "pygame.Rect") -> DrawCtx:
        return DrawCtx(self.screen, self.font, rect)

    def _get_atoms(self) -> List[Any]:
        """Pobiera atomy — z live PhiSpace lub z listy demo."""
        if self.phi_ref is not None:
            return self.phi_ref.matrix.atoms()
        return self._phi_atoms

    def _phi_stats(self) -> Dict[str, int]:
        if self.phi_ref is not None:
            return self.phi_ref.matrix.stats()
        return {"HOT": 0, "WARM": 0, "COLD": 0, "TOMB": 0}

    def render_frame(self, t: float) -> None:
        """Pełny redraw — deterministyczna funkcja t i stanu."""
        # Fizyka: tick co sekundę (niezależnie od frame rate)
        if self._tick_fn and t - self._last_phys >= 1.0:
            self._last_phys = t
            try:
                self._tick_fn()
            except Exception:
                pass

        s = self.screen
        s.fill(C_BG)

        hud_offset = self.HUD_H

        # Flush segmentów LOGO z worker queue → canvas (main thread only)
        self.logo_state.flush_segments()

        # Lewy panel — LOGO canvas (cała wysokość)
        draw_logo(
            self._make_ctx(pygame.Rect(
                0, hud_offset, W//2, H - hud_offset)),
            self.logo_state,
        )

        # Prawy górny — phi-map
        draw_phi_map(
            self._make_ctx(pygame.Rect(
                W//2, hud_offset, W//2, (H - hud_offset)//2)),
            self._get_atoms(),
            self._highlight,
        )

        # Prawy dolny — terminal
        draw_terminal(
            self._make_ctx(pygame.Rect(
                W//2, hud_offset + (H - hud_offset)//2,
                W//2, (H - hud_offset)//2)),
            self.term_state,
            t,
        )

        # HUD + dividers
        draw_hud(s, self.font, self._phi_stats(), t, self._close_rect)
        draw_dividers(s)
        pygame.display.flip()

    def _handle_event(self, event: "pygame.event.Event") -> bool:
        """Zwraca False jeśli quit."""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            # Escape lub Ctrl+Q → quit
            if event.key == pygame.K_ESCAPE:
                return False
            ctrl = event.mod & pygame.KMOD_CTRL
            if ctrl and event.key == pygame.K_q:
                return False
            self.term_state.push_key(event)
        if event.type == pygame.MOUSEBUTTONDOWN:
            # Kliknięcie przycisku × w HUD → quit
            if self._close_rect and self._close_rect[0].collidepoint(event.pos):
                return False
            self._handle_click(event.pos)
        return True

    def _handle_click(self, pos: Tuple[int,int]) -> None:
        """Kliknięcie na atom → highlight + info w terminalu."""
        mx, my = pos
        phi_r  = pygame.Rect(W//2, self.HUD_H,
                             W//2, (H - self.HUD_H)//2)
        if not phi_r.collidepoint(mx, my):
            return

        atoms  = self._get_atoms()
        visible = [a for a in atoms
                   if getattr(a, "state", a.get("state","") if isinstance(a,dict) else "") != "TOMB"]
        visible.sort(key=lambda a: -(getattr(a,"T",0) if not isinstance(a,dict) else a.get("T",0)))
        visible = visible[:120]

        cols   = max(1, (phi_r.w - 12) // 115)
        cell_w = (phi_r.w - 12) // cols
        cell_h = 30
        top    = phi_r.y + 22

        for idx, atom in enumerate(visible):
            col_i = idx % cols
            row_i = idx // cols
            ax    = phi_r.x + 6 + col_i * cell_w
            ay    = top + row_i * (cell_h + 3)
            if ay + cell_h > phi_r.bottom - 4:
                break
            cell = pygame.Rect(ax, ay, cell_w - 4, cell_h)
            if cell.collidepoint(mx, my):
                aid = str(getattr(atom,"id",
                          atom.get("id","?") if isinstance(atom,dict) else "?"))
                T   = float(getattr(atom,"T",
                            atom.get("T",50) if isinstance(atom,dict) else 50))
                st  = str(getattr(atom,"state",
                          atom.get("state","?") if isinstance(atom,dict) else "?"))
                self._highlight = aid
                self.term_state.append(
                    f"φ {aid}  T={T:.1f}  {st}", C_ACCENT)
                return

    def run(self,
            shell_main: Optional[Callable] = None,
            on_quit:    Optional[Callable] = None) -> None:
        """
        Główna pętla. Blokuje main thread (wymóg SDL2).
        shell_main uruchamiany w daemon thread.
        """
        if shell_main:
            t = threading.Thread(
                target=shell_main,
                args=(self.term_state,),
                daemon=True,   # umiera razem z procesem — nie zombie
                name="karmazyn-shell",
            )
            t.start()

        running = True
        while running:
            t = time.monotonic() - self._t0
            for event in pygame.event.get():
                if not self._handle_event(event):
                    running = False
                    break
            if running:
                self.render_frame(t)
            self._clock.tick(FPS)

        # Sygnalizuj workerowi przed pygame.quit()
        # (odblokuje get_input_blocking jeśli czeka)
        self.term_state.shutdown()
        pygame.quit()
        if on_quit:
            on_quit()


# ─── KarmazynDisplay — fasada ─────────────────────────────────────────────────

class KarmazynDisplay:
    """
    Fasada modułu graficznego.

    Użycie:
        display = KarmazynDisplay()
        if display.init():
            display.bind_phi(phi_space)
            display.run(shell_worker, on_quit=cleanup)
        else:
            # Tryb tekstowy — display.available = False
            pass

    display.logo_state — przekaż do LogoEnv
    display.term_state — przekaż do shell workera
    """

    def __init__(self):
        self.available:  bool                        = False
        self.term_state: TerminalState               = TerminalState()
        self.logo_state: LogoState                   = LogoState()
        self._renderer:  Optional[ImmediateRenderer] = None
        self._font:      Optional[Any]               = None
        self._screen:    Optional[Any]               = None

    def init(self,
             w: int = W, h: int = H,
             title: str = "KarmazynOS",
             fullscreen: bool = False) -> bool:
        """
        Inicjalizuje SDL2. Zwraca False jeśli pygame niedostępne
        lub brak wyświetlacza — system działa dalej w trybie tekstowym.
        """
        if not PYGAME_OK:
            return False
        try:
            pygame.init()
            flags  = pygame.FULLSCREEN if fullscreen else pygame.NOFRAME
            screen = pygame.display.set_mode((w, h), flags)
            pygame.display.set_caption(title)

            try:
                font = pygame.font.SysFont("monospace", FONT_SIZE)
            except Exception:
                font = pygame.font.Font(None, FONT_SIZE)

            self.logo_state.init_canvas(w // 2, h)
            self._screen   = screen
            self._font     = font
            self._renderer = ImmediateRenderer(
                screen, font,
                self.term_state,
                self.logo_state,
            )
            self.available = True
            return True
        except Exception as e:
            # Brak X11, brak sterownika, headless — ok
            self.available = False
            return False

    def bind_phi(self, phi_space: Any) -> None:
        """
        Podpina live PhiSpace — phi-map pokazuje realne atomy,
        tick_fn odpala phi.tick() co sekundę z render loop.
        Bezpieczne: można wywołać przed i po init().
        """
        if self._renderer:
            self._renderer.phi_ref = phi_space
            if phi_space is not None and hasattr(phi_space, 'tick'):
                self._renderer._tick_fn = phi_space.tick

    def set_demo_atoms(self, atoms: List[Dict]) -> None:
        """Ustaw listę dict dla trybu demo (bez PhiSpace)."""
        if self._renderer:
            self._renderer._phi_atoms = atoms

    def run(self,
            shell_main: Optional[Callable] = None,
            on_quit:    Optional[Callable] = None) -> None:
        """Uruchamia render loop. Blokuje do zamknięcia okna."""
        if not self.available or self._renderer is None:
            # Fallback — uruchom shell_main bezpośrednio
            if shell_main:
                shell_main(self.term_state)
            return
        self._renderer.run(shell_main, on_quit)

    @property
    def renderer(self) -> Optional[ImmediateRenderer]:
        return self._renderer


# ─── Benchmark (bez X11) ─────────────────────────────────────────────────────

def benchmark(frames: int = 300) -> Dict[str, float]:
    """
    Mierzy koszt render_frame() w trybie dummy.
    Bez flip() — mierzy sam koszt rasteryzacji.
    """
    import time as _time

    os.environ["SDL_VIDEODRIVER"] = "dummy"
    if not PYGAME_OK:
        return {"error": "pygame niedostępny"}

    pygame.init()
    screen = pygame.display.set_mode((W, H))
    try:
        font = pygame.font.SysFont("monospace", FONT_SIZE)
    except Exception:
        font = pygame.font.Font(None, FONT_SIZE)

    term   = TerminalState()
    logo   = LogoState()
    logo.init_canvas(W//2, H)
    atoms  = [{"id": f"atom_{i:03d}",
               "T":  float(i * 100 / 30),
               "state": "HOT" if i > 20 else "WARM"
               } for i in range(30)]

    # Wypełnij terminal
    for i in range(50):
        term.append(f"linia {i} — log shella KarmazynOS")

    # Dodaj segmenty śladu
    import math as _math
    for i in range(360):
        angle = _math.radians(i)
        logo.add_segment(
            50 * _math.cos(_math.radians(i-1)),
            50 * _math.sin(_math.radians(i-1)),
            50 * _math.cos(angle),
            50 * _math.sin(angle),
        )
    logo.set_turtle(50, 0, 0, True)

    r = ImmediateRenderer(screen, font, term, logo)
    r._phi_atoms = atoms

    # Bez display.flip() — tylko rasteryzacja
    _orig_flip = pygame.display.flip
    pygame.display.flip = lambda: None

    t0 = _time.perf_counter()
    for f in range(frames):
        r.render_frame(f / FPS)
    elapsed = _time.perf_counter() - t0

    pygame.display.flip = _orig_flip
    pygame.quit()

    ms_per_frame = elapsed / frames * 1000
    return {
        "ms_per_frame": round(ms_per_frame, 3),
        "fps_capacity": round(1000 / ms_per_frame, 0),
        "frames":       frames,
        "atoms":        len(atoms),
        "trail_segs":   360,
        "term_lines":   50,
    }


# ─── Punkt wejścia ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== karmazyn_display.py benchmark ===")
    result = benchmark(300)
    if "error" in result:
        print(f"Błąd: {result['error']}")
    else:
        print(f"  Rasteryzacja:  {result['ms_per_frame']:.3f} ms/frame")
        print(f"  Pojemność:     {result['fps_capacity']:.0f} fps max")
        print(f"  Atomy:         {result['atoms']}")
        print(f"  Segmenty:      {result['trail_segs']}")
        print(f"  Linie term.:   {result['term_lines']}")
        budget = 1000 / 60
        used   = result["ms_per_frame"] / budget * 100
        print(f"  Użycie budżetu 60fps: {used:.1f}%")
        print(f"  Wolne na logikę:      {budget - result['ms_per_frame']:.2f} ms")