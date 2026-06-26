"""
karmazyn_view.py — Program graficzny KarmazynOS v1.0
=====================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Wyświetla obrazy z bąbli, wewnątrz KarmazynOS. Konsument istniejącej
warstwy graficznej (karmazyn_display.py) — używa tego samego wzorca
co LOGO: claim_left(draw_fn, etykieta) na lewym panelu SDL.

Filozofia (jak każda przeglądarka obrazów): otwórz, zobacz. Cała
mechanika przechowywania pod maską. Obraz to dokument kind=="image".

Odporność na brak (jak odtwarzacz):
  Jest SDL/pygame + okno → dekoduje i rysuje na panelu.
  Brak pygame / brak okna → tryb informacyjny: wymiary (parsowane
  z nagłówka czystym Pythonem) i rozmiar. Nie pada.

Integracja z display (wzorzec LOGO):
  viewer = ImageViewer(workspace, display)
  viewer.show("obrazek")          # claim_left + dekodowanie
  viewer.close()                  # release_left

Wymiary bez pygame:
  image_dimensions(bytes) → (w, h) z nagłówków PNG/GIF/BMP/JPEG/WEBP.
  Używane w trybie info i do skalowania przy rysowaniu.
"""

import struct
import sys
from typing import List, Optional, Tuple

from karmazyn_app import Workspace, Item


# ═══════════════════════════════════════════════════════════════════════════════
# Wymiary obrazu z nagłówka — czysty Python, bez pygame
# ═══════════════════════════════════════════════════════════════════════════════

def image_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    """
    Wyciąga (szerokość, wysokość) z nagłówka obrazu bez dekodowania całości.
    Obsługuje PNG, GIF, BMP, JPEG, WEBP. Zwraca None gdy nie rozpozna.
    """
    if not data or len(data) < 10:
        return None

    # PNG: IHDR zaraz po sygnaturze (8B sig + 4B len + 4B "IHDR" + 4B W + 4B H)
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        try:
            w, h = struct.unpack('>II', data[16:24])
            return (w, h)
        except struct.error:
            return None

    # GIF: bajty 6-10 to W,H little-endian uint16
    if data[:6] in (b'GIF87a', b'GIF89a'):
        try:
            w, h = struct.unpack('<HH', data[6:10])
            return (w, h)
        except struct.error:
            return None

    # BMP: offset 18 → W,H int32 little-endian
    if data[:2] == b'BM':
        try:
            w, h = struct.unpack('<ii', data[18:26])
            return (abs(w), abs(h))
        except struct.error:
            return None

    # WEBP (VP8/VP8L/VP8X w kontenerze RIFF)
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        try:
            fmt = data[12:16]
            if fmt == b'VP8 ':
                w = struct.unpack('<H', data[26:28])[0] & 0x3FFF
                h = struct.unpack('<H', data[28:30])[0] & 0x3FFF
                return (w, h)
            if fmt == b'VP8L':
                b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
                w = ((b1 & 0x3F) << 8 | b0) + 1
                h = ((b3 & 0x0F) << 10 | b2 << 2 | (b1 & 0xC0) >> 6) + 1
                return (w, h)
            if fmt == b'VP8X':
                w = (data[24] | data[25] << 8 | data[26] << 16) + 1
                h = (data[27] | data[28] << 8 | data[29] << 16) + 1
                return (w, h)
        except (struct.error, IndexError):
            return None

    # JPEG: skanuj markery SOF0..SOF15 (pomijając SOF4/8/12)
    if data[:3] == b'\xff\xd8\xff':
        i = 2
        n = len(data)
        try:
            while i < n - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                # SOF markery zawierają wymiary
                if marker in (0xC0, 0xC1, 0xC2, 0xC3,
                              0xC5, 0xC6, 0xC7,
                              0xC9, 0xCA, 0xCB,
                              0xCD, 0xCE, 0xCF):
                    h = struct.unpack('>H', data[i + 5:i + 7])[0]
                    w = struct.unpack('>H', data[i + 7:i + 9])[0]
                    return (w, h)
                # przeskocz segment wg jego długości
                seg_len = struct.unpack('>H', data[i + 2:i + 4])[0]
                i += 2 + seg_len
        except (struct.error, IndexError):
            return None

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ImageState — model obrazu (analogiczny do LogoState z display)
# ═══════════════════════════════════════════════════════════════════════════════

class ImageState:
    """
    Stan wyświetlanego obrazu. Trzyma surowe bajty i zdekodowaną
    powierzchnię pygame (leniwie). Rysowany przez draw_image().
    Bezpieczny bez pygame — surface zostaje None.
    """

    def __init__(self):
        self.name:    str = ""
        self.data:    bytes = b""
        self.dims:    Optional[Tuple[int, int]] = None
        self._surface = None        # pygame.Surface lub None
        self._decoded = False

    def set_image(self, name: str, data: bytes) -> None:
        self.name     = name
        self.data     = data
        self.dims     = image_dimensions(data)
        self._surface = None
        self._decoded = False

    def surface(self):
        """Zwraca pygame.Surface lub None (dekodowanie leniwe, raz)."""
        if self._decoded:
            return self._surface
        self._decoded = True
        try:
            import io, pygame
            self._surface = pygame.image.load(io.BytesIO(self.data))
        except Exception:
            self._surface = None
        return self._surface


# ═══════════════════════════════════════════════════════════════════════════════
# draw_image — czysta funkcja rysująca (jak draw_logo)
# ═══════════════════════════════════════════════════════════════════════════════

def draw_image(ctx, state: ImageState) -> None:
    """
    Rysuje obraz na panelu (ctx.rect). Skaluje z zachowaniem proporcji.
    Gdy brak pygame surface → rysuje info (nazwa, wymiary, rozmiar).
    ctx to DrawCtx z karmazyn_display.
    """
    r = ctx.rect
    ctx.clear()                       # tło panelu
    try:
        from karmazyn_display import C_ACCENT, C_FG, C_STATUS
    except Exception:
        C_ACCENT = (180, 60, 60); C_FG = (255, 255, 255); C_STATUS = (160, 160, 180)
    ctx.box(r, outline=C_ACCENT)

    surf = state.surface()
    if surf is None:
        # Tryb informacyjny — brak dekodera lub błąd
        ctx.text(f"obraz: {state.name}", C_ACCENT, x=r.x + 8, y=r.y + 8)
        if state.dims:
            ctx.text(f"{state.dims[0]} × {state.dims[1]} px",
                     C_FG, x=r.x + 8, y=r.y + 34)
        ctx.text(f"{len(state.data)} B", C_STATUS, x=r.x + 8, y=r.y + 58)
        ctx.text("(podgląd wymaga SDL/pygame)", C_STATUS, x=r.x + 8, y=r.y + 84)
        return

    try:
        import pygame
        iw, ih = surf.get_size()
        # skala "fit" z marginesem
        avail_w = r.w - 16
        avail_h = r.h - 40
        scale = min(avail_w / iw, avail_h / ih, 4.0)  # nie powiększaj > 4x
        sw, sh = max(1, int(iw * scale)), max(1, int(ih * scale))
        scaled = pygame.transform.smoothscale(surf, (sw, sh)) \
            if scale < 1.0 else pygame.transform.scale(surf, (sw, sh))
        # wyśrodkuj
        ox = r.x + (r.w - sw) // 2
        oy = r.y + 8 + (avail_h - sh) // 2
        ctx.surface.blit(scaled, (ox, oy))
        # podpis
        ctx.text(f"{state.name}   {iw}×{ih}", C_STATUS,
                 x=r.x + 8, y=r.bottom - 24)
    except Exception:
        ctx.text(f"obraz: {state.name}", C_ACCENT, x=r.x + 8, y=r.y + 8)


# ═══════════════════════════════════════════════════════════════════════════════
# ImageViewer — ładuje z Workspace, zarządza panelem
# ═══════════════════════════════════════════════════════════════════════════════

class ImageViewer:
    """
    Przeglądarka obrazów na warstwie Workspace + KarmazynDisplay.
    Wzorzec LOGO: claim_left(draw_fn) gdy jest okno SDL.
    """

    def __init__(self, workspace: Workspace, display=None):
        self.ws      = workspace
        self.display = display
        self.state   = ImageState()
        self._claimed = False
        self._window  = None

    def library(self) -> List[dict]:
        """Lista obrazów w workspace."""
        return [d for d in self.ws.list() if d["kind"] == "image"]

    def load(self, name: str) -> Optional[Item]:
        item = self.ws.open(name)
        if item is None:
            return None
        if not item.is_image:
            return None
        self.state.set_image(name, item.data)
        return item

    def _has_window(self) -> bool:
        d = self.display
        return (d is not None and getattr(d, "available", False)
                and getattr(d, "renderer", None) is not None)

    def show(self, name: str) -> str:
        item = self.load(name)
        if item is None:
            it = self.ws.open(name)
            if it is None:
                return f"Nie ma '{name}'"
            return f"'{name}' to nie jest obraz ({it.kind})"

        dims = self.state.dims
        dim_s = f"{dims[0]}×{dims[1]}px" if dims else "wymiary nieznane"

        def _draw_panel(ctx):
            draw_image(ctx, self.state)

        # Tryb okienkowy: pulpit aktywny → otwórz OKNO; inaczej zajmij panel.
        try:
            import karmazyn_wm
            wm = karmazyn_wm.get_active()
        except Exception:
            wm = None
        if wm is not None:
            if self._window is None or self._window not in wm.windows:
                self._window = wm.open(f"Obraz: {name}", _draw_panel, w=500, h=440)
            else:
                self._window.title = f"Obraz: {name}"
                self._window.draw_fn = _draw_panel
                wm.focus(self._window)
            self._claimed = True
            return f"▦ {name}  {dim_s} — w oknie"
        if self._has_window():
            self.display.renderer.claim_left(_draw_panel, f"OBRAZ: {name}")
            self._claimed = True
            return f"▦ {name}  {dim_s} — w oknie graficznym"
        return (f"▦ {name}  {dim_s}  {item.size}B "
                f"(podgląd wymaga okna graficznego/SDL)")

    def close(self) -> str:
        try:
            import karmazyn_wm
            wm = karmazyn_wm.get_active()
        except Exception:
            wm = None
        if wm is not None and self._window is not None and self._window in wm.windows:
            wm.close(self._window)
            self._window = None
            self._claimed = False
            return "Zamknięto podgląd."
        if self._claimed and self._has_window():
            self.display.renderer.release_left()
            self._claimed = False
            return "Zamknięto podgląd."
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# Komenda powłoki (wzorzec cmd_logo)
# ═══════════════════════════════════════════════════════════════════════════════

_WS: Optional[Workspace] = None
_VIEWER: Optional[ImageViewer] = None


def cmd_view(args: List[str], phi=None, display=None) -> str:
    """
    VIEW            — lista obrazów
    VIEW <nazwa>    — pokaż obraz (w oknie SDL lub info gdy brak)
    VIEW CLOSE      — zamknij podgląd, zwolnij panel
    """
    global _WS, _VIEWER
    if _WS is None or (phi is not None and _WS.phi is not phi):
        _WS = Workspace(phi=phi)
        _VIEWER = ImageViewer(_WS, display=display)
    elif display is not None and _VIEWER.display is None:
        _VIEWER.display = display

    if not args:
        lib = _VIEWER.library()
        if not lib:
            return "Brak obrazów. Zapisz plik obrazu jako dokument."
        return "Obrazy:\n" + "\n".join(
            f"  {d['name']:24} {d['size']:>8} B" for d in lib)

    if args[0].upper() == "CLOSE":
        return _VIEWER.close() or "Brak otwartego podglądu."

    return _VIEWER.show(args[0])


if __name__ == "__main__":
    ws = Workspace()
    viewer = ImageViewer(ws)
    if len(sys.argv) > 1:
        print(viewer.show(sys.argv[1]))
    else:
        lib = viewer.library()
        print(f"Obrazy: {[d['name'] for d in lib] or 'brak'}")