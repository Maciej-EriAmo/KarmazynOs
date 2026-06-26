#!/usr/bin/env python3
"""karmazyn_cas.py -- KarmazynOS Content-Addressable Storage v1.0.
Blob store: atom.E = "blob:<sha256[:24]>", dane ~/.karmazyn/blobs/.
Deduplication, refcount, BlobHeatCache, thermal decay."""

import hashlib
import json
import os
import shutil
import time
import threading
from typing import Any, Dict, Iterator, List, Optional, Tuple


# ── Stałe ─────────────────────────────────────────────────────────────────────

CAS_ATOM_PREFIX = "blob:"
CAS_DIR_DEFAULT = os.path.join(os.path.expanduser("~"), ".karmazyn", "blobs")
CAS_INDEX_FILE  = os.path.join(os.path.expanduser("~"), ".karmazyn", "cas.index")
HASH_PREFIX_LEN = 2    # długość podkatalogu (ab/cdef... -> ab/)
HASH_STORE_LEN  = 24   # [FIX] 16->24: 96 bitów -- bezpieczne do ~10^14 blobów
CHUNK_SIZE      = 65536


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_blob_ref(e_field: str) -> bool:
    """Czy pole E atomu jest referencją CAS?"""
    return isinstance(e_field, str) and e_field.startswith(CAS_ATOM_PREFIX)


def extract_hash(e_field: str) -> Optional[str]:
    """Wyciągnij hash z 'blob:<hash>'."""
    if is_blob_ref(e_field):
        return e_field[len(CAS_ATOM_PREFIX):]
    return None


def make_blob_ref(sha256_hex: str) -> str:
    """Zbuduj pole E: 'blob:<hash>'."""
    return f"{CAS_ATOM_PREFIX}{sha256_hex[:HASH_STORE_LEN]}"


# ─────────────────────────────────────────────────────────────────────────────
# BlobStore -- główna klasa CAS
# ─────────────────────────────────────────────────────────────────────────────

class BlobStore:
    """
    Content-Addressable Blob Store dla KarmazynOS.

    Przechowuje pliki binarne indeksowane po SHA256.
    Atomy przechowują tylko hash (16 hex chars) zamiast danych.
    """

    def __init__(self, base_dir: str = CAS_DIR_DEFAULT):
        self.base_dir   = base_dir
        self._lock      = threading.Lock()
        self._index:    Dict[str, dict] = {}   # hash -> metadata
        os.makedirs(base_dir, exist_ok=True)
        self._load_index()

    # ── Zapis ─────────────────────────────────────────────────────────────────

    def put(self, path: str, mime: str = "") -> str:
        """
        Zapisz plik do CAS.
        Zwraca hash (16 hex chars) -- użyj make_blob_ref() do E atomu.
        Jeśli plik już istnieje w CAS (ten sam hash) -- deduplication.
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Brak pliku: {path}")

        full_hash = _sha256_file(path)
        short     = full_hash[:HASH_STORE_LEN]
        blob_path = self._blob_path(full_hash)

        with self._lock:
            if not os.path.exists(blob_path):
                os.makedirs(os.path.dirname(blob_path), exist_ok=True)
                shutil.copy2(path, blob_path)

            # Zaktualizuj index
            if short not in self._index:
                size = os.path.getsize(blob_path)
                if not mime:
                    import mimetypes
                    mime, _ = mimetypes.guess_type(path)
                    mime    = mime or "application/octet-stream"
                self._index[short] = {
                    "full_hash": full_hash,
                    "size":      size,
                    "mime":      mime,
                    "added":     time.strftime("%Y-%m-%d %H:%M"),
                    "sources":   [os.path.basename(path)],
                    "refs":      1,          # [FIX 2] refcount
                    "owners":    [],          # [FIX 2] lista właścicieli
                }
            else:
                # Deduplikacja -- zwiększ refcount
                self._index[short]["refs"] = \
                    self._index[short].get("refs", 1) + 1
                src = os.path.basename(path)
                if src not in self._index[short].get("sources", []):
                    self._index[short].setdefault("sources", []).append(src)

            self._save_index()

        return short

    def put_bytes(self, data: bytes, mime: str = "application/octet-stream",
                  filename: str = "") -> str:
        """
        Zapisz dane binarne bezpośrednio do CAS.
        Używane przy małych plikach już w pamięci.
        """
        full_hash = _sha256_bytes(data)
        short     = full_hash[:HASH_STORE_LEN]
        blob_path = self._blob_path(full_hash)

        with self._lock:
            if not os.path.exists(blob_path):
                os.makedirs(os.path.dirname(blob_path), exist_ok=True)
                with open(blob_path, "wb") as f:
                    f.write(data)
            if short not in self._index:
                self._index[short] = {
                    "full_hash": full_hash,
                    "size":      len(data),
                    "mime":      mime,
                    "added":     time.strftime("%Y-%m-%d %H:%M"),
                    "sources":   [filename] if filename else [],
                }
                self._save_index()

        return short

    # ── Odczyt ────────────────────────────────────────────────────────────────

    def get_path(self, short_hash: str) -> Optional[str]:
        """
        Zwróć ścieżkę do pliku binarnego po hashu.
        None jeśli blob nie istnieje.
        """
        with self._lock:
            meta = self._index.get(short_hash)
            if not meta:
                # Spróbuj znaleźć przez prefix w katalogu
                meta = self._find_by_prefix(short_hash)
                if not meta:
                    return None
            full_hash = meta.get("full_hash", "")
        blob_path = self._blob_path(full_hash)
        return blob_path if os.path.exists(blob_path) else None

    def get_bytes(self, short_hash: str) -> Optional[bytes]:
        """Wczytaj blob do pamięci. Używaj oszczędnie dla dużych plików."""
        path = self.get_path(short_hash)
        if not path:
            return None
        with open(path, "rb") as f:
            return f.read()

    def exists(self, short_hash: str) -> bool:
        return self.get_path(short_hash) is not None

    def meta(self, short_hash: str) -> Optional[dict]:
        """Metadane bloba: size, mime, added, sources."""
        with self._lock:
            return dict(self._index.get(short_hash, {}))

    # ── Usuwanie / GC ─────────────────────────────────────────────────────────

    def delete(self, short_hash: str, force: bool = False) -> bool:
        """
        Usuń blob.
        [FIX 2] Bezpieczny: sprawdza refcount przed usunięciem.
        force=True -- usuń nawet gdy refs > 0 (ostrożnie!).
        """
        with self._lock:
            meta = self._index.get(short_hash, {})
            refs = meta.get("refs", 0)
            if refs > 1 and not force:
                # Tylko dekrementuj -- inni nadal używają
                self._index[short_hash]["refs"] = refs - 1
                self._save_index()
                return False   # nie usunięto fizycznie
        path = self.get_path(short_hash)
        if not path:
            with self._lock:
                self._index.pop(short_hash, None)
            return False
        try:
            os.remove(path)
            parent = os.path.dirname(path)
            if not os.listdir(parent):
                os.rmdir(parent)
            with self._lock:
                self._index.pop(short_hash, None)
                self._save_index()
            return True
        except Exception as e:
            try:
                from karmazyn_syslog import SystemLog
                SystemLog().log("WARN", f"CAS delete {short_hash}: {e}",
                                service="cas")
            except Exception:
                pass
            return False

    def gc(self, phi: Any = None, bubbles: Any = None) -> Tuple[int, int]:
        """
        Garbage collection blobów.
        Usuwa blobs które nie są referencjonowane przez żaden atom φ-space.

        phi     -- PhiSpace (sprawdza atomy)
        bubbles -- BubbleVFS (sprawdź bąble)
        Zwraca (usunięte, zachowane).
        """
        # Zbierz wszystkie aktywne hashe
        active_hashes: set = set()

        if phi is not None:
            try:
                for a in phi.matrix.atoms():
                    E = str(getattr(a, "E", ""))
                    h = extract_hash(E)
                    if h:
                        active_hashes.add(h)
            except Exception:
                pass

        if bubbles is not None:
            try:
                for b in bubbles.list_bubbles():
                    bid = b.get("id")
                    if not bid:
                        continue
                    try:
                        atoms = bubbles.get_active_atoms(bid)
                        for a in atoms:
                            E = (a.get("E") if isinstance(a, dict)
                                 else str(getattr(a, "E", "")))
                            h = extract_hash(str(E or ""))
                            if h:
                                active_hashes.add(h)
                    except Exception:
                        pass
            except Exception:
                pass

        # Znajdź unreferenced blobs
        with self._lock:
            all_hashes = set(self._index.keys())

        to_delete  = all_hashes - active_hashes
        deleted    = kept = 0

        for h in to_delete:
            if self.delete(h):
                deleted += 1
            else:
                kept += 1

        kept += len(active_hashes & all_hashes)
        return deleted, kept

    # ── Statystyki ────────────────────────────────────────────────────────────

    def add_owner(self, short_hash: str, owner: str) -> None:
        """[FIX 2] Zarejestruj właściciela bloba (bubble.photos, cluster.node3...)."""
        with self._lock:
            if short_hash in self._index:
                owners = self._index[short_hash].setdefault("owners", [])
                if owner not in owners:
                    owners.append(owner)
                self._index[short_hash]["refs"] = len(owners) or 1
                self._save_index()

    def remove_owner(self, short_hash: str, owner: str) -> int:
        """Usuń właściciela. Zwraca pozostały refcount."""
        with self._lock:
            if short_hash not in self._index:
                return 0
            owners = self._index[short_hash].get("owners", [])
            if owner in owners:
                owners.remove(owner)
            refs = max(0, len(owners))
            self._index[short_hash]["refs"]  = refs
            self._index[short_hash]["owners"] = owners
            self._save_index()
            return refs

    def stats(self) -> dict:
        """Statystyki CAS."""
        with self._lock:
            total_blobs = len(self._index)
            total_size  = sum(m.get("size", 0) for m in self._index.values())
            mime_counts: Dict[str, int] = {}
            for m in self._index.values():
                mt = m.get("mime", "?").split("/")[0]
                mime_counts[mt] = mime_counts.get(mt, 0) + 1
        return {
            "blobs":      total_blobs,
            "total_size": total_size,
            "mime":       mime_counts,
            "base_dir":   self.base_dir,
        }

    def list_blobs(self) -> Iterator[dict]:
        """Listuj wszystkie blobs z metadanymi."""
        with self._lock:
            items = list(self._index.items())
        for short, meta in sorted(items, key=lambda x: x[1].get("added",""), reverse=True):
            yield {"hash": short, **meta}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _blob_path(self, full_hash: str) -> str:
        prefix = full_hash[:HASH_PREFIX_LEN]
        return os.path.join(self.base_dir, prefix, full_hash + ".bin")

    def _find_by_prefix(self, short_hash: str) -> Optional[dict]:
        """Znajdź metadane przez prefix gdy nie ma w indeksie."""
        prefix = short_hash[:HASH_PREFIX_LEN]
        prefix_dir = os.path.join(self.base_dir, prefix)
        if not os.path.isdir(prefix_dir):
            return None
        for fname in os.listdir(prefix_dir):
            if fname.startswith(short_hash) and fname.endswith(".bin"):
                full_hash = fname[:-4]
                return {"full_hash": full_hash, "size": 0, "mime": "", "added": ""}
        return None

    def _load_index(self) -> None:
        try:
            if os.path.exists(CAS_INDEX_FILE):
                with open(CAS_INDEX_FILE, encoding="utf-8") as f:
                    self._index = json.load(f)
        except Exception:
            self._index = {}

    def _save_index(self) -> None:
        try:
            os.makedirs(os.path.dirname(CAS_INDEX_FILE), exist_ok=True)
            tmp = CAS_INDEX_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CAS_INDEX_FILE)  # atomowe nadpisanie
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Globalny singleton
# ─────────────────────────────────────────────────────────────────────────────


class BlobHeatCache:
    """Blob temperature cache: RAM preload dla goracych blobow.
    blob_heat[hash] = suma T atomow wskazujacych na dany blob.
    Scheduler: preload/evict/priorytetyzacja sieci w klastrze.
    """

    def __init__(self, store, max_ram_mb=64.0):
        import threading as _th
        self.store     = store
        self.max_bytes = int(max_ram_mb * 1024 * 1024)
        self._cache    = {}
        self._heat     = {}
        self._lock     = _th.Lock()
        self._used     = 0

    def update_heat(self, phi, decay=0.95):
        """Aktualizuj cieplo blobow na podstawie temperatur atomow."""
        try:
            atoms = phi.matrix.atoms()
        except Exception:
            return
        new_heat = {}
        for a in atoms:
            E = str(getattr(a, "E", ""))
            h = extract_hash(E)
            if not h: continue
            T = float(getattr(a, "T", 0))
            new_heat[h] = new_heat.get(h, 0) + T
        with self._lock:
            for h in list(self._heat):
                self._heat[h] = self._heat[h] * decay
            for h, T in new_heat.items():
                self._heat[h] = self._heat.get(h, 0) + T
        self._preload_hot()

    def get(self, short_hash):
        """Pobierz blob -- najpierw z RAM cache, potem z dysku."""
        with self._lock:
            if short_hash in self._cache:
                self._heat[short_hash] = self._heat.get(short_hash, 0) + 5
                return self._cache[short_hash]
        data = self.store.get_bytes(short_hash)
        if data:
            self._maybe_cache(short_hash, data)
        return data

    def heat_of(self, short_hash):
        with self._lock:
            return self._heat.get(short_hash, 0.0)

    def hot_blobs(self, top_n=10):
        with self._lock:
            return sorted(self._heat.items(), key=lambda x: x[1], reverse=True)[:top_n]

    def evict_cold(self, threshold=5.0):
        evicted = 0
        with self._lock:
            for h in list(self._cache):
                if self._heat.get(h, 0) < threshold:
                    self._used -= len(self._cache.pop(h))
                    evicted += 1
        return evicted

    def _preload_hot(self, top_n=5):
        hot = sorted(self._heat.items(), key=lambda x: -x[1])[:top_n]
        for h, _ in hot:
            with self._lock:
                if h in self._cache: continue
                if self._used >= self.max_bytes: break
            data = self.store.get_bytes(h)
            if data:
                self._maybe_cache(h, data)

    def _maybe_cache(self, h, data):
        with self._lock:
            if self._used + len(data) <= self.max_bytes:
                self._cache[h] = data
                self._used    += len(data)

    def stats(self):
        with self._lock:
            return {
                "cached":  len(self._cache),
                "used_mb": round(self._used / 1024 / 1024, 2),
                "max_mb":  round(self.max_bytes / 1024 / 1024, 1),
                "tracked": len(self._heat),
            }


BLOB_STORE = BlobStore()

BLOB_HEAT_CACHE = BlobHeatCache(BLOB_STORE, max_ram_mb=64.0)


# ─────────────────────────────────────────────────────────────────────────────
# Integracja z ThermalScheduler -- thermal decay
# ─────────────────────────────────────────────────────────────────────────────

def register_thermal_decay(scheduler: Any, phi: Any,
                            decay_rate: float = 0.98,
                            interval_s: float = 60.0) -> None:
    """
    Podłącz thermal decay do istniejącego ThermalSchedulera.

    Scheduler (ThermalScheduler z karmazyn_scheduler.py) dostaje trigger
    który co interval_s sekund mnoży T wszystkich atomów przez decay_rate.

    decay_rate = 0.98 -> -2% na tick
    interval_s = 60   -> tick co minutę
    Czas do ochłodzenia ze 100 do 2: ln(2/100)/ln(0.98) ≈ 195 minut

    Użycie w shell.py po inicjalizacji schedulera:
        from karmazyn_cas import register_thermal_decay
        register_thermal_decay(SCHEDULER, RUNTIME)
    """
    if scheduler is None or phi is None:
        return

    def _decay_tick():
        """
        Rozszerzony krok thermal decay:
          T_new = T_old * decay + blob_heat_bonus

        blob_heat_bonus = ciepło przychodzące z BLOB_HEAT_CACHE
        (atomy wskazujące na gorące blobs wolniej stygną)
        """
        decayed = 0
        try:
            atoms = phi.matrix.atoms()
        except Exception:
            return
        # Aktualizuj blob heat cache
        try:
            BLOB_HEAT_CACHE.update_heat(phi)
            BLOB_HEAT_CACHE.evict_cold(threshold=5.0)
        except Exception:
            pass

        for a in atoms:
            try:
                T_old = float(getattr(a, "T", 0))
                if T_old < 0.5:
                    continue
                # Bazowy decay
                T_new = T_old * decay_rate
                # Blob heat bonus -- atom wskazuje na gorący blob
                E = str(getattr(a, "E", ""))
                h = extract_hash(E)
                if h:
                    blob_heat = BLOB_HEAT_CACHE.heat_of(h)
                    bonus     = min(5.0, blob_heat * 0.02)
                    T_new    += bonus
                T_new = min(float(getattr(a, "T_max", 100)), max(0.0, T_new))
                if T_new < 2.0:
                    T_new = max(0.0, T_new)
                a.T     = round(T_new, 3)
                decayed += 1
            except Exception as _e:
                try:
                    from karmazyn_syslog import SystemLog
                    SystemLog().log("DEBUG",
                        f"decay atom error: {type(_e).__name__}: {_e}",
                        service="cas.decay")
                except Exception:
                    pass

        return {"decayed": decayed}

    # Zarejestruj trigger w schedulerze
    try:
        scheduler.add_trigger(
            name     = "thermal_decay",
            fn       = _decay_tick,
            interval = interval_s,
            priority = 10,    # niski priorytet -- tło
        )
    except AttributeError:
        # Fallback -- scheduler nie ma add_trigger -> wątek tła
        def _bg():
            import time as _t
            while True:
                _t.sleep(interval_s)
                _decay_tick()
        import threading
        threading.Thread(target=_bg, daemon=True,
                         name="thermal-decay").start()


# ─────────────────────────────────────────────────────────────────────────────
# Migracja base64 -> CAS
# ─────────────────────────────────────────────────────────────────────────────

def migrate_base64_atoms(phi: Any,
                          store: BlobStore = None) -> Tuple[int, int]:
    """
    Jednorazowa migracja istniejących atomów z base64 w E -> CAS.
    Uruchom po aktualizacji systemu.

    Zwraca (zmigrowane, pominięte).
    """
    if store is None:
        store = BLOB_STORE
    if phi is None:
        return 0, 0

    import base64 as _b64
    migrated = skipped = 0

    try:
        atoms = phi.matrix.atoms()
    except Exception:
        return 0, 0

    for a in atoms:
        E = str(getattr(a, "E", ""))
        if not E.startswith("base64:"):
            skipped += 1
            continue
        try:
            raw  = _b64.b64decode(E[7:])
            S    = str(getattr(a, "S", "application/octet-stream"))
            aid  = str(getattr(a, "id", ""))
            hsh  = store.put_bytes(raw, mime=S, filename=aid)
            a.E  = make_blob_ref(hsh)
            try: a.touch()
            except Exception: pass
            migrated += 1
        except Exception:
            skipped += 1

    return migrated, skipped


# ─────────────────────────────────────────────────────────────────────────────
# Komendy shella
# ─────────────────────────────────────────────────────────────────────────────

def cmd_cas(args, runtime=None, bubbles=None, **_) -> str:
    """
    CAS STATUS              -- statystyki blob store
    CAS LS                  -- lista blobów
    CAS GC                  -- garbage collection
    CAS INFO <hash>         -- info o blobie
    CAS GET <hash> [dest]   -- pobierz blob do pliku
    CAS MIGRATE             -- migruj base64 atomów -> CAS
    """
    store = BLOB_STORE
    if not args:
        s = store.stats()
        from karmazyn_shell_cmds import _fmt_size
        return (f"CAS: {s['blobs']} blobów  "
                f"{_fmt_size(s['total_size'])}  "
                f"{s['base_dir']}\n"
                f"  Typy: {s['mime']}")

    sub = args[0].upper()

    if sub == "STATUS":
        s = store.stats()
        lines = [
            f"  Katalog: {s['base_dir']}",
            f"  Blobs:   {s['blobs']}",
        ]
        try:
            from karmazyn_shell_cmds import _fmt_size
            lines.append(f"  Rozmiar: {_fmt_size(s['total_size'])}")
        except ImportError:
            lines.append(f"  Rozmiar: {s['total_size']} B")
        for mt, cnt in s["mime"].items():
            lines.append(f"    {mt}: {cnt}")
        return "\n".join(lines)

    elif sub == "LS":
        rows = []
        for blob in store.list_blobs():
            try:
                from karmazyn_shell_cmds import _fmt_size
                sz = _fmt_size(blob.get("size", 0))
            except ImportError:
                sz = str(blob.get("size", 0))
            mime    = blob.get("mime", "?")[:20]
            added   = blob.get("added", "?")[:16]
            sources = ", ".join(blob.get("sources", [])[:2])
            rows.append(f"  {blob['hash']:16} {sz:>8}  {mime:<22} {added}  {sources}")
        return "\n".join(rows) if rows else "(brak blobów)"

    elif sub == "GC":
        deleted, kept = store.gc(runtime, bubbles)
        return f"GC: usunięto {deleted} blobów, zachowano {kept}"

    elif sub == "INFO" and len(args) > 1:
        hsh  = args[1]
        meta = store.meta(hsh)
        if not meta:
            return f"Blob nie istnieje: {hsh}"
        try:
            from karmazyn_shell_cmds import _fmt_size
            sz = _fmt_size(meta.get("size", 0))
        except ImportError:
            sz = str(meta.get("size", 0))
        path = store.get_path(hsh) or "(brak pliku!)"
        lines = [
            f"  Hash:    {hsh}",
            f"  Full:    {meta.get('full_hash', '?')}",
            f"  MIME:    {meta.get('mime', '?')}",
            f"  Rozmiar: {sz}",
            f"  Dodano:  {meta.get('added', '?')}",
            f"  Źródła:  {', '.join(meta.get('sources', []))}",
            f"  Plik:    {path}",
        ]
        return "\n".join(lines)

    elif sub == "GET" and len(args) > 1:
        hsh  = args[1]
        dest = args[2] if len(args) > 2 else "."
        path = store.get_path(hsh)
        if not path:
            return f"Blob nie istnieje: {hsh}"
        import shutil as _sh
        dest = os.path.expanduser(dest)
        out  = os.path.join(dest, os.path.basename(path)) \
               if os.path.isdir(dest) else dest
        _sh.copy2(path, out)
        return f"OK: {hsh} -> {out}"

    elif sub == "MIGRATE":
        if not runtime:
            return "Brak runtime."
        m, s = migrate_base64_atoms(runtime, store)
        return f"Migracja: {m} atomów -> CAS, {s} pominięto"

    return "CAS STATUS | LS | GC | INFO <hash> | GET <hash> [dest] | MIGRATE"


# ─────────────────────────────────────────────────────────────────────────────
# Poprawka karmazyn_shell_cmds -- BIMPORT używa CAS zamiast base64
# ─────────────────────────────────────────────────────────────────────────────

def bimport_cas(path: str,
                bubble_name: Optional[str] = None,
                force_embed: bool = False,
                runtime: Any = None,
                bubbles: Any = None) -> str:
    """
    Wersja BIMPORT zintegrowana z CAS.
    Zastępuje logikę base64 z karmazyn_shell_cmds.cmd_bimport().
    """
    import mimetypes as _mt

    if not os.path.isfile(path):
        return f"Brak pliku: {path}"

    size     = os.path.getsize(path)
    mime, _  = _mt.guess_type(path)
    mime     = mime or "application/octet-stream"
    filename = os.path.basename(path)
    abs_path = os.path.abspath(path)

    # Temperatura: małe pliki gorące, duże zimniejsze
    import math
    kb  = size / 1024
    T   = max(20.0, 70.0 - math.log10(max(1, kb)) * 12)
    T   = round(T, 1)

    # CAS -- zawsze przez hash, nigdy base64
    import hashlib as _hl
    store    = BLOB_STORE
    hid_atom = _hl.sha1(abs_path.encode()).hexdigest()[:12]
    atom_id  = f"file.{hid_atom}"

    if force_embed or size < 256 * 1024:
        # Małe pliki -> CAS put (ale plik jest kopiowany, nie base64)
        hsh    = store.put(path, mime=mime)
        E_val  = make_blob_ref(hsh)
        storage= f"CAS embed ({os.path.getsize(path):,} B -> blob:{hsh})"
    else:
        # Duże pliki -> CAS put też (deduplikacja) ale E = ścieżka
        hsh    = store.put(path, mime=mime)
        E_val  = make_blob_ref(hsh)
        storage= f"CAS ref ({size:,} B -> blob:{hsh})"

    # Znajdź/utwórz bąbel
    if bubbles and bubble_name:
        bid = (bubbles.find_bubble_by_name(bubble_name)
               or bubbles.create_bubble(bubble_name))
    elif bubbles:
        cat   = mime.split("/")[0]
        bname = f"media.{cat}"
        bid   = (bubbles.find_bubble_by_name(bname)
                 or bubbles.create_bubble(bname))
        bubble_name = bname
    else:
        bid = None

    # Atom φ-space
    if runtime:
        try:
            existing = runtime.get_atom(atom_id)
            if existing:
                existing.T = T
                existing.S = mime
                existing.E = E_val
                try: existing.touch()
                except Exception: pass
            else:
                a = runtime.create_atom(atom_id, S=mime, E=E_val, T=T)
                if a:
                    try: a.touch()
                    except Exception: pass
        except Exception as e:
            return f"Błąd tworzenia atomu: {e}"

    # Import do bąbla
    if runtime and bid:
        try:
            bubbles.import_to_bubble(bid, atom_id, runtime)
        except Exception:
            pass

    return (f"OK: {filename} -> {bubble_name or 'brak bąbla'}\n"
            f"  atom:    {atom_id}\n"
            f"  MIME:    {mime}\n"
            f"  T:       {T:.1f}\n"
            f"  storage: {storage}")


# ─────────────────────────────────────────────────────────────────────────────
# Standalone test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, random

    print("=" * 60)
    print("  KarmazynOS CAS -- test")
    print("=" * 60)

    store = BlobStore(
        base_dir=os.path.join(tempfile.mkdtemp(), "blobs"))

    # Test put/get
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        data = bytes(random.randint(0, 255) for _ in range(1024))
        f.write(data); tmp1 = f.name
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(data); tmp2 = f.name   # identyczna zawartość!

    h1 = store.put(tmp1, "image/png")
    h2 = store.put(tmp2, "image/png")
    print(f"\n[1] Deduplication:")
    print(f"  plik1 hash: {h1}")
    print(f"  plik2 hash: {h2} (identyczna zawartość)")
    print(f"  Deduplicated: {h1 == h2}")

    print(f"\n[2] Blob ref w atomie E:")
    ref = make_blob_ref(h1)
    print(f"  E = '{ref}'  ({len(ref)} chars zamiast {len(data)*1.37:.0f} base64)")
    print(f"  is_blob_ref: {is_blob_ref(ref)}")
    print(f"  extract_hash: {extract_hash(ref)}")

    print(f"\n[3] Get bytes:")
    retrieved = store.get_bytes(h1)
    print(f"  Odczytano: {len(retrieved)} bajtów")
    print(f"  Zgodność:  {retrieved == data}")

    print(f"\n[4] Stats:")
    s = store.stats()
    print(f"  Blobs: {s['blobs']} (dedup: 2 pliki -> 1 blob)")
    print(f"  Rozmiar: {s['total_size']} B")

    print(f"\n[5] GC (bez phi -- usuwa wszystko):")
    d, k = store.gc()
    print(f"  Usunięto: {d}, zachowano: {k}")

    os.unlink(tmp1); os.unlink(tmp2)
    print("\n" + "=" * 60)
    print("  Wszystkie testy OK")
    print("=" * 60)