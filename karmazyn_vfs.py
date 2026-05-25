"""
karmazyn_vfs.py — KarmazynOS Virtual File System v1.0
======================================================
Wspólna warstwa szyfrowanego przechowywania bąbli.
Poprzednio duplikowana w NooEdit.py i AstraEdit.py.

Filozofia:
  Bąbel jest dokumentem — bubble.content to canonical source.
  VFS to zaszyfrowany backup na wypadek restartu (AES-256-GCM).
  Plik tymczasowy (.bubbles/tmp) to workspace edytora — efemeryczny.

Izomorfizm z phi-space:
  label  ≡ atom.id    (adres)
  content ≡ atom.E    (emanacja — treść)
  VFS     ≡ persistence layer dla atomów-dokumentów

Użycie:
  vfs = BubbleVFS()
  vfs.save("moj_skrypt", "print('hello')", ".py")
  content = vfs.load("moj_skrypt", ".py")    # None jeśli brak
  tmp = vfs.materialize("moj_skrypt", content, ".py")  # ścieżka tmp
"""

import hashlib
import hmac as _hmac
import os
from typing import Optional

# ── Szyfrowanie AES-256-GCM ───────────────────────────────────────────────────

_VFS_MAGIC = b"BVFS"  # nagłówek identyfikujący zaszyfrowany blob

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    _CRYPTO_OK = True
except ImportError:
    _AESGCM    = None
    _CRYPTO_OK = False


def _derive_key(workspace_key: bytes, label: str) -> bytes:
    """Derywuje klucz szyfrowania dla konkretnej etykiety bąbla."""
    return _hmac.new(
        workspace_key,
        b"vfs:" + label.encode(),
        hashlib.sha256
    ).digest()


def vfs_encrypt(plaintext: bytes, workspace_key: bytes, label: str) -> bytes:
    """
    Szyfruje treść bąbla (AES-256-GCM).
    Bez cryptography: zwraca plaintext z nagłówkiem (fallback bez szyfrowania).
    """
    if not _CRYPTO_OK:
        return _VFS_MAGIC + b"\x00" * 28 + plaintext
    salt  = os.urandom(16)
    nonce = os.urandom(12)
    key   = _hmac.new(_derive_key(workspace_key, label),
                      salt, hashlib.sha256).digest()
    ct    = _AESGCM(key).encrypt(nonce, plaintext, _VFS_MAGIC + label.encode())
    return _VFS_MAGIC + salt + nonce + ct


def vfs_decrypt(blob: bytes, workspace_key: bytes, label: str) -> bytes:
    """
    Deszyfruje blob z VFS.
    Rozpoznaje blobы niezaszyfrowane (fallback) przez nagłówek.
    """
    if blob[:4] != _VFS_MAGIC:
        return blob  # stary format bez szyfrowania
    salt  = blob[4:20]
    nonce = blob[20:32]
    ct    = blob[32:]
    if not _CRYPTO_OK or (salt == b"\x00" * 16 and nonce == b"\x00" * 12):
        return ct  # fallback: brak szyfrowania
    key = _hmac.new(_derive_key(workspace_key, label),
                    salt, hashlib.sha256).digest()
    try:
        return _AESGCM(key).decrypt(nonce, ct, _VFS_MAGIC + label.encode())
    except Exception as e:
        raise ValueError(f"VFS: deszyfrowanie nieudane dla '{label}': {type(e).__name__}")


def vfs_workspace_key() -> bytes:
    """
    Zwraca klucz workspace (32 bajty).
    Przy pierwszym wywołaniu generuje i zapisuje do .bubbles/.vfskey.
    Klucz jest persistentny między sesjami.
    """
    key_path = os.path.join(".bubbles", ".vfskey")
    if os.path.exists(key_path):
        try:
            raw = open(key_path, "rb").read()
            if len(raw) == 32:
                return raw
        except Exception:
            pass
    new_key = os.urandom(32)
    try:
        os.makedirs(".bubbles", exist_ok=True)
        open(key_path, "wb").write(new_key)
    except Exception:
        pass  # brak dostępu do dysku — klucz sesyjny
    return new_key


# ── BubbleVFS ─────────────────────────────────────────────────────────────────

class BubbleVFS:
    """
    Szyfrowany system plików dla bąbli KarmazynOS.

    Dwa katalogi:
      .bubbles/content/  — zaszyfrowane canonical backupy
      .bubbles/tmp/      — efemeryczne pliki workspace edytora

    Canonical source bąbla: bubble.content (w runtime).
    VFS: zaszyfrowany backup który przeżywa restart.
    Tmp: chwilowy plik do edycji — może być usunięty w każdej chwili.
    """

    CONTENT_DIR = ".bubbles/content"
    TMP_DIR     = ".bubbles/tmp"

    # Mapowanie typów treści → rozszerzenia
    _EXT = {
        "py":   ".py",
        "lua":  ".lua",
        "md":   ".md",
        "txt":  ".txt",
        "karm": ".karm",
        "sh":   ".sh",
    }

    def __init__(self):
        os.makedirs(self.CONTENT_DIR, exist_ok=True)
        os.makedirs(self.TMP_DIR,     exist_ok=True)

    def _ext(self, content_type: str) -> str:
        """Rozszerzenie pliku dla typu treści."""
        return self._EXT.get(content_type, ".txt")

    def _content_path(self, label: str, content_type: str) -> str:
        return os.path.join(self.CONTENT_DIR,
                            f"{label}{self._ext(content_type)}")

    def _tmp_path(self, label: str, content_type: str) -> str:
        return os.path.join(self.TMP_DIR,
                            f"{label}{self._ext(content_type)}")

    # ── Canonical backup ──────────────────────────────────────────────────────

    def save(self, label: str, content: str,
             content_type: str = "py") -> str:
        """
        Zapisz zaszyfrowany backup bąbla.
        Zwraca ścieżkę do pliku lub '' przy błędzie.
        """
        path = self._content_path(label, content_type)
        try:
            key  = vfs_workspace_key()
            blob = vfs_encrypt(content.encode("utf-8"), key, label)
            with open(path, "wb") as f:
                f.write(blob)
            return path
        except Exception:
            return ""

    def load(self, label: str,
             content_type: str = "py") -> Optional[str]:
        """
        Wczytaj zaszyfrowany backup bąbla.
        Zwraca None jeśli brak pliku lub błąd deszyfrowania.
        """
        path = self._content_path(label, content_type)
        if not os.path.exists(path):
            return None
        try:
            raw = open(path, "rb").read()
            key = vfs_workspace_key()
            return vfs_decrypt(raw, key, label).decode("utf-8")
        except Exception:
            # Próba odczytu jako zwykły tekst (migracja starszych plików)
            try:
                return open(path, encoding="utf-8", errors="replace").read()
            except Exception:
                return None

    def has(self, label: str, content_type: str = "py") -> bool:
        """Sprawdza czy istnieje backup dla bąbla."""
        return os.path.exists(self._content_path(label, content_type))

    # ── Tmp workspace ─────────────────────────────────────────────────────────

    def materialize(self, label: str, content: str,
                    content_type: str = "py") -> str:
        """
        Zapisz treść do pliku tymczasowego (workspace edytora).
        Zwraca ścieżkę do pliku tmp.
        Plik tmp nie jest szyfrowany — jest efemeryczny.
        """
        path = self._tmp_path(label, content_type)
        try:
            with open(path, "w", encoding="utf-8", errors="replace") as f:
                f.write(content)
        except Exception:
            pass
        return path

    def read_tmp(self, label: str,
                 content_type: str = "py") -> Optional[str]:
        """Wczytaj plik tymczasowy (po edycji przez zewnętrzny edytor)."""
        path = self._tmp_path(label, content_type)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return None

    def list_bubbles(self) -> list:
        """Zwraca listę bąbli jako słowniki {label, content_type, size}."""
        result = []
        if not os.path.exists(self.CONTENT_DIR):
            return result
        for fname in os.listdir(self.CONTENT_DIR):
            name, _, ext = fname.rpartition('.')
            if name:
                path = os.path.join(self.CONTENT_DIR, fname)
                result.append({
                    "label":        name,
                    "content_type": ext or "txt",
                    "size":         os.path.getsize(path),
                    "active_atoms": 0,
                })
        return result

    def cleanup_tmp(self, label: str, content_type: str = "py") -> None:
        """Usuń plik tymczasowy po zakończeniu edycji."""
        path = self._tmp_path(label, content_type)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except Exception:
            pass