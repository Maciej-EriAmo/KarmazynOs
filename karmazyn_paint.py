"""
karmazyn_paint.py — Płótno na atomach KarmazynOS v1.0
======================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Płótno twórcze gdzie KAŻDY ślad to atom. To nie metafora —
pociągnięcie pędzla tworzy atom w phi-space:
  pozycja (x,y) → atom.metadata
  jasność       → atom.T  (świeże = gorące = jasne)
  kolor         → atom.metadata

Płótno jest immediate-mode jak cała warstwa graficzna: UI to czysta
funkcja stanu czytana co klatkę. draw_canvas() czyta atomy z phi i
rysuje każdy z jasnością = T. Nie trzyma osobnego bufora pikseli —
obrazem JEST zbiór atomów.

Wygasanie wbudowane w fizykę systemu:
  phi.tick() studzi atomy (decay 0.92). Stare ślady blakną i znikają
  (Vacuum Decay gdy T < 2) — płótno samo się czyści w czasie, jak
  ślad żółwia LOGO albo pamięć która zapomina. Świeże pociągnięcia
  jaśnieją, dawne gasną. To nie efekt dorobiony — to ta sama
  termodynamika co reszta KarmazynOS, widziana jako światło.

Sterowanie (komendy w terminalu, wzorzec LOGO — działa bez myszy):
  PAINT DOT x y [kolor]            — punkt świetlny
  PAINT LINE x0 y0 x1 y1 [kolor]   — linia punktów
  PAINT SPRAY x y [promień] [n]    — rozpylenie n punktów
  PAINT CLEAR                       — wygaś wszystko teraz
  PAINT FADE                        — jeden krok wygaszania (phi.tick)
  PAINT SHOW                        — render ASCII (gdy brak okna)

Kolory nazwane: red green blue white amber cyan magenta.
Współrzędne 0..100 (znormalizowane do panelu), środek = 50,50.

Odporność na brak pygame: gdy nie ma okna, PAINT SHOW rysuje ASCII.
"""

import math
import sys
from typing import Dict, List, Optional, Tuple

from karmazyn_phi import PhiSpace


# ─── Stałe ────────────────────────────────────────────────────────────────────

T_FRESH   = 95.0     # temperatura świeżego śladu (jasny)
PAINT_S   = "paint"  # S atomów płótna
COORD_MAX = 100.0    # przestrzeń współrzędnych płótna (0..100)

_COLORS: Dict[str, Tuple[int, int, int]] = {
    "red":     (255, 60,  60),
    "green":   (80,  220, 80),
    "blue":    (80,  140, 255),
    "white":   (240, 240, 240),
    "amber":   (255, 180, 40),
    "cyan":    (60,  220, 220),
    "magenta": (220, 80,  220),
}

_counter = 0
def _uid() -> str:
    global _counter
    _counter += 1
    return f"paint_{_counter}"


def _resolve_color(name: Optional[str]) -> Tuple[int, int, int]:
    if not name:
        return _COLORS["amber"]
    return _COLORS.get(name.lower(), _COLORS["amber"])


# ─── CanvasState — płótno jako zbiór atomów ──────────────────────────────────

class CanvasState:
    """
    Płótno na atomach. NIE trzyma pikseli — obrazem jest zbiór atomów
    w phi-space o S=="paint". Każda metoda tworzy atomy; render czyta je.
    """

    def __init__(self, phi: PhiSpace):
        self.phi = phi

    # ── Tworzenie śladów (każdy = atom) ──────────────────────────────────────

    def dot(self, x: float, y: float,
            color: Tuple[int, int, int] = None,
            T: float = T_FRESH) -> str:
        """Jeden punkt świetlny = jeden atom. Pozycja w metadata, jasność = T."""
        if color is None:
            color = _COLORS["amber"]
        aid = _uid()
        atom = self.phi.create_atom(aid, S=PAINT_S, E="", T=T)
        atom.metadata["x"] = float(x)
        atom.metadata["y"] = float(y)
        atom.metadata["r"] = int(color[0])
        atom.metadata["g"] = int(color[1])
        atom.metadata["b"] = int(color[2])
        return aid

    def line(self, x0: float, y0: float, x1: float, y1: float,
             color: Tuple[int, int, int] = None) -> List[str]:
        """Linia jako ciąg atomów-punktów (interpolacja)."""
        dx, dy = x1 - x0, y1 - y0
        dist = math.hypot(dx, dy)
        steps = max(1, int(dist))
        ids = []
        for i in range(steps + 1):
            t = i / steps
            ids.append(self.dot(x0 + dx * t, y0 + dy * t, color))
        return ids

    def spray(self, x: float, y: float, radius: float = 6.0,
              n: int = 12, color: Tuple[int, int, int] = None) -> List[str]:
        """Rozpylenie — n punktów w okręgu, różne T (nierówna jasność)."""
        import random
        ids = []
        for _ in range(n):
            ang = random.uniform(0, 2 * math.pi)
            rr  = random.uniform(0, radius)
            px  = x + rr * math.cos(ang)
            py  = y + rr * math.sin(ang)
            T   = random.uniform(T_FRESH * 0.6, T_FRESH)
            ids.append(self.dot(px, py, color, T=T))
        return ids

    def clear(self) -> int:
        """Wygaś wszystko teraz — zabij atomy płótna (→ Vacuum Decay)."""
        n = 0
        for atom in list(self.phi.matrix.atoms()):
            if atom.S == PAINT_S:
                self.phi.delete_atom(atom.id)
                n += 1
        return n

    def fade(self) -> dict:
        """Jeden krok wygaszania — to po prostu phi.tick()."""
        return self.phi.tick()

    # ── Odczyt śladów (do renderu) ───────────────────────────────────────────

    def marks(self) -> List[dict]:
        """
        Wszystkie żywe ślady jako dane do rysowania. Peek — nie ogrzewa
        (render nie powinien sztucznie podtrzymywać jasności).
        """
        out = []
        for atom in self.phi.matrix.atoms():
            if atom.S != PAINT_S:
                continue
            m = atom.metadata
            out.append({
                "x": m.get("x", 50.0),
                "y": m.get("y", 50.0),
                "r": m.get("r", 255),
                "g": m.get("g", 180),
                "b": m.get("b", 40),
                "T": atom.T,
            })
        return out

    def count(self) -> int:
        return sum(1 for a in self.phi.matrix.atoms() if a.S == PAINT_S)


# ─── draw_canvas — czysta funkcja rysująca (jak draw_logo) ───────────────────

def draw_canvas(ctx, canvas: CanvasState) -> None:
    """
    Rysuje płótno: każdy atom jako punkt świetlny z jasnością = T.
    ctx to DrawCtx z karmazyn_display. Wymaga pygame do rysowania kół;
    bez niego rysuje tylko ramkę i licznik (tryb informacyjny).
    """
    r = ctx.rect
    ctx.clear()
    try:
        from karmazyn_display import C_ACCENT, C_STATUS
    except Exception:
        C_ACCENT = (180, 60, 60); C_STATUS = (160, 160, 180)
    ctx.box(r, outline=C_ACCENT)

    marks = canvas.marks()

    try:
        import pygame
        for m in marks:
            # współrzędne 0..100 → piksele panelu
            px = r.x + int(m["x"] / COORD_MAX * r.w)
            py = r.y + int(m["y"] / COORD_MAX * r.h)
            # jasność = T/100; kolor skalowany jasnością
            bright = max(0.0, min(1.0, m["T"] / 100.0))
            color = (int(m["r"] * bright),
                     int(m["g"] * bright),
                     int(m["b"] * bright))
            # promień rośnie z jasnością — świeże ślady grubsze
            radius = max(1, int(2 + bright * 4))
            if px - radius >= r.x and px + radius < r.right and \
               py - radius >= r.y and py + radius < r.bottom:
                pygame.draw.circle(ctx.surface, color, (px, py), radius)
        ctx.text(f"płótno · {len(marks)} śladów", C_STATUS,
                 x=r.x + 8, y=r.bottom - 24)
    except Exception:
        ctx.text(f"płótno · {len(marks)} śladów", C_STATUS, x=r.x + 8, y=r.y + 8)
        ctx.text("(podgląd wymaga SDL/pygame)", C_STATUS, x=r.x + 8, y=r.y + 32)


# ─── Render ASCII (gdy brak okna) — jak LogoInterp.render ─────────────────────

def render_ascii(canvas: CanvasState, w: int = 60, h: int = 24) -> str:
    """Render płótna jako ASCII: gęstość znaku = jasność (T)."""
    grid = [[" "] * w for _ in range(h)]
    ramp = " .:-=+*#%@"   # od ciemnego do jasnego
    for m in canvas.marks():
        gx = int(m["x"] / COORD_MAX * (w - 1))
        gy = int(m["y"] / COORD_MAX * (h - 1))
        if 0 <= gx < w and 0 <= gy < h:
            level = int(max(0.0, min(1.0, m["T"] / 100.0)) * (len(ramp) - 1))
            ch = ramp[level]
            # jaśniejszy ślad wygrywa
            cur = grid[gy][gx]
            if ramp.index(ch) >= (ramp.index(cur) if cur in ramp else 0):
                grid[gy][gx] = ch
    border = "+" + "-" * w + "+"
    rows = [border] + ["|" + "".join(r) + "|" for r in grid] + [border]
    return "\n".join(rows)


# ─── KarmazynPaint — powłoka płótna (wzorzec LogoShell) ──────────────────────

class KarmazynPaint:
    """Powłoka płótna. Zajmuje lewy panel gdy jest okno (jak LOGO)."""

    def __init__(self, phi: PhiSpace, display=None):
        self.phi      = phi
        self.canvas   = CanvasState(phi)
        self._display = display
        self._claimed = False
        self._window  = None    # okno w menedżerze (tryb okienkowy)
        # podepnij phi do display (phi-map pokaże też atomy płótna)
        if display is not None and hasattr(display, "bind_phi"):
            try:
                if getattr(display, "renderer", None) and display.renderer.phi_ref is None:
                    display.bind_phi(phi)
            except Exception:
                pass

    def _has_window(self) -> bool:
        d = self._display
        return (d is not None and getattr(d, "available", False)
                and getattr(d, "renderer", None) is not None)

    def _claim(self) -> None:
        if self._claimed:
            return
        def _draw_panel(ctx):
            draw_canvas(ctx, self.canvas)
        # Tryb okienkowy: jeśli pulpit (WM) aktywny — otwórz OKNO, nie zabieraj
        # całego panelu. Inaczej (brak pulpitu) — zachowanie jak LOGO.
        try:
            import karmazyn_wm
            wm = karmazyn_wm.get_active()
        except Exception:
            wm = None
        if wm is not None:
            if self._window is None or self._window not in wm.windows:
                self._window = wm.open("Płótno", _draw_panel, w=480, h=420)
            self._claimed = True
            return
        if self._has_window():
            self._display.renderer.claim_left(_draw_panel, "PŁÓTNO")
            self._claimed = True

    def cmd(self, args: List[str]) -> str:
        if not args:
            return ("PAINT DOT x y [kolor] | LINE x0 y0 x1 y1 [kolor] | "
                    "SPRAY x y [r] [n] | CLEAR | FADE | SHOW")
        sub = args[0].upper()

        try:
            if sub == "DOT":
                x, y = float(args[1]), float(args[2])
                col = _resolve_color(args[3] if len(args) > 3 else None)
                self._claim()
                self.canvas.dot(x, y, col)
                return self._after(f"punkt ({x:.0f},{y:.0f})")

            if sub == "LINE":
                x0, y0, x1, y1 = (float(args[1]), float(args[2]),
                                  float(args[3]), float(args[4]))
                col = _resolve_color(args[5] if len(args) > 5 else None)
                self._claim()
                ids = self.canvas.line(x0, y0, x1, y1, col)
                return self._after(f"linia {len(ids)} punktów")

            if sub == "SPRAY":
                x, y = float(args[1]), float(args[2])
                radius = float(args[3]) if len(args) > 3 else 6.0
                n      = int(args[4]) if len(args) > 4 else 12
                self._claim()
                ids = self.canvas.spray(x, y, radius, n)
                return self._after(f"rozpylono {len(ids)}")

            if sub == "CLEAR":
                n = self.canvas.clear()
                return f"wygaszono {n} śladów"

            if sub == "FADE":
                st = self.canvas.fade()
                return f"wygaszanie: zostało {self.canvas.count()} śladów (GC {st['collected']})"

            if sub == "SHOW":
                if self._has_window():
                    self._claim()
                    return f"płótno w oknie ({self.canvas.count()} śladów)"
                return render_ascii(self.canvas)

        except (IndexError, ValueError):
            return f"Zła składnia. PAINT {sub} — sprawdź argumenty."

        return ("Opcje: DOT, LINE, SPRAY, CLEAR, FADE, SHOW. "
                "Kolory: " + ", ".join(_COLORS))

    def _after(self, what: str) -> str:
        if self._has_window():
            return f"{what} — w oknie graficznym ({self.canvas.count()} śladów)"
        return f"{what} ({self.canvas.count()} śladów). PAINT SHOW aby zobaczyć."


# ─── Komenda powłoki (wzorzec cmd_logo) ──────────────────────────────────────

_PAINT: Optional[KarmazynPaint] = None


def cmd_paint(args: List[str], phi=None, display=None) -> str:
    """
    PAINT ...  — płótno na atomach. Współdzieli phi z systemem.
    Bez phi tworzy własną przestrzeń (samodzielny tryb).
    """
    global _PAINT
    if _PAINT is None or (phi is not None and _PAINT.phi is not phi):
        _PAINT = KarmazynPaint(phi if phi is not None else PhiSpace(), display=display)
    elif display is not None and _PAINT._display is None:
        _PAINT._display = display
    return _PAINT.cmd(args)


if __name__ == "__main__":
    phi = PhiSpace()
    paint = KarmazynPaint(phi)
    if len(sys.argv) > 1:
        print(paint.cmd(sys.argv[1:]))
    else:
        # mały pokaz w ASCII
        paint.cmd(["LINE", "10", "10", "90", "90", "amber"])
        paint.cmd(["LINE", "90", "10", "10", "90", "cyan"])
        paint.cmd(["SPRAY", "50", "50", "10", "30"])
        print(paint.cmd(["SHOW"]))