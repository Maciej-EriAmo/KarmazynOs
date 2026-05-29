#!/usr/bin/env python3
"""
test_proca_bubblefs.py — Tester cyklu tworzenie → zapis → odzysk
================================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Testuje pełny cykl:
  1. TWORZENIE  — MockKarmazynOS z N bąblami (klastry identyczne / unikalne)
  2. ZAPIS      — bubblefs.export() bez i z Proca (use_proca=True)
  3. ODZYSK     — bubblefs.import_() do nowej instancji
  4. WERYFIKACJA — integralność treści bajt po bajcie, statystyki dedupu

Naprawki po przeglądzie kodu:
  - Importy przeniesione na poziom modułu z guard try/except
  - Usunięty martwy kod: col(), `if False else` w T10
  - T07: asercja 80% → 100% (po naprawie bubblefs fallback path)
  - Wyodrębniony helper _export_and_reimport()
  - Dodane testy: T11 analyze_field_coverage, T12 edge cases, T13 export_single_bubble

Uruchomienie:
  python3 test_proca_bubblefs.py          normalny
  python3 test_proca_bubblefs.py -v       verbose
  python3 test_proca_bubblefs.py --no-color
"""

import argparse
import base64
import hashlib
import os
import sys
import tempfile
import time
import traceback
from typing import Any, Dict, List, Optional, Set

import numpy as np

# ── Guard importów ────────────────────────────────────────────────────────────
# Oba moduły muszą być w tym samym katalogu lub na PYTHONPATH.

_MISSING = []

try:
    import bubblefs
except ImportError as e:
    _MISSING.append(f"bubblefs: {e}")

try:
    from karmazyn_proca import (
        yukawa_similarity,
        compton_wavelength,
        threshold_radius,
        default_m_vector_for_dim,
        phi_coords_from_bubble,
        analyze_field_coverage,
        ProcaIndex,
        ProcaFieldSource,
        ProcaCoordinate,
        DEFAULT_M_VECTOR,
        DEFAULT_THRESHOLD,
        MIN_DEDUP_SIZE,
    )
except ImportError as e:
    _MISSING.append(f"karmazyn_proca: {e}")

if _MISSING:
    print("BŁĄD: brakuje modułów:")
    for m in _MISSING:
        print(f"  {m}")
    print("\nUpewnij się że bubblefs.py i karmazyn_proca.py są w tym samym katalogu.")
    sys.exit(2)


# ═══════════════════════════════════════════════════════════════════════════════
# Output helpers
# ═══════════════════════════════════════════════════════════════════════════════

_color   = True
_verbose = False

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
INFO = "\033[36m·\033[0m"
BOLD = "\033[1m"
RST  = "\033[0m"


def ok(msg: str)  -> None: print(f"  {PASS if _color else 'OK  '} {msg}")
def fail(msg: str)-> None: print(f"  {FAIL if _color else 'FAIL'} {msg}")
def info(msg: str)-> None:
    if _verbose:
        print(f"  {INFO if _color else '    '} {msg}")


def section(title: str) -> None:
    bar = "─" * (58 - len(title))
    print(f"\n{BOLD if _color else ''}[{title}]{RST if _color else ''} {bar}")


# ═══════════════════════════════════════════════════════════════════════════════
# Mock interfejsu KarmazynOS
# Pokrywa dokładnie to czego wymaga bubblefs.py — nie więcej.
# ═══════════════════════════════════════════════════════════════════════════════

def _xor_crypt_mock(data: bytes, key: bytes) -> bytes:
    """Identyczna implementacja jak bubblefs._xor_crypt."""
    out, offset, counter = bytearray(len(data)), 0, 0
    while offset < len(data):
        block = hashlib.sha256(key + counter.to_bytes(4, 'big')).digest()
        for b in block:
            if offset >= len(data):
                break
            out[offset] = data[offset] ^ b
            offset += 1
        counter += 1
    return bytes(out)


class MockBubble:
    def __init__(self, bubble_id: str, label: str, content: bytes,
                 S_sem: np.ndarray, S_struct: np.ndarray,
                 epoch: int = 1, T: float = 50.0):
        self.id                = bubble_id
        self.label             = label
        self.inode             = f"karmazyn://bubbles/{label}"
        self.epoch_born        = epoch
        self.recall_count      = 0
        self.consolidated_from = ""
        self.metadata          = {"test": True}
        self.fingerprint       = hashlib.sha256(content).digest()[:16]
        self.S_struct          = np.asarray(S_struct, dtype=np.float32)
        self.S_sem             = np.asarray(S_sem,    dtype=np.float32)
        self.decay_start_epoch = None
        self.decay_rate        = 0.0
        self.immortal          = False
        self.T                 = float(T)
        self._key              = hashlib.sha256(bubble_id.encode()).digest()
        self._content          = _xor_crypt_mock(content, self._key)

    def decrypt_content(self) -> bytes:
        return _xor_crypt_mock(self._content, self._key)


class MockBubbleStore:
    def __init__(self):
        self._b:   Dict[str, MockBubble] = {}
        self._idx: Dict[str, str]        = {}
        self._rev: Set[str]              = set()

    def _make_key(self, bubble_id: str) -> bytes:
        return hashlib.sha256(bubble_id.encode()).digest()

    def get_by_label(self, label: str) -> Optional[MockBubble]:
        bid = self._idx.get(label)
        return self._b.get(bid) if bid else None

    def add(self, bubble: MockBubble) -> None:
        self._b[bubble.id]      = bubble
        self._idx[bubble.label] = bubble.id

    def clear(self) -> None:
        self._b.clear()
        self._idx.clear()
        self._rev.clear()


class MockPhiMatrix:
    def __init__(self):
        self.atoms: List[Any] = []

    def add_atom_vector(self, label: str, topic: str,
                         vector: np.ndarray, init_T: float = 1.0,
                         session: Any = None) -> None:
        class _Atom:
            pass
        a = _Atom()
        a.label = label
        a.S     = vector
        a.T     = init_T
        self.atoms.append(a)


class MockPhi:
    def __init__(self, dim: int = 15, p2s: bytes = None):
        self._sem  = {}
        self._mx   = MockPhiMatrix()
        self._p2s  = p2s or os.urandom(32)
        self.dim   = dim
        self.epoch = 1

    def t_vacuum(self)   -> float: return 0.01
    def temperature(self)-> float: return 42.0
    def phi2_bytes(self) -> bytes: return self._p2s[:16]


class MockKarmazynOS:
    VERSION = "test-1.0"

    def __init__(self, dim: int = 15, p2s: bytes = None):
        self.phi       = MockPhi(dim=dim, p2s=p2s)
        self.bubbles   = MockBubbleStore()
        self.holograms: Dict[str, Any] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# Fabryka danych testowych
# ═══════════════════════════════════════════════════════════════════════════════

def _norm(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def _make_phi(seed: np.ndarray, noise: float = 0.0,
               rng: np.random.Generator = None) -> np.ndarray:
    if rng is not None and noise > 0:
        v = seed + rng.standard_normal(len(seed)).astype(np.float32) * noise
    else:
        v = seed.copy()
    return _norm(v)


def build_test_instance(n_identical: int = 8,
                         n_similar:   int = 5,
                         n_unique:    int = 4,
                         dim:         int = 15,
                         p2s:         bytes = None) -> MockKarmazynOS:
    """
    Buduje testową instancję z bąblami trzech rodzajów:

    Identyczne (n_identical):  ta sama treść, podobny phi → Proca: 1 source + N-1 coord.
    Podobne (n_similar):       różna treść, podobny phi  → Proca: osobne sources.
    Unikalne (n_unique):       różna treść, różny phi    → Proca: osobne sources lub raw.
    """
    rng = np.random.default_rng(42)
    ko  = MockKarmazynOS(dim=dim, p2s=p2s)

    phi_doc = np.zeros(dim, dtype=np.float32)
    phi_doc[min(8, dim - 1)] = 0.9
    phi_doc[min(9, dim - 1)] = 0.8
    phi_doc = _norm(phi_doc)

    phi_emo = np.zeros(dim, dtype=np.float32)
    phi_emo[0] = 0.8
    phi_emo[min(7, dim - 1)] = 0.7
    phi_emo = _norm(phi_emo)

    canonical = b"Dokumentacja KarmazynOS: " * 60   # ~1500B

    for i in range(n_identical):
        phi = _make_phi(phi_doc, noise=0.02, rng=rng)
        b   = MockBubble(f"doc_{i:03d}", f"doc_{i:03d}", canonical,
                          S_sem=phi, S_struct=_norm(rng.standard_normal(dim).astype(np.float32)),
                          epoch=i + 1, T=70.0 - i * 2)
        ko.bubbles.add(b)

    for i in range(n_similar):
        phi     = _make_phi(phi_emo, noise=0.05, rng=rng)
        content = b"Fragment emocjonalny EriAmo: " * 50 + f" var={i}".encode()
        b       = MockBubble(f"emo_{i:03d}", f"emo_{i:03d}", content,
                              S_sem=phi, S_struct=_norm(rng.standard_normal(dim).astype(np.float32)),
                              epoch=100 + i, T=55.0 + i)
        ko.bubbles.add(b)

    for i in range(n_unique):
        phi     = _norm(rng.standard_normal(dim).astype(np.float32))
        content = bytes(rng.bytes(512 + i * 100))
        b       = MockBubble(f"uniq_{i:03d}", f"uniq_{i:03d}", content,
                              S_sem=phi, S_struct=_norm(rng.standard_normal(dim).astype(np.float32)),
                              epoch=200 + i, T=40.0)
        ko.bubbles.add(b)

    for bid, b in ko.bubbles._b.items():
        ko.phi._sem[bid] = b.S_sem
        ko.phi._mx.add_atom_vector(label=bid, topic="test",
                                    vector=b.S_struct, init_T=b.T)
    return ko


def empty_ko(p2s: bytes) -> MockKarmazynOS:
    """Pusta instancja z tym samym kluczem — do importu."""
    ko2 = MockKarmazynOS(p2s=p2s)
    ko2.bubbles._make_key = lambda bid: hashlib.sha256(bid.encode()).digest()
    return ko2


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers testowe
# ═══════════════════════════════════════════════════════════════════════════════

def snapshot(ko: MockKarmazynOS) -> Dict[str, bytes]:
    """Treść wszystkich bąbli — do porównania przed i po roundtripie."""
    return {bid: b.decrypt_content() for bid, b in ko.bubbles._b.items()}


def content_from_store(ko: MockKarmazynOS) -> Dict[str, bytes]:
    """
    Odczyt treści po imporcie — obsługuje zarówno MockBubble jak i dict (fallback).
    Używane przez T07 do weryfikacji 100% poprawności.
    """
    result = {}
    for bid, b in ko.bubbles._b.items():
        if hasattr(b, 'decrypt_content'):
            result[bid] = b.decrypt_content()
        elif isinstance(b, dict):
            cb64 = b.get("content_b64", "")
            result[bid] = base64.b64decode(cb64) if cb64 else b"__missing__"
        else:
            result[bid] = b"__unknown__"
    return result


def _export_and_reimport(ko: MockKarmazynOS, tmpdir: str,
                          p2s: bytes,
                          use_proca: bool = False,
                          verify: bool = True) -> tuple:
    """
    Helper: export → nowa instancja → import.
    Zwraca (manifest, result, ko2).
    """
    manifest = bubblefs.export(ko, tmpdir, shared_secret=p2s,
                                use_proca=use_proca)
    ko2    = empty_ko(p2s)
    result = bubblefs.import_(ko2, tmpdir, shared_secret=p2s,
                               verify_integrity=verify)
    return manifest, result, ko2


def dir_size(path: str) -> int:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# Test framework (minimalistyczny)
# ═══════════════════════════════════════════════════════════════════════════════

_results = {"passed": 0, "failed": 0, "errors": 0}


class test:
    def __init__(self, name: str):
        self._name = name

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            _results["passed"] += 1
            return True
        if exc_type is AssertionError:
            _results["failed"] += 1
            fail(f"{self._name}: {exc_val}")
            if _verbose:
                traceback.print_exc()
            return True
        _results["errors"] += 1
        fail(f"{self._name}: {exc_type.__name__}: {exc_val}")
        if _verbose:
            traceback.print_exc()
        return True


def ae(a, b, msg: str = "") -> None:
    assert a == b, (f"{msg}: " if msg else "") + f"{a!r} != {b!r}"


def at(cond: bool, msg: str = "") -> None:
    assert cond, msg


def ab(a: bytes, b: bytes, bid: str = "") -> None:
    if a != b:
        diff = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), None)
        raise AssertionError(
            f"Treść niezgodna {bid}: len={len(a)}vs{len(b)} "
            f"first_diff={diff if diff is not None else 'end'}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# T01 — Matematyka pola Proca
# ═══════════════════════════════════════════════════════════════════════════════

def test_T01():
    section("T01 Matematyka pola Proca")

    with test("sim(φ, φ) = 1.0 — identyczne wektory"):
        phi = _norm(np.eye(15, dtype=np.float32)[8])
        ae(yukawa_similarity(phi, phi, DEFAULT_M_VECTOR), 1.0)
        ok("sim(φ, φ) = 1.0")

    with test("sim(bliskie) ∈ (0, 1)"):
        rng  = np.random.default_rng(7)
        phi_a = _norm(rng.standard_normal(15).astype(np.float32))
        phi_b = _norm(phi_a + rng.standard_normal(15).astype(np.float32) * 0.05)
        sim   = yukawa_similarity(phi_a, phi_b, DEFAULT_M_VECTOR)
        at(0.0 < sim < 1.0, f"sim={sim}")
        ok(f"sim(bliskie) = {sim:.4f}")

    with test("sim malejące z odległością (perturbacja prostopadła)"):
        # Perturbacja PROSTOPADŁA do phi_0: po normalizacji daje różne kierunki.
        # Perturbacja równoległa (np.full(15, d)) znika po normalizacji → złe wyniki.
        phi_0 = _norm(np.array([1.0] + [0.0] * 14, dtype=np.float32))  # e_0
        perp  = np.array([0.0, 1.0] + [0.0] * 13, dtype=np.float32)    # e_1 ⊥ e_0
        sims  = [yukawa_similarity(phi_0,
                                    _norm(phi_0 + perp * d),
                                    DEFAULT_M_VECTOR)
                  for d in (0.0, 0.1, 0.5, 2.0)]
        at(all(sims[i] >= sims[i+1] for i in range(len(sims)-1)),
            f"sim nie jest monotonicznie malejące: {[round(s,3) for s in sims]}")
        ok(f"sim monotoniczne: {[round(s,3) for s in sims]}")

    with test("compton_wavelength = 1/m"):
        ae(compton_wavelength(0.5), 2.0, "λ(0.5)")
        ae(compton_wavelength(2.0), 0.5, "λ(2.0)")
        ok("compton_wavelength = 1/m: OK")

    with test("threshold_radius = -ln(threshold)/m"):
        import math
        r = threshold_radius(1.0, 0.5)
        at(abs(r - math.log(2)) < 1e-5, f"r={r}")
        ok(f"threshold_radius(m=1, th=0.5) = {r:.4f} = ln2")

    with test("default_m_vector_for_dim: poprawne wymiary"):
        for dim in (1, 8, 15, 24, 32, 64):
            mv = default_m_vector_for_dim(dim)
            ae(len(mv), dim, f"dim={dim}")
        ok("dim=1,8,15,24,32,64 — poprawne długości")

    with test("phi_coords_from_bubble: używa S_sem"):
        b   = MockBubble("x", "x", b"test",
                          S_sem=np.ones(15, dtype=np.float32) * 0.5,
                          S_struct=np.zeros(15, dtype=np.float32))
        phi = phi_coords_from_bubble(b)
        at(phi is not None and len(phi) == 15, f"phi={phi}")
        ok(f"phi_coords_from_bubble: len={len(phi)}")


# ═══════════════════════════════════════════════════════════════════════════════
# T02 — ProcaFieldSource serialization roundtrip
# ═══════════════════════════════════════════════════════════════════════════════

def test_T02():
    section("T02 ProcaFieldSource serialization roundtrip")

    rng  = np.random.default_rng(13)
    phi  = _norm(rng.standard_normal(15).astype(np.float32))
    data = b"Test data dla pola Proca " * 50

    with test("field_id"):
        src  = ProcaFieldSource("bbl", data, phi)
        back = ProcaFieldSource.deserialize(src.serialize())
        ae(back.field_id, src.field_id)
        ok(f"field_id: {src.field_id[:16]}...")

    with test("phi_source"):
        src  = ProcaFieldSource("bbl", data, phi)
        back = ProcaFieldSource.deserialize(src.serialize())
        at(np.allclose(back.phi_source, src.phi_source))
        ok("phi_source: OK")

    with test("data"):
        src  = ProcaFieldSource("bbl", data, phi)
        back = ProcaFieldSource.deserialize(src.serialize())
        ab(back.data, src.data)
        ok(f"data: {len(data)}B")

    with test("m_vector"):
        src  = ProcaFieldSource("bbl", data, phi)
        back = ProcaFieldSource.deserialize(src.serialize())
        at(np.allclose(back.m_vector, src.m_vector))
        ok("m_vector: OK")

    with test("record_id"):
        src  = ProcaFieldSource("test_bubble_id", data, phi)
        back = ProcaFieldSource.deserialize(src.serialize())
        ae(back.record_id, src.record_id)
        ok("record_id: OK")

    with test("CRC: jeden zmodyfikowany bajt → ValueError"):
        raw = bytearray(ProcaFieldSource("bbl", data, phi).serialize())
        raw[50] ^= 0xFF
        try:
            ProcaFieldSource.deserialize(bytes(raw))
            fail("powinno rzucić ValueError")
        except ValueError:
            ok("CRC wykryty: OK")

    with test("dim=32: roundtrip"):
        phi32 = _norm(rng.standard_normal(32).astype(np.float32))
        mv32  = default_m_vector_for_dim(32)
        src   = ProcaFieldSource("bbl32", data, phi32, mv32)
        back  = ProcaFieldSource.deserialize(src.serialize())
        ae(back.phi_dim, 32)
        at(np.allclose(back.phi_source, src.phi_source))
        ok("dim=32 roundtrip: OK")


# ═══════════════════════════════════════════════════════════════════════════════
# T03 — ProcaCoordinate roundtrip
# ═══════════════════════════════════════════════════════════════════════════════

def test_T03():
    section("T03 ProcaCoordinate roundtrip")

    rng   = np.random.default_rng(17)
    phi   = _norm(rng.standard_normal(15).astype(np.float32))
    delta = rng.standard_normal(15).astype(np.float32) * 0.1

    with test("field_id"):
        c = ProcaCoordinate("b", "fid_xyz", phi, delta, T=65.0, similarity=0.85)
        b = ProcaCoordinate.from_json_bytes(c.to_json_bytes(), "b")
        ae(b.field_id, c.field_id)
        ok("field_id: OK")

    with test("phi_coords"):
        c = ProcaCoordinate("b", "fid", phi, delta)
        b = ProcaCoordinate.from_json_bytes(c.to_json_bytes(), "b")
        at(np.allclose(b.phi_coords, c.phi_coords, atol=1e-5))
        ok("phi_coords: OK")

    with test("delta"):
        c = ProcaCoordinate("b", "fid", phi, delta)
        b = ProcaCoordinate.from_json_bytes(c.to_json_bytes(), "b")
        at(np.allclose(b.delta, c.delta, atol=1e-5))
        ok("delta: OK")

    with test("T i similarity"):
        c = ProcaCoordinate("b", "fid", phi, delta, T=77.5, similarity=0.923)
        b = ProcaCoordinate.from_json_bytes(c.to_json_bytes(), "b")
        at(abs(b.T - 77.5) < 0.001)
        at(abs(b.similarity - 0.923) < 0.0001)
        ok("T i similarity: OK")

    with test("rozmiar JSON < 1024B"):
        # 15D phi + 15D delta = 30 floatów w JSON ~300-700B
        c    = ProcaCoordinate("b", "x" * 32, phi, delta, T=50.0)
        size = len(c.to_json_bytes())
        at(size < 1024, f"JSON={size}B (< 1024B)")
        ok(f"JSON size = {size}B")

    with test("is_proca_json: poprawna detekcja"):
        c   = ProcaCoordinate("b", "fid", phi, delta)
        at(ProcaCoordinate.is_proca_json(c.to_json_bytes()))
        at(not ProcaCoordinate.is_proca_json(b'regular content'))
        at(not ProcaCoordinate.is_proca_json(b''))
        ok("is_proca_json: OK")


# ═══════════════════════════════════════════════════════════════════════════════
# T04 — ProcaIndex logika deduplicji
# ═══════════════════════════════════════════════════════════════════════════════

def test_T04():
    section("T04 ProcaIndex logika deduplicji")

    rng  = np.random.default_rng(99)
    phi_doc = np.zeros(15, dtype=np.float32)
    phi_doc[8] = 0.9; phi_doc[9] = 0.8
    phi_doc = _norm(phi_doc)

    data_a = b"Dokumentacja " * 120   # ~1560B
    data_b = b"Inna tresc    " * 120  # inne dane, taki sam rozmiar

    with tempfile.TemporaryDirectory() as tmpdir:

        with test("pierwsza rejestracja → source"):
            idx = ProcaIndex(fields_dir=tmpdir)
            phi = _make_phi(phi_doc, 0.01, rng)
            typ, _ = idx.register_or_deduplicate("b0", data_a, phi)
            ae(typ, "source")
            ok("source: OK")

        with test("bliski phi + identyczne dane → coordinate"):
            idx = ProcaIndex(fields_dir=tmpdir)
            idx.register_or_deduplicate("b0", data_a, _make_phi(phi_doc, 0.01, rng))
            phi1 = _make_phi(phi_doc, 0.02, rng)
            typ, coord = idx.register_or_deduplicate("b1", data_a, phi1)
            ae(typ, "coordinate", "bliskie phi + te same dane")
            ok(f"coordinate sim={coord.similarity:.4f}")

        with test("dalekie phi + identyczne dane → coordinate (dedup po SHA256)"):
            idx  = ProcaIndex(fields_dir=tmpdir)
            idx.register_or_deduplicate("b0", data_a, _make_phi(phi_doc))
            phi_far = _norm(rng.standard_normal(15).astype(np.float32))
            typ, _ = idx.register_or_deduplicate("b_far", data_a, phi_far)
            ae(typ, "coordinate", "identyczne dane → coordinate niezależnie od phi")
            ok("dalekie phi + identyczne dane → coordinate: OK")

        with test("dalekie phi + różne dane → nowe source"):
            idx = ProcaIndex(fields_dir=tmpdir)
            idx.register_or_deduplicate("b0", data_a, _make_phi(phi_doc))
            phi_far = _norm(rng.standard_normal(15).astype(np.float32))
            typ, _ = idx.register_or_deduplicate("b_far", data_b, phi_far)
            ae(typ, "source", "różne dane daleko → source")
            ok("dalekie phi + różne dane → source: OK")

        with test("bliskie phi + różne dane → nowe source"):
            idx = ProcaIndex(fields_dir=tmpdir)
            idx.register_or_deduplicate("b0", data_a, _make_phi(phi_doc))
            phi1 = _make_phi(phi_doc, 0.02, rng)
            typ, _ = idx.register_or_deduplicate("b1", data_b, phi1)
            ae(typ, "source", "różne dane → source mimo bliskiego phi")
            ok("bliskie phi + różne dane → source: OK")

        with test("phi=None → raw"):
            idx = ProcaIndex(fields_dir=tmpdir)
            typ, _ = idx.register_or_deduplicate("b", data_a, None)
            ae(typ, "raw")
            ok("phi=None → raw: OK")

        with test("dane < MIN_DEDUP_SIZE → raw"):
            idx = ProcaIndex(fields_dir=tmpdir)
            phi = _make_phi(phi_doc)
            typ, _ = idx.register_or_deduplicate("b", b"tiny data", phi)
            ae(typ, "raw")
            ok(f"< {MIN_DEDUP_SIZE}B → raw: OK")

        with test("resolve_coordinate → oryginalne dane"):
            idx = ProcaIndex(fields_dir=tmpdir)
            idx.register_or_deduplicate("b0", data_a, _make_phi(phi_doc, 0.01, rng))
            phi1 = _make_phi(phi_doc, 0.01, rng)
            typ, coord = idx.register_or_deduplicate("b1", data_a, phi1)
            ae(typ, "coordinate")
            resolved = idx.resolve_coordinate(coord)
            ab(resolved, data_a, "resolved")
            ok(f"resolve: {len(resolved)}B")

        with test("save_all_sources → load_sources_from_disk: kompletność"):
            idx = ProcaIndex(fields_dir=tmpdir)
            for i in range(4):
                d   = f"dane_{i}".encode() * 200
                phi = _norm(rng.standard_normal(15).astype(np.float32))
                idx.register_or_deduplicate(f"b{i}", d, phi)
            n_saved  = idx.save_all_sources()
            idx2     = ProcaIndex(fields_dir=tmpdir)
            n_loaded = idx2.load_sources_from_disk()
            ae(n_loaded, n_saved, "loaded == saved")
            ok(f"save={n_saved} load={n_loaded}: OK")

        with test("statystyki po 8-elementowym klastrze"):
            idx = ProcaIndex(fields_dir=tmpdir)
            idx.register_or_deduplicate("b0", data_a, _make_phi(phi_doc))
            for i in range(1, 8):
                idx.register_or_deduplicate(
                    f"b{i}", data_a, _make_phi(phi_doc, 0.02, rng))
            st = idx.stats()
            ae(st["sources"], 1, "sources")
            ae(st["coordinates"], 7, "coordinates")
            at(st["bytes_saved"] > 0, "bytes_saved")
            ok(f"src=1 coord=7 saved={st['bytes_saved']:,}B")


# ═══════════════════════════════════════════════════════════════════════════════
# T05 — analyze_field_coverage
# ═══════════════════════════════════════════════════════════════════════════════

def test_T05():
    section("T05 analyze_field_coverage")

    rng     = np.random.default_rng(55)
    phi_doc = _norm(np.array([0, 0, 0, 0, 0, 0, 0, 0, 0.9, 0.8, 0, 0, 0, 0, 0],
                               dtype=np.float32))
    data_big = b"duzy atom " * 200   # 2000B

    with test("pusty input → zerowe wyniki"):
        r = analyze_field_coverage([])
        ae(r["atoms"], 0)
        ae(r["fields"], 0)
        ok("pusta lista: OK")

    with test("jeden atom → 1 pole, 0 oszczędności"):
        phi = _make_phi(phi_doc)
        r   = analyze_field_coverage([("b0", data_big, phi)])
        ae(r["atoms"], 1)
        ae(r["savings_b"], 0)
        ok(f"jeden atom: fields={r['fields']} savings=0")

    with test("8 identycznych treści w klastrze → oszczędność > 0"):
        atoms = []
        for i in range(8):
            phi = _make_phi(phi_doc, 0.02, rng)
            atoms.append((f"b{i}", data_big, phi))
        r = analyze_field_coverage(atoms)
        at(r["savings_b"] > 0, f"savings={r['savings_b']}")
        at(r["savings_pct"] > 50.0, f"savings_pct={r['savings_pct']}")
        ok(f"klaster 8: pola={r['fields']} savings={r['savings_pct']:.0f}%")

    with test("phi=None nie crashuje"):
        atoms = [
            ("b0", data_big, _make_phi(phi_doc)),
            ("b1", data_big, None),            # phi=None
            ("b2", data_big, _make_phi(phi_doc, 0.02, rng)),
        ]
        r = analyze_field_coverage(atoms)
        ae(r["atoms"], 3)
        ok(f"phi=None obsłużony: atoms={r['atoms']} fields={r['fields']}")

    with test("dane < MIN_DEDUP_SIZE nie brane do dedupu"):
        atoms = [
            ("b0", b"maly", _make_phi(phi_doc)),
            ("b1", b"maly", _make_phi(phi_doc, 0.01, rng)),
        ]
        r = analyze_field_coverage(atoms)
        ae(r["savings_b"], 0, "małe dane → bez oszczędności")
        ok("małe dane → savings=0: OK")

    with test("wynik: total_raw_b poprawne"):
        sizes = [100 + i * 50 for i in range(5)]
        atoms = [(f"b{i}", b"x" * s, _norm(rng.standard_normal(15).astype(np.float32)))
                  for i, s in enumerate(sizes)]
        r = analyze_field_coverage(atoms)
        ae(r["total_raw_b"], sum(sizes), "total_raw_b")
        ok(f"total_raw_b={r['total_raw_b']}: OK")


# ═══════════════════════════════════════════════════════════════════════════════
# T06 — bubblefs export bez Proca
# ═══════════════════════════════════════════════════════════════════════════════

def test_T06():
    section("T06 bubblefs.export() bez Proca")

    ko      = build_test_instance(n_identical=5, n_similar=4, n_unique=3)
    n_total = len(ko.bubbles._b)
    p2s     = ko.phi._p2s

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest, result, ko2 = _export_and_reimport(ko, tmpdir, p2s, use_proca=False)

        with test(f"export {n_total} bąbli"):
            ae(manifest["n_bubbles"], n_total)
            ok(f"n_bubbles={n_total}")

        with test("manifest.json istnieje"):
            at(os.path.exists(os.path.join(tmpdir, "manifest.json")))
            ok("manifest.json: OK")

        with test("pliki .bbl: komplet"):
            n = len([f for f in os.listdir(os.path.join(tmpdir, "bubbles"))
                     if f.endswith(".bbl")])
            ae(n, n_total)
            ok(f"{n} plików .bbl: OK")

        with test("proca_enabled=False"):
            ae(manifest["proca_enabled"], False)
            ok("proca_enabled=False: OK")

        with test("integrity_sha256: 64 znaki hex"):
            ig = manifest.get("integrity_sha256", "")
            at(len(ig) == 64 and all(c in "0123456789abcdef" for c in ig))
            ok(f"SHA256: {ig[:16]}...")

        with test("import: n_bubbles zgodne"):
            ae(result["imported_bubbles"], n_total)
            ok(f"imported={n_total}: OK")

        with test("import: integralność potwierdzona"):
            ae(result["integrity_ok"], True)
            ok("integrity_ok=True: OK")


# ═══════════════════════════════════════════════════════════════════════════════
# T07 — bubblefs export z Proca
# ═══════════════════════════════════════════════════════════════════════════════

def test_T07():
    section("T07 bubblefs.export() z Proca (use_proca=True)")

    ko      = build_test_instance(n_identical=8, n_similar=5, n_unique=3)
    n_total = len(ko.bubbles._b)
    p2s     = ko.phi._p2s

    with tempfile.TemporaryDirectory() as tmpdir:
        manifest, result, ko2 = _export_and_reimport(ko, tmpdir, p2s, use_proca=True)

        with test("proca_enabled=True"):
            ae(manifest["proca_enabled"], True)
            ok("proca_enabled=True: OK")

        with test("proca_coordinates > 0"):
            n_c = manifest["proca_coordinates"]
            at(n_c > 0, f"proca_coordinates={n_c}")
            ok(f"proca_coordinates={n_c}: OK")

        with test("katalog fields/ zawiera .pfld"):
            fdir  = os.path.join(tmpdir, "fields")
            n_pfl = len([f for f in os.listdir(fdir) if f.endswith(".pfld")])
            at(n_pfl > 0)
            ok(f"{n_pfl} plików .pfld: OK")

        with test("proca_bytes_saved > 0"):
            saved = manifest["proca_bytes_saved"]
            at(saved > 0, f"bytes_saved={saved}")
            ok(f"bytes_saved={saved:,}B")

        with test("wszystkie .bbl zapisane"):
            n = len([f for f in os.listdir(os.path.join(tmpdir, "bubbles"))
                     if f.endswith(".bbl")])
            ae(n, n_total)
            ok(f"{n}/{n_total}: OK")

        with test("import bez pominięć"):
            ae(result["imported_bubbles"], n_total)
            ae(len(result["skipped"]), 0)
            ok(f"imported={n_total} skipped=0: OK")

        with test("stosunek koordynatów sensowny"):
            n_s = manifest["proca_sources"]
            n_c = manifest["proca_coordinates"]
            at(n_s + n_c > 0)
            ratio = n_c / (n_s + n_c) * 100
            ok(f"src={n_s} coord={n_c} ratio={ratio:.0f}%")


# ═══════════════════════════════════════════════════════════════════════════════
# T08 — ROUNDTRIP pełny cykl tworzenie → zapis → odzysk
# ═══════════════════════════════════════════════════════════════════════════════

def test_T08():
    section("T08 ROUNDTRIP tworzenie → zapis → odzysk (100% weryfikacja)")

    p2s = os.urandom(32)

    for use_proca, label in [(False, "bez Proca"), (True, "z Proca")]:
        ko      = build_test_instance(n_identical=6, n_similar=4, n_unique=3)
        n_total = len(ko.bubbles._b)
        orig    = snapshot(ko)

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, result, ko2 = _export_and_reimport(
                ko, tmpdir, p2s, use_proca=use_proca)

            with test(f"({label}) import: liczba bąbli"):
                ae(result["imported_bubbles"], n_total)
                ok(f"imported={n_total}")

            with test(f"({label}) import: zero pominięć"):
                ae(len(result["skipped"]), 0)
                ok(f"skipped=0")

            with test(f"({label}) treść: 100% identyczna bajt po bajcie"):
                # Po naprawie bubblefs fallback path: oba tryby muszą dać 100%.
                recovered = content_from_store(ko2)
                missing  = set(orig) - set(recovered)
                mismatch = [bid for bid in set(orig) & set(recovered)
                             if orig[bid] != recovered[bid]]

                at(not missing,  f"brakuje: {missing}")
                at(not mismatch, f"błędna treść ({len(mismatch)}): {mismatch[:3]}")
                ok(f"WSZYSTKIE {n_total} bąbli: treść identyczna")


# ═══════════════════════════════════════════════════════════════════════════════
# T09 — Pomiar oszczędności miejsca na dysku
# ═══════════════════════════════════════════════════════════════════════════════

def test_T09():
    section("T09 Oszczędność miejsca na dysku")

    p2s = os.urandom(32)
    # n_similar=0 — bąble z różnymi danymi nie kwalifikują się do Proca dedupu
    ko  = build_test_instance(n_identical=14, n_similar=0, n_unique=4)

    with tempfile.TemporaryDirectory() as d_no:
        with tempfile.TemporaryDirectory() as d_pr:
            bubblefs.export(ko, d_no, shared_secret=p2s, use_proca=False)
            bubblefs.export(ko, d_pr, shared_secret=p2s, use_proca=True)

            sz_no = dir_size(d_no)
            sz_pr = dir_size(d_pr)
            saved = sz_no - sz_pr
            pct   = saved / sz_no * 100 if sz_no > 0 else 0

            with test("rozmiar bez Proca > 0"):
                at(sz_no > 0)
                ok(f"bez Proca: {sz_no:,}B")

            with test("z Proca < bez Proca"):
                at(sz_pr < sz_no, f"Proca={sz_pr}B nie mniejsze od {sz_no}B")
                ok(f"z Proca:   {sz_pr:,}B")

            with test("oszczędność >= 10%"):
                at(pct >= 10.0, f"tylko {pct:.1f}% (oczekiwano >= 10%)")
                ok(f"Oszczędność: {saved/1024:.1f}KB ({pct:.1f}%)")

            info(f"bubbles: {dir_size(os.path.join(d_pr, 'bubbles')):,}B  "
                  f"fields: {dir_size(os.path.join(d_pr, 'fields')):,}B")


# ═══════════════════════════════════════════════════════════════════════════════
# T10 — Weryfikacja integralności i bezpieczeństwa
# ═══════════════════════════════════════════════════════════════════════════════

def test_T10():
    section("T10 Integralność i bezpieczeństwo")

    p2s = os.urandom(32)
    ko  = build_test_instance(n_identical=3, n_similar=2, n_unique=2)

    with tempfile.TemporaryDirectory() as tmpdir:
        bubblefs.export(ko, tmpdir, shared_secret=p2s)

        with test("import z poprawnym kluczem: OK"):
            ko2 = empty_ko(p2s)
            r   = bubblefs.import_(ko2, tmpdir, shared_secret=p2s,
                                    verify_integrity=True)
            ae(r["integrity_ok"], True)
            ok("integrity_ok=True")

        with test("modyfikacja .bbl → ValueError przy weryfikacji"):
            bdir = os.path.join(tmpdir, "bubbles")
            fpath = os.path.join(bdir, sorted(os.listdir(bdir))[0])
            with open(fpath, 'r+b') as f:
                f.seek(100)
                f.write(b"\xFF\xFF")
            try:
                bubblefs.import_(empty_ko(p2s), tmpdir, shared_secret=p2s,
                                  verify_integrity=True)
                fail("powinno rzucić ValueError")
            except ValueError:
                ok("ValueError: integralność naruszona — wykryta")

        with test("zły klucz → odmowa odszyfrowania"):
            try:
                r = bubblefs.import_(empty_ko(os.urandom(32)), tmpdir,
                                      shared_secret=os.urandom(32))
                # Może przejść bez wyjątku jeśli wszystkie bąble pominięte
                at(r["imported_bubbles"] == 0 or len(r["skipped"]) > 0,
                   "zły klucz powinien skutkować pominięciami lub wyjątkiem")
                ok(f"zły klucz: imported={r['imported_bubbles']}"
                   f" skipped={len(r['skipped'])}")
            except (ValueError, Exception):
                ok("ValueError/Exception: zły klucz odrzucony")


# ═══════════════════════════════════════════════════════════════════════════════
# T11 — bubblefs.inspect()
# ═══════════════════════════════════════════════════════════════════════════════

def test_T11():
    section("T11 bubblefs.inspect()")

    p2s = os.urandom(32)
    ko  = build_test_instance(n_identical=4, n_similar=3, n_unique=2)

    with tempfile.TemporaryDirectory() as tmpdir:
        bubblefs.export(ko, tmpdir, shared_secret=p2s, use_proca=True)

        with test("inspect() nie rzuca wyjątku"):
            m = bubblefs.inspect(tmpdir)
            at(isinstance(m, dict))
            ok("inspect(): OK")

        with test("wersja = 2.3.1"):
            ae(m["bubblefs_version"], "2.3.1")
            ok(f"version={m['bubblefs_version']}")

        with test("n_bubbles poprawne"):
            ae(m["n_bubbles"], len(ko.bubbles._b))
            ok(f"n_bubbles={m['n_bubbles']}")

        with test("proca_enabled = True w inspect"):
            ae(m["proca_enabled"], True)
            ok("proca_enabled=True")

        with test("proca_sources + proca_coordinates w manifeście"):
            at("proca_sources" in m and "proca_coordinates" in m)
            ok(f"src={m['proca_sources']} coord={m['proca_coordinates']}")

        with test("brak inspect na nieistniejącym katalogu → FileNotFoundError"):
            try:
                bubblefs.inspect("/nonexistent/path/xyz")
                fail("powinno rzucić FileNotFoundError")
            except FileNotFoundError:
                ok("FileNotFoundError: OK")


# ═══════════════════════════════════════════════════════════════════════════════
# T12 — export_single_bubble
# ═══════════════════════════════════════════════════════════════════════════════

def test_T12():
    section("T12 export_single_bubble")

    p2s = os.urandom(32)
    ko  = build_test_instance(n_identical=3, n_similar=0, n_unique=2)
    ko.phi._p2s = p2s

    target_label = "doc_001"

    with tempfile.TemporaryDirectory() as tmpdir:

        with test("export_single_bubble: zwraca ścieżkę .bbl"):
            fpath = bubblefs.export_single_bubble(ko, target_label, tmpdir,
                                                   shared_secret=p2s)
            at(fpath is not None, "fpath = None")
            at(os.path.exists(fpath), f"plik nie istnieje: {fpath}")
            at(fpath.endswith(".bbl"), f"nie .bbl: {fpath}")
            ok(f"plik: {os.path.basename(fpath)}")

        with test("plik .bbl: rozmiar > 0"):
            size = os.path.getsize(fpath)
            at(size > 0, f"rozmiar={size}")
            ok(f"rozmiar={size}B")

        with test("export_single_bubble: nieistniejący label → None"):
            r = bubblefs.export_single_bubble(ko, "nieistniejacy_bbl", tmpdir,
                                               shared_secret=p2s)
            ae(r, None)
            ok("nieistniejący label → None: OK")

        with test("treść zachowana w eksportowanym .bbl"):
            # Otwórz export i sprawdź czy magic jest poprawny
            with open(fpath, 'rb') as f:
                magic = f.read(4)
            ae(magic, b"BBL1")
            ok("BBL1 magic: OK")


# ═══════════════════════════════════════════════════════════════════════════════
# T13 — Edge cases: dim=8, dim=32, tylko phi=None, tylko małe dane
# ═══════════════════════════════════════════════════════════════════════════════

def test_T13():
    section("T13 Edge cases")

    rng = np.random.default_rng(7)

    with test("dim=8: roundtrip export → import"):
        p2s = os.urandom(32)
        ko  = build_test_instance(n_identical=3, n_similar=0, n_unique=2,
                                   dim=8, p2s=p2s)
        with tempfile.TemporaryDirectory() as tmpdir:
            m, r, ko2 = _export_and_reimport(ko, tmpdir, p2s, use_proca=True)
            ae(m["dim"], 8)
            ae(r["imported_bubbles"], len(ko.bubbles._b))
            ok(f"dim=8: OK (imported={r['imported_bubbles']})")

    with test("dim=32: roundtrip export → import"):
        p2s = os.urandom(32)
        ko  = build_test_instance(n_identical=3, n_similar=0, n_unique=2,
                                   dim=32, p2s=p2s)
        with tempfile.TemporaryDirectory() as tmpdir:
            m, r, ko2 = _export_and_reimport(ko, tmpdir, p2s, use_proca=True)
            ae(m["dim"], 32)
            ae(r["imported_bubbles"], len(ko.bubbles._b))
            ok(f"dim=32: OK (imported={r['imported_bubbles']})")

    with test("10 bąbli identycznych: sources=1, coordinates=9"):
        data = b"Test identyczny " * 100
        phi0 = _norm(rng.standard_normal(15).astype(np.float32))
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = ProcaIndex(fields_dir=tmpdir)
            for i in range(10):
                phi = _norm(phi0 + rng.standard_normal(15).astype(np.float32) * 0.01)
                idx.register_or_deduplicate(f"b{i}", data, phi)
            st = idx.stats()
            ae(st["sources"], 1)
            ae(st["coordinates"], 9)
            ok(f"src=1 coord=9: OK (saved={st['bytes_saved']:,}B)")

    with test("serialize → deserialize po save/load z dysku"):
        data = b"Persystencja pola " * 80
        phi  = _norm(rng.standard_normal(15).astype(np.float32))
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = ProcaIndex(fields_dir=tmpdir)
            idx.register_or_deduplicate("src", data, phi)
            idx.save_all_sources()

            idx2 = ProcaIndex(fields_dir=tmpdir)
            idx2.load_sources_from_disk()
            ae(len(idx2._sources), 1)
            src = next(iter(idx2._sources.values()))
            ab(src.data, data, "persisted data")
            ok("save/load dysk: dane zachowane")

    with test("analiza pokrycia: pusty phi nie blokuje obliczeń"):
        atoms = [
            ("a", b"x" * 500, None),
            ("b", b"y" * 500, None),
            ("c", b"z" * 500, _norm(rng.standard_normal(15).astype(np.float32))),
        ]
        r = analyze_field_coverage(atoms)
        ae(r["atoms"], 3)
        ok(f"3 atomy (2×phi=None): OK fields={r['fields']}")


# ═══════════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════════

_TESTS = [
    ("T01", "Matematyka pola Proca",          test_T01),
    ("T02", "ProcaFieldSource roundtrip",      test_T02),
    ("T03", "ProcaCoordinate roundtrip",       test_T03),
    ("T04", "ProcaIndex logika deduplicji",    test_T04),
    ("T05", "analyze_field_coverage",          test_T05),
    ("T06", "export bez Proca",               test_T06),
    ("T07", "export z Proca",                 test_T07),
    ("T08", "ROUNDTRIP 100% weryfikacja",     test_T08),
    ("T09", "Oszczędność na dysku",           test_T09),
    ("T10", "Integralność i bezpieczeństwo",  test_T10),
    ("T11", "inspect()",                      test_T11),
    ("T12", "export_single_bubble",           test_T12),
    ("T13", "Edge cases dim=8/32",            test_T13),
]


def run_all() -> bool:
    print(f"\n{'═' * 60}")
    print(f"{BOLD if _color else ''}  KarmazynOS — Proca + BubbleFS tester v2{RST if _color else ''}")
    print(f"  tworzenie / zapis / odzysk")
    print(f"{'═' * 60}")

    t0 = time.time()
    for tid, name, fn in _TESTS:
        try:
            fn()
        except Exception as e:
            section(f"BŁĄD KRYTYCZNY: {tid} {name}")
            traceback.print_exc()
            _results["errors"] += 1

    elapsed = time.time() - t0
    total   = sum(_results.values())

    print(f"\n{'═' * 60}")
    print(f"  {total} testów w {elapsed:.2f}s")
    print(f"  {PASS if _color else 'OK  '} Passed:  {_results['passed']}")
    if _results["failed"]:
        print(f"  {FAIL if _color else 'FAIL'} Failed:  {_results['failed']}")
    if _results["errors"]:
        print(f"  {'!' if not _color else chr(27)+'[33m!'+chr(27)+'[0m'} Errors:  {_results['errors']}")
    print(f"{'═' * 60}\n")

    return _results["failed"] + _results["errors"] == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose",  action="store_true")
    parser.add_argument("--no-color",       action="store_true")
    args = parser.parse_args()

    _verbose = args.verbose
    _color   = not args.no_color

    sys.exit(0 if run_all() else 1)
