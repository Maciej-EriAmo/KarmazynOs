#!/usr/bin/env python3
"""
karmazyn_vfs.py — KarmazynOS Virtual File System v2.2.0
========================================================
Warstwa szyfrowanego przechowywania bąbli oparta na KAFD v2.0.

FIX v2.0.1: _sanitize_label() — ochrona przed path traversal

FIX v2.2.0 (diagnoza "nie można zapisać do bąbla"):
  PRZYCZYNA 1 — vfs_workspace_key() ścieżka względna ".bubbles/.vfskey":
    zmiana CWD (Windows z różnych katalogów, Termux po restarcie) → klucz
    nie znaleziony → nowy losowy → stary bąbel nie do odszyfrowania.
    FIX: _VFS_BASE_DIR ABSOLUTNY, ustalony raz przy imporcie.
         Konfiguracja: KARMAZYN_VFS_DIR (env) lub set_vfs_base_dir().
  PRZYCZYNA 2 — _save_kafd() open("wb") bez atomowości/obsługi błędów:
    Windows + plik zablokowany (edytor/OneDrive/antywirus) → PermissionError
    przerywa zapis; crash → plik obcięty.
    FIX: zapis atomowy tempfile + os.replace z retry.
  PRZYCZYNA 3 — _load_kafd() cichy except maskował zły klucz.
    FIX: rozróżnia ValueError i loguje ostrzeżenie z podpowiedzią.
  PRZYCZYNA 4 — list_bubbles() RAW label vs _load_kafd() SANITYZOWANY.
    FIX: oba przez _sanitize_label() — spójny klucz i AAD.
"""

import os
import re
import json
import tempfile
import time
import warnings
from typing import Any, Optional, List, Dict, Tuple

try:
    from karmazyn_kafd import (
        KAFDWriter, KAFDReader, KAFDAtom,
        vfs_pack, vfs_unpack, upgrade_v1,
        A_RAW, A_MANIFEST, A_PHI_ATOM,
        S_HOT, S_WARM, S_COLD, S_TOMB
    )
    _KAFD_OK = True
except ImportError:
    _KAFD_OK = False
    raise ImportError("Brak modułu karmazyn_kafd – wymagany do działania VFS v2.0")

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

_VFS_MAGIC = b"BVFS"

_SAFE_LABEL_RE = re.compile(r'^[a-zA-Z0-9_.-]+$')
_MAX_LABEL_LEN = 128


def _sanitize_label(label: str) -> str:
    """
    Waliduje i sanityzuje label bąbla. IDEMPOTENTNA — gwarantuje zgodność
    nazwy pliku, klucza szyfrowania i AAD. Rzuca ValueError dla niebezpiecznych.
    """
    if not label:
        raise ValueError("Label bąbla nie może być pusty")
    if len(label) > _MAX_LABEL_LEN:
        raise ValueError(f"Label za długi: {len(label)} > {_MAX_LABEL_LEN}")
    if '..' in label:
        raise ValueError(f"Label nie może zawierać '..': {label!r}")
    if '/' in label or '\\' in label:
        raise ValueError(f"Label nie może zawierać separatorów ścieżki: {label!r}")
    if label.startswith('~') or label.startswith('$'):
        raise ValueError(f"Label nie może zaczynać się od ~ lub $: {label!r}")
    if not _SAFE_LABEL_RE.match(label):
        sanitized = re.sub(r'[^a-zA-Z0-9_.-]', '_', label)
        if not sanitized:
            raise ValueError(f"Label nie zawiera dozwolonych znaków: {label!r}")
        return sanitized
    return label


# ── Workspace key — ŚCIEŻKA ABSOLUTNA (FIX PRZYCZYNA 1) ───────────────────────

_VFS_BASE_DIR: str = os.environ.get(
    "KARMAZYN_VFS_DIR",
    os.path.dirname(os.path.abspath(__file__))
)


def set_vfs_base_dir(path: str) -> None:
    """
    Ustaw katalog bazowy PRZED użyciem BubbleVFS.
      Termux:  set_vfs_base_dir("/data/data/com.termux/files/home/karmazyn")
      Windows: set_vfs_base_dir(r"C:\\Users\\Maciej\\karmazyn")
    Alternatywnie: zmienna środowiskowa KARMAZYN_VFS_DIR.
    """
    global _VFS_BASE_DIR
    _VFS_BASE_DIR = os.path.abspath(path)


def _vfskey_path() -> str:
    return os.path.join(_VFS_BASE_DIR, ".bubbles", ".vfskey")


def _derive_key(workspace_key: bytes, label: str) -> bytes:
    import hmac, hashlib
    return hmac.new(workspace_key, b"vfs:" + label.encode(), hashlib.sha256).digest()


def vfs_encrypt(plaintext: bytes, workspace_key: bytes, label: str) -> bytes:
    if not _CRYPTO_OK:
        return _VFS_MAGIC + b"\x00" * 28 + plaintext
    salt  = os.urandom(16)   # zarezerwowane, nieużywane w derywacji (nonce = świeżość)
    nonce = os.urandom(12)
    key   = _derive_key(workspace_key, label)
    ct    = AESGCM(key).encrypt(nonce, plaintext, _VFS_MAGIC + label.encode())
    return _VFS_MAGIC + salt + nonce + ct


def vfs_decrypt(blob: bytes, workspace_key: bytes, label: str) -> bytes:
    if blob[:4] != _VFS_MAGIC:
        return blob
    salt  = blob[4:20]
    nonce = blob[20:32]
    ct    = blob[32:]
    if not _CRYPTO_OK or (salt == b"\x00" * 16 and nonce == b"\x00" * 12):
        return ct
    key = _derive_key(workspace_key, label)
    return AESGCM(key).decrypt(nonce, ct, _VFS_MAGIC + label.encode())


def vfs_workspace_key() -> bytes:
    """
    FIX v2.2.0: _vfskey_path() ABSOLUTNA zamiast ".bubbles/.vfskey" względnej.
    Zmiana CWD generowała nowy klucz → bąble nie do odszyfrowania.
    """
    key_path = _vfskey_path()
    if os.path.exists(key_path):
        try:
            with open(key_path, "rb") as f:
                raw = f.read()
            if len(raw) == 32:
                return raw
        except Exception:
            pass
    new_key = os.urandom(32)
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    with open(key_path, "wb") as f:
        f.write(new_key)
    return new_key


# ── Atomowy zapis (FIX PRZYCZYNA 2) ───────────────────────────────────────────

def _atomic_write(path: str, data: bytes, max_retries: int = 5) -> None:
    """
    tempfile → fsync → os.replace. Atomowe na POSIX i Windows.
    Retry na PermissionError (Windows: OneDrive/antywirus/edytor blokuje plik).
    """
    dir_path = os.path.dirname(os.path.abspath(path))
    os.makedirs(dir_path, exist_ok=True)

    tmp_fd = tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix='.kafd_', suffix='.tmp')
        fd = tmp_fd
        tmp_fd = None   # fdopen przejmuje fd — chroni przed podwójnym close
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        last_err = None
        for attempt in range(max_retries):
            try:
                os.replace(tmp_path, path)
                tmp_path = None
                return
            except PermissionError as e:
                last_err = e
                time.sleep(0.1 * (attempt + 1))
        raise last_err if last_err else OSError(f"os.replace nieudany: {path}")
    except Exception:
        if tmp_fd is not None:
            try: os.close(tmp_fd)
            except OSError: pass
        if tmp_path is not None:
            try: os.unlink(tmp_path)
            except OSError: pass
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# BubbleVFS
# ═══════════════════════════════════════════════════════════════════════════════

class BubbleVFS:
    """
    FIX v2.2.0: CONTENT_DIR i TMP_DIR są ABSOLUTNE (względem _VFS_BASE_DIR),
    niezależne od CWD. Opcjonalny base_dir nadpisuje dla tej instancji.
    """

    def __init__(self, base_dir: str = None):
        base = os.path.abspath(base_dir if base_dir is not None else _VFS_BASE_DIR)
        self.CONTENT_DIR = os.path.join(base, ".bubbles", "content")
        self.TMP_DIR     = os.path.join(base, ".bubbles", "tmp")
        os.makedirs(self.CONTENT_DIR, exist_ok=True)
        os.makedirs(self.TMP_DIR, exist_ok=True)

    def _content_path(self, label: str) -> str:
        return os.path.join(self.CONTENT_DIR, f"{_sanitize_label(label)}.kafd")

    def _tmp_path(self, label: str, ext: str = ".txt") -> str:
        return os.path.join(self.TMP_DIR, f"{_sanitize_label(label)}{ext}")

    # --- Operacje na bąblach (API dla FM) ---

    def list_bubbles(self) -> List[dict]:
        result = []
        if not os.path.exists(self.CONTENT_DIR):
            return result
        for fname in os.listdir(self.CONTENT_DIR):
            if not fname.endswith(".kafd") or fname.startswith('.'):
                continue
            label = fname[:-5]
            path = os.path.join(self.CONTENT_DIR, fname)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                # FIX PRZYCZYNA 4: _sanitize_label spójnie z _load_kafd
                safe_label = _sanitize_label(label)
                dec = vfs_decrypt(raw, vfs_workspace_key(), safe_label)
                reader = KAFDReader(dec)
                meta = reader.meta
                active = len([aid for aid in reader.atom_ids if aid != "__main__"])
                size = os.path.getsize(path)
                result.append({
                    "id": label, "label": label,
                    "content_type": meta.get("content_type", "txt"),
                    "size": size, "size_bytes": size,
                    "active_atoms": active,
                })
            except Exception:
                continue
        return result

    def create_bubble(self, name: str) -> str:
        safe_name = _sanitize_label(name)
        self.save(safe_name, "", "txt")
        return safe_name

    def delete_bubble(self, bubble_id: str) -> None:
        safe_id = _sanitize_label(bubble_id)
        path = os.path.join(self.CONTENT_DIR, f"{safe_id}.kafd")
        if os.path.exists(path):
            os.remove(path)
        for ext in [".txt", ".py", ".md", ".karm", ".sh"]:
            tmp = os.path.join(self.TMP_DIR, f"{safe_id}{ext}")
            if os.path.exists(tmp):
                os.remove(tmp)

    def import_to_bubble(self, bubble_id: str, atom_id: str, phi: Any) -> None:
        atom = phi.get_atom(atom_id)
        if not atom:
            return
        atoms_data, meta = self._load_kafd(bubble_id)
        path = getattr(atom, "E", "")
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
        else:
            data = json.dumps({
                "id": atom_id, "S": getattr(atom, "S", ""),
                "E": getattr(atom, "E", ""), "T": getattr(atom, "T", 50.0),
                "T_max": getattr(atom, "T_max", 100.0),
                "state": getattr(atom, "state", "WARM"), "_manifest_v": 2
            }).encode("utf-8")
        atoms_data[atom_id] = data
        self._save_kafd(bubble_id, atoms_data, meta)

    def remove_from_bubble(self, bubble_id: str, atom_id: str) -> None:
        atoms_data, meta = self._load_kafd(bubble_id)
        if atom_id in atoms_data:
            del atoms_data[atom_id]
            self._save_kafd(bubble_id, atoms_data, meta)

    def get_active_atoms(self, bubble_id: str) -> List[dict]:
        atoms_data, _ = self._load_kafd(bubble_id)
        atoms = []
        for aid in atoms_data:
            if aid == "__main__":
                continue
            raw = atoms_data[aid]
            T, S = 50.0, "binary"
            try:
                if raw.startswith(b'{'):
                    d = json.loads(raw.decode())
                    T = d.get("T", 50.0)
                    S = d.get("S", S)
            except Exception:
                pass
            atoms.append({"id": aid, "S": S, "T": T,
                          "state": "WARM" if T > 30 else "COLD"})
        return atoms

    # --- KAFD odczyt/zapis (z szyfrowaniem) ---

    def _load_kafd(self, label: str) -> Tuple[Dict[str, bytes], dict]:
        path = self._content_path(label)
        if not os.path.exists(path):
            return {}, {"content_type": "txt"}
        try:
            with open(path, "rb") as f:
                raw = f.read()
            safe_label = _sanitize_label(label)
            dec = vfs_decrypt(raw, vfs_workspace_key(), safe_label)
            atoms, meta = vfs_unpack(dec)
            return atoms, meta
        except ValueError as e:
            # FIX PRZYCZYNA 3: zły klucz nie jest cichy
            warnings.warn(
                f"[VFS] Odszyfrowanie nieudane dla {label!r}: {e}\n"
                f"  Klucz workspace się nie zgadza. Ustaw KARMAZYN_VFS_DIR lub\n"
                f"  wywołaj set_vfs_base_dir(). Aktualny .vfskey: {_vfskey_path()}",
                RuntimeWarning, stacklevel=2)
            return {}, {"content_type": "txt"}
        except Exception as e:
            warnings.warn(f"[VFS] Błąd odczytu {label!r}: {type(e).__name__}: {e}",
                          RuntimeWarning, stacklevel=2)
            return {}, {"content_type": "txt"}

    def _save_kafd(self, label: str, atoms_data: Dict[str, bytes], meta: dict) -> None:
        """FIX PRZYCZYNA 2: zapis atomowy zamiast open("wb")."""
        blob = vfs_pack(atoms_data, meta)
        safe_label = _sanitize_label(label)
        enc = vfs_encrypt(blob, vfs_workspace_key(), safe_label)
        _atomic_write(self._content_path(label), enc)

    # --- Metody dla edytorów ---

    def save(self, label: str, content: str, content_type: str = "py") -> str:
        atoms_data, meta = self._load_kafd(label)
        atoms_data["__main__"] = content.encode("utf-8")
        meta["content_type"] = content_type
        self._save_kafd(label, atoms_data, meta)
        return self._content_path(label)

    def load(self, label: str, content_type: str = "py") -> Optional[str]:
        atoms_data, _ = self._load_kafd(label)
        if "__main__" not in atoms_data:
            return None
        data = atoms_data["__main__"]
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return str(data)

    def has(self, label: str, content_type: str = "py") -> bool:
        try:
            return os.path.exists(self._content_path(label))
        except ValueError:
            return False

    def materialize(self, label: str, content: str, content_type: str = "py") -> str:
        ext = {"py": ".py", "txt": ".txt", "md": ".md", "karm": ".karm", "sh": ".sh"}.get(content_type, ".txt")
        path = self._tmp_path(label, ext)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def read_tmp(self, label: str, content_type: str = "py") -> Optional[str]:
        ext = {"py": ".py", "txt": ".txt", "md": ".md", "karm": ".karm", "sh": ".sh"}.get(content_type, ".txt")
        path = self._tmp_path(label, ext)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def cleanup_tmp(self, label: str, content_type: str = "py") -> None:
        ext = {"py": ".py", "txt": ".txt", "md": ".md", "karm": ".karm", "sh": ".sh"}.get(content_type, ".txt")
        path = self._tmp_path(label, ext)
        try:
            os.remove(path)
        except Exception:
            pass