"""
soul_store.py — Format .soul dla KarmazynOS v1.0.0
===================================================
JSONL-based persistence. Każda linia = jeden rekord JSON z polem "type".
Przerwanie zapisu niszczy tylko ostatni rekord — reszta nienaruszona.

Pliki:
    <path>/session.soul   — metadane, bąble, hologramy (JSONL)
    <path>/vectors.npz    — wektory numpy (binarne, bez konwersji)

Typy rekordów w session.soul:
    {"type":"meta",     ...}   — jeden na początku pliku
    {"type":"bubble",   ...}   — jeden per bąbel
    {"type":"hologram", ...}   — jeden per hologram
    {"type":"phi_rc",   ...}   — recall counts atomów Φ
"""

import os
import json
import base64
import hashlib
import numpy as np
from typing import Optional

SOUL_VERSION = "1.0.0"


# ─── helpers ──────────────────────────────────────────────────────────────────

def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()

def _ub64(s: str) -> bytes:
    return base64.b64decode(s)

def _write_record(f, record: dict):
    f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

def _read_records(path: str) -> list:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # uszkodzona linia (np. przerwany zapis) — pomijamy
                print(f"  [.soul] Pominięto uszkodzony rekord (linia {lineno})")
    return records


# ─── SAVE ─────────────────────────────────────────────────────────────────────

def save_soul(karmazyn_os, path: str = "./karmazyn_data") -> bool:
    """
    Zapisuje stan KarmazynOS do formatu .soul.

    Tworzy:
        <path>/session.soul  — JSONL z metadanymi, bąblami, hologramami
        <path>/vectors.npz   — wektory numpy (sem + structural + temperatures)
    """
    os.makedirs(path, exist_ok=True)
    soul_path = os.path.join(path, "session.soul")
    npz_path  = os.path.join(path, "vectors.npz")
    ko = karmazyn_os

    try:
        with open(soul_path, "w", encoding="utf-8") as f:

            # ── meta (pierwszy rekord) ────────────────────────────────────────
            _write_record(f, {
                "type":        "meta",
                "soul_version": SOUL_VERSION,
                "karmazyn_version": getattr(ko, 'VERSION', '?'),
                "epoch":       ko.phi.epoch,
                "temperature": ko.phi.temperature(),
                "t_vacuum":    ko.phi.t_vacuum(),
                "pid":         ko._pid,
                "p2s":         ko.phi._p2s.hex(),   # ← klucz sesji
                "dim":         ko.phi.dim,
                "bubble_idx":  dict(ko.bubbles._idx),
            })

            # ── bąble ─────────────────────────────────────────────────────────
            for bid, b in ko.bubbles._b.items():
                revoked = bid in ko.bubbles._rev
                raw     = b.decrypt_content()

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
                    "content_b64":        _b64(raw),
                    "fingerprint_b64":    _b64(b.fingerprint),
                    "S_struct":           b.S_struct.tolist(),
                    "S_sem":              b.S_sem.tolist(),
                }
                if b.decay_start_epoch is not None:
                    rec["decay_start_epoch"] = b.decay_start_epoch
                    rec["decay_rate"]        = b.decay_rate

                _write_record(f, rec)

            # ── hologramy ─────────────────────────────────────────────────────
            for hid, h in ko.holograms.items():
                _write_record(f, {
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

            # ── recall counts Φ ───────────────────────────────────────────────
            _write_record(f, {
                "type": "phi_rc",
                "data": ko.phi._rc,
            })

        # ── wektory numpy (osobny plik binarny) ───────────────────────────────
        npz_data = {}

        # wektory semantyczne
        for label, vec in ko.phi._sem.items():
            safe = "sem__" + hashlib.md5(label.encode()).hexdigest()[:16]
            npz_data[safe]            = vec
            npz_data[safe + "__lbl"]  = np.array([label])   # mapowanie

        # wektory strukturalne + temperatury z atomów
        for a in ko.phi._mx.atoms:
            lbl  = a["label"]
            safe = "str__" + hashlib.md5(lbl.encode()).hexdigest()[:16]
            npz_data[safe]           = a["S"]
            npz_data[safe + "__lbl"] = np.array([lbl])
            npz_data[safe + "__T"]   = np.array([a["T"]])

        np.savez(npz_path, **npz_data)

        n_bub  = len(ko.bubbles._b)
        n_holo = len(ko.holograms)
        print(f"  [.soul] Zapisano → {soul_path}")
        print(f"  bąble={n_bub}  hologramy={n_holo}  atomy={len(ko.phi._mx.atoms)}")
        return True

    except Exception as e:
        print(f"  [.soul] BŁĄD zapisu: {e}")
        return False


# ─── LOAD ─────────────────────────────────────────────────────────────────────

def load_soul(karmazyn_os, path: str = "./karmazyn_data") -> bool:
    """
    Wczytuje stan KarmazynOS z formatu .soul.
    Odporny na uszkodzone rekordy — pomija je i wczytuje resztę.
    """
    soul_path = os.path.join(path, "session.soul")
    npz_path  = os.path.join(path, "vectors.npz")

    if not os.path.exists(soul_path):
        print(f"  [.soul] Nie znaleziono: {soul_path}")
        return False

    ko      = karmazyn_os
    records = _read_records(soul_path)

    if not records:
        print("  [.soul] Pusty plik — brak rekordów")
        return False

    # ── wczytaj wektory numpy ─────────────────────────────────────────────────
    sem_map = {}   # label → vector
    str_map = {}   # label → (S, T)

    if os.path.exists(npz_path):
        npz = np.load(npz_path, allow_pickle=True)
        keys = list(npz.files)

        sem_keys = [k for k in keys if k.startswith("sem__") and not k.endswith("__lbl")]
        for k in sem_keys:
            lbl_key = k + "__lbl"
            if lbl_key in keys:
                label = str(npz[lbl_key][0])
                sem_map[label] = npz[k]

        str_keys = [k for k in keys if k.startswith("str__")
                    and not k.endswith("__lbl") and not k.endswith("__T")]
        for k in str_keys:
            lbl_key = k + "__lbl"
            t_key   = k + "__T"
            if lbl_key in keys:
                label = str(npz[lbl_key][0])
                T     = float(npz[t_key][0]) if t_key in keys else 1.0
                str_map[label] = (npz[k], T)

    # ── wyczyść stan przed wczytaniem ─────────────────────────────────────────
    ko.bubbles._b.clear()
    ko.bubbles._idx.clear()
    ko.bubbles._rev.clear()
    ko.holograms.clear()
    ko.phi._sem.clear()
    ko.phi._rc.clear()
    ko.phi._mx.atoms.clear()

    n_bubbles = 0
    n_holograms = 0
    meta_epoch = 0

    # ── importuj klasy dynamicznie ────────────────────────────────────────────
    try:
        from karmazyn import Bubble, Hologram
    except ImportError:
        Bubble   = None
        Hologram = None

    # ── przetwarzaj rekordy ───────────────────────────────────────────────────
    for rec in records:
        rtype = rec.get("type")

        if rtype == "meta":
            meta_epoch = rec.get("epoch", 0)
            ko._pid    = rec.get("pid", 100)
            p2s_hex    = rec.get("p2s")
            if p2s_hex:
                ko.phi._p2s     = bytes.fromhex(p2s_hex)
                ko.bubbles._phi2 = ko.phi.phi2_bytes()  # ← sync BubbleStore
            # odtwórz czas w macierzy Φ
            ko.phi._mx.time = meta_epoch

        elif rtype == "bubble" and Bubble is not None:
            try:
                bid   = rec["id"]
                label = rec["label"]

                # odtwórz klucz z p2s (już odtworzony z meta)
                new_key = ko.bubbles._make_key(bid) if not rec.get("revoked") else b""

                # re-encrypt zawartością plaintextową
                raw_content = _ub64(rec["content_b64"])
                from karmazyn import _xor_crypt
                new_encrypted = _xor_crypt(raw_content, new_key) if new_key else raw_content

                b = Bubble(
                    id=bid,
                    label=label,
                    S_struct=np.array(rec["S_struct"], dtype=np.float32),
                    S_sem=np.array(rec["S_sem"],    dtype=np.float32),
                    fingerprint=_ub64(rec["fingerprint_b64"]),
                    bubble_key=new_key,
                    encrypted_content=new_encrypted,
                    inode=rec.get("inode", f"karmazyn://bubbles/{label}"),
                    epoch_born=rec.get("epoch_born", 0),
                    recall_count=rec.get("recall_count", 0),
                    consolidated_from=rec.get("consolidated_from", ""),
                    metadata=rec.get("metadata", {}),
                )
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

    # ── odtwórz wektory semantyczne i atomy Φ ─────────────────────────────────
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


# ─── INFO ─────────────────────────────────────────────────────────────────────

def inspect_soul(path: str) -> dict:
    """Podgląd .soul bez ładowania do KarmazynOS."""
    soul_path = os.path.join(path, "session.soul")
    if not os.path.exists(soul_path):
        raise FileNotFoundError(f"Brak pliku: {soul_path}")

    records  = _read_records(soul_path)
    counts   = {}
    meta     = {}

    for r in records:
        t = r.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
        if t == "meta":
            meta = r

    print(f"[.soul] {soul_path}")
    print(f"  wersja:    {meta.get('soul_version')} / karmazyn {meta.get('karmazyn_version')}")
    print(f"  epoka:     {meta.get('epoch')}  dim={meta.get('dim')}")
    print(f"  rekordy:   {counts}")
    print(f"  p2s:       {'✓' if meta.get('p2s') else '✗'}")
    return {"meta": meta, "counts": counts, "total": len(records)}
