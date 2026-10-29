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
  - shared_secret=None wymaga allow_plaintext=True (tryb debug/lokalny)
  - zaszyfrowana treść ma MAC: HMAC(HMAC(shared_secret, "bbl-mac:" + id),
    id | label | szyfrogram). Import bez zgodnego MAC pomija bąbel
  - bąbel tożsamości (phi._p2s) nigdy nie jest eksportowany ani importowany
"""

import os
import json
import base64
import hashlib
import hmac as _hmac
import numpy as np
from typing import Optional, Dict, Any

BUBBLEFS_VERSION = "1.1.0"   # 1.1: MAC treści, bez bąbla tożsamości
BBL_EXT  = ".bbl"
HGM_EXT  = ".hgm"


# ─── helpers ─────────────────────────────────────────────────────────────────

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()

def _ub64(s: str) -> bytes:
    return base64.b64decode(s)

def _export_key(shared_secret: bytes, bubble_id: str) -> bytes:
    return _hmac.new(shared_secret, b"bbl-export:" + bubble_id.encode(), hashlib.sha256).digest()

def _mac_key(shared_secret: bytes, bubble_id: str) -> bytes:
    return _hmac.new(shared_secret, b"bbl-mac:" + bubble_id.encode(), hashlib.sha256).digest()


def _content_mac(shared_secret: bytes, bubble_id: str, label: str, ct: bytes) -> bytes:
    msg = bubble_id.encode() + b"\x00" + label.encode() + b"\x00" + ct
    return _hmac.new(_mac_key(shared_secret, bubble_id), msg, hashlib.sha256).digest()


IDENTITY_LABEL = "__phi_identity_p2s__"


def _is_identity(label, metadata) -> bool:
    """Bąbel z phi._p2s: nie opuszcza instancji."""
    meta = metadata if isinstance(metadata, dict) else {}
    return label == IDENTITY_LABEL or meta.get("type") == "phi_identity"


def _fingerprint(content: bytes, key: bytes, label: str) -> bytes:
    """Jak karmazyn._compute_fingerprint: HMAC(klucz bąbla, label + treść)."""
    return _hmac.new(key, label.encode() + content, hashlib.sha256).digest()


def _bubble_record(ko, bid, bubble, shared_secret):
    """Rekord .bbl albo None (bąbel tożsamości / uszkodzony)."""
    if _is_identity(bubble.label, bubble.metadata):
        return None
    revoked = bid in ko.bubbles._rev
    try:
        raw_content = bubble.decrypt_content()
    except ValueError as e:   # BubbleIntegrityError: podmieniony szyfrogram
        print(f"[BubbleFS] Pomijam bąbel '{bubble.label}': {e}")
        return None

    if shared_secret is not None and not revoked:
        exported_content = _xor_crypt(raw_content, _export_key(shared_secret, bid))
        content_encrypted = True
    else:
        exported_content = raw_content
        content_encrypted = False

    bbl: Dict[str, Any] = {
        "id":                  bubble.id,
        "label":               bubble.label,
        "inode":               bubble.inode,
        "epoch_born":          bubble.epoch_born,
        "recall_count":        bubble.recall_count,
        "consolidated_from":   bubble.consolidated_from,
        "metadata":            bubble.metadata,
        "revoked":             revoked,
        "content_encrypted":   content_encrypted,
        "content_b64":         _b64(exported_content),
        "fingerprint_b64":     _b64(bubble.fingerprint),
        "S_struct":            bubble.S_struct.tolist(),
        "S_sem":               bubble.S_sem.tolist(),
    }
    if content_encrypted:
        bbl["content_mac_b64"] = _b64(
            _content_mac(shared_secret, bid, bubble.label, exported_content)
        )
    if bubble.decay_start_epoch is not None:
        bbl["decay_start_epoch"] = bubble.decay_start_epoch
        bbl["decay_rate"]        = bubble.decay_rate
    return bbl


def _need_secret(shared_secret, allow_plaintext, what):
    if shared_secret is None and not allow_plaintext:
        raise ValueError(
            f"BubbleFS {what}: bez shared_secret treść bąbli byłaby jawna. "
            f"Podaj shared_secret albo allow_plaintext=True."
        )
    if shared_secret is None:
        print(f"[BubbleFS] UWAGA: {what} bez szyfrowania (allow_plaintext=True)")


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

def _call_or_value(obj):
    """Właściwość albo metoda bez argumentów (t_vacuum bywa jednym i drugim)."""
    return obj() if callable(obj) else obj


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
           include_phi_vectors: bool = True, allow_plaintext: bool = False) -> dict:
    """
    Eksportuje stan KarmazynOS do katalogu BubbleFS.

    Args:
        karmazyn_os:      instancja KarmazynOS
        path:             katalog docelowy (zostanie utworzony)
        shared_secret:    klucz wymiany dla re-szyfrowania bąbli
        include_phi_vectors: czy eksportować wektory Φ (sem + structural)
        allow_plaintext:  True = zgoda na eksport bez shared_secret (jawna treść)

    Returns:
        dict z metadanymi eksportu
    """
    _need_secret(shared_secret, allow_plaintext, "eksport")
    os.makedirs(path, exist_ok=True)
    bdir = os.path.join(path, "bubbles");    os.makedirs(bdir, exist_ok=True)
    hdir = os.path.join(path, "holograms"); os.makedirs(hdir, exist_ok=True)
    pdir = os.path.join(path, "phi");       os.makedirs(pdir, exist_ok=True)

    ko = karmazyn_os
    exported_bubbles = []
    exported_holograms = []

    # ── Bąble ────────────────────────────────────────────────────────────────
    for bid, bubble in ko.bubbles._b.items():
        bbl = _bubble_record(ko, bid, bubble, shared_secret)
        if bbl is None:
            continue

        fpath = os.path.join(bdir, bid + BBL_EXT)
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(bbl, f, indent=2, ensure_ascii=False)
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
        fpath = os.path.join(hdir, hid + HGM_EXT)
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(hgm, f, indent=2, ensure_ascii=False)
        exported_holograms.append(hid)

    # ── Wektory Φ ─────────────────────────────────────────────────────────────
    if include_phi_vectors and ko.phi._sem:
        np.savez(os.path.join(pdir, "sem_vectors.npz"), **ko.phi._sem)

    if include_phi_vectors and ko.phi._mx.atoms:
        s_data = {a['label']: a['S'] for a in ko.phi._mx.atoms}
        t_data = {a['label']: np.array([a['T']]) for a in ko.phi._mx.atoms}
        np.savez(os.path.join(pdir, "structural.npz"), **s_data)
        np.savez(os.path.join(pdir, "temperatures.npz"), **t_data)

    # ── Manifest ──────────────────────────────────────────────────────────────
    integrity = _manifest_hash(bdir, hdir)
    manifest = {
        "bubblefs_version":   BUBBLEFS_VERSION,
        "karmazyn_version":   getattr(ko, 'VERSION', '?'),
        "epoch":              ko.phi.epoch,
        "dim":                ko.phi.dim,
        "t_vacuum()":           _call_or_value(ko.phi.t_vacuum),
        "temperature":        _call_or_value(ko.phi.temperature),
        "n_bubbles":          len(exported_bubbles),
        "n_holograms":        len(exported_holograms),
        "n_phi_atoms":        len(ko.phi._mx.atoms),
        "encrypted":          shared_secret is not None,
        "include_phi_vectors": include_phi_vectors,
        "integrity_sha256":   integrity,
        "bubble_idx":         dict(ko.bubbles._idx),
    }
    with open(os.path.join(path, "manifest.json"), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"[BubbleFS] Eksport → {path}")
    print(f"  bąble={len(exported_bubbles)}  hologramy={len(exported_holograms)}"
          f"  encrypted={shared_secret is not None}")
    return manifest


# ─── IMPORT ──────────────────────────────────────────────────────────────────

def import_(karmazyn_os, path: str, shared_secret: Optional[bytes] = None,
            merge: bool = False, verify_integrity: bool = True,
            allow_plaintext: bool = False, allow_unauthenticated: bool = False) -> dict:
    """
    Importuje stan BubbleFS do instancji KarmazynOS.

    Args:
        karmazyn_os:       instancja KarmazynOS (docelowa)
        path:              katalog źródłowy BubbleFS
        shared_secret:     klucz wymiany (musi zgadzać się z export())
        merge:             True = dołącz do istniejącego stanu
                           False = wyczyść store przed importem
        verify_integrity:  sprawdź hash manifestu
        allow_plaintext:   True = przyjmij bąble zapisane jawnie (bez MAC)
        allow_unauthenticated: True = przyjmij zaszyfrowane bąble bez MAC
                           (eksport BubbleFS 1.0.0)

    Returns:
        dict z metadanymi importu
    """
    if not os.path.isdir(path):
        raise FileNotFoundError(f"BubbleFS: katalog nie istnieje: {path}")

    bdir = os.path.join(path, "bubbles")
    hdir = os.path.join(path, "holograms")
    pdir = os.path.join(path, "phi")

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

    imported_bubbles = []
    imported_holograms = []
    skipped = []
    # Najpierw pamięć. Czyścimy store dopiero gdy pliki się sparsują.
    pending_bubbles = []
    pending_holograms = []

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
            with open(fpath, 'r', encoding='utf-8') as f:
                bbl = json.load(f)

            bid     = bbl["id"]
            label   = bbl["label"]
            revoked = bbl.get("revoked", False)

            if _is_identity(label, bbl.get("metadata")):
                skipped.append(f"{bid}: bąbel tożsamości nie jest importowany")
                continue

            # Bez klucza nie xorujemy szyfrogramu drugim kluczem.
            if bbl.get("content_encrypted") and shared_secret is None:
                skipped.append(f"{bid}: encrypted without shared_secret")
                continue

            # re-decrypt zawartość
            raw_content_enc = _ub64(bbl["content_b64"])
            if bbl.get("content_encrypted"):
                mac_b64 = bbl.get("content_mac_b64")
                if mac_b64 is None:
                    if not allow_unauthenticated:
                        skipped.append(f"{bid}: brak MAC (eksport 1.0.0)")
                        continue
                elif not _hmac.compare_digest(
                    _ub64(mac_b64),
                    _content_mac(shared_secret, bid, label, raw_content_enc),
                ):
                    skipped.append(f"{bid}: MAC niezgodny (zły klucz albo podmiana)")
                    continue
            elif not allow_plaintext and not revoked:
                # unieważniony bąbel nie ma treści do ochrony
                skipped.append(f"{bid}: jawna treść bez allow_plaintext")
                continue
            if bbl.get("content_encrypted"):
                exp_key = _export_key(shared_secret, bid)
                raw_content = _xor_crypt(raw_content_enc, exp_key)
            else:
                raw_content = raw_content_enc

            # wygeneruj nowy klucz dla tej instancji
            new_key = ko.bubbles._make_key(bid) if not revoked else b""

            S_struct = np.array(bbl["S_struct"], dtype=np.float32)
            S_sem    = np.array(bbl["S_sem"],    dtype=np.float32)
            fp       = _ub64(bbl["fingerprint_b64"])

            # re-encrypt nowym kluczem instancji. Odcisk liczony tym kluczem,
            # inaczej decrypt_content uznałby treść za podmienioną.
            new_encrypted = _xor_crypt(raw_content, new_key) if new_key else raw_content
            if new_key:
                fp = _fingerprint(raw_content, new_key, label)

            if BubbleClass is not None:
                import dataclasses
                b = BubbleClass(
                    id=bid,
                    label=label,
                    S_struct=S_struct,
                    S_sem=S_sem,
                    fingerprint=fp,
                    bubble_key=new_key,
                    encrypted_content=new_encrypted,
                    inode=bbl.get("inode", f"karmazyn://bubbles/{label}"),
                    epoch_born=bbl.get("epoch_born", 0),
                    recall_count=bbl.get("recall_count", 0),
                    consolidated_from=bbl.get("consolidated_from", ""),
                    metadata=bbl.get("metadata", {}),
                )
                if "decay_start_epoch" in bbl:
                    b.decay_start_epoch = bbl["decay_start_epoch"]
                    b.decay_rate        = bbl.get("decay_rate", 0.0)
            else:
                # fallback dict-based (gdy brak importu klasy)
                b = type('Bubble', (), bbl)()
                b.S_struct          = S_struct
                b.S_sem             = S_sem
                b.fingerprint       = fp
                b.bubble_key        = new_key
                b.encrypted_content = new_encrypted
                b.is_alive          = lambda: bool(b.bubble_key)
                b.decrypt_content   = lambda: _xor_crypt(b.encrypted_content, b.bubble_key)

            pending_bubbles.append((bid, label, revoked, b))

    # ── Hologramy ─────────────────────────────────────────────────────────────
    if os.path.isdir(hdir):
        try:
            from karmazyn import Hologram
        except ImportError:
            Hologram = None

        for fname in sorted(os.listdir(hdir)):
            if not fname.endswith(HGM_EXT):
                continue
            fpath = os.path.join(hdir, fname)
            with open(fpath, 'r', encoding='utf-8') as f:
                hgm = json.load(f)

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
                pending_holograms.append((hid, h))
            else:
                pending_holograms.append((hid, hgm))

    # ── Wektory Φ (odczyt zanim ruszamy store) ───────────────────────────────
    sem_path = os.path.join(pdir, "sem_vectors.npz")
    sem_loaded = None
    if os.path.exists(sem_path):
        # allow_pickle=False: npz trzyma same tablice numeryczne (bez object arrays).
        sem_loaded = np.load(sem_path, allow_pickle=False)

    str_path  = os.path.join(pdir, "structural.npz")
    temp_path = os.path.join(pdir, "temperatures.npz")
    str_data = temp_data = None
    if os.path.exists(str_path) and os.path.exists(temp_path):
        str_data  = np.load(str_path,  allow_pickle=False)
        temp_data = np.load(temp_path, allow_pickle=False)

    if not merge:
        ko.bubbles._b.clear()
        ko.bubbles._idx.clear()
        ko.bubbles._rev.clear()
        ko.holograms.clear()

    for bid, label, revoked, b in pending_bubbles:
        ko.bubbles._b[bid] = b
        ko.bubbles._idx[label] = bid
        if revoked:
            ko.bubbles._rev.add(bid)
        imported_bubbles.append(bid)

    for hid, h in pending_holograms:
        ko.holograms[hid] = h
        imported_holograms.append(hid)

    if sem_loaded is not None:
        try:
            for k in sem_loaded.files:
                ko.phi._sem[k] = np.array(sem_loaded[k])
        finally:
            sem_loaded.close()

    if str_data is not None and temp_data is not None:
        try:
            existing_labels = {a['label'] for a in ko.phi._mx.atoms}
            for lbl in str_data.files:
                if lbl not in existing_labels:
                    T = float(temp_data[lbl][0]) if lbl in temp_data.files else 1.0
                    ko.phi._mx.add_atom_vector(
                        label=lbl, topic="bubblefs_import",
                        vector=np.array(str_data[lbl]), init_T=T
                    )
        finally:
            str_data.close()
            temp_data.close()

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

    raw_tv = m.get("t_vacuum()", m.get("t_vacuum"))
    try:
        tv_txt = f"{float(raw_tv):.4f}"
    except (TypeError, ValueError):
        tv_txt = "?"
    print(f"[BubbleFS] {path}")
    print(f"  wersja:     {m.get('bubblefs_version')} / karmazyn {m.get('karmazyn_version')}")
    print(f"  epoka:      {m.get('epoch')}  dim={m.get('dim')}")
    print(f"  bąble:      {len(bubble_files)}  hologramy={len(hologram_files)}")
    print(f"  szyfrowane: {m.get('encrypted')}  T_vacuum={tv_txt}")
    return m


def export_single_bubble(karmazyn_os, label: str, path: str,
                         shared_secret: Optional[bytes] = None,
                         allow_plaintext: bool = False) -> Optional[str]:
    """
    Eksportuje pojedynczy Bubble do pliku .bbl.
    Przydatne do przesyłania konkretnych informacji między instancjami.
    """
    ko = karmazyn_os
    b  = ko.bubbles.get_by_label(label)
    if b is None:
        print(f"[BubbleFS] Bąbel '{label}' nie istnieje")
        return None

    _need_secret(shared_secret, allow_plaintext, "eksport bąbla")
    bbl = _bubble_record(ko, b.id, b, shared_secret)
    if bbl is None:
        print(f"[BubbleFS] Bąbel '{label}' nie podlega eksportowi")
        return None
    os.makedirs(path, exist_ok=True)

    fpath = os.path.join(path, b.id + BBL_EXT)
    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(bbl, f, indent=2, ensure_ascii=False)

    print(f"[BubbleFS] Eksport bąbla '{label}' → {fpath}")
    return fpath
