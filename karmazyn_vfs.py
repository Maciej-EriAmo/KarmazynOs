#!/usr/bin/env python3
"""
karmazyn_vfs.py — KarmazynOS Virtual File System v2.0
======================================================
Warstwa szyfrowanego przechowywania bąbli oparta na KAFD v2.0.
Kompatybilna z FM (karmazyn_fm.py v2.1) i innymi komponentami.
"""

import os
import json
from typing import Any, Optional, List, Dict, Tuple

# Import KAFD v2.0
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

# Szyfrowanie AES-256-GCM
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

_VFS_MAGIC = b"BVFS"

def _derive_key(workspace_key: bytes, label: str) -> bytes:
    import hmac, hashlib
    return hmac.new(workspace_key, b"vfs:" + label.encode(), hashlib.sha256).digest()

def vfs_encrypt(plaintext: bytes, workspace_key: bytes, label: str) -> bytes:
    if not _CRYPTO_OK:
        return _VFS_MAGIC + b"\x00" * 28 + plaintext
    import os
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(workspace_key, label)
    ct = AESGCM(key).encrypt(nonce, plaintext, _VFS_MAGIC + label.encode())
    return _VFS_MAGIC + salt + nonce + ct

def vfs_decrypt(blob: bytes, workspace_key: bytes, label: str) -> bytes:
    if blob[:4] != _VFS_MAGIC:
        return blob
    salt = blob[4:20]
    nonce = blob[20:32]
    ct = blob[32:]
    if not _CRYPTO_OK or (salt == b"\x00" * 16 and nonce == b"\x00" * 12):
        return ct
    key = _derive_key(workspace_key, label)
    return AESGCM(key).decrypt(nonce, ct, _VFS_MAGIC + label.encode())

def vfs_workspace_key() -> bytes:
    key_path = os.path.join(".bubbles", ".vfskey")
    if os.path.exists(key_path):
        try:
            raw = open(key_path, "rb").read()
            if len(raw) == 32: return raw
        except: pass
    new_key = os.urandom(32)
    os.makedirs(".bubbles", exist_ok=True)
    with open(key_path, "wb") as f: f.write(new_key)
    return new_key

class BubbleVFS:
    CONTENT_DIR = ".bubbles/content"
    TMP_DIR = ".bubbles/tmp"

    def __init__(self):
        os.makedirs(self.CONTENT_DIR, exist_ok=True)
        os.makedirs(self.TMP_DIR, exist_ok=True)

    def _content_path(self, label: str) -> str:
        return os.path.join(self.CONTENT_DIR, f"{label}.kafd")

    def _tmp_path(self, label: str, ext: str = ".txt") -> str:
        return os.path.join(self.TMP_DIR, f"{label}{ext}")

    # --- Operacje na bąblach (API dla FM) ---

    def list_bubbles(self) -> List[dict]:
        result = []
        if not os.path.exists(self.CONTENT_DIR):
            return result
        for fname in os.listdir(self.CONTENT_DIR):
            if not fname.endswith(".kafd"):
                continue
            label = fname[:-5]
            path = self._content_path(label)
            if not os.path.exists(path):
                continue
            try:
                raw = open(path, "rb").read()
                dec = vfs_decrypt(raw, vfs_workspace_key(), label)
                reader = KAFDReader(dec)
                meta = reader.meta
                active = len([aid for aid in reader.atom_ids if aid != "__main__"])
                size = os.path.getsize(path)
                result.append({
                    "id": label,
                    "label": label,
                    "content_type": meta.get("content_type", "txt"),
                    "size": size,
                    "size_bytes": size,
                    "active_atoms": active,
                })
            except Exception:
                continue
        return result

    def create_bubble(self, name: str) -> str:
        self.save(name, "", "txt")
        return name

    def delete_bubble(self, bubble_id: str) -> None:
        path = self._content_path(bubble_id)
        if os.path.exists(path):
            os.remove(path)
        for ext in [".txt", ".py", ".md", ".karm", ".sh"]:
            tmp = self._tmp_path(bubble_id, ext)
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
                "id": atom_id,
                "S": getattr(atom, "S", ""),
                "E": getattr(atom, "E", ""),
                "T": getattr(atom, "T", 50.0),
                "T_max": getattr(atom, "T_max", 100.0),
                "state": getattr(atom, "state", "WARM"),
                "_manifest_v": 2
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
            # Odczytaj z danych atomu (jeśli JSON) aby wydobyć T i S
            raw = atoms_data[aid]
            T = 50.0
            S = "binary"
            try:
                if raw.startswith(b'{'):
                    d = json.loads(raw.decode())
                    T = d.get("T", 50.0)
                    S = d.get("S", S)
            except:
                pass
            atoms.append({
                "id": aid,
                "S": S,
                "T": T,
                "state": "WARM" if T > 30 else "COLD"
            })
        return atoms

    # --- Metody pomocnicze do odczytu/zapisu KAFD (z szyfrowaniem) ---

    def _load_kafd(self, label: str) -> Tuple[Dict[str, bytes], dict]:
        path = self._content_path(label)
        if not os.path.exists(path):
            return {}, {"content_type": "txt"}
        try:
            raw = open(path, "rb").read()
            dec = vfs_decrypt(raw, vfs_workspace_key(), label)
            atoms, meta = vfs_unpack(dec)
            return atoms, meta
        except Exception:
            return {}, {"content_type": "txt"}

    def _save_kafd(self, label: str, atoms_data: Dict[str, bytes], meta: dict) -> None:
        blob = vfs_pack(atoms_data, meta)
        enc = vfs_encrypt(blob, vfs_workspace_key(), label)
        path = self._content_path(label)
        with open(path, "wb") as f:
            f.write(enc)

    # --- Metody dla edytorów (zgodność z poprzednim API) ---

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
        return os.path.exists(self._content_path(label))

    def materialize(self, label: str, content: str, content_type: str = "py") -> str:
        ext = { "py": ".py", "txt": ".txt", "md": ".md", "karm": ".karm", "sh": ".sh" }.get(content_type, ".txt")
        path = self._tmp_path(label, ext)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def read_tmp(self, label: str, content_type: str = "py") -> Optional[str]:
        ext = { "py": ".py", "txt": ".txt", "md": ".md", "karm": ".karm", "sh": ".sh" }.get(content_type, ".txt")
        path = self._tmp_path(label, ext)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()

    def cleanup_tmp(self, label: str, content_type: str = "py") -> None:
        ext = { "py": ".py", "txt": ".txt", "md": ".md", "karm": ".karm", "sh": ".sh" }.get(content_type, ".txt")
        path = self._tmp_path(label, ext)
        try:
            os.remove(path)
        except:
            pass