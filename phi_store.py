"""
phi_store.py — Systemowy magazyn danych KarmazynOS
===================================================
Jeden punkt szyfrowania/deszyfrowania dla calego systemu.
Aplikacje (NooEdit, shell, agenci, BubbleFS) nie wiedza ze
szyfrowanie istnieje — uzywaja prostego API save/load.

Klucz = phi1.signature Babla tozsamosci systemu ([Phi-ID]).
Bez zywego systemu z tym samym Bablem — wszystko to szum.

Tryby:
  NOISE  — XOR z kluczem systemowym (domyslne, szybkie)
  FULL   — XOR z kluczem systemowym + phi Babla docelowego
  PLAIN  — brak szyfrowania (testy, debug)

Uzycie:
  # W runtime.__init__:
  from phi_store import PhiStore
  self.phi_store = PhiStore(identity_phi=identity_bubble.phi1.signature)

  # Wszedzie w systemie:
  runtime.phi_store.save("dom", content, bubble=bubble)
  content = runtime.phi_store.load("dom", bubble=bubble)
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from karmazyn_core import Bubble

# ===========================================================================
# STALE
# ===========================================================================

STORE_DIR    = ".bubbles/store"
TMP_DIR      = ".bubbles/tmp"

HEADER_NOISE = b"KOS_NOISE_V1\x00"   # 13 bajtow
HEADER_FULL  = b"KOS_FULL_V1\x00\x00"  # 13 bajtow
HEADER_PLAIN = b"KOS_PLAIN_V1\x00"   # 13 bajtow

HEADER_LEN   = 13


# ===========================================================================
# KRYPTOGRAFIA — bez zaleznosci zewnetrznych
# ===========================================================================

def _xor_stream(data: bytes, key: bytes) -> bytes:
    """
    XOR stream cipher z SHA-256 jako CSPRNG.
    Deterministyczny: te same dane + klucz = ten sam wynik.
    """
    out     = bytearray(len(data))
    offset  = 0
    counter = 0
    while offset < len(data):
        block = hashlib.sha256(
            key + counter.to_bytes(4, 'big')
        ).digest()
        for b in block:
            if offset >= len(data):
                break
            out[offset] = data[offset] ^ b
            offset += 1
        counter += 1
    return bytes(out)


def _derive_noise_key(system_phi: np.ndarray) -> bytes:
    """
    Klucz NOISE z phi-wektora tozsamosci systemu.
    Klucz = HKDF-like(SHA-256(phi_bytes), "karmazyn_noise_v1").
    """
    raw = hashlib.sha256(system_phi.tobytes()).digest()
    return hashlib.sha256(raw + b"karmazyn_noise_v1").digest()


def _derive_full_key(system_phi: np.ndarray,
                     bubble_phi1: np.ndarray,
                     bubble_phi2: np.ndarray) -> bytes:
    """
    Klucz FULL z phi systemu + obu biegunow Babla.
    Mocniejszy niz NOISE — wymaga znajomosci pelnej geometrii.
    """
    combined = (system_phi.tobytes()
                + bubble_phi1.tobytes()
                + bubble_phi2.tobytes())
    k = hashlib.sha256(combined).digest()
    return hashlib.sha256(k + b"karmazyn_full_v1").digest()


# ===========================================================================
# PHI STORE
# ===========================================================================

class PhiStore:
    """
    Systemowy magazyn danych KarmazynOS.

    Inicjalizacja (w runtime.__init__):
        self.phi_store = PhiStore(identity_phi=identity_bubble.phi1.signature)

    Zapis (aplikacje, agenci, shell):
        runtime.phi_store.save("dom", content)
        runtime.phi_store.save("dom", content, bubble=babl, mode='full')

    Odczyt:
        content = runtime.phi_store.load("dom")
        content = runtime.phi_store.load("dom", bubble=babl)

    Szum dla Windows:
        type .bubbles/store/dom.kos   -> binarne smieci (raw bytes)
    """

    EXT = ".kos"   # KarmazynOS Store

    def __init__(self, identity_phi: Optional[np.ndarray] = None,
                 store_dir: str = STORE_DIR,
                 tmp_dir:   str = TMP_DIR,
                 default_mode: str = 'noise'):
        """
        identity_phi  — phi1.signature Babla tozsamosci systemu ([Phi-ID])
                        Jesli None — tryb PLAIN (tymczasowy, bez szyfrowania)
        default_mode  — 'noise' | 'full' | 'plain'
        """
        self._system_phi  = identity_phi
        self._store_dir   = Path(store_dir)
        self._tmp_dir     = Path(tmp_dir)
        self._default_mode = default_mode if identity_phi is not None else 'plain'

        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._tmp_dir.mkdir(  parents=True, exist_ok=True)

        # Cache kluczy — unika wielokrotnego obliczania
        self._key_cache: dict[str, bytes] = {}

    # ── Klucze ────────────────────────────────────────────────────────────────

    def _noise_key(self) -> bytes:
        if 'noise' not in self._key_cache:
            if self._system_phi is None:
                raise RuntimeError("PhiStore: brak klucza systemowego")
            self._key_cache['noise'] = _derive_noise_key(self._system_phi)
        return self._key_cache['noise']

    def _full_key(self, bubble) -> bytes:
        bid = getattr(bubble, 'label', id(bubble))
        cache_key = f"full_{bid}"
        if cache_key not in self._key_cache:
            phi1 = bubble.phi1.signature
            phi2 = bubble.phi2
            self._key_cache[cache_key] = _derive_full_key(
                self._system_phi, phi1, phi2
            )
        return self._key_cache[cache_key]

    def update_identity(self, new_phi: np.ndarray) -> None:
        """
        Aktualizuje klucz systemowy gdy Babl tozsamosci ewoluuje.
        Uwaga: stare dane zaszyfrowane starym kluczem staja sie nieczytelne.
        Wywolaj jesli hologram systemowy zostal zaktualizowany.
        """
        self._system_phi = new_phi
        self._key_cache.clear()

    # ── Szyfrowanie / deszyfrowanie ───────────────────────────────────────────

    def _encrypt(self, data: bytes, mode: str,
                 bubble=None) -> bytes:
        if mode == 'noise':
            key = self._noise_key()
            return HEADER_NOISE + _xor_stream(data, key)
        if mode == 'full':
            if bubble is None:
                # Fallback do noise jesli brak Babla
                key = self._noise_key()
                return HEADER_NOISE + _xor_stream(data, key)
            key = self._full_key(bubble)
            return HEADER_FULL + _xor_stream(data, key)
        # plain
        return HEADER_PLAIN + data

    def _decrypt(self, raw: bytes, bubble=None) -> bytes:
        if len(raw) < HEADER_LEN:
            return raw  # za krotki — traktuj jako plaintext legacy

        header = raw[:HEADER_LEN]
        body   = raw[HEADER_LEN:]

        if header == HEADER_NOISE:
            key = self._noise_key()
            return _xor_stream(body, key)

        if header == HEADER_FULL:
            if bubble is None:
                raise ValueError(
                    "Dane zaszyfrowane trybem FULL wymagaja Babla."
                )
            key = self._full_key(bubble)
            return _xor_stream(body, key)

        if header == HEADER_PLAIN:
            return body

        # Nieznany naglowek — probuj jako UTF-8 plaintext (legacy)
        return raw

    # ── Publiczne API ─────────────────────────────────────────────────────────

    def save(self, label: str, content: str,
             bubble=None,
             mode: Optional[str] = None,
             subdir: str = "") -> Path:
        """
        Zapisuje tresc do magazynu (zaszyfrowana).

        label    — identyfikator (np. nazwa Babla)
        content  — tresc jako string
        bubble   — Babl dla trybu FULL (opcjonalny)
        mode     — 'noise'|'full'|'plain' (domyslnie: default_mode)
        subdir   — podkatalog w store (np. 'souls', 'agents')
        """
        m    = mode or self._default_mode
        data = content.encode('utf-8')
        enc  = self._encrypt(data, m, bubble=bubble)

        target_dir = self._store_dir / subdir if subdir else self._store_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{label}{self.EXT}"

        # Atomowy zapis: tmp -> rename
        tmp_path = path.with_suffix('.kos.tmp')
        tmp_path.write_bytes(enc)
        tmp_path.replace(path)

        return path

    def load(self, label: str,
             bubble=None,
             subdir: str = "") -> Optional[str]:
        """
        Wczytuje i deszyfruje tresc z magazynu.
        Zwraca None jesli plik nie istnieje.
        Rzuca ValueError jesli nie mozna deszyfrowa (zly klucz).
        """
        target_dir = self._store_dir / subdir if subdir else self._store_dir
        path = target_dir / f"{label}{self.EXT}"

        if not path.exists():
            return None

        raw = path.read_bytes()
        data = self._decrypt(raw, bubble=bubble)
        try:
            return data.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError(
                f"Nie mozna odczytac '{label}' — zly klucz lub uszkodzone dane."
            )

    def exists(self, label: str, subdir: str = "") -> bool:
        target_dir = self._store_dir / subdir if subdir else self._store_dir
        return (target_dir / f"{label}{self.EXT}").exists()

    def delete(self, label: str, subdir: str = "") -> bool:
        target_dir = self._store_dir / subdir if subdir else self._store_dir
        path = target_dir / f"{label}{self.EXT}"
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    def list_labels(self, subdir: str = "") -> list[str]:
        """Lista wszystkich zapisanych etykiet."""
        target_dir = self._store_dir / subdir if subdir else self._store_dir
        if not target_dir.exists():
            return []
        return [p.stem for p in target_dir.glob(f"*{self.EXT}")]

    # ── Pliki tymczasowe (dla edytorow) ──────────────────────────────────────

    def materialize(self, label: str, content: str,
                    ext: str = ".txt") -> Path:
        """
        Zapisuje plaintext do pliku tymczasowego (dla edytorow TUI/GUI).
        Plik tymczasowy NIGDY nie jest szyfrowany — zyje tylko podczas edycji.
        """
        path = self._tmp_dir / f"{label}{ext}"
        path.write_text(content, encoding='utf-8')
        return path

    def read_tmp(self, label: str, ext: str = ".txt") -> Optional[str]:
        """Czyta plik tymczasowy po edycji."""
        path = self._tmp_dir / f"{label}{ext}"
        if path.exists():
            return path.read_text(encoding='utf-8')
        return None

    def cleanup_tmp(self, label: str, ext: str = ".txt") -> None:
        """Usuwa plik tymczasowy po synchronizacji z magazynem."""
        path = self._tmp_dir / f"{label}{ext}"
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        labels = self.list_labels()
        return {
            "store_dir":    str(self._store_dir),
            "n_files":      len(labels),
            "mode":         self._default_mode,
            "has_key":      self._system_phi is not None,
            "labels":       labels,
        }


# ===========================================================================
# INTEGRACJA Z RUNTIME — PATCH
# ===========================================================================

def attach_to_runtime(runtime, identity_bubble_label: str = None) -> PhiStore:
    """
    Podlacza PhiStore do istniejacego SanctuaryRuntime.

    Wywolaj po inicjalizacji runtime:
        from phi_store import attach_to_runtime
        attach_to_runtime(RUNTIME)

    Lub w runtime.__init__:
        self.phi_store = attach_to_runtime(self)

    Automatycznie wykrywa Babl tozsamosci systemu ([Phi-ID]).
    """
    identity_phi = None

    # Szukaj Babla tozsamosci ([Phi-ID])
    if identity_bubble_label and identity_bubble_label in runtime._bubbles:
        b = runtime._bubbles[identity_bubble_label]
        if b.phi1:
            identity_phi = b.phi1.signature

    # Fallback: pierwszy Babl z depth=3 lub pierwszy dostepny
    if identity_phi is None:
        for label, b in runtime._bubbles.items():
            if b.phi1 is not None:
                identity_phi = b.phi1.signature
                break

    # Fallback: hash z phi_epoch jesli brak Babli
    if identity_phi is None and hasattr(runtime, 'phi'):
        epoch_bytes = str(runtime.phi.epoch).encode()
        # Uzywamy bajtow jako liczb 0-255, nie jako raw float32
        # (raw float32 moze dac NaN/Inf z losowych bajtow)
        raw = list(hashlib.sha256(epoch_bytes).digest()[:15])
        arr = np.array(raw, dtype=np.float32)
        norm = np.linalg.norm(arr)
        identity_phi = arr / norm if norm > 1e-8 else arr

    store = PhiStore(
        identity_phi  = identity_phi,
        default_mode  = 'noise',
    )
    runtime.phi_store = store
    return store


# ===========================================================================
# TESTY
# ===========================================================================

def _run_tests() -> None:
    import tempfile
    import shutil

    print("=" * 55)
    print("phi_store.py — testy")
    print("=" * 55)

    passed = failed = 0

    def chk(name, ok, detail=""):
        nonlocal passed, failed
        print(f"  {'OK' if ok else 'XX'}  {name}")
        if detail and not ok:
            print(f"      {detail}")
        if ok: passed += 1
        else:  failed += 1

    # Tymczasowy katalog dla testow
    tmpdir = tempfile.mkdtemp()
    try:
        rng = np.random.default_rng(42)
        phi = rng.standard_normal(15).astype(np.float32)
        phi = phi / np.linalg.norm(phi)

        store = PhiStore(
            identity_phi = phi,
            store_dir    = os.path.join(tmpdir, "store"),
            tmp_dir      = os.path.join(tmpdir, "tmp"),
            default_mode = 'noise',
        )

        # [1] Podstawowy zapis/odczyt NOISE
        print("\n[1] Tryb NOISE")
        store.save("test1", "Hello KarmazynOS!")
        loaded = store.load("test1")
        chk("save/load round-trip", loaded == "Hello KarmazynOS!",
            f"got: {repr(loaded)}")

        # Plik na dysku to szum
        raw = (Path(tmpdir) / "store" / "test1.kos").read_bytes()
        chk("plik na dysku nie jest plaintext",
            b"Hello" not in raw,
            f"plaintext widoczny w pliku!")
        chk("naglowek NOISE",
            raw[:HEADER_LEN] == HEADER_NOISE)

        # [2] Rozny klucz — nie moze odczytac
        print("\n[2] Inny klucz = szum")
        phi2 = rng.standard_normal(15).astype(np.float32)
        phi2 = phi2 / np.linalg.norm(phi2)
        store2 = PhiStore(
            identity_phi = phi2,
            store_dir    = os.path.join(tmpdir, "store"),
            tmp_dir      = os.path.join(tmpdir, "tmp"),
        )
        loaded_wrong = None
        try:
            loaded_wrong = store2.load("test1")
        except (UnicodeDecodeError, ValueError):
            loaded_wrong = None  # oczekiwany wynik — nieczytelne
        chk("inny klucz = nieczytelne (UnicodeDecodeError lub garbled)",
            loaded_wrong != "Hello KarmazynOS!",
            f"got: {repr(loaded_wrong)}")

        # [3] Tryb PLAIN
        print("\n[3] Tryb PLAIN")
        store.save("test_plain", "plaintext data", mode='plain')
        raw_plain = (Path(tmpdir) / "store" / "test_plain.kos").read_bytes()
        chk("PLAIN: tresc widoczna w pliku",
            b"plaintext data" in raw_plain)
        chk("PLAIN: round-trip OK",
            store.load("test_plain") == "plaintext data")

        # [4] Tryb FULL z pseudo-Bablem
        print("\n[4] Tryb FULL")
        class FakePhi1:
            signature = rng.standard_normal(15).astype(np.float32)
            signature /= np.linalg.norm(signature)
        class FakeBubble:
            label = "fake"
            phi1  = FakePhi1()
            phi2  = rng.standard_normal(15).astype(np.float32)
            phi2 /= np.linalg.norm(phi2)

        fb = FakeBubble()
        store.save("test_full", "secret data", bubble=fb, mode='full')
        loaded_full = store.load("test_full", bubble=fb)
        chk("FULL: round-trip OK", loaded_full == "secret data")

        raw_full = (Path(tmpdir) / "store" / "test_full.kos").read_bytes()
        chk("FULL: naglowek FULL",
            raw_full[:HEADER_LEN] == HEADER_FULL)
        chk("FULL: tresc niewidoczna",
            b"secret" not in raw_full)

        # [5] exists / delete / list
        print("\n[5] Operacje na plikach")
        chk("exists: True dla zapisanego", store.exists("test1"))
        chk("exists: False dla nieistniejacego", not store.exists("brak"))
        store.delete("test1")
        chk("delete: plik usuniety", not store.exists("test1"))
        labels = store.list_labels()
        chk("list_labels zawiera test_plain",
            "test_plain" in labels,
            f"labels: {labels}")

        # [6] Pliki tymczasowe
        print("\n[6] Pliki tymczasowe")
        tmp_path = store.materialize("edit_dom", "edytowana tresc", ext=".py")
        chk("materialize tworzy plik", tmp_path.exists())
        content  = store.read_tmp("edit_dom", ext=".py")
        chk("read_tmp odczytuje", content == "edytowana tresc")
        # Plik tmp to plaintext
        raw_tmp = tmp_path.read_bytes()
        chk("tmp nie jest szyfrowany", b"edytowana tresc" in raw_tmp)
        store.cleanup_tmp("edit_dom", ext=".py")
        chk("cleanup_tmp usuwa plik", not tmp_path.exists())

        # [7] Atomowy zapis (crash-safe)
        print("\n[7] Atomowy zapis")
        store.save("atomic", "wersja 1")
        store.save("atomic", "wersja 2")
        chk("nadpisanie dziala", store.load("atomic") == "wersja 2")

        # [8] Unicode / polskie znaki
        print("\n[8] Unicode")
        tekst = "Bąble i Hologramy — KarmazynOS żyje!"
        store.save("unicode_test", tekst)
        chk("polskie znaki round-trip",
            store.load("unicode_test") == tekst)

        # [9] Status
        print("\n[9] Status")
        s = store.status()
        chk("status ma klucz", s["has_key"])
        chk("status tryb noise", s["mode"] == "noise")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    total = passed + failed
    print(f"\n{'='*55}")
    print(f"Wyniki: {passed}/{total}")
    if failed == 0:
        print("PASS — PhiStore operacyjny")
    else:
        print(f"FAIL — {failed} testow nie przeszlo")
    print("=" * 55)


if __name__ == "__main__":
    _run_tests()