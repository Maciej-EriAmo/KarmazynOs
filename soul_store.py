"""
soul_store.py — Format .soul dla KarmazynOS v2.0.0
===================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

v2.0: Całkowite szyfrowanie plików (AES-256-GCM).

Pliki na dysku:
    <path>/session.soul   — zaszyfrowany binarny blob
    <path>/vectors.npz    — zaszyfrowany binarny blob
    <path>/identity.bin   — phi._p2s zaciemniony przez machine fingerprint

Format binarny:
    [4B]  magic  = b"SOUL" | b"SVEC" | b"PHID"
    [1B]  version = 0x02
    [16B] salt   (losowe, nowe przy każdym zapisie)
    [12B] nonce  (losowe, nowe przy każdym zapisie)
    [N B] ciphertext + GCM tag (16B na końcu)
    AAD   = magic (uwierzytelnia typ pliku)

Klucz szyfrowania soul/svec:
    soul_key = HMAC-SHA256(phi._p2s, purpose + b":" + salt.hex())

Wewnętrznie: niezmieniony format JSONL rekordów.
Na dysku: szum nie do odróżnienia od danych losowych.

Wsteczna zgodność:
    Jeśli plik zaczyna się od "{" (stary JSONL) → read_soul_legacy().
    Stare pliki można zmigrować przez save_soul().

Wymaga:
    pip install cryptography
"""

import os
import io
import json
import base64
import hashlib
import hmac as _hmac
import numpy as np
from typing import Optional

SOUL_VERSION = "2.0.0"

# ─── Szyfrowanie ──────────────────────────────────────────────────────────────

SOUL_MAGIC     = b"SOUL"
SVEC_MAGIC     = b"SVEC"
IDENTITY_MAGIC = b"PHID"
_VERSION_BYTE  = b"\x02"
_HEADER_LEN    = 4 + 1 + 16 + 12  # magic + version + salt + nonce

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    _CRYPTO_OK = True
except ImportError:
    _AESGCM    = None
    _CRYPTO_OK = False
    import warnings
    warnings.warn(
        "Biblioteka 'cryptography' niedostępna — soul_store bez szyfrowania. "
        "Zainstaluj: pip install cryptography",
        RuntimeWarning,
        stacklevel=1,
    )


def _soul_key(p2s: bytes, salt: bytes, purpose: bytes) -> bytes:
    """Derywacja klucza AES-256 dla konkretnego pliku.

    HMAC-SHA256(p2s, purpose + b":" + salt.hex())
    Nowy salt przy każdym zapisie → nowy klucz → forward secrecy.
    """
    msg = purpose + b":" + salt.hex().encode()
    return _hmac.new(p2s, msg, "sha256").digest()


def _encrypt_blob(data: bytes, p2s: bytes, magic: bytes) -> bytes:
    """Zaszyfruj dane i zwróć binarny blob.

    Układ: magic(4) + version(1) + salt(16) + nonce(12) + ciphertext+tag
    AAD = magic — uwierzytelnia typ pliku, uniemożliwia podmianę soul↔svec.
    """
    if not _CRYPTO_OK:
        # Fallback bez szyfrowania — plaintext z ostrzeżeniem
        import warnings
        warnings.warn(
            "soul_store: cryptography niedostępna, plik NIE jest zaszyfrowany.",
            RuntimeWarning, stacklevel=2,
        )
        return magic + _VERSION_BYTE + (b"\x00" * 16) + (b"\x00" * 12) + data

    salt  = os.urandom(16)
    nonce = os.urandom(12)
    key   = _soul_key(p2s, salt, magic)
    ct    = _AESGCM(key).encrypt(nonce, data, magic)
    return magic + _VERSION_BYTE + salt + nonce + ct


def _decrypt_blob(data: bytes, p2s: bytes, magic: bytes) -> bytes:
    """Odszyfruj binarny blob. Rzuca ValueError przy złym kluczu/pliku.

    Obsługuje też fallback bez szyfrowania (salt+nonce = zero bytes).
    """
    if len(data) < _HEADER_LEN + 16:
        raise ValueError(f"Plik za krótki: {len(data)}B")

    if data[:4] != magic:
        raise ValueError(
            f"Niepoprawny magic: {data[:4]!r}, oczekiwano {magic!r}. "
            "Plik może być z innego systemu lub uszkodzony."
        )
    if data[4:5] != _VERSION_BYTE:
        # Sprawdź czy to stary format (wsteczna zgodność)
        raise ValueError(
            f"Nieznana wersja: {data[4]}. Użyj load_soul() który wykrywa format."
        )

    salt  = data[5:21]
    nonce = data[21:33]
    ct    = data[33:]

    # Fallback bez szyfrowania: salt i nonce są zerami
    if not _CRYPTO_OK or (salt == b"\x00" * 16 and nonce == b"\x00" * 12):
        return ct

    key = _soul_key(p2s, salt, magic)
    try:
        return _AESGCM(key).decrypt(nonce, ct, magic)
    except Exception:
        raise ValueError(
            "Odszyfrowanie nieudane — zły klucz (phi._p2s) lub uszkodzony plik. "
            "Warp Oblivion: bez poprawnego phi._p2s odczyt niemożliwy."
        )


# ─── identity.bin — bootstrap phi._p2s ───────────────────────────────────────

def _machine_fingerprint() -> bytes:
    """Prosty, deterministyczny odcisk maszyny (nie sekret, ale unikalny).

    Używany do zaciemnienia identity.bin — nie zastępuje właściwego szyfrowania,
    ale uniemożliwia odczyt p2s na innej maszynie bez dodatkowych danych.
    """
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
    # Stabilny identyfikator OS jeśli dostępny
    for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(candidate) as f:
                parts.append(f.read().strip())
            break
        except Exception:
            pass
    raw = "|".join(parts).encode() or b"karmazyn-default"
    return hashlib.sha256(raw).digest()


def save_identity(p2s: bytes, path: str) -> None:
    """Zapisz phi._p2s do identity.bin.

    Zaciemniony przez machine fingerprint XOR — nie jest to szyfrowanie,
    ale sprawia że przeniesiony plik na inną maszynę zwróci złe p2s.
    Format: PHID(4) + version(1) + fp_hash(8) + xored_p2s(32)
    """
    fp     = _machine_fingerprint()
    fp_tag = fp[:8]  # 8-bajtowy skrót do weryfikacji maszyny
    xored  = bytes(a ^ b for a, b in zip(p2s, fp))
    identity_path = os.path.join(path, "identity.bin")
    with open(identity_path, "wb") as f:
        f.write(IDENTITY_MAGIC + _VERSION_BYTE + fp_tag + xored)


def load_identity(path: str) -> Optional[bytes]:
    """Wczytaj phi._p2s z identity.bin.

    Zwraca None jeśli plik nie istnieje lub maszyna się nie zgadza.
    """
    identity_path = os.path.join(path, "identity.bin")
    if not os.path.exists(identity_path):
        return None
    try:
        with open(identity_path, "rb") as f:
            data = f.read()
        if len(data) != 4 + 1 + 8 + 32:
            return None
        if data[:4] != IDENTITY_MAGIC or data[4:5] != _VERSION_BYTE:
            return None
        fp       = _machine_fingerprint()
        fp_tag   = fp[:8]
        stored_tag = data[5:13]
        if stored_tag != fp_tag:
            print("  [.soul] identity.bin: inna maszyna — nowe phi._p2s zostanie wygenerowane")
            return None
        xored = data[13:]
        return bytes(a ^ b for a, b in zip(xored, fp))
    except Exception:
        return None


# ─── helpers ──────────────────────────────────────────────────────────────────

def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()

def _ub64(s: str) -> bytes:
    return base64.b64decode(s)

def _write_record(buf: io.BytesIO, record: dict):
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    buf.write(line.encode("utf-8"))

def _read_records_from_bytes(data: bytes) -> list:
    """Parsuj JSONL z bajty (po odszyfrowaniu)."""
    records = []
    for lineno, line in enumerate(data.decode("utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"  [.soul] Pominięto uszkodzony rekord (linia {lineno})")
    return records

def _read_records_legacy(path: str) -> list:
    """Wsteczna zgodność — czytaj stary plaintext JSONL."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"  [.soul] Pominięto uszkodzony rekord (linia {lineno})")
    return records


# ─── SAVE ─────────────────────────────────────────────────────────────────────

def save_soul(karmazyn_os, path: str = "./karmazyn_data") -> bool:
    """Zapisuje stan KarmazynOS do zaszyfrowanego formatu .soul v2.

    Pliki na dysku:
        session.soul  — zaszyfrowany binarny blob (JSONL w środku)
        vectors.npz   — zaszyfrowany binarny blob (npz w środku)
        identity.bin  — phi._p2s zaciemniony przez machine fingerprint

    Strategia zapisu:
        1. Buduj JSONL w pamięci (BytesIO)
        2. Zaszyfruj cały bufor
        3. Atomowy zapis przez .plasma (rename)
    """
    os.makedirs(path, exist_ok=True)
    soul_path = os.path.join(path, "session.soul")
    npz_path  = os.path.join(path, "vectors.npz")
    ko = karmazyn_os

    p2s: Optional[bytes] = getattr(getattr(ko, "phi", None), "_p2s", None)
    if p2s is None:
        print("  [.soul] BŁĄD: phi._p2s niedostępne — nie można zaszyfrować")
        return False

    try:
        # ── 1. Buduj JSONL w pamięci ──────────────────────────────────────────
        buf = io.BytesIO()

        # meta (pierwszy rekord)
        _write_record(buf, {
            "type":             "meta",
            "soul_version":     SOUL_VERSION,
            "karmazyn_version": getattr(ko, "VERSION", "?"),
            "epoch":            ko.phi.epoch,
            "temperature":      ko.phi.temperature(),
            "t_vacuum()":         ko.phi.t_vacuum,
            "pid":              ko._pid,
            "dim":              ko.phi.dim,
            "bubble_idx":       dict(ko.bubbles._idx),
            # p2s NIE jest w meta — przechowywane w identity.bin + bąblu tożsamości
        })

        # bąble
        for bid, b in ko.bubbles._b.items():
            revoked = bid in ko.bubbles._rev
            raw     = b.decrypt_content()   # bajty plaintextu

            rec = {
                "type":               "bubble",
                "id":                 b.id,
                "label":              b.label,
                "inode":              b.inode,
                "epoch_born":         b.epoch_born,
                "recall_count":       b.recall_count,
                "consolidated_from":  b.consolidated_from,
                "metadata":           b.metadata,
                "revoked":            revoked,
                "immortal":           getattr(b, "immortal", False),
                # content_b64 = plaintext base64 — bezpieczne BO cały plik jest zaszyfrowany
                "content_b64":        _b64(raw),
                "fingerprint_b64":    _b64(b.fingerprint),
                "S_struct":           b.S_struct.tolist(),
                "S_sem":              b.S_sem.tolist(),
            }
            if b.decay_start_epoch is not None:
                rec["decay_start_epoch"] = b.decay_start_epoch
                rec["decay_rate"]        = b.decay_rate
            _write_record(buf, rec)

        # hologramy
        for hid, h in ko.holograms.items():
            _write_record(buf, {
                "type":          "hologram",
                "id":            h.id,
                "topic":         h.topic,
                "proto":         h.proto.tolist(),
                "generators":    [g.tolist() for g in h.generators],
                "weights":       h.weights,
                "bubble_labels": h.bubble_labels,
                "epoch_created": h.epoch_created,
                "decay_rate":    h.decay_rate,
                "metadata":      h.metadata,
            })

        # recall counts Φ
        _write_record(buf, {
            "type": "phi_rc",
            "data": ko.phi._rc,
        })

        # ── 2. Zaszyfruj JSONL i zapisz atomowo ──────────────────────────────
        jsonl_bytes  = buf.getvalue()
        encrypted    = _encrypt_blob(jsonl_bytes, p2s, SOUL_MAGIC)

        soul_tmp = soul_path + ".plasma"
        with open(soul_tmp, "wb") as f:
            f.write(encrypted)
            f.flush()
            os.fsync(f.fileno())
        os.replace(soul_tmp, soul_path)

        # ── 3. Wektory numpy — zaszyfrowany npz ──────────────────────────────
        npz_data = {}

        # wektory semantyczne
        for label, vec in ko.phi._sem.items():
            safe = "sem__" + hashlib.md5(label.encode()).hexdigest()[:16]
            npz_data[safe]           = vec
            npz_data[safe + "__lbl"] = np.array([label])

        # wektory strukturalne + temperatury
        for a in ko.phi._mx.atoms:
            lbl  = a["label"]
            safe = "str__" + hashlib.md5(lbl.encode()).hexdigest()[:16]
            npz_data[safe]            = a["S"]
            npz_data[safe + "__lbl"]  = np.array([lbl])
            npz_data[safe + "__T"]    = np.array([a["T"]])

        # serializuj do pamięci, zaszyfruj, zapisz
        npz_buf = io.BytesIO()
        np.savez(npz_buf, **npz_data)
        npz_encrypted = _encrypt_blob(npz_buf.getvalue(), p2s, SVEC_MAGIC)

        npz_tmp = npz_path + ".plasma"
        with open(npz_tmp, "wb") as f:
            f.write(npz_encrypted)
            f.flush()
            os.fsync(f.fileno())
        os.replace(npz_tmp, npz_path)

        # ── 4. identity.bin — backup phi._p2s ────────────────────────────────
        save_identity(p2s, path)

        n_bub  = len(ko.bubbles._b)
        n_holo = len(ko.holograms)
        print(f"  [.soul] Zapisano → {soul_path} (zaszyfrowane)")
        print(f"  bąble={n_bub}  hologramy={n_holo}  atomy={len(ko.phi._mx.atoms)}")
        return True

    except Exception as e:
        import traceback
        print(f"  [.soul] BŁĄD zapisu: {e}")
        traceback.print_exc()
        return False


# ─── LOAD ─────────────────────────────────────────────────────────────────────

def load_soul(karmazyn_os, path: str = "./karmazyn_data") -> bool:
    """Wczytuje stan KarmazynOS z .soul v2 (zaszyfrowanego).

    Automatycznie wykrywa format:
        - Plik binarny zaczynający się od b"SOUL" → v2 (zaszyfrowany)
        - Plik tekstowy zaczynający się od b"{"   → v1 (stary JSONL, wsteczna zgodność)

    Odporny na uszkodzone rekordy — pomija je i wczytuje resztę.
    """
    soul_path = os.path.join(path, "session.soul")
    npz_path  = os.path.join(path, "vectors.npz")

    if not os.path.exists(soul_path):
        print(f"  [.soul] Nie znaleziono: {soul_path}")
        return False

    ko = karmazyn_os

    # ── Odczytaj i odczytaj phi._p2s (potrzebne do odszyfrowania) ─────────────
    # Kolejność bootstrap:
    # 1. Użyj p2s który już jest w ko.phi (jeśli sesja była zainicjowana)
    # 2. Spróbuj wczytać z identity.bin
    # 3. Inicjuj nowe (nowa instalacja)
    p2s = getattr(getattr(ko, "phi", None), "_p2s", None)
    if p2s is None:
        p2s = load_identity(path)
    if p2s is None:
        print("  [.soul] Brak phi._p2s — nowa tożsamość zostanie wygenerowana po wczytaniu")

    # ── Wykryj format pliku ───────────────────────────────────────────────────
    with open(soul_path, "rb") as f:
        magic = f.read(4)

    if magic == SOUL_MAGIC:
        # Nowy format v2 — zaszyfrowany
        if p2s is None:
            print("  [.soul] BŁĄD: plik v2 wymaga phi._p2s. Warp Oblivion.")
            return False
        try:
            with open(soul_path, "rb") as f:
                encrypted = f.read()
            jsonl_bytes = _decrypt_blob(encrypted, p2s, SOUL_MAGIC)
            records     = _read_records_from_bytes(jsonl_bytes)
        except ValueError as e:
            print(f"  [.soul] Odszyfrowanie nieudane: {e}")
            return False
    elif magic[:1] == b"{":
        # Stary format v1 — plaintext JSONL (wsteczna zgodność)
        print("  [.soul] Wykryto stary format v1 (plaintext) — wczytywanie...")
        records = _read_records_legacy(soul_path)
    else:
        print(f"  [.soul] Nieznany format pliku: {magic!r}")
        return False

    if not records:
        print("  [.soul] Pusty plik — brak rekordów")
        return False

    # ── Wektory numpy ─────────────────────────────────────────────────────────
    sem_map = {}
    str_map = {}

    if os.path.exists(npz_path):
        try:
            with open(npz_path, "rb") as f:
                npz_raw = f.read()

            # Wykryj format npz
            if npz_raw[:4] == SVEC_MAGIC and p2s is not None:
                # Nowy format — zaszyfrowany
                npz_bytes = _decrypt_blob(npz_raw, p2s, SVEC_MAGIC)
                npz = np.load(io.BytesIO(npz_bytes), allow_pickle=True)
            else:
                # Stary format — plaintext .npz
                npz = np.load(npz_path, allow_pickle=True)

            keys = list(npz.files)
            for k in keys:
                if k.startswith("sem__") and not k.endswith("__lbl"):
                    lbl_key = k + "__lbl"
                    if lbl_key in keys:
                        sem_map[str(npz[lbl_key][0])] = npz[k]

            for k in keys:
                if k.startswith("str__") and not k.endswith("__lbl") and not k.endswith("__T"):
                    lbl_key = k + "__lbl"
                    t_key   = k + "__T"
                    if lbl_key in keys:
                        T = float(npz[t_key][0]) if t_key in keys else 1.0
                        str_map[str(npz[lbl_key][0])] = (npz[k], T)

        except Exception as e:
            print(f"  [.soul] Ostrzeżenie: nie wczytano wektorów numpy: {e}")

    # ── Wyczyść stan przed wczytaniem ─────────────────────────────────────────
    ko.bubbles._b.clear()
    ko.bubbles._idx.clear()
    ko.bubbles._rev.clear()
    ko.holograms.clear()
    ko.phi._sem.clear()
    ko.phi._rc.clear()
    ko.phi._mx.atoms.clear()

    n_bubbles   = 0
    n_holograms = 0
    meta_epoch  = 0

    try:
        from karmazyn import Bubble, Hologram
    except ImportError:
        Bubble   = None
        Hologram = None

    # ── Przetwarzaj rekordy ───────────────────────────────────────────────────
    for rec in records:
        rtype = rec.get("type")

        if rtype == "meta":
            meta_epoch = rec.get("epoch", 0)
            ko._pid    = rec.get("pid", 100)
            # Wsteczna zgodność: stary format mógł mieć p2s w meta
            p2s_hex = rec.get("p2s")
            if p2s_hex:
                ko.phi._p2s     = bytes.fromhex(p2s_hex)
                ko.bubbles._phi2 = ko.phi.phi2_bytes()
            ko.phi._mx.time = meta_epoch

        elif rtype == "bubble" and Bubble is not None:
            try:
                bid   = rec["id"]
                label = rec["label"]

                new_key     = ko.bubbles._make_key(bid) if not rec.get("revoked") else b""
                raw_content = _ub64(rec["content_b64"])

                b = Bubble(
                    id=bid,
                    label=label,
                    S_struct=np.array(rec["S_struct"], dtype=np.float32),
                    S_sem=np.array(rec["S_sem"],    dtype=np.float32),
                    fingerprint=_ub64(rec["fingerprint_b64"]),
                    bubble_key=new_key,
                    encrypted_content=b"",
                    inode=rec.get("inode", f"karmazyn://bubbles/{label}"),
                    epoch_born=rec.get("epoch_born", 0),
                    recall_count=rec.get("recall_count", 0),
                    consolidated_from=rec.get("consolidated_from", ""),
                    metadata=rec.get("metadata", {}),
                    immortal=rec.get("immortal", False),
                )
                b.metadata["__raw_content_temp"] = raw_content
                if "decay_start_epoch" in rec:
                    b.decay_start_epoch = rec["decay_start_epoch"]
                    b.decay_rate        = rec.get("decay_rate", 0.0)

                ko.bubbles._b[bid]     = b
                ko.bubbles._idx[label] = bid
                if rec.get("revoked"):
                    ko.bubbles._rev.add(bid)
                n_bubbles += 1

            except Exception as e:
                print(f"  [.soul] Pominięto bąbel '{rec.get('id','?')}': {e}")

        elif rtype == "hologram" and Hologram is not None:
            try:
                hid = rec["id"]
                h   = Hologram(
                    id=hid,
                    topic=rec["topic"],
                    proto=np.array(rec["proto"],      dtype=np.float32),
                    generators=[np.array(g, dtype=np.float32) for g in rec["generators"]],
                    weights=rec["weights"],
                    bubble_labels=rec["bubble_labels"],
                    epoch_created=rec["epoch_created"],
                    decay_rate=rec.get("decay_rate", 0.001),
                    metadata=rec.get("metadata", {}),
                )
                ko.holograms[hid] = h
                n_holograms += 1
            except Exception as e:
                print(f"  [.soul] Pominięto hologram '{rec.get('id','?')}': {e}")

        elif rtype == "phi_rc":
            ko.phi._rc.update(rec.get("data", {}))

    # ── Synchronizacja tożsamości i szyfrowania ───────────────────────────────
    for b in ko.bubbles._b.values():
        if b.metadata.get("type") == "phi_identity":
            p2s_raw = b.metadata.get("__raw_content_temp")
            if p2s_raw and len(p2s_raw) == 32:
                ko.phi._p2s      = p2s_raw
                ko.bubbles._phi2 = ko.phi.phi2_bytes()
                print(f"  [.soul] Odzyskano tożsamość Φ: {ko.get_phi_id()}")
            if b.label not in ko.bubbles._idx:
                ko.bubbles._idx[b.label] = b.id
            break

    if not ko.phi._p2s:
        ko._init_p2s_bubble()

    from karmazyn import _xor_crypt
    for bid, b in ko.bubbles._b.items():
        raw = b.metadata.pop("__raw_content_temp", None)
        if raw is not None:
            if bid not in ko.bubbles._rev:
                b.bubble_key        = ko.bubbles._make_key(bid)
                b.encrypted_content = _xor_crypt(raw, b.bubble_key)
            else:
                b.bubble_key        = b""
                b.encrypted_content = raw

    # Zaktualizuj identity.bin jeśli p2s jest teraz znane
    if ko.phi._p2s:
        try:
            save_identity(ko.phi._p2s, path)
        except Exception:
            pass

    # ── Odtwórz wektory semantyczne i atomy Φ ────────────────────────────────
    ko.phi._sem.update(sem_map)
    for label, (S, T) in str_map.items():
        ko.phi._mx.add_atom_vector(
            label=label, topic="soul_restore",
            vector=S, init_T=T, session=ko.phi._sid
        )

    print(f"  [.soul] Wczytano ← {soul_path}")
    print(f"  bąble={n_bubbles}  hologramy={n_holograms}"
          f"  atomy={len(ko.phi._mx.atoms)}  epoka={meta_epoch}")
    return True


# ─── INFO / DIAGNOSTYKA ───────────────────────────────────────────────────────

def inspect_soul(path: str, p2s: Optional[bytes] = None) -> dict:
    """Podgląd .soul bez ładowania do KarmazynOS.

    Jeśli p2s podany: odszyfruje i wyświetli statystyki rekordów.
    Jeśli p2s nie podany: wyświetli tylko informacje o formacie.
    """
    soul_path = os.path.join(path, "session.soul")
    if not os.path.exists(soul_path):
        raise FileNotFoundError(f"Brak pliku: {soul_path}")

    with open(soul_path, "rb") as f:
        header = f.read(4)

    print(f"[.soul] {soul_path}")

    if header == SOUL_MAGIC:
        print(f"  format:   v2 (zaszyfrowany AES-256-GCM)")
        print(f"  rozmiar:  {os.path.getsize(soul_path)} B")

        if p2s is None:
            # Spróbuj wczytać z identity.bin
            p2s = load_identity(path)

        if p2s is None:
            print(f"  zawartość: [niedostępna bez phi._p2s]")
            return {"format": "v2", "encrypted": True}

        try:
            with open(soul_path, "rb") as f:
                encrypted = f.read()
            jsonl_bytes = _decrypt_blob(encrypted, p2s, SOUL_MAGIC)
            records     = _read_records_from_bytes(jsonl_bytes)
        except ValueError as e:
            print(f"  odszyfrowanie: NIEUDANE — {e}")
            return {"format": "v2", "encrypted": True, "error": str(e)}

    elif header[:1] == b"{":
        print(f"  format:   v1 (plaintext JSONL — niezaszyfrowany)")
        records = _read_records_legacy(soul_path)
    else:
        print(f"  format:   nieznany ({header!r})")
        return {"format": "unknown"}

    counts = {}
    meta   = {}
    for r in records:
        t = r.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
        if t == "meta":
            meta = r

    print(f"  wersja:   {meta.get('soul_version')} / karmazyn {meta.get('karmazyn_version')}")
    print(f"  epoka:    {meta.get('epoch')}  dim={meta.get('dim')}")
    print(f"  rekordy:  {counts}")
    return {"meta": meta, "counts": counts, "total": len(records)}