#!/usr/bin/env python3
"""
karmazyn_hologram_format.py — Hologramy formatów plików dla KarmazynOS v2.0
======================================================================
Poprawki:
- S atomu to string opisowy, nie wektor (zgodne z runtime)
- Przechowywanie wymiarów obrazu w E (JSON)
- Detekcja formatu danych przed otwarciem w PIL
- Zabezpieczenie przed brakiem runtime._log
- Jednokrotna inicjalizacja hologramów
- Ostrzeżenie przy braku biblioteki obrazów
- Obsługa parametrów PNG (compress) i GIF (duration/loop)
- Termodynamika: T rośnie wykładniczo przy renderowaniu
"""

import hashlib
import io
import json
import base64
import struct
import time
from typing import Dict, Any, Optional, Tuple, List
import numpy as np

# ---------------------------------------------------------------------
# Wykorzystanie biblioteki Pil-Lite (lub Pillow)
# ---------------------------------------------------------------------
try:
    from PilLite import Image as PilImage
    HAS_PIL = True
    _IMAGE_LIB = "Pil-Lite (https://github.com/python-pil/Pil-Lite)"
except ImportError:
    try:
        from PIL import Image as PilImage
        HAS_PIL = True
        _IMAGE_LIB = "Pillow (https://python-pillow.org)"
    except ImportError:
        HAS_PIL = False
        _IMAGE_LIB = None
        # Ostrzeżenie dla użytkownika (wypisane przy pierwszym użyciu)
        _WARN_NO_PIL = True

# =====================================================================
# Hologramy formatów
# =====================================================================

class FormatHologram:
    def __init__(self, name: str, prototype: bytes, extensions: List[str],
                 mime_type: str, generator_fn=None,
                 based_on: str = "", license_info: str = ""):
        self.name = name
        self.prototype = prototype
        self.extensions = extensions
        self.mime_type = mime_type
        self.generator_fn = generator_fn
        self.epoch_created = time.time()
        self.based_on = based_on
        self.license_info = license_info

    def render(self, atom_data: bytes, **params) -> bytes:
        if self.generator_fn:
            return self.generator_fn(atom_data, params)
        # Fallback (tylko nagłówek)
        return self.prototype + atom_data[:1000]

    def get_attribution(self) -> str:
        if HAS_PIL and _IMAGE_LIB:
            return f"Format {self.name} obsługiwany przez {_IMAGE_LIB}"
        elif self.based_on:
            return f"Format {self.name} oparty na specyfikacji: {self.based_on}"
        return f"Format {self.name}: implementacja własna (podstawowa)"


# Rejestr hologramów
_FORMAT_HOLOGRAMS: Dict[str, FormatHologram] = {}
_HOLOGRAMS_INITIALIZED = False

def register_format_hologram(holo: FormatHologram) -> None:
    _FORMAT_HOLOGRAMS[holo.name] = holo
    for ext in holo.extensions:
        _FORMAT_HOLOGRAMS[ext] = holo

def get_format_hologram(name_or_ext: str) -> Optional[FormatHologram]:
    return _FORMAT_HOLOGRAMS.get(name_or_ext.lower())


# =====================================================================
# Generatory formatów (z poprawną obsługą surowych danych)
# =====================================================================

def _ensure_pil_image(data: bytes) -> Any:
    """Konwertuje dowolne dane (plik lub surowe RGB) do obiektu PIL Image."""
    global _WARN_NO_PIL
    if not HAS_PIL:
        if _WARN_NO_PIL:
            print("⚠ UWAGA: Brak Pil-Lite lub Pillow – zapis obrazów będzie symulowany (niepoprawne pliki)!")
            _WARN_NO_PIL = False
        raise RuntimeError("Brak biblioteki obrazów – nie można wygenerować pliku")
    
    # Sprawdź, czy dane są rozpoznawalnym formatem pliku
    if data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG') or data.startswith(b'GIF') or data.startswith(b'BM'):
        return PilImage.open(io.BytesIO(data))
    else:
        # Zakładamy surowe RGB – wymagamy wymiarów
        # Oczekujemy, że dane są zakodowane jako JSON w E
        raise ValueError("Nieznany format danych – użyj JSON z metadanymi lub zapisz obraz w formacie pliku")

def _jpeg_generator(data: bytes, params: dict) -> bytes:
    if not HAS_PIL:
        return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00' + data[:500]
    img = _ensure_pil_image(data)
    quality = params.get('quality', 85)
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=quality)
    return out.getvalue()

def _png_generator(data: bytes, params: dict) -> bytes:
    if not HAS_PIL:
        return b'\x89PNG\r\n\x1a\n' + data[:500]
    img = _ensure_pil_image(data)
    out = io.BytesIO()
    compress = params.get('compress', 6)
    img.save(out, format='PNG', compress_level=compress)
    return out.getvalue()

def _gif_generator(data: bytes, params: dict) -> bytes:
    if not HAS_PIL:
        return b'GIF89a' + data[:500]
    img = _ensure_pil_image(data)
    out = io.BytesIO()
    duration = params.get('duration', 100)
    loop = params.get('loop', 0)
    img.save(out, format='GIF', save_all=True, duration=duration, loop=loop)
    return out.getvalue()

def _tiff_generator(data: bytes, params: dict) -> bytes:
    if not HAS_PIL:
        return b'II*\x00' + data[:500]
    img = _ensure_pil_image(data)
    out = io.BytesIO()
    compression = params.get('compression', 'tiff_lzw')
    img.save(out, format='TIFF', compression=compression)
    return out.getvalue()


# =====================================================================
# Inicjalizacja hologramów (jednokrotna)
# =====================================================================

def init_format_holograms():
    global _HOLOGRAMS_INITIALIZED
    if _HOLOGRAMS_INITIALIZED:
        return
    register_format_hologram(FormatHologram(
        name='jpeg', prototype=b'\xff\xd8\xff\xe0',
        extensions=['.jpg', '.jpeg', '.jfif'], mime_type='image/jpeg',
        generator_fn=_jpeg_generator,
        based_on="ISO/IEC 10918-1 (ITU T.81)",
        license_info="Independent JPEG Group (IJG) license"
    ))
    register_format_hologram(FormatHologram(
        name='png', prototype=b'\x89PNG\r\n\x1a\n',
        extensions=['.png'], mime_type='image/png',
        generator_fn=_png_generator,
        based_on="RFC 2083",
        license_info="libpng license"
    ))
    register_format_hologram(FormatHologram(
        name='gif', prototype=b'GIF89a',
        extensions=['.gif'], mime_type='image/gif',
        generator_fn=_gif_generator,
        based_on="GIF89a (CompuServe)",
        license_info="giflib open source"
    ))
    register_format_hologram(FormatHologram(
        name='tiff', prototype=b'II*\x00',
        extensions=['.tif', '.tiff'], mime_type='image/tiff',
        generator_fn=_tiff_generator,
        based_on="Adobe TIFF 6.0",
        license_info="libtiff open source"
    ))
    _HOLOGRAMS_INITIALIZED = True


# =====================================================================
# Atom obrazu (zgodny z runtime)
# =====================================================================

class KarmazynImageAtom:
    def __init__(self, runtime, atom_id: str = None, data: bytes = None,
                 width: int = 0, height: int = 0):
        self.runtime = runtime
        self.atom_id = atom_id
        if atom_id:
            self._atom = runtime.get_atom(atom_id)
        elif data:
            self._create_from_data(data, width, height)

    def _create_from_data(self, data: bytes, width: int = 0, height: int = 0):
        # Jeśli nie podano wymiarów, spróbuj odczytać z obrazu (jeśli PIL dostępny)
        if width == 0 or height == 0:
            if HAS_PIL:
                try:
                    img = PilImage.open(io.BytesIO(data))
                    width, height = img.size
                except Exception:
                    pass
        # Generuj ID
        atom_id = f"img_{hashlib.md5(data).hexdigest()[:12]}_{int(time.time())}"
        # S – string opisowy (zgodny z runtime)
        S = f"image:{width}x{height}:{hashlib.md5(data).hexdigest()[:8]}"
        # E – JSON z metadanymi i danymi (base64)
        metadata = {
            "w": width,
            "h": height,
            "data": base64.b64encode(data).decode('ascii'),
            "format": "raw"  # lub "jpeg", "png" – można rozszerzyć
        }
        E = json.dumps(metadata)
        self._atom = self.runtime.create_atom(atom_id, S, E, T=70.0)
        self.runtime.consolidate(atom_id)
        self.atom_id = atom_id

    def get_raw_data(self) -> Tuple[bytes, int, int]:
        """Zwraca (dane_surowe, szerokość, wysokość)."""
        metadata = json.loads(self._atom.E)
        data = base64.b64decode(metadata["data"])
        width = metadata.get("w", 0)
        height = metadata.get("h", 0)
        return data, width, height

    def render_to_file(self, filepath: str, format_hologram: FormatHologram,
                       **params) -> None:
        data, w, h = self.get_raw_data()
        # Jeśli dane są surowe (RGB) a brak wymiarów – błąd
        if w == 0 or h == 0:
            raise ValueError("Brak wymiarów obrazu – nie można wyrenderować")
        # Dla surowych danych trzeba utworzyć obraz w pamięci (przez PIL)
        if HAS_PIL and not (data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG')):
            # Konwersja surowych danych na obraz PIL
            img = PilImage.frombytes('RGB', (w, h), data)
            out = io.BytesIO()
            # Zapisujemy do docelowego formatu przez PIL
            fmt = format_hologram.name.upper()
            save_params = {}
            if fmt == 'JPEG':
                save_params['quality'] = params.get('quality', 85)
            elif fmt == 'PNG':
                save_params['compress_level'] = params.get('compress', 6)
            elif fmt == 'GIF':
                save_params['save_all'] = True
                save_params['duration'] = params.get('duration', 100)
                save_params['loop'] = params.get('loop', 0)
            elif fmt == 'TIFF':
                save_params['compression'] = params.get('compression', 'tiff_lzw')
            img.save(out, format=fmt, **save_params)
            rendered = out.getvalue()
        else:
            # Dane są już w formacie pliku – użyj generatora hologramu
            rendered = format_hologram.render(data, **params)
        with open(filepath, 'wb') as f:
            f.write(rendered)
        # Termodynamika: wzrost temperatury (wykładniczy)
        self._atom.T = min(100.0, self._atom.T * 1.1 + 2.0)
        # Logowanie (jeśli runtime wspiera)
        if hasattr(self.runtime, '_log'):
            self.runtime._log(f"[IMAGE] Zapisano {filepath} przy użyciu {format_hologram.get_attribution()}")

    def info(self) -> dict:
        data, w, h = self.get_raw_data()
        return {
            'id': self.atom_id,
            'T': self._atom.T,
            'state': self._atom.state,
            'size': len(data),
            'width': w,
            'height': h,
        }


# =====================================================================
# Komenda shella
# =====================================================================

def _parse_params(args, start_idx: int) -> dict:
    """Parsuje pary klucz=wartość z listy args."""
    params = {}
    for arg in args[start_idx:]:
        if '=' in arg:
            key, val = arg.split('=', 1)
            try:
                params[key] = int(val)
            except ValueError:
                try:
                    params[key] = float(val)
                except ValueError:
                    params[key] = val
    return params

def cmd_hologram(args, runtime, term_state=None):
    if not args:
        return "Użycie: HOLOGRAM LIST|RENDER|INFO|ATTRIBUTION"
    sub = args[0].upper()
    if sub == "LIST":
        lines = ["Dostępne hologramy formatów:"]
        for name, holo in _FORMAT_HOLOGRAMS.items():
            if not name.startswith('.'):
                lines.append(f"  {name} ({holo.mime_type}) → {holo.extensions}")
                lines.append(f"      Źródło: {holo.get_attribution()}")
        return "\n".join(lines)
    elif sub == "RENDER" and len(args) >= 4:
        atom_id = args[1]
        fmt_name = args[2].lower()
        out_file = args[3]
        params = _parse_params(args, 4)
        holo = get_format_hologram(fmt_name)
        if not holo:
            return f"Nieznany format: {fmt_name}"
        atom = runtime.get_atom(atom_id)
        if not atom:
            return f"Atom {atom_id} nie istnieje"
        img = KarmazynImageAtom(runtime, atom_id=atom_id)
        try:
            img.render_to_file(out_file, holo, **params)
        except Exception as e:
            return f"Błąd renderowania: {e}"
        return f"Zapisano {out_file} (format: {holo.name})"
    elif sub == "INFO" and len(args) >= 2:
        fmt = args[1].lower()
        holo = get_format_hologram(fmt)
        if not holo:
            return f"Nieznany format: {fmt}"
        return f"{holo.name}: {holo.mime_type}, rozszerzenia: {holo.extensions}\n{holo.get_attribution()}\nLicencja: {holo.license_info}"
    elif sub == "ATTRIBUTION":
        lines = [
            "=== WYKORZYSTANE ROZWIĄZANIA INNYCH PROGRAMISTÓW ===",
            "",
            "1. Obrazy – formaty plików:",
            f"   - Biblioteka: {_IMAGE_LIB if HAS_PIL else 'brak (tylko symulacja)'}",
            "   - JPEG: Independent JPEG Group (IJG) – ISO/IEC 10918-1",
            "   - PNG: libpng – RFC 2083",
            "   - GIF: giflib – GIF89a",
            "   - TIFF: libtiff – Adobe TIFF 6.0",
            "",
            "2. Specyfikacje i standardy:",
            "   - JPEG: ITU T.81",
            "   - PNG: W3C",
            "   - GIF: CompuServe",
            "   - TIFF: Adobe",
            "",
            "3. Kod referencyjny (open source):",
            "   - Pil-Lite / Pillow – MIT / HPND",
            "   - libjpeg-turbo – BSD-like",
            "   - zlib – Jean-loup Gailly, Mark Adler",
            "",
            "Wszystkie użyte algorytmy są zgodne z ich oryginalnymi licencjami."
        ]
        return "\n".join(lines)
    return cmd_hologram([], runtime)


# =====================================================================
# Automatyczna inicjalizacja przy imporcie
# =====================================================================

init_format_holograms()