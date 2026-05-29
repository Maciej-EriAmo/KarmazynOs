#!/usr/bin/env python3
"""
bubblefs.py — BubbleFS v2.3.1
==============================
KarmazynOS — Maciej Mazur, Warsaw 2026

Poprawki v2.3.1:
  - Dodano import warnings (naprawa NameError)
  - Wyjaśniono model szyfrowania PFLD (BubbleFS jako warstwa transportowa)
  - Ulepszono ProcaCoordinate.is_proca_json (odporniejsze)
"""

import io
import os
import json
import base64
import hashlib
import hmac as _hmac
import re
import tempfile
import time
import warnings
import numpy as np
from typing import Optional, Dict, Any, List

BUBBLEFS_VERSION = "2.3.1"
BBL_EXT   = ".bbl"
HGM_EXT   = ".hgm"
PFLD_EXT  = ".pfld"

# Magiki warstwy BubbleFS – do plików szyfrowanych/plaintext
_BBL_MAGIC_ENC = b"BBL1"
_BBL_MAGIC_PLN = b"BBL0"
_HGM_MAGIC_ENC = b"HGM1"
_HGM_MAGIC_PLN = b"HGM0"
_NPZ_MAGIC_ENC = b"NPZ1"
_NPZ_MAGIC_PLN = b"NPZ0"

# Crypto header
CRYPTO_VERSION = 0x01
CRYPTO_ALG_AES256GCM = 0x01

_ID_REGEX = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')
MAX_ID_LENGTH = 128
_BLOCKED_NAMES = frozenset({
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1','COM2','COM3','COM4','COM5','COM6','COM7','COM8','COM9',
    'LPT1','LPT2','LPT3','LPT4','LPT5','LPT6','LPT7','LPT8','LPT9',
    'DEV', 'NULL', 'ZERO', 'RANDOM', 'URANDOM'
})

MAX_BBL_SIZE  = 10 * 1024 * 1024
MAX_HGM_SIZE  = 10 * 1024 * 1024
MAX_NPZ_SIZE  = 256 * 1024 * 1024
MAX_PFLD_SIZE = 50 * 1024 * 1024

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.exceptions import InvalidTag
    _CRYPTO_OK = True
except ImportError:
    _AESGCM = HKDF = hashes = None
    InvalidTag = Exception
    _CRYPTO_OK = False


def _canonical_json(obj: dict) -> bytes:
    return json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), indent=None
    ).encode('utf-8')


def _bbl_key(master_key: bytes, record_id: str) -> bytes:
    return _hmac.new(master_key, b"bbl-v3:" + record_id.encode(), hashlib.sha256).digest()


def _derive_key_hkdf(key: bytes, salt: bytes, record_id: str, context: bytes) -> bytes:
    if not _CRYPTO_OK:
        return key
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt,
                info=b"bubblefs-v3:" + context + b":" + record_id.encode())
    return hkdf.derive(key)


def _aes_encrypt(data: bytes, master_key: bytes, record_id: str,
                 magic_enc: bytes, magic_pln: bytes) -> bytes:
    """Szyfruje dane lub zapisuje jako plaintext z odpowiednim magikiem warstwy BubbleFS."""
    if not _CRYPTO_OK:
        return magic_pln + data
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _bbl_key(master_key, record_id)
    derived = _derive_key_hkdf(key, salt, record_id, magic_enc)
    aad = magic_enc + bytes([CRYPTO_VERSION, CRYPTO_ALG_AES256GCM]) + record_id.encode()
    ct = _AESGCM(derived).encrypt(nonce, data, aad)
    return magic_enc + bytes([CRYPTO_VERSION, CRYPTO_ALG_AES256GCM]) + salt + nonce + ct


def _aes_decrypt(blob: bytes, master_key: bytes, record_id: str,
                 magic_enc: bytes, magic_pln: bytes) -> bytes:
    """Deszyfruje dane – rozpoznaje magik warstwy BubbleFS i odszyfrowuje."""
    if len(blob) < 4:
        raise ValueError("Plik za krótki")
    magic = blob[:4]
    if magic == magic_pln:
        return blob[4:]
    if magic != magic_enc:
        raise ValueError(f"Zły magic: {magic!r}")
    if len(blob) < 6 + 16 + 12 + 16:
        raise ValueError("Plik za krótki")
    crypto_ver = blob[4]
    crypto_alg = blob[5]
    if crypto_ver != CRYPTO_VERSION or crypto_alg != CRYPTO_ALG_AES256GCM:
        raise ValueError(f"Nieobsługiwany crypto header: v{crypto_ver} alg{crypto_alg}")
    salt = blob[6:22]
    nonce = blob[22:34]
    ct = blob[34:]
    if not _CRYPTO_OK:
        return ct
    key = _bbl_key(master_key, record_id)
    derived = _derive_key_hkdf(key, salt, record_id, magic_enc)
    aad = magic_enc + bytes([CRYPTO_VERSION, CRYPTO_ALG_AES256GCM]) + record_id.encode()
    try:
        return _AESGCM(derived).decrypt(nonce, ct, aad)
    except InvalidTag:
        raise ValueError("Odszyfrowanie nieudane")


def _get_master_key(karmazyn_os, shared_secret: Optional[bytes]) -> bytes:
    if shared_secret is not None:
        return shared_secret
    p2s = getattr(getattr(karmazyn_os, "phi", None), "_p2s", None)
    if p2s:
        return p2s
    raise ValueError("Brak klucza")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()

def _ub64(s: str) -> bytes:
    return base64.b64decode(s)

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

def _validate_id(id_str: str) -> None:
    if len(id_str) > MAX_ID_LENGTH:
        raise ValueError(f"ID za długie: {len(id_str)} > {MAX_ID_LENGTH}")
    if not _ID_REGEX.match(id_str):
        raise ValueError(f"Niedozwolone znaki w ID: {id_str!r}")
    if id_str.upper() in _BLOCKED_NAMES:
        raise ValueError(f"Zarezerwowana nazwa: {id_str!r}")

def _atomic_write(fpath: str, data: bytes) -> None:
    dir_path = os.path.dirname(os.path.abspath(fpath))
    os.makedirs(dir_path, exist_ok=True)
    tmp_fd = tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix='.bfs_', suffix='.tmp')
        with os.fdopen(tmp_fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        tmp_fd = None
        os.replace(tmp_path, fpath)
        tmp_path = None
    except Exception:
        if tmp_fd is not None: os.close(tmp_fd)
        if tmp_path is not None: os.unlink(tmp_path)
        raise

def _get_atom_label(atom) -> Optional[str]:
    return atom.get('label') if isinstance(atom, dict) else getattr(atom, 'label', None)

def _get_atom_S(atom) -> Optional[np.ndarray]:
    v = atom.get('S') if isinstance(atom, dict) else getattr(atom, 'S', None)
    if v is None: return None
    try: return np.asarray(v, dtype=np.float32)
    except: return None

def _get_atom_T(atom) -> float:
    return float(atom.get('T', 1.0)) if isinstance(atom, dict) else float(getattr(atom, 'T', 1.0))

def _manifest_hash(base_path: str) -> str:
    h = hashlib.sha256()
    for subdir in ("bubbles", "holograms", "phi", "fields"):
        d = os.path.join(base_path, subdir)
        if not os.path.isdir(d): continue
        for root, _, files in os.walk(d):
            for fname in sorted(files):
                if fname.startswith('.'): continue
                fpath = os.path.join(root, fname)
                if not os.path.isfile(fpath): continue
                rel = os.path.relpath(fpath, base_path)
                h.update(rel.encode('utf-8'))
                with open(fpath, 'rb') as f:
                    while chunk := f.read(65536):
                        h.update(chunk)
    return h.hexdigest()

def _read_with_limit(fpath: str, max_size: int) -> bytes:
    size = os.path.getsize(fpath)
    if size > max_size:
        raise ValueError(f"Plik {fpath} przekracza limit {max_size} bajtów (ma {size})")
    with open(fpath, 'rb') as f:
        return f.read()


# ═══════════════ EKSPORT / IMPORT ═══════════════

def export(karmazyn_os, path: str, shared_secret: Optional[bytes] = None,
           include_phi_vectors: bool = True, use_proca: bool = False) -> dict:
    os.makedirs(path, exist_ok=True)
    bdir = os.path.join(path, "bubbles"); os.makedirs(bdir, exist_ok=True)
    hdir = os.path.join(path, "holograms"); os.makedirs(hdir, exist_ok=True)
    pdir = os.path.join(path, "phi"); os.makedirs(pdir, exist_ok=True)
    fdir = os.path.join(path, "fields"); os.makedirs(fdir, exist_ok=True)

    ko = karmazyn_os
    master_key = _get_master_key(ko, shared_secret)

    proca_idx = None
    if use_proca:
        try:
            from karmazyn_proca import ProcaIndex, phi_coords_from_bubble
            proca_idx = ProcaIndex(fields_dir=fdir)
        except ImportError:
            warnings.warn("[BubbleFS] karmazyn_proca.py niedostępny – eksport bez Proca.")

    exported_bubbles, exported_holograms = [], []
    n_proca_src = n_proca_coord = 0

    for bid, bubble in list(ko.bubbles._b.items()):
        _validate_id(bid)
        revoked = bid in ko.bubbles._rev
        raw_content = bubble.decrypt_content()
        bbl = {
            "id": bid, "label": bubble.label, "inode": bubble.inode,
            "epoch_born": bubble.epoch_born, "recall_count": bubble.recall_count,
            "consolidated_from": bubble.consolidated_from, "metadata": bubble.metadata,
            "revoked": revoked, "fingerprint_b64": _b64(bubble.fingerprint),
            "S_struct": bubble.S_struct.tolist(), "S_sem": bubble.S_sem.tolist()
        }
        if bubble.decay_start_epoch is not None:
            bbl["decay_start_epoch"] = bubble.decay_start_epoch
            bbl["decay_rate"] = bubble.decay_rate

        proca_done = False
        if proca_idx and raw_content:
            try:
                phi_coords = phi_coords_from_bubble(bubble)
                typ, obj = proca_idx.register_or_deduplicate(
                    bid, raw_content, phi_coords, T=float(getattr(bubble, 'T', 50.0)))
                if typ == "coordinate":
                    bbl["storage"] = "proca"
                    bbl["proca_coord"] = obj.to_json_bytes().decode('utf-8')
                    n_proca_coord += 1; proca_done = True
                elif typ == "source":
                    bbl["storage"] = "proca_src"
                    bbl["proca_field_id"] = obj.field_id
                    bbl["content_b64"] = _b64(raw_content)
                    n_proca_src += 1; proca_done = True
            except Exception as e:
                warnings.warn(f"[BubbleFS] Proca error {bid}: {e}")

        if not proca_done:
            bbl["storage"] = "full"
            bbl["content_b64"] = _b64(raw_content)

        _atomic_write(os.path.join(bdir, bid + BBL_EXT),
            _aes_encrypt(json.dumps(bbl, ensure_ascii=False, default=str).encode(),
                         master_key, bid, _BBL_MAGIC_ENC, _BBL_MAGIC_PLN))
        exported_bubbles.append(bid)

    # Proca sources – zapisane jako plaintext .pfld, następnie szyfrowane warstwą BubbleFS
    if proca_idx:
        proca_idx.save_all_sources()        # zapisuje surowe pliki .pfld (magic PFLD)
        for fname in list(os.listdir(fdir)):
            if not fname.endswith(PFLD_EXT): continue
            fpath = os.path.join(fdir, fname)
            raw_pfld = _read_with_limit(fpath, MAX_PFLD_SIZE)
            # Szyfrujemy jako plik BubbleFS – używamy magików BBL, bo to warstwa transportowa
            if raw_pfld[:4] == b'PFLD':      # surowy .pfld?
                field_id = fname.replace("proca_", "").replace(PFLD_EXT, "")
                _validate_id(field_id)
                _atomic_write(fpath,
                    _aes_encrypt(raw_pfld, master_key, field_id,
                                 _BBL_MAGIC_ENC, _BBL_MAGIC_PLN))

    # Hologramy
    for hid, h in ko.holograms.items():
        _validate_id(hid)
        hgm = {
            "id": h.id, "topic": h.topic, "proto": h.proto.tolist(),
            "generators": [g.tolist() for g in h.generators], "weights": h.weights,
            "bubble_labels": h.bubble_labels, "epoch_created": h.epoch_created,
            "decay_rate": h.decay_rate, "metadata": h.metadata
        }
        _atomic_write(os.path.join(hdir, hid + HGM_EXT),
            _aes_encrypt(json.dumps(hgm, ensure_ascii=False, default=str).encode(),
                         master_key, hid, _HGM_MAGIC_ENC, _HGM_MAGIC_PLN))
        exported_holograms.append(hid)

    # Wektory Φ
    if include_phi_vectors and ko.phi._sem:
        buf = io.BytesIO()
        np.savez(buf, **ko.phi._sem)
        _atomic_write(os.path.join(pdir, "sem_vectors.npz"),
            _aes_encrypt(buf.getvalue(), master_key, "sem_vectors",
                         _NPZ_MAGIC_ENC, _NPZ_MAGIC_PLN))
    if include_phi_vectors and ko.phi._mx.atoms:
        atoms_list = list(ko.phi._mx.atoms)
        s_data, t_data = {}, {}
        for a in atoms_list:
            lbl = _get_atom_label(a)
            if not lbl: continue
            sv = _get_atom_S(a)
            if sv is not None: s_data[lbl] = sv
            t_data[lbl] = np.array([_get_atom_T(a)], dtype=np.float32)
        for fname, d, uid in [("structural.npz", s_data, "structural"),
                              ("temperatures.npz", t_data, "temperatures")]:
            if not d: continue
            buf = io.BytesIO()
            np.savez(buf, **d)
            _atomic_write(os.path.join(pdir, fname),
                _aes_encrypt(buf.getvalue(), master_key, uid,
                             _NPZ_MAGIC_ENC, _NPZ_MAGIC_PLN))

    # Manifest
    integrity = _manifest_hash(path)
    proca_stats = proca_idx.stats() if proca_idx else {}
    manifest = {
        "bubblefs_version": BUBBLEFS_VERSION,
        "karmazyn_version": getattr(ko, 'VERSION', '?'),
        "epoch": ko.phi.epoch, "dim": ko.phi.dim,
        "t_vacuum": ko.phi.t_vacuum(), "temperature": ko.phi.temperature(),
        "n_bubbles": len(exported_bubbles), "n_holograms": len(exported_holograms),
        "n_phi_atoms": len(ko.phi._mx.atoms), "encrypted": _CRYPTO_OK,
        "include_phi_vectors": include_phi_vectors,
        "proca_enabled": use_proca and proca_idx is not None,
        "proca_sources": n_proca_src, "proca_coordinates": n_proca_coord,
        "proca_bytes_saved": proca_stats.get("bytes_saved", 0),
        "integrity_sha256": integrity, "bubble_idx": dict(ko.bubbles._idx)
    }
    canonical_bytes = _canonical_json(manifest)
    if _CRYPTO_OK:
        manifest["integrity_hmac"] = _hmac.new(master_key, canonical_bytes, hashlib.sha256).hexdigest()
        canonical_bytes = _canonical_json(manifest)
    _atomic_write(os.path.join(path, "manifest.json"), canonical_bytes)
    print(f"[BubbleFS] Eksport → {path}")
    return manifest


def import_(karmazyn_os, path: str, shared_secret: Optional[bytes] = None,
            merge: bool = False, verify_integrity: bool = True) -> dict:
    if not os.path.isdir(path):
        raise FileNotFoundError(f"BubbleFS: katalog nie istnieje: {path}")
    bdir = os.path.join(path, "bubbles")
    hdir = os.path.join(path, "holograms")
    pdir = os.path.join(path, "phi")
    fdir = os.path.join(path, "fields")
    master_key = _get_master_key(karmazyn_os, shared_secret)

    with open(os.path.join(path, "manifest.json"), 'rb') as f:
        manifest = json.loads(f.read().decode('utf-8'))

    if verify_integrity:
        actual = _manifest_hash(path)
        if actual != manifest.get("integrity_sha256"):
            raise ValueError(f"Błąd integralności! Oczekiwano {manifest['integrity_sha256']}, jest {actual}")
        if _CRYPTO_OK and "integrity_hmac" in manifest:
            stored = manifest.pop("integrity_hmac", None)
            recalc = _hmac.new(master_key, _canonical_json(manifest), hashlib.sha256).hexdigest()
            manifest["integrity_hmac"] = stored
            if recalc != stored:
                raise ValueError("Nieprawidłowy HMAC manifestu!")

    ko = karmazyn_os
    if not merge:
        ko.bubbles._b.clear(); ko.bubbles._idx.clear(); ko.bubbles._rev.clear()
        ko.holograms.clear()

    imported_bubbles, imported_holograms, skipped = [], [], []

    # Proca index – wczytaj źródła z dysku (deszyfruj warstwę BubbleFS)
    proca_idx = None
    if manifest.get("proca_enabled") and os.path.isdir(fdir):
        try:
            from karmazyn_proca import ProcaIndex, ProcaFieldSource
            proca_idx = ProcaIndex(fields_dir=fdir)
            for fname in os.listdir(fdir):
                if not fname.endswith(PFLD_EXT): continue
                fpath = os.path.join(fdir, fname)
                raw = _read_with_limit(fpath, MAX_PFLD_SIZE)
                # Jeśli plik ma magik BBL (zaszyfrowany), odszyfruj go
                if raw[:4] in (_BBL_MAGIC_ENC, _BBL_MAGIC_PLN):
                    field_id = fname.replace("proca_", "").replace(PFLD_EXT, "")
                    _validate_id(field_id)
                    raw = _aes_decrypt(raw, master_key, field_id,
                                       _BBL_MAGIC_ENC, _BBL_MAGIC_PLN)
                src = ProcaFieldSource.deserialize(raw)
                proca_idx._sources[src.field_id] = src
        except ImportError:
            pass
        except Exception as e:
            warnings.warn(f"[BubbleFS] Proca index error: {e}")

    # Klasy
    BubbleClass = type(next(iter(ko.bubbles._b.values()))) if ko.bubbles._b else None
    if BubbleClass is None:
        try: from karmazyn import Bubble as BubbleClass
        except: pass
    try: from karmazyn import Hologram as HologramClass
    except: HologramClass = None

    # Bąble
    if os.path.isdir(bdir):
        for fname in sorted(os.listdir(bdir)):
            if not fname.endswith(BBL_EXT): continue
            record_id = fname[:-len(BBL_EXT)]
            _validate_id(record_id)
            try:
                raw = _read_with_limit(os.path.join(bdir, fname), MAX_BBL_SIZE)
                bbl = json.loads(_aes_decrypt(raw, master_key, record_id,
                                              _BBL_MAGIC_ENC, _BBL_MAGIC_PLN).decode())
                bid, label = bbl["id"], bbl["label"]
                if merge and bid in ko.bubbles._b:
                    skipped.append(bid); continue
                storage = bbl.get("storage", "full")
                raw_content = None
                if storage in ("full", "proca_src"):
                    raw_content = _ub64(bbl["content_b64"])
                elif storage == "proca":
                    if proca_idx:
                        try:
                            from karmazyn_proca import ProcaCoordinate
                            coord = ProcaCoordinate.from_json_bytes(bbl["proca_coord"].encode(), bid)
                            raw_content = proca_idx.resolve_coordinate(coord)
                        except Exception as e:
                            warnings.warn(f"Proca resolve {bid}: {e}")
                    if raw_content is None:
                        skipped.append(bid); continue
                else:
                    raw_content = _ub64(bbl.get("content_b64", ""))
                raw_content = raw_content or b""
                if BubbleClass:
                    new_key = ko.bubbles._make_key(bid) if not bbl.get("revoked") else b""
                    b = BubbleClass(
                        id=bid, label=label,
                        S_struct=np.array(bbl["S_struct"], dtype=np.float32),
                        S_sem=np.array(bbl["S_sem"], dtype=np.float32),
                        fingerprint=_ub64(bbl["fingerprint_b64"]),
                        bubble_key=new_key,
                        encrypted_content=_xor_crypt(raw_content, new_key) if new_key else raw_content,
                        inode=bbl.get("inode", f"karmazyn://bubbles/{label}"),
                        epoch_born=bbl.get("epoch_born", 0),
                        recall_count=bbl.get("recall_count", 0),
                        consolidated_from=bbl.get("consolidated_from", ""),
                        metadata=bbl.get("metadata", {}))
                    if bbl.get("decay_start_epoch"):
                        b.decay_start_epoch = bbl["decay_start_epoch"]
                        b.decay_rate = bbl.get("decay_rate", 0.0)
                    if hasattr(b, "immortal"): b.immortal = bbl.get("immortal", False)
                    ko.bubbles._b[bid] = b
                    ko.bubbles._idx[label] = bid
                    if bbl.get("revoked"): ko.bubbles._rev.add(bid)
                else:
                    bbl["content_b64"] = _b64(raw_content)
                    bbl["storage"] = "full"
                    ko.bubbles._b[bid] = bbl
                    ko.bubbles._idx[label] = bid
                imported_bubbles.append(bid)
            except Exception as e:
                warnings.warn(f"[BubbleFS] Pominięto bąbel {fname}: {e}")
                skipped.append(record_id)

    # Hologramy
    if os.path.isdir(hdir):
        for fname in sorted(os.listdir(hdir)):
            if not fname.endswith(HGM_EXT): continue
            record_id = fname[:-len(HGM_EXT)]
            _validate_id(record_id)
            try:
                raw = _read_with_limit(os.path.join(hdir, fname), MAX_HGM_SIZE)
                hgm = json.loads(_aes_decrypt(raw, master_key, record_id,
                                              _HGM_MAGIC_ENC, _HGM_MAGIC_PLN).decode())
                hid = hgm["id"]
                if HologramClass:
                    ko.holograms[hid] = HologramClass(
                        id=hid, topic=hgm["topic"],
                        proto=np.array(hgm["proto"], dtype=np.float32),
                        generators=[np.array(g, dtype=np.float32) for g in hgm["generators"]],
                        weights=hgm["weights"], bubble_labels=hgm["bubble_labels"],
                        epoch_created=hgm["epoch_created"], decay_rate=hgm.get("decay_rate", 0.001),
                        metadata=hgm.get("metadata", {}))
                else:
                    ko.holograms[hid] = hgm
                imported_holograms.append(hid)
            except Exception as e:
                warnings.warn(f"[BubbleFS] Pominięto hologram {fname}: {e}")
                skipped.append(record_id)

    # Φ wektory
    def _load_npz(fpath, uid):
        raw = _read_with_limit(fpath, MAX_NPZ_SIZE)
        if raw[:4] in (_NPZ_MAGIC_ENC, _NPZ_MAGIC_PLN):
            raw = _aes_decrypt(raw, master_key, uid, _NPZ_MAGIC_ENC, _NPZ_MAGIC_PLN)
        return np.load(io.BytesIO(raw), allow_pickle=False)

    sem_path = os.path.join(pdir, "sem_vectors.npz")
    if os.path.exists(sem_path):
        try:
            sem = _load_npz(sem_path, "sem_vectors")
            for k in sem.files: ko.phi._sem[k] = sem[k]
        except Exception as e: warnings.warn(f"[BubbleFS] Ostrzeżenie sem_vectors: {e}")
    str_path = os.path.join(pdir, "structural.npz")
    temp_path = os.path.join(pdir, "temperatures.npz")
    if os.path.exists(str_path) and os.path.exists(temp_path):
        try:
            s = _load_npz(str_path, "structural")
            t = _load_npz(temp_path, "temperatures")
            existing = set()
            for a in ko.phi._mx.atoms:
                lbl = _get_atom_label(a)
                if lbl: existing.add(lbl)
            for lbl in s.files:
                if lbl not in existing:
                    T = float(t[lbl][0]) if lbl in t.files else 1.0
                    ko.phi._mx.add_atom_vector(label=lbl, topic="bubblefs_import",
                                               vector=s[lbl], init_T=T)
        except Exception as e: warnings.warn(f"[BubbleFS] Ostrzeżenie structural: {e}")

    result = {"imported_bubbles": len(imported_bubbles), "imported_holograms": len(imported_holograms),
              "skipped": skipped, "merged": merge, "source_epoch": manifest.get("epoch"),
              "source_dim": manifest.get("dim"), "integrity_ok": verify_integrity,
              "proca_resolved": manifest.get("proca_coordinates", 0)}
    print(f"[BubbleFS] Import ← {path}")
    return result


def inspect(path: str) -> dict:
    mpath = os.path.join(path, "manifest.json")
    if not os.path.exists(mpath): raise FileNotFoundError
    with open(mpath, 'rb') as f: m = json.loads(f.read())
    b_files = os.listdir(os.path.join(path, "bubbles")) if os.path.isdir(os.path.join(path, "bubbles")) else []
    h_files = os.listdir(os.path.join(path, "holograms")) if os.path.isdir(os.path.join(path, "holograms")) else []
    f_files = [x for x in (os.listdir(os.path.join(path, "fields")) if os.path.isdir(os.path.join(path, "fields")) else [])
               if x.endswith(PFLD_EXT)]
    print(f"[BubbleFS] {path}  wersja {m.get('bubblefs_version')}")
    return m

def export_single_bubble(karmazyn_os, label: str, path: str, shared_secret=None) -> Optional[str]:
    ko = karmazyn_os
    b = ko.bubbles.get_by_label(label)
    if not b: return
    os.makedirs(path, exist_ok=True)
    _validate_id(b.id)
    raw_content = b.decrypt_content()
    master_key = _get_master_key(ko, shared_secret)
    bbl = {"id": b.id, "label": b.label, "inode": b.inode, "epoch_born": b.epoch_born,
           "recall_count": b.recall_count, "consolidated_from": b.consolidated_from,
           "metadata": b.metadata, "revoked": b.id in ko.bubbles._rev,
           "storage": "full", "content_b64": _b64(raw_content), "fingerprint_b64": _b64(b.fingerprint),
           "S_struct": b.S_struct.tolist(), "S_sem": b.S_sem.tolist()}
    if b.decay_start_epoch is not None:
        bbl["decay_start_epoch"] = b.decay_start_epoch
        bbl["decay_rate"] = b.decay_rate
    fpath = os.path.join(path, b.id + BBL_EXT)
    _atomic_write(fpath, _aes_encrypt(json.dumps(bbl, ensure_ascii=False, default=str).encode(),
                                      master_key, b.id, _BBL_MAGIC_ENC, _BBL_MAGIC_PLN))
    print(f"[BubbleFS] Eksport bąbla → {fpath}")
    return fpath