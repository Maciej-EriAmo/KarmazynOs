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
import hashlib
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

# ─── Graceful degradation bez pygame ─────────────────────────────────────────

try:
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame
    PYGAME_OK = True
except ImportError:
    PYGAME_OK = False

# ─── Stałe layoutu ───────────────────────────────────────────────────────────

W, H       = 1440, 900
FPS        = 60
FONT_SIZE  = 20

# Kolory — jeden zestaw dla całego systemu
C_BG     = (12,  12,  20)
C_FG     = (255, 255, 255)
C_ACCENT = (180, 60,  60)   # karmazynowy — akcenty, prompt, obramowania
C_HOT    = (255, 80,  40)   # czerwony — T >= 70
C_WARM   = (60,  160, 255)  # niebieski — T 30-70
C_COLD   = (40,  80,  140)  # ciemny — T < 30
C_TURTLE = (100, 220, 100)  # zielony — żółw
C_TRAIL  = (50,  120, 50)   # ciemniejszy zielony — ślad
C_GRID   = (20,  20,  35)
C_STATUS = (160, 160, 180)   # szarawy — komunikaty systemu   # siatka phi-map


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
        self._history:   List[str]        = []      # historia komend
        self._hist_idx:  int              = 0       # pozycja w historii
        self._scroll_offset: int          = 0

    def scroll(self, delta: int) -> None:
        """Przewiń widok terminala (delta<0=góra, delta>0=dół)."""
        with self._lock:
            self._scroll_offset = max(0, self._scroll_offset + delta)

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
        
        with self._lock:
            if event.key == pygame.K_RETURN:
                line            = self.input_buf
                self.input_buf  = ""
                if line.strip():
                    self._history.append(line)
                    self._hist_idx = len(self._history)
                self._key_queue.put(line)
            elif event.key == pygame.K_BACKSPACE:
                self.input_buf = self.input_buf[:-1]
            elif event.key == pygame.K_DELETE:
                self.input_buf = ''  # Ctrl+Del czyści cały bufor
            elif event.key == pygame.K_UP:
                if self._history and self._hist_idx > 0:
                    self._hist_idx -= 1
                    self.input_buf = self._history[self._hist_idx]
            elif event.key == pygame.K_DOWN:
                if self._history and self._hist_idx < len(self._history) - 1:
                    self._hist_idx += 1
                    self.input_buf = self._history[self._hist_idx]
                else:
                    self._hist_idx = len(self._history)
                    self.input_buf = ""
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

    def clear(self, color: Tuple = C_BG, alpha: int = 220) -> None:
        """Tło panelu. alpha<255 = mgła phi przebija, 255 = nieprzezroczyste."""
        if alpha >= 255:
            self.surface.fill(color, self.rect)
        else:
            overlay = pygame.Surface(
                (self.rect.w, self.rect.h), pygame.SRCALPHA)
            overlay.fill((*color[:3], alpha))
            self.surface.blit(overlay, self.rect.topleft)


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
    ctx.clear(C_BG, alpha=230)   # lekko półprzezroczysty — mgła widoczna
    ctx.box(r, outline=C_ACCENT)

    line_h  = ctx._line_h
    visible = max(1, (r.h - 8) // line_h - 1)
    lines, input_buf = state.snapshot()

    # Scroll: _scroll_offset=0 → najnowsze linie; >0 → starsze
    offset = getattr(state, '_scroll_offset', 0)
    total  = len(lines)
    end    = max(visible, total - offset)
    start  = max(0, end - visible)
    view   = lines[start:end]

    y = r.y + 4
    for text, color in view:
        ctx.text(text, color, x=r.x + 6, y=y)
        y += line_h

    # Input z migającym kursorem
    cursor  = "|" if int(t * 2) % 2 == 0 else " "
    inp_txt = state.prompt + input_buf + cursor
    ctx.text(inp_txt, (255, 220, 100), x=r.x + 6, y=y)  # żółty prompt — czytelny


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
    cell_h  = 22   # kompaktowy przy 28% wysokości
    top     = r.y + 20

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
             font:    "pygame.font.Font",
             stats:   Dict[str, Any],
             t:       float) -> None:
    """
    HUD — pasek statusu + przycisk [×] w stałym miejscu (W-30, 1, 28, 20).
    Pozycja × nie zmienia się — brak mutowalnej listy, brak race condition.
    """

    r = pygame.Rect(0, 0, W, 26)
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
        (f"  F1=zamknij-panel  F2=phi-map  ESC=wyjście", (70, 70, 70)),
    ]
    x = 4
    for text, color in parts:
        s = font.render(text, True, color)
        surface.blit(s, (x, 3))
        x += s.get_width()

    # Przycisk [×] — stała pozycja (W-30, 1, 28, 20) = CLOSE_BTN_RECT
    btn_r = pygame.Rect(W - 30, 1, 28, 20)
    pygame.draw.rect(surface, (120, 30, 30), btn_r, 0, 3)
    pygame.draw.rect(surface, C_ACCENT,      btn_r, 1, 3)
    lbl = font.render("×", True, (220, 220, 220))
    surface.blit(lbl, (btn_r.x + (btn_r.w - lbl.get_width()) // 2,
                        btn_r.y + 2))

    # Linia oddzielająca HUD od paneli
    pygame.draw.line(surface, C_ACCENT, (0, 25), (W, 25), 1)


def draw_dividers(surface: "pygame.Surface") -> None:
    """Linia podziału — tylko pionowa, tylko gdy split."""
    pygame.draw.line(surface, C_ACCENT,
                     (W//2, 22), (W//2, H), 1)
    pygame.draw.line(surface, (40, 20, 20),
                     (W//2, H//2), (W, H//2), 1)


# ─── ImmediateRenderer ────────────────────────────────────────────────────────

# ─── PhiBuffer — mgła termodynamiczna ────────────────────────────────────────

class PhiBuffer:
    """
    Natywna warstwa emisyjna KarmazynOS.
    Rzutuje atomy z phi-space na płótno 2D przez temperaturę T.

    Trzy właściwości wizualne:
      Sól 1 — tętno: każdy atom pulsuje w swoim rytmie (faza z hash)
      Sól 2 — ślad:  fade zamiast clear, historia aktywności widoczna
      Pieprz — regiony semantyczne: prefix id → region ekranu
    """

    # Regiony semantyczne: prefix → (cx, cy) w [0,1]
    _REGIONS = {
        "shell":   (0.15, 0.15),   # lewy górny  — powłoka
        "file":    (0.85, 0.15),   # prawy górny — pliki
        "module":  (0.50, 0.15),   # góra środek — moduły
        "program": (0.50, 0.50),   # centrum      — programy
        "bubble":  (0.15, 0.80),   # lewy dolny  — bąble
        "run":     (0.85, 0.80),   # prawy dolny — wyniki
        "cache":   (0.50, 0.85),   # dół środek  — cache
        "out":     (0.85, 0.80),   # prawy dolny — output
        "code":    (0.85, 0.15),   # prawy górny — kod
        "nooedit": (0.15, 0.15),   # lewy górny  — edytor
        "luneta":  (0.50, 0.50),   # centrum      — przeglądarka
        "logo":    (0.15, 0.50),   # lewy środek — logo
    }

    def __init__(self, width: int, height: int):
        self.width   = width
        self.height  = height
        self.surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self.surface.fill((0, 0, 0, 0))
        self._C_HOT  = (255,  50,  50)
        self._C_WARM = (180,  20,  50)
        self._C_COLD = (100, 100, 100)
        # Fade surface — skaluje alpha w dół (BLEND_RGBA_MULT)
        # 210/255 ≈ 0.82 → każda klatka alpha * 0.82
        # Przy 60fps: zanika w ~10 klatek ≈ 0.17s (szybki ślad)
        # Przy 30fps: zanika w ~5 klatek  ≈ 0.17s (spójne)
        self._fade   = pygame.Surface((width, height), pygame.SRCALPHA)
        self._fade.fill((255, 255, 255, 210))  # MULT: alpha *= 210/255

    def _project(self, atom) -> tuple:
        """
        Projekcja → (x, y).
        Wektor N-D:  dim[0], dim[1] ∈ [-1,1] → ekran
        String id:   prefix → region semantyczny + MD5 rozproszenie ±12.5%
        """
        S = None
        try:    S = atom["S"]
        except Exception: pass
        if S is None:
            S = getattr(atom, "S", None)

        if S is not None and hasattr(S, "__len__") and not isinstance(S, str):
            try:
                x = int((float(S[0]) + 1.0) / 2.0 * self.width)
                y = int((float(S[1]) + 1.0) / 2.0 * self.height)
                return max(0, min(self.width-1, x)), max(0, min(self.height-1, y))
            except Exception:
                pass

        # Prefix → region semantyczny
        atom_id = atom.get("id", None) if isinstance(atom, dict) else getattr(atom, "id", None)
        atom_id = str(atom_id or S or "?")
        prefix  = atom_id.split(".")[0]
        cx, cy  = self._REGIONS.get(prefix, (0.50, 0.50))

        # MD5 jako rozproszenie wokół centrum regionu (±12.5% ekranu)
        h  = int(hashlib.md5(atom_id.encode()).hexdigest(), 16)
        dx = ((h & 0xFF) / 255.0 - 0.5) * 0.25
        dy = (((h >> 8) & 0xFF) / 255.0 - 0.5) * 0.25

        x  = int((cx + dx) * self.width)
        y  = int((cy + dy) * self.height)
        return max(0, min(self.width-1, x)), max(0, min(self.height-1, y))

    def sync_matrix(self, matrix) -> None:
        """
        Pętla renderująca mgłę.
        Sól 1: tętno — sinus na radius, faza unikalna per atom
        Sól 2: ślad  — fade zamiast fill, historia aktywności
        """
        import math as _math

        # Ślad termiczny — skaluj alpha zamiast dodawać czarne tło
        # BLEND_RGBA_MULT: każdy piksel alpha *= 210/255 ≈ 0.82
        self.surface.blit(self._fade, (0, 0),
                         special_flags=pygame.BLEND_RGBA_MULT)

        if matrix is None:
            return

        try:
            atoms = matrix.atoms() if callable(matrix.atoms) else matrix.atoms
        except Exception:
            return

        now = _math.fmod(_math.floor(_math.pi * 1e6 + id(matrix) * 1e-9)
                         + __import__("time").monotonic(), 1e6)

        for atom in atoms:
            T = atom.get("T", 0) if isinstance(atom, dict) else getattr(atom, "T", 0)
            T = float(T)
            if T < 10.0:
                continue

            alpha  = min(220, int(T * 2.2))

            # Tętno — każdy atom ma własną fazę z hash id
            atom_id = atom.get("id", "?") if isinstance(atom, dict) else getattr(atom, "id", "?")
            atom_id = str(atom_id)
            phase   = (hash(atom_id) & 0x3F) / 63.0 * 6.28   # 0–2π unikalne
            pulse   = 1.0 + 0.18 * _math.sin(
                __import__("time").monotonic() * 2.8 + phase)
            radius  = max(2, int(T / 18 * pulse))

            x, y = self._project(atom)

            if T >= 70.0:
                color = (*self._C_HOT,  alpha)
            elif T >= 30.0:
                color = (*self._C_WARM, alpha)
            else:
                # Szum termiczny — drobny drift ale stabilny między klatkami
                random.seed(hash(atom_id) ^ int(T))
                x += random.randint(-2, 2)
                y += random.randint(-2, 2)
                color = (*self._C_COLD, max(40, alpha))

            x = max(0, min(self.width  - 1, x))
            y = max(0, min(self.height - 1, y))

            pygame.draw.circle(self.surface, color, (x, y), radius)

    def get_frame(self) -> pygame.Surface:
        return self.surface


# ─── EditorState ─────────────────────────────────────────────────────────────

class EditorState:
    """
    Bufor tekstu wbudowanego edytora SDL.

    Klawiatura → push_key() (main thread SDL)
    Shell worker → process_key() (blokuje do następnego klawisza)

    Jeden EditorState = jeden otwarty bąbel.
    Zapis Ctrl+S → bubble.content + VFS backup.
    Uruchomienie F5 → output w prawym terminalu.
    """
    INDENT = 4

    def __init__(self, label, content, content_type="py"):
        self.label        = label
        self.content_type = content_type
        self.lines        = content.split("\n")
        if not self.lines: self.lines = [""]
        self.cursor_row   = 0
        self.cursor_col   = 0
        self.scroll_top   = 0
        self.modified     = False
        self.status       = "Ctrl+S zapisz | Ctrl+Q wyjdz | F5 uruchom"
        self._key_queue: queue.Queue = queue.Queue()
        self._quit        = False
        self._save        = False
        self._run         = False

    def push_key(self, event):
        self._key_queue.put(event)

    def process_key(self):
        event = self._key_queue.get()
        key   = event.key
        mod   = event.mod
        ctrl  = bool(mod & pygame.KMOD_CTRL)

        if ctrl and key == pygame.K_q:
            self._quit = True; return "quit"
        if ctrl and key == pygame.K_s:
            self._save = True; return "save"
        if key == pygame.K_F5:
            self._run  = True; return "run"

        if key == pygame.K_UP:
            self.cursor_row = max(0, self.cursor_row - 1)
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_row]))
        elif key == pygame.K_DOWN:
            self.cursor_row = min(len(self.lines)-1, self.cursor_row + 1)
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_row]))
        elif key == pygame.K_LEFT:
            if self.cursor_col > 0: self.cursor_col -= 1
            elif self.cursor_row > 0:
                self.cursor_row -= 1
                self.cursor_col  = len(self.lines[self.cursor_row])
        elif key == pygame.K_RIGHT:
            line = self.lines[self.cursor_row]
            if self.cursor_col < len(line): self.cursor_col += 1
            elif self.cursor_row < len(self.lines)-1:
                self.cursor_row += 1; self.cursor_col = 0
        elif key == pygame.K_HOME:  self.cursor_col = 0
        elif key == pygame.K_END:   self.cursor_col = len(self.lines[self.cursor_row])
        elif key == pygame.K_PAGEUP:
            self.cursor_row = max(0, self.cursor_row - 20)
        elif key == pygame.K_PAGEDOWN:
            self.cursor_row = min(len(self.lines)-1, self.cursor_row + 20)
        elif key == pygame.K_RETURN:
            line   = self.lines[self.cursor_row]
            indent = len(line) - len(line.lstrip())
            if line.rstrip().endswith(":"): indent += self.INDENT
            rest   = line[self.cursor_col:]
            self.lines[self.cursor_row] = line[:self.cursor_col]
            self.cursor_row += 1
            self.lines.insert(self.cursor_row, " " * indent + rest)
            self.cursor_col  = indent
            self.modified    = True
        elif key == pygame.K_BACKSPACE:
            if self.cursor_col > 0:
                line = self.lines[self.cursor_row]
                self.lines[self.cursor_row] = line[:self.cursor_col-1]+line[self.cursor_col:]
                self.cursor_col -= 1; self.modified = True
            elif self.cursor_row > 0:
                prev = self.lines[self.cursor_row-1]
                cur  = self.lines.pop(self.cursor_row)
                self.cursor_row -= 1; self.cursor_col = len(prev)
                self.lines[self.cursor_row] = prev + cur
                self.modified = True
        elif key == pygame.K_DELETE:
            line = self.lines[self.cursor_row]
            if self.cursor_col < len(line):
                self.lines[self.cursor_row] = line[:self.cursor_col]+line[self.cursor_col+1:]
                self.modified = True
            elif self.cursor_row < len(self.lines)-1:
                nxt = self.lines.pop(self.cursor_row+1)
                self.lines[self.cursor_row] += nxt; self.modified = True
        elif key == pygame.K_TAB:
            line = self.lines[self.cursor_row]
            self.lines[self.cursor_row] = line[:self.cursor_col]+" "*self.INDENT+line[self.cursor_col:]
            self.cursor_col += self.INDENT; self.modified = True
        elif event.unicode and event.unicode.isprintable():
            line = self.lines[self.cursor_row]
            self.lines[self.cursor_row] = line[:self.cursor_col]+event.unicode+line[self.cursor_col:]
            self.cursor_col += 1; self.modified = True

        self._clamp_scroll()
        return "continue"

    def _clamp_scroll(self, visible_lines=40):
        if self.cursor_row < self.scroll_top:
            self.scroll_top = self.cursor_row
        elif self.cursor_row >= self.scroll_top + visible_lines:
            self.scroll_top = self.cursor_row - visible_lines + 1

    def get_text(self): return "\n".join(self.lines)

    def snapshot(self):
        return (list(self.lines), self.cursor_row, self.cursor_col,
                self.scroll_top, self.modified, self.label,
                self.content_type, self.status)


_PY_KW = frozenset((
    'def','class','return','if','elif','else','for','while','try','except',
    'finally','with','import','from','as','pass','break','continue',
    'and','or','not','in','is','lambda','yield','raise','True','False','None',
))

def _draw_py_line(ctx, line, x, y, max_w):
    char_w = max(1, ctx.font.size('A')[0])
    max_c  = max(1, max_w // char_w)
    line   = line[:max_c]
    s = line.lstrip()
    if s.startswith('#'):
        ctx.text(line, (100,160,100), x=x, y=y); return
    quote3d = ('"""',)
    quote3s = ("'''",)
    if s.startswith(quote3d) or s.startswith(quote3s):
        ctx.text(line, (200,140,100), x=x, y=y); return
    if s and s[0] in ('"', "'"):
        ctx.text(line, (200,140,100), x=x, y=y); return
    import re as _re
    for m in _re.finditer(r'[A-Za-z_][A-Za-z_0-9]*|.', line):
        tok = m.group()
        px  = x + m.start() * char_w
        col = (120,180,255) if tok in _PY_KW else C_FG
        ctx.text(tok, col, x=px, y=y)


def draw_editor(ctx, state):
    r = ctx.rect
    ctx.clear(C_BG, alpha=230)   # lekko półprzezroczysty — mgła widoczna
    ctx.box(r, outline=C_ACCENT)
    line_h    = ctx._line_h
    lnum_w    = 52
    text_x    = r.x + lnum_w + 4
    text_w    = r.w - lnum_w - 8
    visible_n = max(1, (r.h - line_h - 4) // line_h)
    lines, cur_row, cur_col, scroll_top, modified, label, ct, status = state.snapshot()
    state._clamp_scroll(visible_n)
    scroll_top = state.scroll_top
    char_w = max(1, ctx.font.size('A')[0])
    for i, line in enumerate(lines[scroll_top:scroll_top + visible_n]):
        abs_row = scroll_top + i
        y       = r.y + 4 + i * line_h
        lc = C_ACCENT if abs_row == cur_row else (70, 70, 100)
        ctx.text(f'{abs_row+1:4}', lc, x=r.x+4, y=y)
        if abs_row == cur_row:
            hl = pygame.Rect(text_x-2, y-1, text_w, line_h)
            pygame.draw.rect(ctx.surface, (30,30,55), hl)
        if ct == 'py':
            _draw_py_line(ctx, line, text_x, y, text_w)
        else:
            ctx.text(line[:max(1,text_w//char_w)], C_FG, x=text_x, y=y)
        if abs_row == cur_row:
            cpx = text_x + cur_col * char_w
            pygame.draw.line(ctx.surface, (255,255,100),
                             (cpx, y), (cpx, y+line_h-2), 2)
    sb_y = r.bottom - line_h - 2
    ctx.surface.fill((20,30,60), pygame.Rect(r.x, sb_y, r.w, line_h+2))
    mark = '*' if modified else ''
    ct_s = {'py':'Python','lua':'Lua','md':'Markdown','txt':'Tekst'}.get(ct,ct)
    ctx.text(f' {label}{mark} [{ct_s}]  {status}',
             (200,220,255), x=r.x+4, y=sb_y+2)


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

    HUD_H = 26   # piksele HUD na górze

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
        self.browser_ref = None   # KarmazynBrowser — podpinany przez bind_browser()
        self._clock      = pygame.time.Clock()
        self._t0         = time.monotonic()
        self._tick_n     = 0
        # Stała pozycja przycisku × — zawsze w prawym górnym rogu HUD
        self.CLOSE_BTN_RECT = pygame.Rect(W - 30, 1, 28, 20)
        self._tick_fn:   Optional[Callable] = None  # fizyka: phi.tick()
        self._last_phys  = 0.0        # ostatni czas wywołania tick_fn
        self._editor:    Optional[Any]  = None   # EditorState gdy aktywny

        # ── Workspace — dynamiczne panele ────────────────────────────────────
        # Programy rejestrują się gdy aktywne, zwalniają gdy nieaktywne.
        # layout: "solo"  — terminal full-screen
        #         "split" — lewy program + prawy terminal
        #         "trio"  — lewy program + prawy: phi-map+terminal
        self._layout:      str              = "solo"
        self._left_draw:   Optional[Callable] = None   # fn(ctx) → None
        self._left_label:  str              = ""
        self._show_phi:    bool             = False     # F2 toggle

        # ── PhiBuffer — mgła termodynamiczna ──────────────────────────
        self._phi_buf:     Optional[PhiBuffer] = None

    def _make_ctx(self, rect: "pygame.Rect") -> DrawCtx:
        return DrawCtx(self.screen, self.font, rect)

    def _get_atoms(self) -> List[Any]:
        """Pobiera atomy — z live PhiSpace lub z listy demo."""
        if self.phi_ref is not None:
            return self.phi_ref.matrix.atoms()
        return self._phi_atoms

    # ── Workspace API ─────────────────────────────────────────────────────────

    def claim_left(self, draw_fn: Callable, label: str = "") -> None:
        """Program zajmuje lewy panel.
        draw_fn(ctx: DrawCtx) → None  — wywoływane każdą klatkę.
        """
        if not callable(draw_fn): return
        self._left_draw  = draw_fn
        self._left_label = label
        self._layout     = "split"

    def release_left(self) -> None:
        """Program zwalnia lewy panel — terminal wraca do full-screen."""
        self._left_draw  = None
        self._left_label = ""
        self._layout     = "solo"
        self._editor     = None   # edytor zwolniony razem z panelem

    def set_editor(self, state: Optional[Any]) -> None:
        """Podepnij EditorState — klawiatura idzie do edytora (nie terminala)."""
        self._editor = state

    def toggle_phi(self) -> bool:
        """Przełącz widoczność phi-map (F2). Zwraca nowy stan."""
        self._show_phi = not self._show_phi
        return self._show_phi

    def _try_click_link(self, pos: Tuple[int,int]) -> None:
        """Klik w terminalu — wykryj [N] i podążaj za linkiem N."""
        if not self.browser_ref or not getattr(self.browser_ref, '_current', False):
            return
        # Snapshot layoutu — spójny z ostatnią klatką render_frame
        layout    = self._layout      # odczyt atomowy — nie zmieni się w trakcie
        show_phi  = self._show_phi
        available_h = H - self.HUD_H
        phi_h   = int(available_h * 0.25) if show_phi else 0
        right_x = W//2 if layout == "split" else 0
        right_w = W - right_x
        term_y  = self.HUD_H + phi_h
        term_h  = available_h - phi_h
        term_r  = pygame.Rect(right_x, term_y, right_w, term_h)
        if not term_r.collidepoint(pos):
            return
        # Która linia? Oblicz indeks klikniętej linii
        line_h  = self.font.get_height() + 2
        rel_y   = pos[1] - term_y
        line_idx = rel_y // line_h
        # Pobierz tekst linii
        lines, _ = self.term_state.snapshot()
        visible_start = max(0, len(lines) - (term_h // line_h) - 1)
        abs_idx = visible_start + line_idx
        if abs_idx >= len(lines):
            return
        line_text, _ = lines[abs_idx]
        # Szukaj [N] w linii
        import re
        m = re.search(r'\[(\d+)\]', line_text)
        if m:
            n = int(m.group(1))
            _, msg = self.browser_ref.follow_link(n)
            self.term_state.append(msg)

    def _phi_stats(self) -> Dict[str, int]:
        if self.phi_ref is not None:
            return self.phi_ref.matrix.stats()
        return {"HOT": 0, "WARM": 0, "COLD": 0, "TOMB": 0}

    def render_frame(self, t: float) -> None:
        """Pełny redraw — deterministyczna funkcja t i stanu."""
        # Lazy init PhiBuffer
        if self._phi_buf is None:
            self._phi_buf = PhiBuffer(W, H)
        # Fizyka: tick co sekundę (niezależnie od frame rate)
        if self._tick_fn and t - self._last_phys >= 1.0:
            self._last_phys = t
            try:
                self._tick_fn()
            except Exception:
                pass

        s = self.screen

        # ── Warstwa 1: mgła termodynamiczna (PhiBuffer) ──────────────
        if self._phi_buf is not None and self.phi_ref is not None:
            self._phi_buf.sync_matrix(self.phi_ref.matrix)
            s.fill(C_BG)  # tło pod mgłę
            s.blit(self._phi_buf.get_frame(), (0, 0))
        else:
            s.fill(C_BG)

        hud_offset = self.HUD_H

        # Flush segmentów LOGO z worker queue → canvas (main thread only)
        self.logo_state.flush_segments()

        available_h = H - hud_offset

        # ── Workspace layout ─────────────────────────────────────────────────
        if self._layout == "split" and self._left_draw:
            # Program zajął lewy panel
            left_w  = W // 2
            right_x = left_w
            right_w = W - left_w

            # Lewy panel — program (LOGO, edytor, itp.)
            left_ctx = self._make_ctx(
                pygame.Rect(0, hud_offset, left_w, available_h))
            self._left_draw(left_ctx)

        else:
            # "solo" — terminal full-screen (brak lewego panelu)
            right_x = 0
            right_w = W

        # Prawy obszar: phi-map (opcjonalny) + terminal
        if self._show_phi and self._get_atoms():
            phi_h  = int(available_h * 0.25)
            term_y = hud_offset + phi_h
            term_h = available_h - phi_h
            draw_phi_map(
                self._make_ctx(pygame.Rect(
                    right_x, hud_offset, right_w, phi_h)),
                self._get_atoms(), self._highlight,
            )
        else:
            term_y = hud_offset
            term_h = available_h

        draw_terminal(
            self._make_ctx(pygame.Rect(right_x, term_y, right_w, term_h)),
            self.term_state, t,
        )

        # Linia pionowa tylko gdy split
        if self._layout == "split":
            pygame.draw.line(s, C_ACCENT,
                             (W//2, hud_offset), (W//2, H), 1)

        # HUD + dividers
        draw_hud(s, self.font, self._phi_stats(), t)
        # Linia środkowa tylko gdy split
        if self._layout == 'split':
            draw_dividers(s)
        pygame.display.flip()

    def _handle_event(self, event: "pygame.event.Event") -> bool:
        """Zwraca False jeśli quit."""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            # Escape → quit (tylko gdy brak aktywnego edytora)
            if event.key == pygame.K_ESCAPE and not self._editor:
                return False
            ctrl = event.mod & pygame.KMOD_CTRL
            if ctrl and event.key == pygame.K_q and not self._editor:
                return False
            # F1 — zwolnij lewy panel
            if event.key == pygame.K_F1 and not self._editor:
                self.release_left()
                return True
            # F2 — przełącz phi-map
            if event.key == pygame.K_F2 and not self._editor:
                self.toggle_phi()
                return True
            # Edytor aktywny → klawiatura do EditorState
            if self._editor is not None:
                self._editor.push_key(event)
                return True
            self.term_state.push_key(event)
        if event.type == pygame.MOUSEBUTTONDOWN:
            # Kliknięcie × w HUD → quit
            if self.CLOSE_BTN_RECT.collidepoint(event.pos):
                return False
            if event.button == 1:    # LPM
                self._handle_click(event.pos)
                self._try_click_link(event.pos)
            elif event.button == 3:  # PPM — skróty
                self._handle_right_click(event.pos)
            elif event.button == 4:  # kółko góra
                self.term_state.scroll(-3)
            elif event.button == 5:  # kółko dół
                self.term_state.scroll(3)
        return True

    def _handle_right_click(self, pos: Tuple[int,int]) -> None:
        """PPM — pokaż dostępne skróty w terminalu."""
        W2 = self.screen.get_width() // 2
        # Lewy panel aktywny tylko gdy layout=split ORAZ _left_draw ustawiony
        is_left_panel = (
            self._layout == "split"
            and self._left_draw is not None
            and pos[0] < W2
        )
        if is_left_panel:
            label = self._left_label or "panel"
            self.term_state.append(
                f"Panel lewy [{label}]: F1=zamknij  Ctrl+S=zapisz  Ctrl+Q=wyjdz",
                (160, 200, 255))
        else:
            self.term_state.append(
                "Skroty: F1=panel  F2=phi-map  j/k=scroll  b=wstecz (Luneta)",
                (160, 200, 255))


    def _handle_click(self, pos: Tuple[int,int]) -> None:
        """Kliknięcie: atom w phi-map lub link w terminalu."""
        mx, my = pos
        # Snapshot stanu — identyczny z ostatnią klatką render_frame
        show_phi = self._show_phi
        layout   = self._layout
        if not show_phi:
            return   # phi-map niewidoczna — nic do kliknięcia
        available_h = H - self.HUD_H
        phi_h   = int(available_h * 0.25)
        right_x = W//2 if layout == "split" else 0
        phi_r   = pygame.Rect(right_x, self.HUD_H,
                              W - right_x, phi_h)
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
        if getattr(self, "available", False): return True
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

    def bind_browser(self, browser: Any) -> None:
        """Podpina przeglądarkę — klik myszą w terminalu śledzi linki."""
        if self._renderer:
            self._renderer.browser_ref = browser

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



def cmd_display(args: List[str],
                display: Optional["KarmazynDisplay"] = None) -> str:
    """Komenda DISPLAY dla shell — bez globalnych zależności."""
    if display is None or not display.available:
        return "Display niedostepny (brak pygame lub X11)"
    sub = args[0].upper() if args else "STATUS"
    if sub == "STATUS":
        r = display._renderer
        phi_n = len(r.phi_ref.matrix.atoms()) if r and r.phi_ref else 0
        return (f"Display: aktywny  "
                f"atoms:{phi_n}  "
                f"tick_fn:{'OK' if r and r._tick_fn else 'brak'}")
    if sub == "BENCH":
        r = benchmark(100)
        used = r['ms_per_frame'] / 16.67 * 100
        return (f"Benchmark: {r['ms_per_frame']:.2f} ms/frame  "
                f"{r['fps_capacity']:.0f} fps max  "
                f"{used:.0f}% budzetu 60fps")
    return "DISPLAY STATUS | BENCH"

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