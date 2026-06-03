"""
karmazyn_store.py — Trwałość dokumentów KarmazynOS v1.1
========================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Zapisuje dokumenty natywnych aplikacji na dysk fizyczny i odczytuje
przy starcie. Treść idzie PRZEZ POLE PROCA — content-addressable
storage z deduplikacją na poziomie atomu, pliki pola (.pfld) lądują
na dowolnym systemie plików (NTFS, ext4, F2FS — to zwykłe pliki).

v1.1 — oparcie na karmazyn_proca (zgodnie z zaprojektowaną rolą Proca:
       zapis pola na obcy FS + zarządzanie informacją na poziomie atomu):
  - Treść (tekst/audio/obraz) → ProcaIndex.register_or_deduplicate
      identyczna treść (ten sam SHA256) zapisuje się RAZ jako .pfld;
      kolejne odwołania to współrzędne w polu Yukawy, nie kopie bajtów.
  - Struktura dokumentu (manifest, S/E/T/metadata, odwołania do pól)
      → lekki indeks index.kafd (format KAFD, spójny z resztą systemu).
  - Mała treść (< MIN_DEDUP_SIZE Proca) trzymana wprost w indeksie —
      nie warto dla niej osobnego pliku pola.

Bez karmazyn_proca moduł degraduje się do trybu inline (wszystko w
indeksie KAFD) — działa, tylko bez deduplikacji.

Układ na dysku (base_dir — może być na NTFS/ext4):
    <base_dir>/
      index.kafd                      ← struktura dokumentów (KAFD)
      fields/
        proca_<sha256>.pfld           ← pola treści (dedup, content-addressed)

Zachowywane wiernie: S, E, T, metadata, surowe bajty, temperatury,
historia wersji. Atomy płótna (S="paint") pomijane — z natury ulotne.

API (ukryte pod maską):
    import karmazyn_store as store
    store.save_documents(phi, base_dir)
    store.load_documents(phi, base_dir)
  lub przez Workspace:
    ws.persist(base_dir);  ws.restore(base_dir)
"""

import hashlib
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

try:
    from karmazyn_proca import ProcaIndex
    _PROCA_OK = True
except ImportError:
    _PROCA_OK = False

try:
    import numpy as _np
except ImportError:
    _np = None

DOC_KINDS  = ("document", "version")          # + "content:*"
STORE_META = "karmazyn_store_v1.1"
INDEX_NAME = "index.kafd"
FIELDS_DIR = "fields"


# ─── Klasyfikacja atomów dokumentów ──────────────────────────────────────────

def _is_doc_atom(atom, kinds) -> bool:
    S = atom.S or ""
    return S in kinds or S.startswith("content:")

def _has_content(atom) -> bool:
    """Atom niosący treść (do skierowania przez Proca)."""
    S = atom.S or ""
    if S.startswith("content:") or S == "version":
        return bool(atom.E) or bool(atom.metadata.get("data"))
    return False

def _content_bytes(atom):
    """Zwraca (bytes, is_text) treści atomu lub (None, None)."""
    data = atom.metadata.get("data")
    if isinstance(data, (bytes, bytearray)) and data:
        return bytes(data), False
    if atom.E:
        return atom.E.encode("utf-8"), True
    return None, None


# ─── phi treści (dla pola Yukawy) ────────────────────────────────────────────

def _content_phi(phi_space, content: bytes, is_text: bool):
    """
    Wektor phi (15D) dla treści. Tekst → phi_space.embed. Binarne →
    deterministyczny wektor z SHA256 (dedup i tak po haszu, phi steruje
    tylko geometrią współrzędnej).
    """
    if _np is None:
        return None
    if is_text:
        try:
            v = phi_space.embed(content.decode("utf-8", "ignore"))
            if v is not None:
                return v
        except Exception:
            pass
    # synteza z hasza
    seed = int(hashlib.sha256(content).hexdigest()[:8], 16)
    v = _np.random.default_rng(seed).standard_normal(15).astype(_np.float32)
    n = _np.linalg.norm(v)
    return v / n if n > 1e-9 else v


# ─── Serializacja rekordu atomu w indeksie ───────────────────────────────────
# Ramka: [4B len JSON][JSON head][opcjonalne surowe bajty]
#   head.ref   — field_id w Proca (treść w polu, brak bajtów inline)
#   head.ctext — czy treść jest tekstem (rekonstrukcja do E vs metadata['data'])
#   head.raw   — czy po JSON następują surowe bajty inline

def _encode_record(atom, ref=None, ctext=None, inline_data=None) -> bytes:
    meta = {k: v for k, v in atom.metadata.items() if k != "data"}
    head = {"S": atom.S, "T": float(atom.T), "meta": meta}
    if ref is not None:
        head["ref"] = ref
        head["ctext"] = bool(ctext)
    else:
        head["E"] = atom.E
        if inline_data is not None:
            head["raw"] = True
    hb = json.dumps(head, ensure_ascii=False).encode("utf-8")
    tail = inline_data if (ref is None and inline_data is not None) else b""
    return struct.pack(">I", len(hb)) + hb + tail

def _decode_record(blob):
    hlen = struct.unpack(">I", blob[:4])[0]
    head = json.loads(blob[4:4 + hlen].decode("utf-8"))
    tail = blob[4 + hlen:]
    return head, tail


# ─── Atomowy zapis ────────────────────────────────────────────────────────────

def _atomic_write(path: str, data: bytes) -> None:
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".store_", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path); tmp = None
    finally:
        if tmp and os.path.exists(tmp):
            try: os.unlink(tmp)
            except OSError: pass


def _fsync_dir(path: str) -> None:
    """Utrwala wpisy katalogu (rename/create) — bez tego os.replace może
    nie przetrwać nagłego odcięcia zasilania na niektórych FS."""
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (OSError, AttributeError):
        pass   # np. Windows nie pozwala fsync katalogu — degradacja łagodna


# ─── Zapis ────────────────────────────────────────────────────────────────────

def save_documents(phi, base_dir: str,
                   kinds: Iterable[str] = DOC_KINDS,
                   confirm=None, reason: str = "") -> dict:
    """
    Zapisz dokumenty z phi do base_dir. Treść przez Proca (dedup, .pfld),
    struktura w index.kafd. Zwraca statystyki.

    Atomowość transakcyjna: nowe pola są dopisywane (content-addressed,
    nigdy nie nadpisują starych), a punktem zatwierdzenia jest pojedyncza
    atomowa podmiana index.kafd. Przerwanie przed podmianą zostawia stary
    indeks i stare pola nietknięte. Przed zatwierdzeniem weryfikujemy że
    wszystkie pola wskazywane przez nowy indeks są fizycznie na dysku.

    confirm: opcjonalny callable(reason)->bool. Gdy podany i zwróci False,
             zapis NIE jest wykonywany (zwraca {"skipped": True}). Służy do
             pytania użytkownika "wykonać zapis?" przy zapisie z edytora,
             po przekształceniu informacji albo przy wyjściu z systemu.
    """
    if not _KAFD_OK:
        raise RuntimeError("Brak karmazyn_kafd — nie można zapisać indeksu")

    if confirm is not None and not confirm(reason):
        return {"skipped": True, "reason": reason}

    kinds = tuple(kinds)
    os.makedirs(base_dir, exist_ok=True)
    fields_dir = os.path.join(base_dir, FIELDS_DIR)

    proca = ProcaIndex(fields_dir=fields_dir) if _PROCA_OK else None
    records = {}
    n_atoms = n_fields = n_coords = n_inline = 0

    for atom in phi.matrix.atoms():
        if not _is_doc_atom(atom, kinds):
            continue
        n_atoms += 1

        if proca is not None and _has_content(atom):
            content, is_text = _content_bytes(atom)
            if content is not None:
                ph = _content_phi(phi, content, is_text)
                kind, obj = proca.register_or_deduplicate(
                    atom.id, content, ph, T=float(atom.T))
                if kind == "source":
                    records[atom.id] = _encode_record(atom, ref=obj.field_id, ctext=is_text)
                    n_fields += 1
                    continue
                if kind == "coordinate":
                    records[atom.id] = _encode_record(atom, ref=obj.field_id, ctext=is_text)
                    n_coords += 1
                    continue
                # kind == "raw" → mała treść, trzymaj inline
                if is_text:
                    records[atom.id] = _encode_record(atom, inline_data=None)  # E w head
                else:
                    records[atom.id] = _encode_record(atom, inline_data=content)
                n_inline += 1
                continue

        # manifest albo brak treści — pełny rekord inline
        data = atom.metadata.get("data")
        inline = bytes(data) if isinstance(data, (bytes, bytearray)) else None
        records[atom.id] = _encode_record(atom, inline_data=inline)
        n_inline += 1

    # zapisz pola Proca na FS (każde atomowo: tmp+fsync+replace), potem
    # utrwal katalog pól, by wpisy plików przetrwały odcięcie zasilania
    saved_fields = proca.save_all_sources() if proca is not None else 0
    if proca is not None:
        _fsync_dir(fields_dir)

    # WERYFIKACJA przed zatwierdzeniem: każde pole wskazywane przez nowy
    # indeks musi istnieć na dysku. Jeśli nie — przerwij BEZ ruszania
    # starego indeksu (stary, spójny stan zostaje nietknięty).
    if proca is not None:
        for rec in records.values():
            try:
                head, _ = _decode_record(rec)
            except Exception:
                continue
            ref = head.get("ref")
            if ref and not os.path.exists(proca._source_path(ref)):
                raise RuntimeError(
                    f"Pole {ref[:12]} nie zapisane na dysk — zapis przerwany, "
                    f"stary stan nietknięty")

    # zapisz indeks (KAFD) — POJEDYNCZY punkt zatwierdzenia, atomowy
    meta = {"format": STORE_META, "saved": time.time(),
            "atoms": n_atoms, "proca": bool(proca)}
    blob = vfs_pack(records, meta)
    _atomic_write(os.path.join(base_dir, INDEX_NAME), blob)
    _fsync_dir(base_dir)

    return {"atoms": n_atoms, "fields": n_fields, "coordinates": n_coords,
            "inline": n_inline, "pfld_written": saved_fields}


# ─── Odczyt ────────────────────────────────────────────────────────────────────

def load_documents(phi, base_dir: str) -> int:
    """Odczytaj dokumenty z base_dir do phi. Zwraca liczbę atomów."""
    if not _KAFD_OK:
        raise RuntimeError("Brak karmazyn_kafd — nie można odczytać indeksu")
    index_path = os.path.join(base_dir, INDEX_NAME)
    if not os.path.exists(index_path):
        return 0

    with open(index_path, "rb") as f:
        blob = f.read()
    try:
        records, _meta = vfs_unpack(blob)
    except Exception:
        return 0

    fields_dir = os.path.join(base_dir, FIELDS_DIR)
    proca = None
    if _PROCA_OK and os.path.isdir(fields_dir):
        proca = ProcaIndex(fields_dir=fields_dir)
        proca.load_sources_from_disk()

    n = 0
    for aid, rec in records.items():
        try:
            head, tail = _decode_record(rec)
        except Exception:
            continue

        S = head.get("S", "")
        T = float(head.get("T", 50.0))
        meta = head.get("meta", {})

        if "ref" in head and proca is not None:
            # treść w polu Proca — rozwiąż field_id
            src = proca._get_source(head["ref"])
            data = src.data if src else b""
            if head.get("ctext"):
                atom = phi.create_atom(aid, S=S, E=data.decode("utf-8", "ignore"), T=T)
            else:
                atom = phi.create_atom(aid, S=S, E="", T=T)
                if data:
                    atom.metadata["data"] = data
        else:
            # inline
            E = head.get("E", "")
            atom = phi.create_atom(aid, S=S, E=E, T=T)
            if tail:
                atom.metadata["data"] = tail

        if isinstance(meta, dict):
            atom.metadata.update(meta)
        n += 1
    return n


def store_stats(base_dir: str) -> dict:
    index_path = os.path.join(base_dir, INDEX_NAME)
    if not os.path.exists(index_path):
        return {"exists": False}
    try:
        with open(index_path, "rb") as f:
            blob = f.read()
        records, meta = vfs_unpack(blob)
        fields_dir = os.path.join(base_dir, FIELDS_DIR)
        pfld = len([f for f in os.listdir(fields_dir)
                    if f.endswith(".pfld")]) if os.path.isdir(fields_dir) else 0
        return {"exists": True, "atoms": len(records),
                "index_size": len(blob), "pfld_files": pfld, "meta": meta}
    except Exception as e:
        return {"exists": True, "error": str(e)}


# ─── Warstwa potwierdzenia zapisu ─────────────────────────────────────────────
# Zapis z edytorów / po przekształceniu informacji ma pytać użytkownika.
# Bramka jest agnostyczna wobec UI: przyjmuje callback confirm(reason)->bool.
# UI (terminal SDL, prompt, GUI) dostarcza własną implementację pytania.

def terminal_confirm(reason: str = "") -> bool:
    """
    Domyślny prompt w zwykłym terminalu. W trybie graficznym SDL shell
    powinien podać własny confirm (np. modal w oknie). Brak TTY → True
    (nie blokuje zapisu wsadowego).
    """
    import sys
    if not sys.stdin or not sys.stdin.isatty():
        return True
    q = f"Wykonać zapis{(' — ' + reason) if reason else ''}? [T/n] "
    try:
        ans = input(q).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans in ("", "t", "tak", "y", "yes")


def request_save(phi, base_dir: str, confirm=None,
                 reason: str = "", kinds: Iterable[str] = DOC_KINDS) -> dict:
    """
    Zapis za zgodą. Pyta przez confirm(reason); zapisuje atomowo gdy
    potwierdzono. Domyślny confirm = terminal_confirm. Wołane przy zapisie
    z edytora, po przekształceniu informacji albo przy wyjściu.
    """
    if confirm is None:
        confirm = terminal_confirm
    return save_documents(phi, base_dir, kinds=kinds,
                          confirm=confirm, reason=reason)


def save_on_exit(phi, base_dir: str, confirm=None, dirty: bool = True) -> dict:
    """
    Hook wyjścia z systemu. Gdy nic się nie zmieniło (dirty=False) — nie
    pyta i nie zapisuje. Gdy są zmiany — pyta i zapisuje atomowo.
    """
    if not dirty:
        return {"skipped": True, "reason": "brak zmian"}
    return request_save(phi, base_dir, confirm=confirm, reason="wyjście z systemu")


# ─── Komenda powłoki ──────────────────────────────────────────────────────────

_DEFAULT_DIR = os.environ.get(
    "KARMAZYN_STORE",
    os.path.join(os.path.expanduser("~"), ".karmazyn", "store"))


def cmd_store(args, phi=None) -> str:
    """
    STORE SAVE [katalog]  — zapisz dokumenty na dysk (przez pole Proca)
    STORE LOAD [katalog]  — wczytaj dokumenty z dysku
    STORE INFO [katalog]  — pokaż zawartość zapisu
    Domyślny katalog: $KARMAZYN_STORE lub ~/.karmazyn/store
    """
    if phi is None:
        return "Brak runtime (phi)."
    if not args:
        return (f"STORE SAVE|LOAD|INFO [katalog]\nDomyślny: {_DEFAULT_DIR}\n"
                f"Pole Proca: {'aktywne' if _PROCA_OK else 'brak — tryb inline'}")
    sub = args[0].upper()
    base = args[1] if len(args) > 1 else _DEFAULT_DIR
    try:
        if sub == "SAVE":
            s = save_documents(phi, base)
            return (f"Zapisano {s['atoms']} atomów → {base}\n"
                    f"  pola: {s['fields']} nowe, {s['coordinates']} dedup, "
                    f"{s['inline']} inline  ({s['pfld_written']} plików .pfld)")
        if sub == "LOAD":
            n = load_documents(phi, base)
            return f"Wczytano {n} atomów z {base}"
        if sub == "INFO":
            st = store_stats(base)
            if not st.get("exists"):
                return f"Brak zapisu: {base}"
            if "error" in st:
                return f"Uszkodzony zapis: {st['error']}"
            return (f"Zapis: {base}\n  atomów: {st['atoms']}  "
                    f"indeks: {st['index_size']}B  pól .pfld: {st['pfld_files']}")
    except Exception as e:
        return f"Błąd magazynu: {type(e).__name__}: {e}"
    return "Użycie: STORE SAVE|LOAD|INFO [katalog]"


if __name__ == "__main__":
    import sys
    from karmazyn_phi import PhiSpace
    print(cmd_store(sys.argv[1:], phi=PhiSpace()))