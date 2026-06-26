"""
karmazyn_store.py — Trwałość dokumentów KarmazynOS v1.0
========================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Zapisuje dokumenty natywnych aplikacji (edytor, przeglądarka, odtwarzacz)
na dysk fizyczny i odczytuje przy starcie. Bez tego wszystko żyje tylko
w pamięci i znika po restarcie.

Spójność formatu: używa KAFD (karmazyn_kafd.vfs_pack/vfs_unpack) — tego
samego formatu on-disk co karmazyn_vfs.BubbleVFS i bubblefs. Dokumenty
z natywnych aplikacji leżą w tym samym formacie co reszta systemu, nie
w równoległym JSON-ie.

Co jest zapisywane:
  atomy rodziny dokumentów — manifest (S="document"), treść
  (S="content:*"), wersje (S="version"). Wiernie: S, E, T, metadata
  ORAZ surowe bajty (audio/obraz) z metadata['data'].

Czego NIE zapisujemy domyślnie:
  atomy płótna (S="paint") — z natury ulotne, mają wygasać. Trwały
  ślad pędzla przeczyłby idei stygnącego canvasu. (Można wymusić
  parametrem kinds.)

Temperatury (T) też się zapisują — dokument który stygł wraca w tym
samym stanie cieplnym, więc historia wersji która blakła nie "odżywa"
sztucznie po restarcie.

API (ukryte pod maską, jak reszta):
    import karmazyn_store as store
    store.save_documents(phi, "/ścieżka/karmazyn.kafd")   # zapis
    store.load_documents(phi, "/ścieżka/karmazyn.kafd")   # odczyt

  Albo przez Workspace (wygodniej):
    ws.persist("/ścieżka/karmazyn.kafd")
    ws.restore("/ścieżka/karmazyn.kafd")
"""

import json
import os
import struct
import tempfile
import time
from typing import Iterable, Optional

try:
    from karmazyn_kafd import vfs_pack, vfs_unpack
    _KAFD_OK = True
except ImportError:
    _KAFD_OK = False

# Rodziny S które uznajemy za "dokument" (trwałe)
DOC_KINDS = ("document", "version")          # + wszystko zaczynające się od "content:"
STORE_META = "karmazyn_store_v1"


# ─── Serializacja pojedynczego atomu ─────────────────────────────────────────
# Ramka: [4B len JSON][JSON: S,E,T,meta-bez-data][surowe bajty data]
# Pozwala trzymać i tekst (E) i bajty (metadata['data']) w jednym blobie atomu.

def _encode_atom(atom) -> bytes:
    meta = {k: v for k, v in atom.metadata.items() if k != "data"}
    head = json.dumps(
        {"S": atom.S, "E": atom.E, "T": float(atom.T), "meta": meta},
        ensure_ascii=False,
    ).encode("utf-8")
    data = atom.metadata.get("data", b"")
    if not isinstance(data, (bytes, bytearray)):
        data = b""
    return struct.pack(">I", len(head)) + head + bytes(data)


def _decode_atom(blob: bytes):
    hlen = struct.unpack(">I", blob[:4])[0]
    head = json.loads(blob[4:4 + hlen].decode("utf-8"))
    data = blob[4 + hlen:]
    return head, data


def _is_doc_atom(atom, kinds: Iterable[str]) -> bool:
    S = atom.S or ""
    if S in kinds:
        return True
    if S.startswith("content:"):
        return True
    return False


# ─── Atomowy zapis ────────────────────────────────────────────────────────────

def _atomic_write(path: str, data: bytes) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".store_", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp and os.path.exists(tmp):
            try: os.unlink(tmp)
            except OSError: pass


# ─── Zapis / odczyt ─────────────────────────────────────────────────────────

def save_documents(phi, path: str,
                   kinds: Iterable[str] = DOC_KINDS) -> int:
    """
    Zapisz atomy dokumentów z phi na dysk (KAFD). Zwraca liczbę atomów.
    """
    if not _KAFD_OK:
        raise RuntimeError("Brak karmazyn_kafd — nie można zapisać na dysk")

    kinds = tuple(kinds)
    atoms_dict = {}
    for atom in phi.matrix.atoms():
        if _is_doc_atom(atom, kinds):
            atoms_dict[atom.id] = _encode_atom(atom)

    meta = {"format": STORE_META, "saved": time.time(),
            "count": len(atoms_dict)}
    blob = vfs_pack(atoms_dict, meta)
    _atomic_write(path, blob)
    return len(atoms_dict)


def load_documents(phi, path: str) -> int:
    """
    Odczytaj atomy dokumentów z dysku do phi. Zwraca liczbę odtworzonych.
    Wiernie odtwarza S, E, T, metadata i surowe bajty. Nie rusza atomów
    spoza pliku (dokłada do istniejącego phi).
    """
    if not _KAFD_OK:
        raise RuntimeError("Brak karmazyn_kafd — nie można odczytać z dysku")
    if not os.path.exists(path):
        return 0

    with open(path, "rb") as f:
        blob = f.read()

    try:
        atoms_dict, _meta = vfs_unpack(blob)
    except Exception:
        return 0

    n = 0
    for aid, atom_bytes in atoms_dict.items():
        try:
            head, data = _decode_atom(atom_bytes)
        except Exception:
            continue
        atom = phi.create_atom(aid, S=head.get("S", ""),
                               E=head.get("E", ""),
                               T=float(head.get("T", 50.0)))
        # odtwórz metadata
        m = head.get("meta", {})
        if isinstance(m, dict):
            atom.metadata.update(m)
        if data:
            atom.metadata["data"] = data
        n += 1
    return n


def store_stats(path: str) -> dict:
    """Metadane zapisu bez ładowania atomów do phi."""
    if not os.path.exists(path):
        return {"exists": False}
    try:
        with open(path, "rb") as f:
            blob = f.read()
        atoms_dict, meta = vfs_unpack(blob)
        return {"exists": True, "atoms": len(atoms_dict),
                "size": len(blob), "meta": meta}
    except Exception as e:
        return {"exists": True, "error": str(e)}


# ─── Komenda powłoki ──────────────────────────────────────────────────────────

_DEFAULT_PATH = os.environ.get(
    "KARMAZYN_STORE",
    os.path.join(os.path.expanduser("~"), ".karmazyn", "documents.kafd"))


def cmd_store(args, phi=None) -> str:
    """
    STORE SAVE [ścieżka]  — zapisz dokumenty na dysk
    STORE LOAD [ścieżka]  — wczytaj dokumenty z dysku
    STORE INFO [ścieżka]  — pokaż co jest w zapisie
    Domyślna ścieżka: $KARMAZYN_STORE lub ~/.karmazyn/documents.kafd
    """
    if phi is None:
        return "Brak runtime (phi)."
    if not args:
        return ("STORE SAVE|LOAD|INFO [ścieżka]\n"
                f"Domyślna ścieżka: {_DEFAULT_PATH}")
    sub = args[0].upper()
    path = args[1] if len(args) > 1 else _DEFAULT_PATH

    try:
        if sub == "SAVE":
            n = save_documents(phi, path)
            return f"Zapisano {n} atomów dokumentów → {path}"
        if sub == "LOAD":
            n = load_documents(phi, path)
            return f"Wczytano {n} atomów dokumentów z {path}"
        if sub == "INFO":
            s = store_stats(path)
            if not s.get("exists"):
                return f"Brak zapisu: {path}"
            if "error" in s:
                return f"Uszkodzony zapis: {s['error']}"
            return (f"Zapis: {path}\n  atomów: {s['atoms']}  rozmiar: {s['size']}B")
    except Exception as e:
        return f"Błąd magazynu: {type(e).__name__}: {e}"
    return "Użycie: STORE SAVE|LOAD|INFO [ścieżka]"


if __name__ == "__main__":
    import sys
    from karmazyn_phi import PhiSpace
    phi = PhiSpace()
    print(cmd_store(sys.argv[1:], phi=phi))