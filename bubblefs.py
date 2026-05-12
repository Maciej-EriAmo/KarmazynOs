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

import os
import json
import base64
import hashlib
import hmac as _hmac
import numpy as np
from typing import Optional, Dict, Any

BUBBLEFS_VERSION = "1.0.0"
BBL_EXT  = ".bbl"
HGM_EXT  = ".hgm"


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
    for bid, bubble in ko.bubbles._b.items():
        revoked = bid in ko.bubbles._rev

        # odszyfruj oryginalną zawartość
        raw_content = bubble.decrypt_content()

        # re-encrypt kluczem eksportowym (lub zostaw plaintext)
        if shared_secret is not None and not revoked:
            exp_key = _export_key(shared_secret, bid)
            exported_content = _xor_crypt(raw_content, exp_key)
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
        # decay
        if bubble.decay_start_epoch is not None:
            bbl["decay_start_epoch"] = bubble.decay_start_epoch
            bbl["decay_rate"]        = bubble.decay_rate

        fpath = os.path.join(bdir, bid + BBL_EXT)
        fpath_tmp = fpath + ".plasma"
        with open(fpath_tmp, 'w', encoding='utf-8') as f:
            json.dump(bbl, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(fpath_tmp, fpath)
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
        fpath_tmp = fpath + ".plasma"
        with open(fpath_tmp, 'w', encoding='utf-8') as f:
            json.dump(hgm, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(fpath_tmp, fpath)
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
    manifest_tmp = manifest_path + ".plasma"
    with open(manifest_tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(manifest_tmp, manifest_path)

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
            with open(fpath, 'r', encoding='utf-8') as f:
                bbl = json.load(f)

            bid     = bbl["id"]
            label   = bbl["label"]
            revoked = bbl.get("revoked", False)

            # re-decrypt zawartość
            raw_content_enc = _ub64(bbl["content_b64"])
            if bbl.get("content_encrypted") and shared_secret is not None:
                exp_key = _export_key(shared_secret, bid)
                raw_content = _xor_crypt(raw_content_enc, exp_key)
            else:
                raw_content = raw_content_enc

            # wygeneruj nowy klucz dla tej instancji
            new_key = ko.bubbles._make_key(bid) if not revoked else b""

            S_struct = np.array(bbl["S_struct"], dtype=np.float32)
            S_sem    = np.array(bbl["S_sem"],    dtype=np.float32)
            fp       = _ub64(bbl["fingerprint_b64"])

            # re-encrypt nowym kluczem instancji
            new_encrypted = _xor_crypt(raw_content, new_key) if new_key else raw_content

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

            ko.bubbles._b[bid]     = b
            ko.bubbles._idx[label] = bid
            if revoked:
                ko.bubbles._rev.add(bid)

            imported_bubbles.append(bid)

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
                ko.holograms[hid] = h
            else:
                # fallback
                ko.holograms[hid] = hgm

            imported_holograms.append(hid)

    # ── Wektory Φ ─────────────────────────────────────────────────────────────
    sem_path = os.path.join(pdir, "sem_vectors.npz")
    if os.path.exists(sem_path):
        sem_data = np.load(sem_path, allow_pickle=True)
        for k in sem_data.files:
            ko.phi._sem[k] = sem_data[k]

    str_path  = os.path.join(pdir, "structural.npz")
    temp_path = os.path.join(pdir, "temperatures.npz")
    if os.path.exists(str_path) and os.path.exists(temp_path):
        str_data  = np.load(str_path,  allow_pickle=True)
        temp_data = np.load(temp_path, allow_pickle=True)
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

    if shared_secret is not None and not revoked:
        exp_key           = _export_key(shared_secret, b.id)
        exported_content  = _xor_crypt(raw_content, exp_key)
        content_encrypted = True
    else:
        exported_content  = raw_content
        content_encrypted = False

    bbl = {
        "id":                 b.id,
        "label":              b.label,
        "inode":              b.inode,
        "epoch_born":         b.epoch_born,
        "recall_count":       b.recall_count,
        "consolidated_from":  b.consolidated_from,
        "metadata":           b.metadata,
        "revoked":            revoked,
        "content_encrypted":  content_encrypted,
        "content_b64":        _b64(exported_content),
        "fingerprint_b64":    _b64(b.fingerprint),
        "S_struct":           b.S_struct.tolist(),
        "S_sem":              b.S_sem.tolist(),
    }
    if b.decay_start_epoch is not None:
        bbl["decay_start_epoch"] = b.decay_start_epoch
        bbl["decay_rate"]        = b.decay_rate

    fpath = os.path.join(path, b.id + BBL_EXT)
    fpath_tmp = fpath + ".plasma"
    with open(fpath_tmp, 'w', encoding='utf-8') as f:
        json.dump(bbl, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(fpath_tmp, fpath)

    print(f"[BubbleFS] Eksport bąbla '{label}' → {fpath}")
    return fpath
