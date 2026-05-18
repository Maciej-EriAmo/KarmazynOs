"""
bubblefs.py — BubbleFS: Portable Storage Format for KarmazynOS v1.0.0
======================================================================

Format wymiany danych struktury bąbelkowej między instancjami KarmazynOS.
Zastępuje pickle-based save/load przenośnym, czytelnym formatem.

Struktura na dysku:
  <path>/
    manifest.json          # wersja, epoch, dim, hash integrity
    bubbles/
      <bubble_id>.bbl      # JSON + base64, jeden plik = jeden Bubble
    holograms/
      <holo_id>.hgm        # JSON, hologram skompresowany do proto+generatorów
    phi/
      sem_vectors.npz      # macierz wektorów semantycznych (label → vector)
      structural.npz       # wektory strukturalne z HSSKarmazynMatrix

Szyfrowanie przy eksporcie:
  - bubble_key jest pochodną phi2_bytes (per-instancja, nie przenośna)
  - przy eksporcie: decrypt content → re-encrypt nowym kluczem eksportowym
  - klucz eksportowy = HMAC(shared_secret, bubble_id) gdzie shared_secret
    to argument export() / import_()
  - jeśli shared_secret=None → eksport plaintextów (tryb debug/lokalny)
"""

import io
import os
import json
import base64
import hashlib
import hmac as _hmac
import numpy as np
from typing import Optional, Dict, Any

BUBBLEFS_VERSION = "2.0.0"
BBL_EXT  = ".bbl"
HGM_EXT  = ".hgm"

# --- Szyfrowanie AES-256-GCM ---
# Kazdy .bbl i .hgm jest binarnym zaszyfrowanym blobem.
# Format: magic(4) + salt(16) + nonce(12) + ciphertext+tag
# Klucz: HMAC(HMAC(master, "bbl-v2:"+id), salt) - forward secrecy per zapis

_BBL_MAGIC = b"BBL1"
_HGM_MAGIC = b"HGM1"
_NPZ_MAGIC = b"NPZ1"

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    _CRYPTO_OK = True
except ImportError:
    _AESGCM    = None
    _CRYPTO_OK = False


def _bbl_key(master_key: bytes, record_id: str) -> bytes:
    """Unikalny klucz AES-256: HMAC-SHA256(master, b"bbl-v2:" + id)."""
    return _hmac.new(master_key, b"bbl-v2:" + record_id.encode(), hashlib.sha256).digest()


def _aes_encrypt(data: bytes, master_key: bytes, record_id: str, magic: bytes) -> bytes:
    """Zaszyfruj dane. Zwraca: magic(4) + salt(16) + nonce(12) + ct+tag."""
    if not _CRYPTO_OK:
        import warnings
        warnings.warn("bubblefs: cryptography niedostepna, plik niezaszyfrowany.", RuntimeWarning)
        return magic + b"\x00" * 28 + data
    salt    = os.urandom(16)
    nonce   = os.urandom(12)
    key     = _bbl_key(master_key, record_id)
    derived = _hmac.new(key, salt, hashlib.sha256).digest()
    aad     = magic + record_id.encode()
    ct      = _AESGCM(derived).encrypt(nonce, data, aad)
    return magic + salt + nonce + ct


def _aes_decrypt(blob: bytes, master_key: bytes, record_id: str, magic: bytes) -> bytes:
    """Odszyfruj blob. Rzuca ValueError przy zlym kluczu."""
    if len(blob) < 4 + 16 + 12 + 16:
        raise ValueError(f"Plik za krotki: {len(blob)}B")
    if blob[:4] != magic:
        raise ValueError(f"Zly magic: {blob[:4]!r}, oczekiwano {magic!r}")
    salt  = blob[4:20]
    nonce = blob[20:32]
    ct    = blob[32:]
    if not _CRYPTO_OK or (salt == b"\x00" * 16 and nonce == b"\x00" * 12):
        return ct
    key     = _bbl_key(master_key, record_id)
    derived = _hmac.new(key, salt, hashlib.sha256).digest()
    aad     = magic + record_id.encode()
    try:
        return _AESGCM(derived).decrypt(nonce, ct, aad)
    except Exception:
        raise ValueError(f"Odszyfrowanie nieudane dla {record_id!r}.")


def _get_master_key(karmazyn_os, shared_secret: Optional[bytes]) -> bytes:
    """Wybierz master key: shared_secret jesli podany, inaczej phi._p2s."""
    if shared_secret is not None:
        return shared_secret
    p2s = getattr(getattr(karmazyn_os, "phi", None), "_p2s", None)
    if p2s:
        return p2s
    raise ValueError(
        "Brak klucza: podaj shared_secret lub upewnij sie ze phi._p2s jest zainicjowane."
    )


# ─── helpers ─────────────────────────────────────────────────────────────────

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()

def _ub64(s: str) -> bytes:
    return base64.b64decode(s)

def _export_key(shared_secret: bytes, bubble_id: str) -> bytes:
    return _hmac.new(shared_secret, b"bbl-export:" + bubble_id.encode(), hashlib.sha256).digest()

def _xor_crypt(data: bytes, key: bytes) -> bytes:
    out, offset, counter = bytearray(len(data)), 0, 0
    while offset < len(data):
        block = hashlib.sha256(key + counter.to_bytes(4, 'big')).digest()
        for b in block:
            if offset >= len(data): break
            out[offset] = data[offset] ^ b
            offset += 1
        counter += 1
    return bytes(out)

def _manifest_hash(bubbles_dir: str, holograms_dir: str) -> str:
    h = hashlib.sha256()
    for d in [bubbles_dir, holograms_dir]:
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            fpath = os.path.join(d, fname)
            with open(fpath, 'rb') as f:
                h.update(fname.encode())
                h.update(f.read())
    return h.hexdigest()


# ─── EXPORT ──────────────────────────────────────────────────────────────────

def export(karmazyn_os, path: str, shared_secret: Optional[bytes] = None,
           include_phi_vectors: bool = True) -> dict:
    """
    Eksportuje stan KarmazynOS do katalogu BubbleFS.

    Args:
        karmazyn_os:      instancja KarmazynOS
        path:             katalog docelowy (zostanie utworzony)
        shared_secret:    klucz wymiany dla re-szyfrowania bąbli
                          None = plaintext (tryb lokalny/debug)
        include_phi_vectors: czy eksportować wektory Φ (sem + structural)

    Returns:
        dict z metadanymi eksportu
    """
    os.makedirs(path, exist_ok=True)
    bdir = os.path.join(path, "bubbles");    os.makedirs(bdir, exist_ok=True)
    hdir = os.path.join(path, "holograms"); os.makedirs(hdir, exist_ok=True)
    pdir = os.path.join(path, "phi");       os.makedirs(pdir, exist_ok=True)

    ko = karmazyn_os
    exported_bubbles = []
    exported_holograms = []

    # ── Bąble ────────────────────────────────────────────────────────────────
    # master key: shared_secret lub phi._p2s (nigdy plaintext)
    master_key = _get_master_key(ko, shared_secret)

    for bid, bubble in ko.bubbles._b.items():
        revoked = bid in ko.bubbles._rev

        raw_content = bubble.decrypt_content()

        bbl: Dict[str, Any] = {
            "id":                 bubble.id,
            "label":              bubble.label,
            "inode":              bubble.inode,
            "epoch_born":         bubble.epoch_born,
            "recall_count":       bubble.recall_count,
            "consolidated_from":  bubble.consolidated_from,
            "metadata":           bubble.metadata,
            "revoked":            revoked,
            # content jako plaintext base64 -- bezpieczne BO caly .bbl jest zaszyfrowany
            "content_b64":        _b64(raw_content),
            "fingerprint_b64":    _b64(bubble.fingerprint),
            "S_struct":           bubble.S_struct.tolist(),
            "S_sem":              bubble.S_sem.tolist(),
        }
        if bubble.decay_start_epoch is not None:
            bbl["decay_start_epoch"] = bubble.decay_start_epoch
            bbl["decay_rate"]        = bubble.decay_rate

        # Serialzuj JSON -> zaszyfruj -> zapisz jako binarny blob
        bbl_json  = json.dumps(bbl, ensure_ascii=False, default=str).encode("utf-8")
        bbl_blob  = _aes_encrypt(bbl_json, master_key, bid, _BBL_MAGIC)

        fpath     = os.path.join(bdir, bid + BBL_EXT)
        fpath_tmp = fpath + ".atom"
        with open(fpath_tmp, "wb") as f:
            f.write(bbl_blob)
            f.flush()
            os.fsync(f.fileno())

        import time
        for _ in range(5):
            try:
                os.replace(fpath_tmp, fpath)
                break
            except PermissionError:
                time.sleep(0.1)

        exported_bubbles.append(bid)

    # ── Hologramy ─────────────────────────────────────────────────────────────
    for hid, h in ko.holograms.items():
        hgm: Dict[str, Any] = {
            "id":             h.id,
            "topic":          h.topic,
            "proto":          h.proto.tolist(),
            "generators":     [g.tolist() for g in h.generators],
            "weights":        h.weights,
            "bubble_labels":  h.bubble_labels,
            "epoch_created":  h.epoch_created,
            "decay_rate":     h.decay_rate,
            "metadata":       h.metadata,
        }
        hgm_json  = json.dumps(hgm, ensure_ascii=False, default=str).encode("utf-8")
        hgm_blob  = _aes_encrypt(hgm_json, master_key, hid, _HGM_MAGIC)

        fpath     = os.path.join(hdir, hid + HGM_EXT)
        fpath_tmp = fpath + ".atom"
        with open(fpath_tmp, "wb") as f:
            f.write(hgm_blob)
            f.flush()
            os.fsync(f.fileno())

        import time
        for _ in range(5):
            try:
                os.replace(fpath_tmp, fpath)
                break
            except PermissionError:
                time.sleep(0.1)

        exported_holograms.append(hid)

    # ── Wektory Φ ─────────────────────────────────────────────────────────────
    if include_phi_vectors and ko.phi._sem:
        buf = io.BytesIO()
        np.savez(buf, **ko.phi._sem)
        with open(os.path.join(pdir, "sem_vectors.npz"), "wb") as f:
            f.write(_aes_encrypt(buf.getvalue(), master_key, "sem_vectors", _NPZ_MAGIC))

    if include_phi_vectors and ko.phi._mx.atoms:
        s_data = {a["label"]: a["S"] for a in ko.phi._mx.atoms}
        t_data = {a["label"]: np.array([a["T"]]) for a in ko.phi._mx.atoms}
        for fname, npz_d, uid in [("structural.npz", s_data, "structural"), ("temperatures.npz", t_data, "temperatures")]:
            buf = io.BytesIO()
            np.savez(buf, **npz_d)
            with open(os.path.join(pdir, fname), "wb") as f:
                f.write(_aes_encrypt(buf.getvalue(), master_key, uid, _NPZ_MAGIC))

    # ── Manifest ──────────────────────────────────────────────────────────────
    integrity = _manifest_hash(bdir, hdir)
    manifest = {
        "bubblefs_version":   BUBBLEFS_VERSION,
        "karmazyn_version":   getattr(ko, 'VERSION', '?'),
        "epoch":              ko.phi.epoch,
        "dim":                ko.phi.dim,
        "t_vacuum()":           ko.phi.t_vacuum(),
        "temperature":        ko.phi.temperature(),
        "n_bubbles":          len(exported_bubbles),
        "n_holograms":        len(exported_holograms),
        "n_phi_atoms":        len(ko.phi._mx.atoms),
        "encrypted":          shared_secret is not None,
        "include_phi_vectors": include_phi_vectors,
        "integrity_sha256":   integrity,
        "bubble_idx":         dict(ko.bubbles._idx),
    }
    manifest_path = os.path.join(path, "manifest.json")
    manifest_tmp = manifest_path + ".atom"
    with open(manifest_tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())

    import time
    for _ in range(5):
        try:
            os.replace(manifest_tmp, manifest_path)
            break
        except PermissionError:
            time.sleep(0.1)

    print(f"[BubbleFS] Eksport → {path}")
    print(f"  bąble={len(exported_bubbles)}  hologramy={len(exported_holograms)}"
          f"  encrypted={shared_secret is not None}")
    return manifest


# ─── IMPORT ──────────────────────────────────────────────────────────────────

def import_(karmazyn_os, path: str, shared_secret: Optional[bytes] = None,
            merge: bool = False, verify_integrity: bool = True) -> dict:
    """
    Importuje stan BubbleFS do instancji KarmazynOS.

    Args:
        karmazyn_os:       instancja KarmazynOS (docelowa)
        path:              katalog źródłowy BubbleFS
        shared_secret:     klucz wymiany (musi zgadzać się z export())
        merge:             True = dołącz do istniejącego stanu
                           False = wyczyść store przed importem
        verify_integrity:  sprawdź hash manifestu

    Returns:
        dict z metadanymi importu
    """
    if not os.path.isdir(path):
        raise FileNotFoundError(f"BubbleFS: katalog nie istnieje: {path}")

    bdir = os.path.join(path, "bubbles")
    hdir = os.path.join(path, "holograms")
    pdir = os.path.join(path, "phi")

    master_key = _get_master_key(karmazyn_os, shared_secret)

    # ── Manifest ──────────────────────────────────────────────────────────────
    with open(os.path.join(path, "manifest.json"), 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    if verify_integrity:
        actual = _manifest_hash(bdir, hdir)
        if actual != manifest.get("integrity_sha256"):
            raise ValueError(
                f"[BubbleFS] Błąd integralności!\n"
                f"  oczekiwano: {manifest.get('integrity_sha256')}\n"
                f"  znaleziono: {actual}"
            )

    ko = karmazyn_os

    if not merge:
        ko.bubbles._b.clear()
        ko.bubbles._idx.clear()
        ko.bubbles._rev.clear()
        ko.holograms.clear()

    imported_bubbles = []
    imported_holograms = []
    skipped = []

    """
bubblefs.py — BubbleFS: Portable Storage Format for KarmazynOS v1.0.0
======================================================================

Format wymiany danych struktury bąbelkowej między instancjami KarmazynOS.
Zastępuje pickle-based save/load przenośnym, czytelnym formatem.

Struktura na dysku:
  <path>/
    manifest.json          # wersja, epoch, dim, hash integrity
    bubbles/
      <bubble_id>.bbl      # JSON + base64, jeden plik = jeden Bubble
    holograms/
      <holo_id>.hgm        # JSON, hologram skompresowany do proto+generatorów
    phi/
      sem_vectors.npz      # macierz wektorów semantycznych (label → vector)
      structural.npz       # wektory strukturalne z HSSKarmazynMatrix

Szyfrowanie przy eksporcie:
  - bubble_key jest pochodną phi2_bytes (per-instancja, nie przenośna)
  - przy eksporcie: decrypt content → re-encrypt nowym kluczem eksportowym
  - klucz eksportowy = HMAC(shared_secret, bubble_id) gdzie shared_secret
    to argument export() / import_()
  - jeśli shared_secret=None → eksport plaintextów (tryb debug/lokalny)
"""

import io
import os
import json
import base64
import hashlib
import hmac as _hmac
import numpy as np
from typing import Optional, Dict, Any

BUBBLEFS_VERSION = "2.0.0"
BBL_EXT  = ".bbl"
HGM_EXT  = ".hgm"

# --- Szyfrowanie AES-256-GCM ---
# Kazdy .bbl i .hgm jest binarnym zaszyfrowanym blobem.
# Format: magic(4) + salt(16) + nonce(12) + ciphertext+tag
# Klucz: HMAC(HMAC(master, "bbl-v2:"+id), salt) - forward secrecy per zapis

_BBL_MAGIC = b"BBL1"
_HGM_MAGIC = b"HGM1"
_NPZ_MAGIC = b"NPZ1"

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    _CRYPTO_OK = True
except ImportError:
    _AESGCM    = None
    _CRYPTO_OK = False


def _bbl_key(master_key: bytes, record_id: str) -> bytes:
    """Unikalny klucz AES-256: HMAC-SHA256(master, b"bbl-v2:" + id)."""
    return _hmac.new(master_key, b"bbl-v2:" + record_id.encode(), hashlib.sha256).digest()


def _aes_encrypt(data: bytes, master_key: bytes, record_id: str, magic: bytes) -> bytes:
    """Zaszyfruj dane. Zwraca: magic(4) + salt(16) + nonce(12) + ct+tag."""
    if not _CRYPTO_OK:
        import warnings
        warnings.warn("bubblefs: cryptography niedostepna, plik niezaszyfrowany.", RuntimeWarning)
        return magic + b"\x00" * 28 + data
    salt    = os.urandom(16)
    nonce   = os.urandom(12)
    key     = _bbl_key(master_key, record_id)
    derived = _hmac.new(key, salt, hashlib.sha256).digest()
    aad     = magic + record_id.encode()
    ct      = _AESGCM(derived).encrypt(nonce, data, aad)
    return magic + salt + nonce + ct


def _aes_decrypt(blob: bytes, master_key: bytes, record_id: str, magic: bytes) -> bytes:
    """Odszyfruj blob. Rzuca ValueError przy zlym kluczu."""
    if len(blob) < 4 + 16 + 12 + 16:
        raise ValueError(f"Plik za krotki: {len(blob)}B")
    if blob[:4] != magic:
        raise ValueError(f"Zly magic: {blob[:4]!r}, oczekiwano {magic!r}")
    salt  = blob[4:20]
    nonce = blob[20:32]
    ct    = blob[32:]
    if not _CRYPTO_OK or (salt == b"\x00" * 16 and nonce == b"\x00" * 12):
        return ct
    key     = _bbl_key(master_key, record_id)
    derived = _hmac.new(key, salt, hashlib.sha256).digest()
    aad     = magic + record_id.encode()
    try:
        return _AESGCM(derived).decrypt(nonce, ct, aad)
    except Exception:
        raise ValueError(f"Odszyfrowanie nieudane dla {record_id!r}.")


def _get_master_key(karmazyn_os, shared_secret: Optional[bytes]) -> bytes:
    """Wybierz master key: shared_secret jesli podany, inaczej phi._p2s."""
    if shared_secret is not None:
        return shared_secret
    p2s = getattr(getattr(karmazyn_os, "phi", None), "_p2s", None)
    if p2s:
        return p2s
    raise ValueError(
        "Brak klucza: podaj shared_secret lub upewnij sie ze phi._p2s jest zainicjowane."
    )


# ─── helpers ─────────────────────────────────────────────────────────────────

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()

def _ub64(s: str) -> bytes:
    return base64.b64decode(s)

def _export_key(shared_secret: bytes, bubble_id: str) -> bytes:
    return _hmac.new(shared_secret, b"bbl-export:" + bubble_id.encode(), hashlib.sha256).digest()

def _xor_crypt(data: bytes, key: bytes) -> bytes:
    out, offset, counter = bytearray(len(data)), 0, 0
    while offset < len(data):
        block = hashlib.sha256(key + counter.to_bytes(4, 'big')).digest()
        for b in block:
            if offset >= len(data): break
            out[offset] = data[offset] ^ b
            offset += 1
        counter += 1
    return bytes(out)

def _manifest_hash(bubbles_dir: str, holograms_dir: str) -> str:
    h = hashlib.sha256()
    for d in [bubbles_dir, holograms_dir]:
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            fpath = os.path.join(d, fname)
            with open(fpath, 'rb') as f:
                h.update(fname.encode())
                h.update(f.read())
    return h.hexdigest()


# ─── EXPORT ──────────────────────────────────────────────────────────────────

def export(karmazyn_os, path: str, shared_secret: Optional[bytes] = None,
           include_phi_vectors: bool = True) -> dict:
    """
    Eksportuje stan KarmazynOS do katalogu BubbleFS.

    Args:
        karmazyn_os:      instancja KarmazynOS
        path:             katalog docelowy (zostanie utworzony)
        shared_secret:    klucz wymiany dla re-szyfrowania bąbli
                          None = plaintext (tryb lokalny/debug)
        include_phi_vectors: czy eksportować wektory Φ (sem + structural)

    Returns:
        dict z metadanymi eksportu
    """
    os.makedirs(path, exist_ok=True)
    bdir = os.path.join(path, "bubbles");    os.makedirs(bdir, exist_ok=True)
    hdir = os.path.join(path, "holograms"); os.makedirs(hdir, exist_ok=True)
    pdir = os.path.join(path, "phi");       os.makedirs(pdir, exist_ok=True)

    ko = karmazyn_os
    exported_bubbles = []
    exported_holograms = []

    # ── Bąble ────────────────────────────────────────────────────────────────
    # master key: shared_secret lub phi._p2s (nigdy plaintext)
    master_key = _get_master_key(ko, shared_secret)

    for bid, bubble in ko.bubbles._b.items():
        revoked = bid in ko.bubbles._rev

        raw_content = bubble.decrypt_content()

        bbl: Dict[str, Any] = {
            "id":                 bubble.id,
            "label":              bubble.label,
            "inode":              bubble.inode,
            "epoch_born":         bubble.epoch_born,
            "recall_count":       bubble.recall_count,
            "consolidated_from":  bubble.consolidated_from,
            "metadata":           bubble.metadata,
            "revoked":            revoked,
            # content jako plaintext base64 -- bezpieczne BO caly .bbl jest zaszyfrowany
            "content_b64":        _b64(raw_content),
            "fingerprint_b64":    _b64(bubble.fingerprint),
            "S_struct":           bubble.S_struct.tolist(),
            "S_sem":              bubble.S_sem.tolist(),
        }
        if bubble.decay_start_epoch is not None:
            bbl["decay_start_epoch"] = bubble.decay_start_epoch
            bbl["decay_rate"]        = bubble.decay_rate

        # Serialzuj JSON -> zaszyfruj -> zapisz jako binarny blob
        bbl_json  = json.dumps(bbl, ensure_ascii=False, default=str).encode("utf-8")
        bbl_blob  = _aes_encrypt(bbl_json, master_key, bid, _BBL_MAGIC)

        fpath     = os.path.join(bdir, bid + BBL_EXT)
        fpath_tmp = fpath + ".atom"
        with open(fpath_tmp, "wb") as f:
            f.write(bbl_blob)
            f.flush()
            os.fsync(f.fileno())

        import time
        for _ in range(5):
            try:
                os.replace(fpath_tmp, fpath)
                break
            except PermissionError:
                time.sleep(0.1)

        exported_bubbles.append(bid)

    # ── Hologramy ─────────────────────────────────────────────────────────────
    for hid, h in ko.holograms.items():
        hgm: Dict[str, Any] = {
            "id":             h.id,
            "topic":          h.topic,
            "proto":          h.proto.tolist(),
            "generators":     [g.tolist() for g in h.generators],
            "weights":        h.weights,
            "bubble_labels":  h.bubble_labels,
            "epoch_created":  h.epoch_created,
            "decay_rate":     h.decay_rate,
            "metadata":       h.metadata,
        }
        hgm_json  = json.dumps(hgm, ensure_ascii=False, default=str).encode("utf-8")
        hgm_blob  = _aes_encrypt(hgm_json, master_key, hid, _HGM_MAGIC)

        fpath     = os.path.join(hdir, hid + HGM_EXT)
        fpath_tmp = fpath + ".atom"
        with open(fpath_tmp, "wb") as f:
            f.write(hgm_blob)
            f.flush()
            os.fsync(f.fileno())

        import time
        for _ in range(5):
            try:
                os.replace(fpath_tmp, fpath)
                break
            except PermissionError:
                time.sleep(0.1)

        exported_holograms.append(hid)

    # ── Wektory Φ ─────────────────────────────────────────────────────────────
    if include_phi_vectors and ko.phi._sem:
        buf = io.BytesIO()
        np.savez(buf, **ko.phi._sem)
        with open(os.path.join(pdir, "sem_vectors.npz"), "wb") as f:
            f.write(_aes_encrypt(buf.getvalue(), master_key, "sem_vectors", _NPZ_MAGIC))

    if include_phi_vectors and ko.phi._mx.atoms:
        s_data = {a["label"]: a["S"] for a in ko.phi._mx.atoms}
        t_data = {a["label"]: np.array([a["T"]]) for a in ko.phi._mx.atoms}
        for fname, npz_d, uid in [("structural.npz", s_data, "structural"), ("temperatures.npz", t_data, "temperatures")]:
            buf = io.BytesIO()
            np.savez(buf, **npz_d)
            with open(os.path.join(pdir, fname), "wb") as f:
                f.write(_aes_encrypt(buf.getvalue(), master_key, uid, _NPZ_MAGIC))

    # ── Manifest ──────────────────────────────────────────────────────────────
    integrity = _manifest_hash(bdir, hdir)
    manifest = {
        "bubblefs_version":   BUBBLEFS_VERSION,
        "karmazyn_version":   getattr(ko, 'VERSION', '?'),
        "epoch":              ko.phi.epoch,
        "dim":                ko.phi.dim,
        "t_vacuum":           ko.phi.t_vacuum(),
        "temperature":        ko.phi.temperature(),
        "n_bubbles":          len(exported_bubbles),
        "n_holograms":        len(exported_holograms),
        "n_phi_atoms":        len(ko.phi._mx.atoms),
        "encrypted":          shared_secret is not None,
        "include_phi_vectors": include_phi_vectors,
        "integrity_sha256":   integrity,
        "bubble_idx":         dict(ko.bubbles._idx),
    }
    manifest_path = os.path.join(path, "manifest.json")
    manifest_tmp = manifest_path + ".atom"
    with open(manifest_tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())

    import time
    for _ in range(5):
        try:
            os.replace(manifest_tmp, manifest_path)
            break
        except PermissionError:
            time.sleep(0.1)

    print(f"[BubbleFS] Eksport → {path}")
    print(f"  bąble={len(exported_bubbles)}  hologramy={len(exported_holograms)}"
          f"  encrypted={shared_secret is not None}")
    return manifest


# ─── IMPORT ──────────────────────────────────────────────────────────────────

def import_(karmazyn_os, path: str, shared_secret: Optional[bytes] = None,
            merge: bool = False, verify_integrity: bool = True) -> dict:
    """
    Importuje stan BubbleFS do instancji KarmazynOS.

    Args:
        karmazyn_os:       instancja KarmazynOS (docelowa)
        path:              katalog źródłowy BubbleFS
        shared_secret:     klucz wymiany (musi zgadzać się z export())
        merge:             True = dołącz do istniejącego stanu
                           False = wyczyść store przed importem
        verify_integrity:  sprawdź hash manifestu

    Returns:
        dict z metadanymi importu
    """
    if not os.path.isdir(path):
        raise FileNotFoundError(f"BubbleFS: katalog nie istnieje: {path}")

    bdir = os.path.join(path, "bubbles")
    hdir = os.path.join(path, "holograms")
    pdir = os.path.join(path, "phi")

    master_key = _get_master_key(karmazyn_os, shared_secret)

    # ── Manifest ──────────────────────────────────────────────────────────────
    with open(os.path.join(path, "manifest.json"), 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    if verify_integrity:
        actual = _manifest_hash(bdir, hdir)
        if actual != manifest.get("integrity_sha256"):
            raise ValueError(
                f"[BubbleFS] Błąd integralności!\n"
                f"  oczekiwano: {manifest.get('integrity_sha256')}\n"
                f"  znaleziono: {actual}"
            )

    ko = karmazyn_os

    if not merge:
        ko.bubbles._b.clear()
        ko.bubbles._idx.clear()
        ko.bubbles._rev.clear()
        ko.holograms.clear()

    imported_bubbles = []
    imported_holograms = []
    skipped = []

    # ── Bąble ────────────────────────────────────────────────────────────────
    if os.path.isdir(bdir):
        from dataclasses import fields as dc_fields

        # import Bubble class from karmazyn module dynamically
        # (działa czy to import czy bezpośrednie użycie)
        BubbleClass = type(next(iter(ko.bubbles._b.values()), None)) if ko.bubbles._b else None
        if BubbleClass is None:
            # fallback: importuj z karmazyn
            try:
                from karmazyn import Bubble as BubbleClass
            except ImportError:
                BubbleClass = None

        for fname in sorted(os.listdir(bdir)):
            if not fname.endswith(BBL_EXT):
                continue
            fpath = os.path.join(bdir, fname)
            with open(fpath, "rb") as f:
                raw_hgm = f.read()
            if raw_hgm[:4] == _HGM_MAGIC:
                hgm = json.loads(_aes_decrypt(raw_hgm, master_key, fname.replace(HGM_EXT, ""), _HGM_MAGIC).decode("utf-8"))
            else:
                hgm = json.loads(raw_hgm.decode("utf-8"))

            hid = hgm["id"]
            if Hologram is not None:
                h = Hologram(
                    id=hid,
                    topic=hgm["topic"],
                    proto=np.array(hgm["proto"], dtype=np.float32),
                    generators=[np.array(g, dtype=np.float32) for g in hgm["generators"]],
                    weights=hgm["weights"],
                    bubble_labels=hgm["bubble_labels"],
                    epoch_created=hgm["epoch_created"],
                    decay_rate=hgm.get("decay_rate", 0.001),
                    metadata=hgm.get("metadata", {}),
                )
                ko.holograms[hid] = h
            else:
                # fallback
                ko.holograms[hid] = hgm

            imported_holograms.append(hid)

    # ── Wektory Φ ─────────────────────────────────────────────────────────────
    def _load_npz(fpath, uid):
        with open(fpath, "rb") as f:
            raw = f.read()
        if raw[:4] == _NPZ_MAGIC:
            raw = _aes_decrypt(raw, master_key, uid, _NPZ_MAGIC)
        import io
        return np.load(io.BytesIO(raw), allow_pickle=True)

    sem_path = os.path.join(pdir, "sem_vectors.npz")
    if os.path.exists(sem_path):
        sem_data = _load_npz(sem_path, "sem_vectors")
        for k in sem_data.files:
            ko.phi._sem[k] = sem_data[k]

    str_path  = os.path.join(pdir, "structural.npz")
    temp_path = os.path.join(pdir, "temperatures.npz")
    if os.path.exists(str_path) and os.path.exists(temp_path):
        str_data  = _load_npz(str_path,  "structural")
        temp_data = _load_npz(temp_path, "temperatures")
        existing_labels = {a['label'] for a in ko.phi._mx.atoms}
        for lbl in str_data.files:
            if lbl not in existing_labels:
                T = float(temp_data[lbl][0]) if lbl in temp_data.files else 1.0
                ko.phi._mx.add_atom_vector(
                    label=lbl, topic="bubblefs_import",
                    vector=str_data[lbl], init_T=T
                )

    result = {
        "imported_bubbles":   len(imported_bubbles),
        "imported_holograms": len(imported_holograms),
        "skipped":            skipped,
        "merged":             merge,
        "source_epoch":       manifest.get("epoch"),
        "source_dim":         manifest.get("dim"),
        "integrity_ok":       verify_integrity,
    }
    print(f"[BubbleFS] Import ← {path}")
    print(f"  bąble={len(imported_bubbles)}  hologramy={len(imported_holograms)}"
          f"  merge={merge}")
    return result


# ─── UTILITES ────────────────────────────────────────────────────────────────

def inspect(path: str) -> dict:
    """Odczytuje manifest bez ładowania danych. Przydatne do podglądu."""
    mpath = os.path.join(path, "manifest.json")
    if not os.path.exists(mpath):
        raise FileNotFoundError(f"Brak manifestu w {path}")
    with open(mpath, 'r', encoding='utf-8') as f:
        m = json.load(f)

    bdir = os.path.join(path, "bubbles")
    hdir = os.path.join(path, "holograms")
    bubble_files   = os.listdir(bdir) if os.path.isdir(bdir) else []
    hologram_files = os.listdir(hdir) if os.path.isdir(hdir) else []

    print(f"[BubbleFS] {path}")
    print(f"  wersja:     {m.get('bubblefs_version')} / karmazyn {m.get('karmazyn_version')}")
    print(f"  epoka:      {m.get('epoch')}  dim={m.get('dim')}")
    print(f"  bąble:      {len(bubble_files)}  hologramy={len(hologram_files)}")
    print(f"  szyfrowane: {m.get('encrypted')}  T_vacuum={m.get('t_vacuum', '?'):.4f}")
    return m


def export_single_bubble(karmazyn_os, label: str, path: str,
                         shared_secret: Optional[bytes] = None) -> Optional[str]:
    """
    Eksportuje pojedynczy Bubble do pliku .bbl.
    Przydatne do przesyłania konkretnych informacji między instancjami.
    """
    ko = karmazyn_os
    b  = ko.bubbles.get_by_label(label)
    if b is None:
        print(f"[BubbleFS] Bąbel '{label}' nie istnieje")
        return None

    os.makedirs(path, exist_ok=True)
    revoked    = b.id in ko.bubbles._rev
    raw_content = b.decrypt_content()

    master_key = _get_master_key(ko, shared_secret)

    bbl = {
        "id":                 b.id,
        "label":              b.label,
        "inode":              b.inode,
        "epoch_born":         b.epoch_born,
        "recall_count":       b.recall_count,
        "consolidated_from":  b.consolidated_from,
        "metadata":           b.metadata,
        "revoked":            revoked,
        "content_b64":        _b64(raw_content),
        "fingerprint_b64":    _b64(b.fingerprint),
        "S_struct":           b.S_struct.tolist(),
        "S_sem":              b.S_sem.tolist(),
    }
    if b.decay_start_epoch is not None:
        bbl["decay_start_epoch"] = b.decay_start_epoch
        bbl["decay_rate"]        = b.decay_rate

    bbl_blob  = _aes_encrypt(json.dumps(bbl, ensure_ascii=False, default=str).encode("utf-8"), master_key, b.id, _BBL_MAGIC)
    fpath     = os.path.join(path, b.id + BBL_EXT)
    fpath_tmp = fpath + ".atom"
    with open(fpath_tmp, "wb") as f:
        f.write(bbl_blob)
        f.flush()
        os.fsync(f.fileno())

    import time
    for _ in range(5):
        try:
            os.replace(fpath_tmp, fpath)
            break
        except PermissionError:
            time.sleep(0.1)

    print(f"[BubbleFS] Eksport bąbla '{label}' → {fpath}")
    return fpath