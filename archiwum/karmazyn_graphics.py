#!/usr/bin/env python3
"""
karmazyn_graphics.py -- KarmazynOS Graphics Engine v1.0
========================================================
Maciej Mazur, Warszawa 2026

Warstwa graficzna KarmazynOS: viewer, archiwizer, przetwarzanie.
Pelna integracja z phi-space, BubbleVFS i CAS.

Filozofia:
  Obraz = atom phi-space z blobem w CAS.
  Kolekcja = babel z atomami-obrazami.
  Temperatura atomu = log(rozmiar) * dostep * entropia_wizualna.
  Oglądanie obrazu podnosi jego temperature -- aktywny wizualnie jest gorący.

Architektura:
  ImageMeta      -- metadane obrazu (EXIF, histogram, dominujące kolory)
  AsciiRenderer  -- podgląd w terminalu (bloki Unicode, 2x rozdzielczość)
  GraphicsEngine -- operacje Pillow (thumb, resize, convert, crop, info)
  ImageVault     -- archiwum bąblowe (bulk import, gallery, dedup CAS)

Komendy shell:
  BVIEW    <atom|plik> [--ascii|--sdl]  -- podgląd obrazu
  BTHUMB   <atom|plik> [rozmiar]        -- miniatura -> CAS
  BRESIZE  <atom|plik> <WxH>            -- zmień rozmiar -> nowy atom
  BCONVERT <atom|plik> <format>         -- konwertuj format -> nowy atom
  BINFO    <atom|plik>                  -- metadane + histogram
  BGALLERY [babel]                      -- przeglądarka kolekcji (curses)
  BARCHIVE <katalog> [babel] [--thumb]  -- zaimportuj katalog do bąbla
  BTHERMO  [babel]                      -- termografia phi-space -> PNG

Zależności:
  pip install Pillow           -- wymagane (przetwarzanie obrazów)
  pip install pillow-avif-plugin  -- opcjonalne (AVIF)
  pygame                       -- opcjonalne (SDL viewer)

Termux:
  pkg install python
  pip install Pillow
  Viewer ASCII działa wszędzie bez SDL.
"""

import hashlib
import json
import math
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


# ── Importy opcjonalne ────────────────────────────────────────────────────────

try:
    from PIL import Image, ImageDraw, ImageFont, ImageStat, ExifTags
    from PIL import ImageFilter, ImageEnhance, ImageOps
    _PIL_OK = True
except ImportError:
    _PIL_OK = False
    Image = None

try:
    import curses as _curses
    _CURSES_OK = True
except ImportError:
    _CURSES_OK = False

try:
    import pygame as _pygame
    _SDL_OK = True
except ImportError:
    _SDL_OK = False

# KarmazynOS
try:
    from karmazyn_cas import (BLOB_STORE, BLOB_HEAT_CACHE,
                               make_blob_ref, extract_hash, is_blob_ref)
    _CAS_OK = True
except ImportError:
    _CAS_OK = False
    BLOB_STORE = BLOB_HEAT_CACHE = None
    def make_blob_ref(h): return f"blob:{h}"
    def extract_hash(e): return e[5:] if e.startswith("blob:") else None
    def is_blob_ref(e): return e.startswith("blob:")

try:
    from karmazyn_syslog import SystemLog
    REGISTRY = SystemLog()
except ImportError:
    class _Log:
        def log(self, *a, **kw): pass
        def register(self, *a, **kw): pass
    REGISTRY = _Log()


# ── Stałe ─────────────────────────────────────────────────────────────────────

THUMB_SIZE      = (256, 256)
PREVIEW_SIZE    = (800, 600)
ASCII_WIDTH     = 80
ASCII_HEIGHT    = 40
SUPPORTED_EXTS  = {".jpg", ".jpeg", ".png", ".gif", ".bmp",
                   ".webp", ".tiff", ".tif", ".ico", ".avif", ".heic"}
TEMP_BASE       = 55.0    # bazowa temperatura atomu obrazu
ENTROPY_WEIGHT  = 0.3     # waga entropii wizualnej w obliczeniu T


# ── Bloki Unicode do renderingu ASCII ────────────────────────────────────────

# Polówki bloków -- 2x rozdzielczość pionowa
HALF_BLOCKS = " ▀▄█"
# Skala jasności
DENSITY     = " .:-=+*#%@"
DENSITY_REV = "@%#*+=-:. "


# ─────────────────────────────────────────────────────────────────────────────
# ImageMeta -- metadane obrazu
# ─────────────────────────────────────────────────────────────────────────────

class ImageMeta:
    """Metadane obrazu: wymiary, format, EXIF, histogram, dominujące kolory."""

    __slots__ = ("path", "width", "height", "mode", "format",
                 "file_size", "exif", "dominant_colors",
                 "mean_brightness", "entropy", "has_alpha",
                 "atom_id", "blob_hash", "thumb_hash")

    def __init__(self):
        self.path            = ""
        self.width           = 0
        self.height          = 0
        self.mode            = ""
        self.format          = ""
        self.file_size       = 0
        self.exif            = {}
        self.dominant_colors = []   # [(R,G,B, count), ...]
        self.mean_brightness = 0.0
        self.entropy         = 0.0
        self.has_alpha       = False
        self.atom_id         = ""
        self.blob_hash       = ""
        self.thumb_hash      = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}

    @classmethod
    def from_dict(cls, d: dict) -> "ImageMeta":
        m = cls()
        for k, v in d.items():
            if k in cls.__slots__:
                setattr(m, k, v)
        return m

    def T_value(self) -> float:
        """
        Temperatura atomu obrazu.
        Mniejszy plik + wyższa entropia wizualna = gorętszy.
        Wzór: TEMP_BASE - log10(KB) * 5 + entropy * ENTROPY_WEIGHT
        """
        kb     = max(1, self.file_size / 1024)
        size_t = max(0.0, TEMP_BASE - math.log10(kb) * 5)
        ent_t  = self.entropy * ENTROPY_WEIGHT
        return round(min(95.0, size_t + ent_t), 1)

    def summary(self) -> str:
        return (f"{self.width}x{self.height} {self.format} {self.mode} "
                f"{_fmt_size(self.file_size)} "
                f"entropy={self.entropy:.2f} T={self.T_value():.1f}")


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024: return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# ─────────────────────────────────────────────────────────────────────────────
# GraphicsEngine -- operacje Pillow
# ─────────────────────────────────────────────────────────────────────────────

class GraphicsEngine:
    """
    Silnik przetwarzania obrazów oparty na Pillow.
    Wszystkie operacje zwracają nowe obrazy lub metadane.
    Nie modyfikuje oryginałów.
    """

    def __init__(self):
        if not _PIL_OK:
            raise ImportError(
                "Pillow nie zainstalowany. Uruchom: pip install Pillow")

    # ── Ładowanie ─────────────────────────────────────────────────────────────

    def load(self, source) -> Image.Image:
        """
        Załaduj obraz ze ścieżki, bytes lub hasha CAS.
        source: str (ścieżka lub blob:hash), bytes, lub PIL.Image
        """
        if isinstance(source, Image.Image):
            return source
        if isinstance(source, bytes):
            from io import BytesIO
            _i = Image.open(BytesIO(source)); _i.load(); return _i
        if isinstance(source, str):
            if is_blob_ref(source) and _CAS_OK:
                data = BLOB_STORE.get_bytes(extract_hash(source))
                if data is None:
                    raise FileNotFoundError(f"Blob nie istnieje: {source}")
                from io import BytesIO
                _i = Image.open(BytesIO(data)); _i.load(); return _i
            _i = Image.open(source); _i.load(); return _i
        raise TypeError(f"Nieobsługiwany typ źródła: {type(source)}")

    # ── Metadane ──────────────────────────────────────────────────────────────

    def meta(self, source) -> ImageMeta:
        """Wyciągnij pełne metadane obrazu."""
        img  = self.load(source)
        m    = ImageMeta()

        m.width   = img.width
        m.height  = img.height
        m.mode    = img.mode
        m.format  = img.format or ""
        m.has_alpha = img.mode in ("RGBA", "LA", "PA")

        if isinstance(source, str) and not is_blob_ref(source):
            m.path      = os.path.abspath(source)
            m.file_size = os.path.getsize(source) if os.path.exists(source) else 0

        # EXIF
        try:
            raw_exif = img._getexif() if hasattr(img, "_getexif") else None
            if raw_exif:
                m.exif = {
                    ExifTags.TAGS.get(k, str(k)): str(v)[:80]
                    for k, v in raw_exif.items()
                    if k in ExifTags.TAGS
                }
        except Exception:
            pass

        # Statystyki jasności i entropia wizualna
        try:
            rgb = img.convert("RGB").resize((64, 64), Image.LANCZOS)
            stat         = ImageStat.Stat(rgb)
            m.mean_brightness = sum(stat.mean) / 3
            # Entropia = różnorodność kolorów (uproszczona)
            hist  = rgb.histogram()
            total = sum(hist)
            if total > 0:
                probs     = [c / total for c in hist if c > 0]
                m.entropy = min(10.0, -sum(p * math.log2(p) for p in probs) / 8)
        except Exception:
            pass

        # Dominujące kolory (k-means uproszczony przez kwantyzację)
        try:
            small   = img.convert("RGB").resize((50, 50), Image.LANCZOS)
            palette = small.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
            rgb_pal = palette.convert("RGB")
            colors  = {}
            pixels = list(rgb_pal.getdata()) if hasattr(rgb_pal,"getdata") else list(rgb_pal.get_flattened_data())
            for px in pixels:
                r = (px[0] // 32) * 32
                g = (px[1] // 32) * 32
                b = (px[2] // 32) * 32
                colors[(r, g, b)] = colors.get((r, g, b), 0) + 1
            m.dominant_colors = sorted(
                [(r, g, b, c) for (r, g, b), c in colors.items()],
                key=lambda x: -x[3])[:5]
        except Exception:
            pass

        return m

    # ── Transformacje ─────────────────────────────────────────────────────────

    def thumbnail(self, source,
                  size: Tuple[int, int] = THUMB_SIZE) -> bytes:
        """Wygeneruj miniaturę. Zwraca bytes PNG."""
        img   = self.load(source)
        thumb = img.copy()
        thumb.thumbnail(size, Image.LANCZOS)
        # Konwertuj do RGB jeśli potrzeba (RGBA -> białe tlo)
        if thumb.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", thumb.size, (255, 255, 255))
            if thumb.mode == "P":
                thumb = thumb.convert("RGBA")
            bg.paste(thumb, mask=thumb.split()[-1] if "A" in thumb.mode else None)
            thumb = bg
        elif thumb.mode != "RGB":
            thumb = thumb.convert("RGB")
        from io import BytesIO
        buf = BytesIO()
        thumb.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()

    def resize(self, source,
               width: int, height: int,
               keep_ratio: bool = True) -> bytes:
        """Zmień rozmiar obrazu. Zwraca bytes w oryginalnym formacie."""
        img = self.load(source)
        if keep_ratio:
            img.thumbnail((width, height), Image.LANCZOS)
        else:
            img = img.resize((width, height), Image.LANCZOS)
        from io import BytesIO
        buf = BytesIO()
        fmt = img.format or "PNG"
        img.save(buf, format=fmt)
        return buf.getvalue()

    def convert(self, source, target_format: str) -> bytes:
        """Konwertuj format obrazu (JPEG, PNG, WEBP, BMP...)."""
        img  = self.load(source)
        fmt  = target_format.upper().replace("JPG", "JPEG")
        # JPEG wymaga RGB
        if fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            img = bg
        from io import BytesIO
        buf = BytesIO()
        kwargs = {"quality": 90} if fmt == "JPEG" else {}
        img.save(buf, format=fmt, **kwargs)
        return buf.getvalue()

    def crop(self, source,
             left: int, top: int, right: int, bottom: int) -> bytes:
        """Wytnij fragment obrazu."""
        img    = self.load(source)
        cropped= img.crop((left, top, right, bottom))
        from io import BytesIO
        buf = BytesIO()
        cropped.save(buf, format=img.format or "PNG")
        return buf.getvalue()

    def thermoshot(self, phi: Any,
                   width: int = 800, height: int = 600) -> bytes:
        """
        Termografia phi-space -> obraz PNG.
        Atomy renderowane jako piksele/regiony:
          HOT  (T>70) = czerwony
          WARM (T>30) = zolty
          COLD (T>2)  = niebieski
          TOMB (T<=2) = ciemnoszary
        """
        try:
            atoms = phi.matrix.atoms()
        except Exception:
            atoms = []

        img  = Image.new("RGB", (width, height), (15, 15, 30))
        draw = ImageDraw.Draw(img)

        if not atoms:
            draw.text((10, 10), "phi-space pusty", fill=(100, 100, 100))
            from io import BytesIO
            buf = BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        # Rozmieszcz atomy na siatce
        n    = len(atoms)
        cols = max(1, int(math.sqrt(n * width / height)))
        rows = max(1, math.ceil(n / cols))
        cw   = width  // cols
        ch   = height // rows

        for idx, a in enumerate(atoms):
            T     = float(getattr(a, "T",     0))
            T_max = float(getattr(a, "T_max", 100))
            aid   = str(getattr(a,  "id",     ""))
            state = str(getattr(a,  "state",  ""))
            col   = idx % cols
            row   = idx // cols
            x0    = col * cw
            y0    = row * ch
            x1    = x0 + cw - 1
            y1    = y0 + ch - 1

            # Kolor oparty na T
            pct = T / max(1, T_max)
            if T > 70:
                r = int(200 + 55 * pct)
                g = int(50  * (1 - pct))
                b = 20
            elif T > 30:
                r = int(180 * pct)
                g = int(150 + 80 * pct)
                b = 20
            elif T > 2:
                r = 20
                g = int(80 * pct)
                b = int(150 + 100 * pct)
            else:
                r = g = b = int(30 + 20 * pct)

            # Wypelnij prostokat
            draw.rectangle([x0, y0, x1, y1], fill=(r, g, b))

            # Ramka
            border = (min(255, r+40), min(255, g+40), min(255, b+40))
            draw.rectangle([x0, y0, x1, y1], outline=border)

            # Etykieta (jezeli prostokat wystarczajaco duzy)
            if cw > 40 and ch > 20:
                label = aid[:12] if len(aid) <= 12 else aid[:9] + "..."
                draw.text((x0+2, y0+2), label, fill=(220, 220, 220))
                draw.text((x0+2, y0+12), f"T={T:.0f}", fill=(220, 220, 180))

        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()



def dhash(img, hash_size=8):
    """Difference Hash. Hamming<10 = podobne obrazy."""
    if not _PIL_OK: return 0
    gray=img.convert('L').resize((hash_size+1,hash_size),Image.LANCZOS)
    pixels=list(gray.getdata())
    bits=[1 if pixels[r*(hash_size+1)+c]>pixels[r*(hash_size+1)+c+1] else 0
          for r in range(hash_size) for c in range(hash_size)]
    return sum(b<<i for i,b in enumerate(bits))

def phash(img, hash_size=8):
    """Perceptual Hash (DCT uproszczony). Hamming<15 = prawie identyczne."""
    if not _PIL_OK: return 0
    size=hash_size*4
    gray=img.convert('L').resize((size,size),Image.LANCZOS)
    pixels=list(gray.getdata())
    mean=sum(pixels)/max(1,len(pixels))
    bits=[1 if p>mean else 0 for p in pixels[:hash_size*hash_size]]
    return sum(b<<i for i,b in enumerate(bits))

def hamming_distance(h1,h2): return bin(h1^h2).count('1')

# ─────────────────────────────────────────────────────────────────────────────
# AsciiRenderer -- podgląd w terminalu
# ─────────────────────────────────────────────────────────────────────────────

class AsciiRenderer:
    """
    Renderuje obraz jako bloki Unicode w terminalu.
    Uzywaj polowkowych blokow (U+2580 / U+2584) dla 2x rozdzielczosci pionowej.
    """

    def render(self, img: Any,
               width:  int = ASCII_WIDTH,
               height: int = ASCII_HEIGHT,
               color:  bool = True) -> List[str]:
        """
        Zwraca liste stringow gotowych do wydruku.
        Kazdy string = jedna linia terminala.
        """
        if not _PIL_OK:
            return ["[Pillow niedostepny -- brak podgladu]"]

        # Skaluj obraz zachowujac proporcje
        aspect = img.height / max(1, img.width)
        h      = min(height, int(width * aspect * 0.5))  # terminale maja 2:1 aspect
        h      = max(1, h)
        small  = img.convert("RGB").resize((width, h * 2), Image.LANCZOS)

        lines = []
        pix   = small.load()

        for row in range(0, h * 2, 2):
            line = ""
            for col in range(width):
                # Gorny piksel
                r0, g0, b0 = pix[col, row]       if row     < h*2 else (0,0,0)
                # Dolny piksel
                r1, g1, b1 = pix[col, row + 1]   if row + 1 < h*2 else (0,0,0)

                top_bright  = (r0 + g0 + b0) // 3
                bot_bright  = (r1 + g1 + b1) // 3

                if color and _CURSES_OK:
                    # W trybie curses -- zwroc kod ANSI
                    ansi_top = self._ansi_fg(r0, g0, b0)
                    ansi_bot = self._ansi_bg(r1, g1, b1)
                    line += f"{ansi_top}{ansi_bot}\u2580\033[0m"
                else:
                    # Bez koloru -- skala szarosci znakami
                    avg = (top_bright + bot_bright) // 2
                    idx = int(avg / 255 * (len(DENSITY) - 1))
                    line += DENSITY[idx]
            lines.append(line)

        return lines

    def render_to_string(self, source, width=80, height=40) -> str:
        """Zwroc string z podgladem do wyswietlenia w ksh."""
        if not _PIL_OK:
            return "[Pillow niedostepny]"
        try:
            eng = GraphicsEngine()
            img = eng.load(source)
            lines = self.render(img, width, height, color=False)
            return "\n".join(lines)
        except Exception as e:
            return f"[blad renderingu: {e}]"

    def _ansi_fg(self, r, g, b) -> str:
        return f"\033[38;2;{r};{g};{b}m"

    def _ansi_bg(self, r, g, b) -> str:
        return f"\033[48;2;{r};{g};{b}m"


# ─────────────────────────────────────────────────────────────────────────────
# ImageVault -- archiwum bablowe
# ─────────────────────────────────────────────────────────────────────────────

class ImageVault:
    """
    Archiwum obrazow oparte na bablach KarmazynOS.
    Jeden babel = jedna kolekcja/album.
    Kazdy obraz = atom phi-space + blob w CAS + opcjonalna miniatura.
    """

    def __init__(self, phi: Any = None, bubbles: Any = None):
        self.phi     = phi
        self.bubbles = bubbles
        self.engine  = GraphicsEngine() if _PIL_OK else None

    # ── Import ────────────────────────────────────────────────────────────────

    def import_image(self, path: str,
                     bubble_name: Optional[str] = None,
                     make_thumb: bool = False,
                     log_fn = None) -> Optional[str]:
        """
        Importuj plik graficzny do bąbla.
        Zwraca atom_id lub None przy błędzie.
        """
        def _log(msg):
            if log_fn: log_fn(msg)

        if not os.path.isfile(path):
            _log(f"Brak pliku: {path}")
            return None

        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED_EXTS:
            _log(f"Nieobslugiwany format: {ext}")
            return None

        # CAS -- zapisz oryginał
        blob_hash = None
        if _CAS_OK and BLOB_STORE:
            try:
                blob_hash = BLOB_STORE.put(path)
            except Exception as e:
                _log(f"CAS błąd: {e}")
                return None
        else:
            # Bez CAS -- atom E = ścieżka
            blob_hash = None

        # Metadane
        meta = None
        if self.engine:
            try:
                meta = self.engine.meta(path)
            except Exception:
                pass

        abs_path = os.path.abspath(path)
        atom_id  = (f"img.{blob_hash[:12]}" if blob_hash
                    else f"img.{hashlib.sha1(abs_path.encode()).hexdigest()[:12]}")
        T        = meta.T_value() if meta else 55.0

        if blob_hash:
            E_val = make_blob_ref(blob_hash)
        else:
            E_val = abs_path

        mime = _ext_to_mime(ext)

        # Miniatura
        thumb_hash = None
        if make_thumb and self.engine and blob_hash:
            try:
                thumb_data = self.engine.thumbnail(path)
                if _CAS_OK and BLOB_STORE:
                    thumb_hash = BLOB_STORE.put_bytes(thumb_data, mime="image/jpeg",
                                                       filename=f"thumb_{hid}.jpg")
            except Exception as e:
                _log(f"Thumb blad: {e}")

        # Atom phi-space
        if self.phi:
            try:
                existing = self.phi.get_atom(atom_id)
                if existing:
                    existing.T = T
                    existing.S = mime
                    existing.E = E_val
                    try: existing.touch()
                    except Exception: pass
                else:
                    a = self.phi.create_atom(atom_id, S=mime, E=E_val, T=T)
                    if a:
                        try: a.touch()
                        except Exception: pass
                        # Metadane jako atrybuty rozszerzone
                        if meta:
                            try:
                                a.img_width   = meta.width
                                a.img_height  = meta.height
                                a.img_format  = meta.format
                                a.thumb_hash  = thumb_hash or ""
                                a.entropy     = round(meta.entropy, 3)
                            except Exception:
                                pass
            except Exception as e:
                _log(f"Atom blad: {e}")

        # Import do bąbla
        if bubble_name and self.bubbles and self.phi:
            try:
                bid = (self.bubbles.find_bubble_by_name(bubble_name)
                       or self.bubbles.create_bubble(bubble_name))
                if bid:
                    self.bubbles.import_to_bubble(bid, atom_id, self.phi)
            except Exception as e:
                _log(f"Babel blad: {e}")

        if self.phi and bubble_name and T>50:
            try:
                ba=self.phi.get_atom(f'bubble.{bubble_name}')
                if ba:
                    ba.T=min(float(getattr(ba,'T_max',100)),
                             float(ba.T)+(T-float(ba.T))*0.1)
                    try: ba.touch()
                    except Exception: pass
            except Exception: pass
        name = os.path.basename(path)
        size_str = _fmt_size(os.path.getsize(path))
        dims = f"{meta.width}x{meta.height}" if meta else "?"
        _log(f"OK: {name} [{dims} {size_str}] T={T:.1f} -> {atom_id}")
        return atom_id

    def import_directory(self, directory: str,
                          bubble_name: Optional[str] = None,
                          make_thumb: bool = False,
                          recursive: bool = False,
                          log_fn = None) -> dict:
        """
        Bulk import katalogu z obrazami do bąbla.
        Zwraca {imported, skipped, errors}.
        """
        def _log(msg):
            if log_fn: log_fn(msg)

        imported = skipped = errors = 0
        bname = bubble_name or os.path.basename(directory.rstrip("/"))

        _log(f"Import: {directory} -> babel '{bname}'")

        walker = (os.walk(directory) if recursive
                  else [(directory, [], os.listdir(directory))])

        for root, _, files in walker:
            for fname in sorted(files):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SUPPORTED_EXTS:
                    skipped += 1
                    continue
                fpath = os.path.join(root, fname)
                aid   = self.import_image(fpath, bname, make_thumb, _log)
                if aid:
                    imported += 1
                else:
                    errors += 1

        _log(f"Zakończono: +{imported} zaimportowanych, {skipped} pominiętych, {errors} błędów")
        return {"imported": imported, "skipped": skipped, "errors": errors, "bubble": bname}

    # ── Lista / browse ────────────────────────────────────────────────────────

    def list_images(self, bubble_name: Optional[str] = None) -> List[dict]:
        """Listuj obrazy z bąbla lub całego phi-space."""
        results = []
        if bubble_name and self.bubbles:
            try:
                bid   = (self.bubbles.find_bubble_by_name(bubble_name)
                          or bubble_name)
                atoms = self.bubbles.get_active_atoms(bid)
                for a in atoms:
                    aid  = a.get("id") if isinstance(a,dict) else getattr(a,"id","")
                    if str(aid).startswith("img."):
                        results.append(self._atom_to_info(a))
            except Exception:
                pass
        elif self.phi:
            try:
                for a in self.phi.matrix.atoms():
                    if str(getattr(a,"id","")).startswith("img."):
                        results.append(self._atom_to_info(a))
            except Exception:
                pass
        results.sort(key=lambda x: -x.get("T", 0))
        return results

    def _atom_to_info(self, a) -> dict:
        get = lambda k, d="": (a.get(k, d) if isinstance(a,dict)
                               else getattr(a, k, d))
        return {
            "id":     str(get("id")),
            "S":      str(get("S")),
            "E":      str(get("E")),
            "T":      float(get("T", 0)),
            "w":      int(get("img_width",  0)),
            "h":      int(get("img_height", 0)),
            "fmt":    str(get("img_format", "")),
            "thumb":  str(get("thumb_hash", "")),
            "entropy":float(get("entropy",  0)),
        }

    # ── Pobierz dane ──────────────────────────────────────────────────────────

    def get_image_data(self, atom_id: str) -> Optional[bytes]:
        """Pobierz bytes obrazu dla atomu."""
        if not self.phi: return None
        try:
            atom = self.phi.get_atom(atom_id)
            if not atom: return None
            E = str(getattr(atom, "E", ""))
            if is_blob_ref(E) and _CAS_OK:
                return BLOB_STORE.get_bytes(extract_hash(E))
            if os.path.exists(E):
                return open(E, "rb").read()
        except Exception:
            pass
        return None

    def get_thumb_data(self, atom_id: str) -> Optional[bytes]:
        """Pobierz bytes miniatury dla atomu."""
        if not self.phi: return None
        try:
            atom = self.phi.get_atom(atom_id)
            if not atom: return None
            th = str(getattr(atom, "thumb_hash", ""))
            if th and _CAS_OK:
                return BLOB_STORE.get_bytes(th)
        except Exception:
            pass
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Gallery viewer (curses TUI)
# ─────────────────────────────────────────────────────────────────────────────

class GalleryViewer:
    """Przeglądarka kolekcji obrazów w terminalu (curses)."""

    def __init__(self, vault: ImageVault):
        self.vault   = vault
        self.images  = []
        self.cursor  = 0
        self.view    = "grid"    # "grid" | "preview" | "info"
        self._ascii  = AsciiRenderer()

    def run(self, bubble_name: Optional[str] = None) -> None:
        """Uruchom przeglądarkę."""
        if not _CURSES_OK:
            print("curses niedostępny")
            return
        self.images = self.vault.list_images(bubble_name)
        if not self.images:
            print("Brak obrazów do wyświetlenia.")
            return
        _curses.wrapper(self._main)

    def _main(self, scr) -> None:
        import curses
        curses.curs_set(0)
        curses.noecho()
        scr.keypad(True)
        self._init_colors()
        h, w = scr.getmaxyx()

        while True:
            scr.erase()
            h, w = scr.getmaxyx()
            if   self.view == "grid":    self._draw_grid(scr, h, w)
            elif self.view == "preview": self._draw_preview(scr, h, w)
            elif self.view == "info":    self._draw_info(scr, h, w)
            self._draw_footer(scr, h, w)
            scr.refresh()

            ch = scr.getch()
            if ch == -1: continue
            if ch in (ord("q"), ord("Q"), 27): break
            elif ch == ord("\t"):
                views = ["grid", "preview", "info"]
                self.view = views[(views.index(self.view) + 1) % len(views)]
            elif ch in (curses.KEY_UP, ord("k")):
                self.cursor = max(0, self.cursor - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                self.cursor = min(len(self.images)-1, self.cursor + 1)
            elif ch in (curses.KEY_LEFT, ord("h")):
                cols = max(1, w // 25)
                self.cursor = max(0, self.cursor - cols)
            elif ch in (curses.KEY_RIGHT, ord("l")):
                cols = max(1, w // 25)
                self.cursor = min(len(self.images)-1, self.cursor + cols)
            elif ch == 10:
                self.view = "preview"
            elif ch == ord("i"):
                self.view = "info"
            elif ch == ord("g"):
                self.view = "grid"

    def _draw_grid(self, scr, h: int, w: int) -> None:
        import curses
        col_w   = 25
        cols    = max(1, w // col_w)
        visible = (h - 3) * cols
        offset  = (self.cursor // cols) * cols
        offset  = max(0, offset - (h-3) // 2 * cols)

        for i, img in enumerate(self.images[offset:offset + visible]):
            idx    = i + offset
            col    = i % cols
            row    = i // cols
            x      = col * col_w
            y      = row + 2
            if y >= h - 1: break

            is_sel = (idx == self.cursor)
            T      = img.get("T", 0)
            col_c  = (curses.COLOR_RED    if T > 70 else
                      curses.COLOR_YELLOW if T > 30 else
                      curses.COLOR_CYAN)
            try:
                attr = curses.color_pair(1) | (curses.A_REVERSE if is_sel else 0)
                name = os.path.basename(img.get("E","")
                        if not is_blob_ref(img.get("E",""))
                        else img.get("id","?"))[:col_w-8]
                dims = f"{img.get('w',0)}x{img.get('h',0)}"[:6]
                line = f"{'>' if is_sel else ' '}{name:<{col_w-9}}{dims:>6}"
                scr.addstr(y, x, line[:col_w], attr)
            except curses.error:
                pass

    def _draw_preview(self, scr, h: int, w: int) -> None:
        import curses
        if not self.images: return
        img_info = self.images[self.cursor]
        E        = img_info.get("E", "")
        name     = os.path.basename(E if not is_blob_ref(E) else img_info.get("id","?"))

        self._put(scr, 0, 0,
                  f"  {name}  [{self.cursor+1}/{len(self.images)}]".ljust(w),
                  curses.color_pair(2) | curses.A_BOLD)

        preview_w = min(w-2, ASCII_WIDTH)
        preview_h = h - 5

        if _PIL_OK:
            try:
                data = self.vault.get_thumb_data(img_info["id"])
                if data:
                    from io import BytesIO
                    pil_img = Image.open(BytesIO(data))
                else:
                    src = E if not is_blob_ref(E) else img_info["E"]
                    pil_img = GraphicsEngine().load(src)

                lines = self._ascii.render(pil_img, preview_w, preview_h, color=False)
                for row, line in enumerate(lines[:preview_h]):
                    self._put(scr, row+2, 1, line, curses.color_pair(1))
            except Exception as e:
                self._put(scr, 3, 2, f"[blad podgladu: {e}]", curses.color_pair(1))
        else:
            self._put(scr, 3, 2, "[Pillow niedostepny]", curses.color_pair(1))

    def _draw_info(self, scr, h: int, w: int) -> None:
        import curses
        if not self.images: return
        img_info = self.images[self.cursor]
        self._put(scr, 0, 0, "  INFO".ljust(w), curses.color_pair(2)|curses.A_BOLD)

        rows = [
            f"  ID:       {img_info.get('id','?')}",
            f"  Format:   {img_info.get('fmt','?')}  {img_info.get('S','')}",
            f"  Wymiary:  {img_info.get('w',0)} x {img_info.get('h',0)} px",
            f"  T:        {img_info.get('T',0):.1f}",
            f"  Entropia: {img_info.get('entropy',0):.3f}",
            f"  Blob:     {img_info.get('E','')}",
            f"  Miniatura:{img_info.get('thumb','')}",
        ]
        for i, row in enumerate(rows[:h-4]):
            self._put(scr, i+2, 0, row[:w], curses.color_pair(1))

    def _draw_footer(self, scr, h: int, w: int) -> None:
        import curses
        keys = ("Tab=widok  ↑↓←→/jkhl=nawigacja  Enter=podgląd  i=info  g=siatka  q=wyjście")
        self._put(scr, h-1, 0, keys[:w].ljust(w), curses.color_pair(2))

    def _put(self, scr, y, x, text, attr=0) -> None:
        try:
            scr.addstr(y, x, text, attr)
        except Exception:
            pass

    def _init_colors(self) -> None:
        import curses
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE, -1)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(3, curses.COLOR_RED,   -1)
        curses.init_pair(4, curses.COLOR_YELLOW,-1)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ext_to_mime(ext: str) -> str:
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".gif": "image/gif",
        ".bmp": "image/bmp",  ".webp": "image/webp",
        ".tiff": "image/tiff",".tif": "image/tiff",
        ".ico": "image/x-icon",".avif": "image/avif",
        ".heic": "image/heic",
    }.get(ext.lower(), "image/octet-stream")


def _resolve_source(arg: str, phi: Any) -> str:
    """Rozwiąż argument: atom_id -> E field, ścieżka -> ścieżka."""
    if not arg: return arg
    if os.path.exists(arg): return arg
    if arg.startswith("img.") or arg.startswith("file."):
        if phi:
            a = phi.get_atom(arg)
            if a: return str(getattr(a, "E", arg))
    return arg


# ─────────────────────────────────────────────────────────────────────────────
# Komendy shell
# ─────────────────────────────────────────────────────────────────────────────

def cmd_bview(args, runtime=None, bubbles=None, **_) -> str:
    """
    BVIEW <atom_id|plik> [--ascii|--w <sz>]
    Wyswietl obraz w terminalu (ASCII bloki) lub przez SDL.
    """
    if not args: return "Uzycie: BVIEW <atom_id|plik>"
    if not _PIL_OK: return "Pillow niedostepny. pip install Pillow"

    src   = _resolve_source(args[0], runtime)
    width = 80
    for i, a in enumerate(args):
        if a == "--w" and i+1 < len(args):
            try: width = int(args[i+1])
            except ValueError: pass

    renderer = AsciiRenderer()
    result   = renderer.render_to_string(src, width=width, height=width//2)

    # Dotknij atom phi-space
    if runtime and args[0].startswith("img."):
        try:
            a = runtime.get_atom(args[0])
            if a:
                T_now=float(a.T); T_max=float(getattr(a,"T_max",100))
                delta=max(0.5, 8.0*(1.0-T_now/max(1.0,T_max)))
                a.T=min(T_max, T_now+delta)
                try: a.touch()
                except Exception: pass
        except Exception: pass

    return result


def cmd_bthumb(args, runtime=None, bubbles=None, **_) -> str:
    """BTHUMB <atom_id|plik> [WxH]   -- wygeneruj miniaturę -> CAS"""
    if not args: return "Uzycie: BTHUMB <atom_id|plik> [WxH]"
    if not _PIL_OK: return "Pillow niedostepny."

    src  = _resolve_source(args[0], runtime)
    size = THUMB_SIZE
    if len(args) > 1:
        try:
            w, h = map(int, args[1].lower().split("x"))
            size = (w, h)
        except Exception: pass

    try:
        eng        = GraphicsEngine()
        thumb_data = eng.thumbnail(src, size)
        if _CAS_OK and BLOB_STORE:
            th_hash = BLOB_STORE.put_bytes(thumb_data, mime="image/jpeg",
                                           filename=f"thumb_{args[0]}.jpg")
            # Zapisz hash miniatury w atomie
            if runtime:
                try:
                    a = runtime.get_atom(args[0])
                    if a: a.thumb_hash = th_hash
                except Exception: pass
            return (f"OK: miniatura {size[0]}x{size[1]}\n"
                    f"  hash: {th_hash}\n"
                    f"  rozmiar: {_fmt_size(len(thumb_data))}")
        else:
            return f"OK: miniatura {size[0]}x{size[1]} (brak CAS -- niezapisana)"
    except Exception as e:
        return f"Blad BTHUMB: {e}"


def cmd_bresize(args, runtime=None, **_) -> str:
    """BRESIZE <atom_id|plik> <WxH> [--stretch]  -- zmień rozmiar -> nowy atom"""
    if len(args) < 2: return "Uzycie: BRESIZE <atom_id|plik> <WxH>"
    if not _PIL_OK: return "Pillow niedostepny."

    src    = _resolve_source(args[0], runtime)
    keep   = "--stretch" not in args
    try:
        w, h = map(int, args[1].lower().split("x"))
    except Exception:
        return "Podaj rozmiar jako WxH np. 800x600"

    try:
        eng  = GraphicsEngine()
        data = eng.resize(src, w, h, keep_ratio=keep)
        if _CAS_OK and BLOB_STORE:
            h_new = BLOB_STORE.put_bytes(data, mime="image/png",
                                         filename=f"resized_{w}x{h}.png")
            aid = f"img.{h_new[:12]}"
            if runtime:
                a = runtime.create_atom(aid, S="image/png",
                                        E=make_blob_ref(h_new), T=60.0)
                if a:
                    try: a.touch()
                    except Exception: pass
            return f"OK: {w}x{h} -> {aid} ({_fmt_size(len(data))})"
        return f"OK: {w}x{h} ({_fmt_size(len(data))}) -- brak CAS"
    except Exception as e:
        return f"Blad BRESIZE: {e}"


def cmd_bconvert(args, runtime=None, **_) -> str:
    """BCONVERT <atom_id|plik> <format>   -- konwertuj (JPEG PNG WEBP BMP)"""
    if len(args) < 2: return "Uzycie: BCONVERT <atom_id|plik> <format>"
    if not _PIL_OK: return "Pillow niedostepny."

    src = _resolve_source(args[0], runtime)
    fmt = args[1].upper().replace("JPG", "JPEG")

    try:
        eng  = GraphicsEngine()
        data = eng.convert(src, fmt)
        mime = f"image/{fmt.lower()}"
        if _CAS_OK and BLOB_STORE:
            h_new = BLOB_STORE.put_bytes(data, mime=mime,
                                          filename=f"converted.{fmt.lower()}")
            aid = f"img.{h_new[:12]}"
            if runtime:
                a = runtime.create_atom(aid, S=mime,
                                        E=make_blob_ref(h_new), T=58.0)
                if a:
                    try: a.touch()
                    except Exception: pass
            return f"OK: -> {fmt} {_fmt_size(len(data))} -> {aid}"
        return f"OK: -> {fmt} {_fmt_size(len(data))}"
    except Exception as e:
        return f"Blad BCONVERT: {e}"


def cmd_binfo(args, runtime=None, **_) -> str:
    """BINFO <atom_id|plik>   -- szczegolowe metadane obrazu"""
    if not args: return "Uzycie: BINFO <atom_id|plik>"
    if not _PIL_OK: return "Pillow niedostepny."

    src = _resolve_source(args[0], runtime)
    try:
        meta  = GraphicsEngine().meta(src)
        lines = [
            f"  Wymiary:    {meta.width} x {meta.height} px",
            f"  Format:     {meta.format}  tryb: {meta.mode}",
            f"  Rozmiar:    {_fmt_size(meta.file_size)}",
            f"  Alpha:      {'tak' if meta.has_alpha else 'nie'}",
            f"  Jasnosc:    {meta.mean_brightness:.1f}/255",
            f"  Entropia:   {meta.entropy:.3f}",
            f"  T atomu:    {meta.T_value():.1f}",
        ]
        if meta.dominant_colors:
            lines.append("  Kolory:")
            for r,g,b,c in meta.dominant_colors[:3]:
                bar = "█" * min(20, c // 10)
                lines.append(f"    RGB({r:3},{g:3},{b:3}) {bar}")
        if meta.exif:
            lines.append("  EXIF:")
            for k, v in list(meta.exif.items())[:6]:
                lines.append(f"    {k}: {v[:50]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Blad BINFO: {e}"


def cmd_bgallery(args, runtime=None, bubbles=None, **_) -> str:
    """BGALLERY [babel]   -- przeglądarka kolekcji obrazów (curses TUI)"""
    vault  = ImageVault(runtime, bubbles)
    bubble = args[0] if args else None
    viewer = GalleryViewer(vault)
    try:
        viewer.run(bubble)
    except Exception as e:
        return f"Gallery blad: {e}"
    return ""


def cmd_barchive(args, runtime=None, bubbles=None, **_) -> str:
    """
    BARCHIVE <katalog> [babel] [--thumb] [--recursive]
    Zaimportuj caly katalog obrazow do babla.
    """
    if not args: return "Uzycie: BARCHIVE <katalog> [babel] [--thumb] [--recursive]"
    if not _PIL_OK: return "Pillow niedostepny. pip install Pillow"

    directory = os.path.expanduser(args[0])
    if not os.path.isdir(directory):
        return f"Brak katalogu: {directory}"

    bubble_name = next((a for a in args[1:] if not a.startswith("--")), None)
    make_thumb  = "--thumb" in args
    recursive   = "--recursive" in args or "-r" in args

    log_lines = []
    vault     = ImageVault(runtime, bubbles)
    result    = vault.import_directory(
        directory, bubble_name, make_thumb, recursive,
        log_fn=log_lines.append)

    lines = log_lines[-20:]   # ostatnie 20 linii logu
    lines.append(f"Wynik: +{result['imported']} obrazów, "
                 f"{result['skipped']} pominiętych, "
                 f"{result['errors']} błędów -> babel '{result['bubble']}'")
    return "\n".join(lines)


def cmd_bthermo(args, runtime=None, bubbles=None, **_) -> str:
    """
    BTHERMO [--w px] [--h px] [babel]
    Wygeneruj termografię phi-space jako PNG -> CAS.
    """
    if not runtime: return "Brak runtime."
    if not _PIL_OK: return "Pillow niedostepny."

    w = 800; h = 600
    for i, a in enumerate(args):
        if a == "--w" and i+1 < len(args):
            try: w = int(args[i+1])
            except ValueError: pass
        if a == "--h" and i+1 < len(args):
            try: h = int(args[i+1])
            except ValueError: pass

    try:
        eng  = GraphicsEngine()
        data = eng.thermoshot(runtime, w, h)
        if _CAS_OK and BLOB_STORE:
            ts    = time.strftime("%Y%m%d_%H%M%S")
            hsh   = BLOB_STORE.put_bytes(data, mime="image/png",
                                          filename=f"thermo_{ts}.png")
            aid   = f"img.thermo.{hsh[:8]}"
            if runtime:
                a = runtime.create_atom(aid, S="image/png",
                                        E=make_blob_ref(hsh), T=75.0)
                if a:
                    try: a.touch()
                    except Exception: pass
            return (f"OK: termografia phi-space {w}x{h}\n"
                    f"  atom:  {aid}\n"
                    f"  blob:  blob:{hsh}\n"
                    f"  rozmiar: {_fmt_size(len(data))}\n"
                    f"  Pobierz: CAS GET {hsh}")
        return f"OK: {w}x{h} {_fmt_size(len(data))} (brak CAS)"
    except Exception as e:
        return f"Blad BTHERMO: {e}"



def cmd_bfind(args, runtime=None, bubbles=None, **_) -> str:
    """BFIND [--hot] [--cold] [--fmt PNG] [--min-entropy N] [--similar id]"""
    if not runtime: return 'Brak runtime.'
    hot='--hot' in args; cold='--cold' in args
    fmt_f=None; min_ent=0.0; ref_dh=None
    i=0
    while i<len(args):
        if args[i]=='--fmt' and i+1<len(args): fmt_f=args[i+1].upper(); i+=1
        if args[i]=='--min-entropy' and i+1<len(args):
            try: min_ent=float(args[i+1]); i+=1
            except ValueError: pass
        if args[i]=='--similar' and i+1<len(args):
            try:
                ra=runtime.get_atom(args[i+1])
                if ra: ref_dh=int(getattr(ra,'dhash',0))
            except Exception: pass
            i+=1
        i+=1
    results=[]
    try:
        for a in runtime.matrix.atoms():
            aid=str(getattr(a,'id',''))
            if not aid.startswith('img.'): continue
            T=float(getattr(a,'T',0)); ent=float(getattr(a,'entropy',0))
            fmt=str(getattr(a,'img_format','')).upper()
            ad=int(getattr(a,'dhash',0))
            if hot and T<60: continue
            if cold and T>40: continue
            if fmt_f and fmt_f not in fmt: continue
            if ent<min_ent: continue
            dist=hamming_distance(ref_dh,ad) if ref_dh is not None else 0
            if ref_dh is not None and dist>15: continue
            results.append({'id':aid,'T':T,'entropy':ent,'fmt':fmt,'dist':dist})
    except Exception as e: return f'Blad BFIND: {e}'
    results.sort(key=lambda x:-x['T'])
    if not results: return 'Brak wynikow.'
    lines=[f"  {'ID':<22} {'T':>6} {'Entr':>6} {'Dist'}","  "+'-'*45]
    for r in results[:20]:
        d=str(r['dist']) if ref_dh is not None else ''
        lines.append(f"  {r['id']:<22} {r['T']:>6.1f} {r['entropy']:>6.3f} {d}")
    lines.append(f"  Razem: {len(results)}")
    return '\n'.join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# Rejestracja w shell.py
# ─────────────────────────────────────────────────────────────────────────────

def register_graphics(reg_fn, runtime=None, bubbles=None) -> None:
    """
    Zarejestruj komendy graficzne w shellu.

    Uzycie w shell.py:
        from karmazyn_graphics import register_graphics
        register_graphics(reg, RUNTIME, BUBBLES)
    """
    def _w(fn):
        return lambda args: fn(args, runtime=runtime, bubbles=bubbles)

    reg_fn("BVIEW",    _w(cmd_bview),    "Podglad obrazu (ASCII terminal)",  category="graphics")
    reg_fn("BTHUMB",   _w(cmd_bthumb),   "Miniatura -> CAS",                 category="graphics")
    reg_fn("BRESIZE",  _w(cmd_bresize),  "Zmien rozmiar obrazu",             category="graphics")
    reg_fn("BCONVERT", _w(cmd_bconvert), "Konwertuj format obrazu",          category="graphics")
    reg_fn("BINFO",    _w(cmd_binfo),    "Metadane + histogram obrazu",      category="graphics")
    reg_fn("BGALLERY", _w(cmd_bgallery), "Przegladarka kolekcji (curses)",   category="graphics")
    reg_fn("BARCHIVE", _w(cmd_barchive), "Import katalogu obrazow do babla", category="graphics")
    reg_fn("BFIND",    _w(cmd_bfind),    "Szukaj obrazow semantycznie",       category="graphics")
    reg_fn("BTHERMO",  _w(cmd_bthermo),  "Termografia phi-space -> PNG",     category="graphics")


# ─────────────────────────────────────────────────────────────────────────────
# Test standalone
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, tempfile

    ap = argparse.ArgumentParser(description="KarmazynOS Graphics Engine v1.0")
    ap.add_argument("--demo",   action="store_true")
    ap.add_argument("--info",   metavar="FILE")
    ap.add_argument("--view",   metavar="FILE")
    ap.add_argument("--thumb",  metavar="FILE")
    ap.add_argument("--thermo", action="store_true")
    opt = ap.parse_args()

    if not _PIL_OK:
        print("Pillow niedostepny. Uruchom: pip install Pillow")
        sys.exit(1)

    if opt.demo:
        print("=" * 60)
        print("  KarmazynOS Graphics Engine -- demo")
        print("=" * 60)

        # Stwórz testowy obraz
        img = Image.new("RGB", (200, 100))
        draw = ImageDraw.Draw(img)
        for x in range(200):
            for y in range(100):
                r = int(x / 200 * 255)
                g = int(y / 100 * 255)
                b = 128
                draw.point((x, y), fill=(r, g, b))

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            img.save(f.name)
            tmp = f.name

        print(f"\n[1] Metadane {tmp}:")
        eng  = GraphicsEngine()
        meta = eng.meta(tmp)
        print(f"  {meta.summary()}")

        print("\n[2] ASCII preview (30x15):")
        lines = AsciiRenderer().render(img, 30, 15, color=False)
        for l in lines: print("  " + l)

        print("\n[3] Miniatura:")
        tb   = eng.thumbnail(tmp, (64, 64))
        print(f"  {_fmt_size(len(tb))} JPEG")

        print("\n[4] Termografia phi-space (mock):")
        class _MockAtom:
            def __init__(self,id,T):
                self.id=id; self.T=T; self.T_max=100
                self.state="WARM"
        class _MockPhi:
            class _M:
                def atoms(s): return [
                    _MockAtom("shell.init",90),
                    _MockAtom("bubble.alpha",65),
                    _MockAtom("program.logo",40),
                    _MockAtom("old.session",5),
                ]
            matrix = _M()
        thermo = eng.thermoshot(_MockPhi(), 400, 200)
        print(f"  {_fmt_size(len(thermo))} PNG termografia")

        os.unlink(tmp)
        print("\n  Wszystkie testy OK")
        print("=" * 60)

    elif opt.info:
        print(cmd_binfo([opt.info]))
    elif opt.view:
        print(cmd_bview([opt.view, "--w", "80"]))
    elif opt.thumb:
        print(cmd_bthumb([opt.thumb]))
    elif opt.thermo:
        print("Uruchom z KarmazynOS runtime (wymaga phi-space)")
    else:
        ap.print_help()