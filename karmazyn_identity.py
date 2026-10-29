"""karmazyn_identity — identity.bin: phi._p2s chroniony przez system albo hasło.

Format v3: PHID(4) + 0x03 + schemat(1) + dane.

  schemat 1  DPAPI (Windows, konto użytkownika). Plik na innym koncie albo
             innej maszynie się nie odszyfruje.
  schemat 2  hasło z KARMAZYN_IDENTITY_PASSPHRASE: scrypt + AES-GCM.
             Dane: sól(16) + nonce(12) + szyfrogram z tagiem.
  schemat 3  jawny p2s, plik 0600. Brak ochrony poza uprawnieniami pliku,
             o czym zapis ostrzega. Tylko gdy nie ma DPAPI ani hasła.

Format v2 (XOR z sha256(hostname|użytkownik)) jest czytany i od razu
przepisywany na v3. v2 dało się łamać offline: tag w pliku potwierdzał
zgadnięty hostname.

KARMAZYN_IDENTITY_SCHEME=dpapi|passphrase|plain wymusza schemat (testy).
"""
from __future__ import annotations

import hashlib
import os
import sys
from typing import Optional, Tuple

MAGIC = b"PHID"
V2 = b"\x02"
V3 = b"\x03"
SCHEME_DPAPI = 1
SCHEME_PASSPHRASE = 2
SCHEME_PLAIN = 3
_NAMES = {"dpapi": SCHEME_DPAPI, "passphrase": SCHEME_PASSPHRASE, "plain": SCHEME_PLAIN}
_ENTROPY = b"karmazyn-identity-v3"
FILENAME = "identity.bin"


class IdentityError(Exception):
    """Plik tożsamości istnieje, ale nie da się go odczytać tym kluczem."""


# ── DPAPI (Windows) ──────────────────────────────────────────────────────────

def _dpapi_available() -> bool:
    return sys.platform == "win32"


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(b: bytes) -> Tuple[_Blob, ctypes.Array]:
        buf = ctypes.create_string_buffer(b, len(b))
        return _Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    blob_in, _keep_in = _blob(data)
    blob_ent, _keep_ent = _blob(_ENTROPY)
    blob_out = _Blob()
    ui_forbidden = 0x1
    if protect:
        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in), "KarmazynOS identity", ctypes.byref(blob_ent),
            None, None, ui_forbidden, ctypes.byref(blob_out),
        )
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, ctypes.byref(blob_ent),
            None, None, ui_forbidden, ctypes.byref(blob_out),
        )
    if not ok:
        raise IdentityError(f"DPAPI: błąd {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


# ── hasło: scrypt + AES-GCM ──────────────────────────────────────────────────

def _passphrase() -> Optional[bytes]:
    p = os.environ.get("KARMAZYN_IDENTITY_PASSPHRASE")
    return p.encode("utf-8") if p else None


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        return None
    return AESGCM


def _kdf(passphrase: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(passphrase, salt=salt, n=2 ** 15, r=8, p=1,
                          maxmem=64 * 1024 * 1024, dklen=32)


# ── v2 (stary XOR) ───────────────────────────────────────────────────────────

def _machine_fingerprint() -> bytes:
    parts = []
    try:
        import socket
        parts.append(socket.gethostname())
    except Exception:
        pass
    try:
        import getpass
        parts.append(getpass.getuser())
    except Exception:
        pass
    for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(candidate) as f:
                parts.append(f.read().strip())
            break
        except Exception:
            pass
    raw = "|".join(parts).encode() or b"karmazyn-default"
    return hashlib.sha256(raw).digest()


def _read_v2(data: bytes) -> Optional[bytes]:
    if len(data) != 4 + 1 + 8 + 32:
        return None
    fp = _machine_fingerprint()
    if data[5:13] != fp[:8]:
        return None
    return bytes(a ^ b for a, b in zip(data[13:], fp))


# ── API ──────────────────────────────────────────────────────────────────────

def _pick_scheme() -> int:
    forced = os.environ.get("KARMAZYN_IDENTITY_SCHEME", "").strip().lower()
    if forced:
        if forced not in _NAMES:
            raise IdentityError(f"nieznany KARMAZYN_IDENTITY_SCHEME={forced}")
        return _NAMES[forced]
    if _dpapi_available():
        return SCHEME_DPAPI
    if _passphrase() and _aesgcm() is not None:
        return SCHEME_PASSPHRASE
    return SCHEME_PLAIN


def encode(p2s: bytes, scheme: Optional[int] = None) -> bytes:
    if len(p2s) != 32:
        raise ValueError("p2s musi mieć 32 bajty")
    scheme = _pick_scheme() if scheme is None else scheme
    head = MAGIC + V3 + bytes([scheme])
    if scheme == SCHEME_DPAPI:
        return head + _dpapi(p2s, protect=True)
    if scheme == SCHEME_PASSPHRASE:
        pw, aes = _passphrase(), _aesgcm()
        if not pw or aes is None:
            raise IdentityError("schemat hasła wymaga KARMAZYN_IDENTITY_PASSPHRASE i cryptography")
        salt, nonce = os.urandom(16), os.urandom(12)
        ct = aes(_kdf(pw, salt)).encrypt(nonce, p2s, MAGIC + V3)
        return head + salt + nonce + ct
    if scheme == SCHEME_PLAIN:
        return head + p2s
    raise IdentityError(f"nieznany schemat {scheme}")


def decode(data: bytes) -> Tuple[bytes, bool]:
    """(p2s, legacy). legacy=True dla v2: wołający powinien zapisać v3."""
    if data[:4] != MAGIC or len(data) < 6:
        raise IdentityError("to nie jest plik tożsamości")
    if data[4:5] == V2:
        p2s = _read_v2(data)
        if p2s is None:
            raise IdentityError("identity.bin v2 z innej maszyny")
        return p2s, True
    if data[4:5] != V3:
        raise IdentityError("nieznana wersja identity.bin")
    scheme, body = data[5], data[6:]
    if scheme == SCHEME_DPAPI:
        if not _dpapi_available():
            raise IdentityError("identity.bin chroni DPAPI (Windows)")
        p2s = _dpapi(body, protect=False)
    elif scheme == SCHEME_PASSPHRASE:
        pw, aes = _passphrase(), _aesgcm()
        if not pw or aes is None:
            raise IdentityError("identity.bin wymaga KARMAZYN_IDENTITY_PASSPHRASE")
        salt, nonce, ct = body[:16], body[16:28], body[28:]
        try:
            p2s = aes(_kdf(pw, salt)).decrypt(nonce, ct, MAGIC + V3)
        except Exception:
            raise IdentityError("złe hasło tożsamości albo uszkodzony plik") from None
    elif scheme == SCHEME_PLAIN:
        p2s = body
    else:
        raise IdentityError(f"nieznany schemat {scheme}")
    if len(p2s) != 32:
        raise IdentityError("uszkodzony identity.bin")
    return p2s, False


def save_identity(p2s: bytes, path: str) -> int:
    """Zapisz atomowo <path>/identity.bin. Zwraca użyty schemat."""
    scheme = _pick_scheme()
    blob = encode(p2s, scheme)
    os.makedirs(path, exist_ok=True)
    final = os.path.join(path, FILENAME)
    tmp = final + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    try:
        os.write(fd, blob)
    finally:
        os.close(fd)
    os.replace(tmp, final)
    if scheme == SCHEME_PLAIN:
        print(
            "  [identity] UWAGA: p2s zapisany jawnie (tylko uprawnienia 0600). "
            "Ustaw KARMAZYN_IDENTITY_PASSPHRASE, aby go zaszyfrować.",
            file=sys.stderr,
        )
    return scheme


def load_identity(path: str, *, migrate: bool = True) -> Optional[bytes]:
    """p2s z <path>/identity.bin albo None (brak pliku albo nie da się odczytać).

    Plik v2 zostaje przepisany na v3, gdy migrate=True.
    """
    final = os.path.join(path, FILENAME)
    if not os.path.exists(final):
        return None
    try:
        with open(final, "rb") as f:
            p2s, legacy = decode(f.read())
    except IdentityError as e:
        print(f"  [identity] {e}", file=sys.stderr)
        return None
    if legacy and migrate:
        try:
            save_identity(p2s, path)
        except Exception as e:
            print(f"  [identity] migracja v2→v3 nieudana: {e}", file=sys.stderr)
    return p2s


def soul_check(p2s: bytes) -> str:
    """Krótki znacznik w zapisie sesji: która tożsamość go zaszyfrowała.

    Nie zdradza p2s (jednokierunkowy, z separatorem domeny).
    """
    return hashlib.sha256(b"karmazyn-soul-check\x00" + p2s).hexdigest()[:16]
