# -*- coding: utf-8 -*-
"""karmazyn_io_sdl — Studio backend: SDL2 (pygame) × matryca termiczna Stage 1.

Wzorzec Luneta (luneta_gui_port / luneta_sdl):
  • silnik (Store, shell, heat) NIE importuje pygame w ścieżce krytycznej jądra
  • ten moduł = cienki viewer + input
  • DisplayAdapter.frame() / KeyboardAdapter → ThermalSurface

Wymaga: pygame (SDL2). Brak → sdl_available() False.

  python software/karmazyn_studio.py
  python karmazyn_boot.py --studio
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── kolory (studio karmazyn) ────────────────────────────────────────────────
C_BG = (12, 12, 20)
C_PANEL = (20, 20, 32)
C_FG = (220, 220, 230)
C_DIM = (120, 120, 140)
C_ACCENT = (180, 50, 55)
C_HOT = (255, 90, 50)
C_WARM = (200, 180, 60)
C_COLD = (60, 100, 180)
C_TOMB = (50, 50, 60)
C_INPUT = (30, 30, 48)
C_OK = (80, 200, 120)

W_DEFAULT, H_DEFAULT = 960, 640
FPS = 30
STATUS_H = 22
INPUT_H = 36
LINE_H = 18
PAD = 12
# tło termiczne: siatka komórek (mapa T pod promptem)
CELL = 28
MAP_MAX = 96          # max atomów w tle
BG_DIM = 0.35         # jak mocno wygasić mapę pod tekstem (0=żywa, 1=czarna)
TEXT_SHADOW = (0, 0, 0)


def sdl_available() -> bool:
    try:
        import pygame  # noqa: F401
        return True
    except Exception:
        return False


def _color_for_T(T: float) -> Tuple[int, int, int]:
    T = max(0.0, min(100.0, float(T)))
    if T >= 70:
        return C_HOT
    if T >= 30:
        # lerp warm→hot
        u = (T - 30) / 40.0
        return (
            int(C_WARM[0] + u * (C_HOT[0] - C_WARM[0])),
            int(C_WARM[1] + u * (C_HOT[1] - C_WARM[1])),
            int(C_WARM[2] + u * (C_HOT[2] - C_WARM[2])),
        )
    if T >= 2:
        u = (T - 2) / 28.0
        return (
            int(C_COLD[0] + u * (C_WARM[0] - C_COLD[0])),
            int(C_COLD[1] + u * (C_WARM[1] - C_COLD[1])),
            int(C_COLD[2] + u * (C_WARM[2] - C_COLD[2])),
        )
    return C_TOMB


class SdlIo:
    """IoPort nad buforem studium (nie blokuje event loop SDL).

    read_line w SDL nie woła input() — studio podaje linie przez push_input
    albo studio nie używa read_line (shell.feed z lokalnego bufora).
    """

    name = "sdl"

    def __init__(self):
        self._in: List[str] = []
        self._out: List[str] = []
        self._log: List[str] = []  # ostatnie linie wyjścia (UI)
        self._max_log = 200

    def write(self, text: str) -> None:
        self._out.append(text)
        for line in str(text).splitlines() or [""]:
            self._log.append(line)
        if len(self._log) > self._max_log:
            self._log = self._log[-self._max_log :]

    def write_err(self, text: str) -> None:
        self.write(text)

    def read_line(self, prompt: str = "") -> str:
        if prompt:
            self.write(prompt)
        if not self._in:
            return ""
        return self._in.pop(0)

    def try_read(self) -> Optional[str]:
        if not self._in:
            return None
        return self._in.pop(0)

    def push_input(self, line: str) -> None:
        self._in.append(str(line))

    def is_tty(self) -> bool:
        return True

    def clear(self) -> None:
        self._log.clear()
        self._out.append("<clear>")


class KarmazynStudio:
    """Okno SDL2: heatmapa matrycy T + shell + klawiatura/mysz → thermal."""

    def __init__(
        self,
        store: Any,
        shell: Any,
        thermal: Any,
        *,
        title: str = "KarmazynOs Studio",
        width: int = W_DEFAULT,
        height: int = H_DEFAULT,
        tick_every_frames: int = 15,
    ):
        if not sdl_available():
            raise RuntimeError("pygame/SDL2 niedostępne — pip install pygame")
        self.store = store
        self.shell = shell
        self.thermal = thermal
        self.title = title
        self.w = width
        self.h = height
        self.tick_every = max(1, int(tick_every_frames))
        self._closed = False
        self._input = ""
        self._history: List[str] = []
        self._hist_i = 0
        self._scroll = 0
        self._hover_aid = None
        self._hover_cell: Optional[Tuple[int, int]] = None
        self._frame_i = 0
        self._status = "studio ready — mapa T = tło, prompt = całe okno"
        self._map_layout: List[Tuple[Any, Dict[str, Any], int, int, int, int]] = []
        # adaptery na istniejącej matrycy
        from karmazyn_io import KeyboardAdapter, DisplayAdapter

        self.kbd = KeyboardAdapter(thermal)
        self.disp = DisplayAdapter(thermal)
        # podmień IoPort shell/thermal na SdlIo jeśli jeszcze nie
        if getattr(thermal.io, "name", "") != "sdl":
            sio = SdlIo()
            thermal.io = sio
            if shell.io is not None:
                shell.io = sio
            self.io = sio
        else:
            self.io = thermal.io

    def run(self) -> int:
        import pygame

        os.environ.setdefault("SDL_VIDEODRIVER", os.environ.get("SDL_VIDEODRIVER", ""))
        pygame.init()
        pygame.display.set_caption(self.title)
        screen = pygame.display.set_mode((self.w, self.h), pygame.RESIZABLE)
        clock = pygame.time.Clock()
        font = pygame.font.SysFont("Consolas", 16)
        font_sm = pygame.font.SysFont("Consolas", 13)
        font_b = pygame.font.SysFont("Consolas", 16, bold=True)

        try:
            while not self._closed:
                for ev in pygame.event.get():
                    self._handle_event(ev, pygame)

                self._frame_i += 1
                if self._frame_i % self.tick_every == 0:
                    try:
                        self.store.tick()
                    except Exception:
                        pass
                    # widoczność surface raz na tick_every — NIE co klatkę (anti self-heat)
                    try:
                        self.thermal.note_visible(["io:display"])
                    except Exception:
                        pass

                # projekcja bez grzania skanu (Stage 1) — tło + hit-test
                recs = self.thermal.project_hot(min_T=0.0, limit=MAP_MAX, mark_visible=False)

                self.w, self.h = screen.get_size()
                self._draw(screen, pygame, font, font_sm, font_b, recs)
                pygame.display.flip()
                clock.tick(FPS)
        finally:
            pygame.quit()
        return 0

    def _handle_event(self, ev, pygame) -> None:
        if ev.type == pygame.QUIT:
            self._closed = True
            return
        if ev.type == pygame.VIDEORESIZE:
            self.w, self.h = ev.w, ev.h
            return
        if ev.type == pygame.MOUSEMOTION:
            self._on_mouse(ev.pos, click=False)
            return
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            self._on_mouse(ev.pos, click=True)
            return
        if ev.type == pygame.MOUSEWHEEL:
            self._scroll = max(0, self._scroll - int(ev.y))
            return
        if ev.type == pygame.KEYDOWN:
            self._on_key(ev, pygame)

    def _on_key(self, ev, pygame) -> None:
        # mały heat na każdy klawisz (KeyboardAdapter)
        try:
            self.kbd.on_key(str(getattr(ev, "key", "")), getattr(ev, "unicode", "") or "")
        except Exception:
            pass

        if ev.key == pygame.K_ESCAPE:
            self._closed = True
            return
        if ev.key == pygame.K_RETURN:
            line = self._input
            self._input = ""
            if line.strip():
                self._history.append(line)
                self._hist_i = len(self._history)
                self.kbd.on_line(line)
                self._run_line(line)
            return
        if ev.key == pygame.K_BACKSPACE:
            self._input = self._input[:-1]
            return
        if ev.key == pygame.K_UP:
            if self._history:
                self._hist_i = max(0, self._hist_i - 1)
                self._input = self._history[self._hist_i]
            return
        if ev.key == pygame.K_DOWN:
            if self._history:
                self._hist_i = min(len(self._history), self._hist_i + 1)
                self._input = (
                    self._history[self._hist_i]
                    if self._hist_i < len(self._history)
                    else ""
                )
            return
        if ev.key == pygame.K_F5:
            # ręczny tick burst
            try:
                self.store.settle(10)
                self._status = "settle×10"
            except Exception as e:
                self._status = f"settle err: {e}"
            return
        ch = getattr(ev, "unicode", "") or ""
        if ch and ch.isprintable():
            self._input += ch

    def _run_line(self, line: str) -> None:
        try:
            # feed grzeje raz (shell); kbd.on_line już grzał — Stage1 double heat
            # akceptowalne w studio (interakcja silna)
            out = self.shell.feed(line)
            if out == "__EXIT__":
                self._closed = True
                return
            if out:
                self.io.write(str(out) + ("" if str(out).endswith("\n") else "\n"))
            self._status = f"ok: {line[:40]}"
        except Exception as e:
            self.io.write(f"err: {type(e).__name__}: {e}\n")
            self._status = "error"

    def _prompt_area(self) -> Tuple[int, int, int, int]:
        """Całe okno minus pasek statusu i linia input — obszar logu promptu."""
        return 0, 0, self.w, max(1, self.h - STATUS_H - INPUT_H)

    def _on_mouse(self, pos, click: bool) -> None:
        mx, my = pos
        self._hover_aid = None
        self._hover_cell = None
        for aid, r, x, y, cw, ch in self._map_layout:
            if x <= mx < x + cw and y <= my < y + ch:
                self._hover_aid = aid
                self._hover_cell = (x, y)
                try:
                    self.thermal.heat_hit(aid)
                    lab = r.get("name") or aid
                    self._status = f"hit {lab}  T={r.get('T')}"
                except Exception:
                    pass
                if click:
                    try:
                        self.thermal.set_focus(str(r.get("name") or aid))
                        self._status = f"focus {r.get('name') or aid}"
                    except Exception:
                        pass
                return

    def _mix(self, c: Tuple[int, int, int], bg: Tuple[int, int, int], a: float) -> Tuple[int, int, int]:
        """a=1 → c, a=0 → bg."""
        a = max(0.0, min(1.0, a))
        return (
            int(bg[0] + (c[0] - bg[0]) * a),
            int(bg[1] + (c[1] - bg[1]) * a),
            int(bg[2] + (c[2] - bg[2]) * a),
        )

    def _draw_thermal_background(self, screen, pygame, recs: List[Dict]) -> None:
        """Mapa termiczna jako pełnoekranowe tło (siatka komórek)."""
        screen.fill(C_BG)
        self._map_layout = []
        if not recs:
            return

        cols = max(1, self.w // CELL)
        rows = max(1, self.h // CELL)
        # ułóż od najgorętszych; powtórz wzór jeśli mało atomów
        n = len(recs)
        for i in range(cols * rows):
            r = recs[i % n]
            T = float(r.get("T") or 0.0)
            col = _color_for_T(T)
            # wygaszenie pod czytelność promptu + odrobina „żaru”
            intensity = 0.25 + 0.75 * min(1.0, T / 100.0)
            col = self._mix(col, C_BG, intensity * (1.0 - BG_DIM * 0.5))
            cx = (i % cols) * CELL
            cy = (i // cols) * CELL
            if cy >= self.h:
                break
            rect = (cx, cy, CELL - 1, CELL - 1)
            pygame.draw.rect(screen, col, rect)
            # delikatna ramka
            edge = self._mix(col, (0, 0, 0), 0.7)
            pygame.draw.rect(screen, edge, rect, 1)
            if i < n:
                self._map_layout.append((r["id"], r, cx, cy, CELL - 1, CELL - 1))

        # podświetlenie hover
        if self._hover_cell is not None:
            hx, hy = self._hover_cell
            pygame.draw.rect(screen, (255, 255, 255), (hx, hy, CELL - 1, CELL - 1), 2)

    def _blit_text(self, screen, font, text: str, xy: Tuple[int, int],
                   color=C_FG) -> None:
        """Tekst z cieniem — czytelny na mapie T."""
        x, y = xy
        sh = font.render(text, True, TEXT_SHADOW)
        screen.blit(sh, (x + 1, y + 1))
        screen.blit(font.render(text, True, color), (x, y))

    def _draw(self, screen, pygame, font, font_sm, font_b, recs: List[Dict]) -> None:
        # 1) TŁO = mapa termiczna na całe okno
        self._draw_thermal_background(screen, pygame, recs)

        # 2) lekki welon na obszarze promptu (całe okno poza status/input)
        px, py, pw, ph = self._prompt_area()
        veil = pygame.Surface((pw, ph), pygame.SRCALPHA)
        veil.fill((8, 8, 14, int(180 * BG_DIM + 40)))
        screen.blit(veil, (px, py))

        # 3) PROMPT = pełne okno: log + linia komend
        st = self.thermal.stats() if self.thermal else {}
        header = (
            f"Karmazyn Studio  io={st.get('io')}  stage={st.get('stage')}  "
            f"T_c={st.get('T_console')}  T_k={st.get('T_keyboard')}  T_d={st.get('T_display')}"
        )
        self._blit_text(screen, font_b, header[:100], (PAD, PAD), C_ACCENT)

        # log zajmuje prawie całe okno
        log_top = PAD + 28
        log_bottom = self.h - STATUS_H - INPUT_H - 8
        max_lines = max(1, (log_bottom - log_top) // LINE_H)
        log_lines = list(getattr(self.io, "_log", []))
        # scroll: 0 = dół (najnowsze)
        if self._scroll > 0 and len(log_lines) > max_lines:
            end = max(max_lines, len(log_lines) - self._scroll)
            visible = log_lines[max(0, end - max_lines) : end]
        else:
            visible = log_lines[-max_lines:]

        yy = log_top
        for line in visible:
            raw = str(line)
            # zawijanie proste
            max_chars = max(20, (self.w - PAD * 2) // 9)
            while raw:
                chunk = raw[:max_chars]
                raw = raw[max_chars:]
                self._blit_text(screen, font, chunk, (PAD, yy), C_FG)
                yy += LINE_H
                if yy > log_bottom:
                    break
            if yy > log_bottom:
                break

        # linia input — na całą szerokość, nad statusem
        iy = self.h - STATUS_H - INPUT_H
        inp_bg = pygame.Surface((self.w, INPUT_H), pygame.SRCALPHA)
        inp_bg.fill((20, 20, 36, 210))
        screen.blit(inp_bg, (0, iy))
        pygame.draw.line(screen, C_ACCENT, (0, iy), (self.w, iy), 1)
        prompt = f"karmazyn> {self._input}█"
        self._blit_text(screen, font, prompt[: max(20, self.w // 9)], (PAD, iy + 8), C_FG)

        # status
        st_bg = pygame.Surface((self.w, STATUS_H), pygame.SRCALPHA)
        st_bg.fill((12, 12, 20, 220))
        screen.blit(st_bg, (0, self.h - STATUS_H))
        try:
            stats = self.store.stats()
            sline = (
                f"{self._status}  |  atoms={stats.get('total', '?')}  "
                f"reaped={stats.get('reaped', '?')}  |  "
                f"Enter=feed  F5=settle  Esc=exit  hover mapa=heat  tło=matryca T"
            )
        except Exception:
            sline = str(self._status)
        self._blit_text(screen, font_sm, sline[:130], (PAD, self.h - STATUS_H + 4), C_DIM)


def run_studio(store=None, shell=None, thermal=None, **kw) -> int:
    """Uruchom studio; jeśli brak store/shell — boot() Stage 1."""
    if store is None or shell is None:
        import karmazyn_boot as boot

        # SdlIo przed bootem — resolve przez env
        os.environ.setdefault("KARMAZYN_IO", "stdio")  # boot zbuduje stdio, podmienimy
        store, shell = boot.boot(verbose_events=False)
        thermal = shell.thermal
        if thermal is None:
            raise RuntimeError("brak ThermalSurface — Stage 1 wymagany (bez KARMAZYN_IO_OPTIONAL)")
    if thermal is None:
        thermal = getattr(shell, "thermal", None)
    studio = KarmazynStudio(store, shell, thermal, **kw)
    return studio.run()
