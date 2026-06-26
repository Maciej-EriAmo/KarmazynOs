#!/usr/bin/env python3
"""
karmazyn_shell_cmds.py — KarmazynOS Shell Commands v1.0.1
==========================================================
Maciej Mazur, Warsaw 2026

FIX v1.0.1:
  - atom_id hash w cmd_bimport: 10→12 znaków (zgodność z karmazyn_fm.py)
  - _touch_file_atom: ten sam hash length co FM (_atom_id)

WARSTWA 1 — Filesystem (prawdziwe operacje na plikach):
  CP   src dst         — kopiuj plik lub katalog
  MV   src dst         — przenieś / zmień nazwę
  RM   path [--force]  — usuń plik (nie atom!)
  RMF  path            — alias RM --force
  TOUCHF path          — utwórz pusty plik
  SETE atom_id value   — ustaw emanację atomu

WARSTWA 2 — Bubble management:
  MKB  name [opis]     — make bubble (utwórz bąbel)
  RMB  name            — remove bubble (usuń bąbel)
  LSB  [name]          — list bubble contents
  RENB stara nowa      — rename bubble

WARSTWA 3 — Binary blob storage w bąblach:
  BIMPORT path [bubble] [--embed]  — importuj plik do bąbla
  BEXPORT atom_id [dest]           — eksportuj plik z bąbla
  BINFO   atom_id                  — info o pliku w bąblu

Filozofia przechowywania binarnego:
  Mały plik (< EMBED_THRESHOLD = 256KB):
    E = "base64:<dane>"  ← plik osadzony bezpośrednio w bąblu
    Przenosimy się między maszynami — plik jedzie razem.

  Duży plik (>= 256KB):
    E = "/ścieżka/do/pliku"  ← referencja — bąbel jako manifest
    S = "image/png"          ← MIME type
    Bąbel indeksuje plik, nie przechowuje.

  Temperatura atomu pliku = log(rozmiar_w_bajtach) * 10
  → duże pliki są naturalnie chłodniejsze (mniej aktywne)
  → małe, często używane = gorące (w pamięci semantic)

Rejestracja w shell.py:
  from karmazyn_shell_cmds import register_all
  register_all(reg, RUNTIME, BUBBLES)
"""

import base64
import hashlib
import json
import mimetypes
import os
import shutil
import time
from typing import Any, Optional


# ── Stałe ─────────────────────────────────────────────────────────────────────

EMBED_THRESHOLD = 256 * 1024   # 256 KB — powyżej tego tylko referencja
MAX_EMBED_SIZE  = 4 * 1024 * 1024  # 4 MB — twardy limit embeddowania

# FIX v1.0.1: Stała długości hasha — jeden punkt prawdy dla całego systemu
# Musi być identyczna z karmazyn_fm._atom_id() (12 znaków)
ATOM_HASH_LEN = 12


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mime(path: str) -> str:
    """Zgadnij MIME type po rozszerzeniu."""
    mt, _ = mimetypes.guess_type(path)
    return mt or "application/octet-stream"


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _file_T(size_bytes: int) -> float:
    """
    Temperatura atomu plikowego — mniejsze pliki gorętsze.
    Małe (< 1KB) → T=70, Duże (> 10MB) → T=20.
    """
    import math
    if size_bytes <= 0: return 50.0
    kb   = size_bytes / 1024
    T    = max(20.0, 70.0 - math.log10(max(1, kb)) * 12)
    return round(T, 1)


def _atom_id_for_path(path: str) -> str:
    """
    Generuje atom_id dla ścieżki pliku.
    FIX v1.0.1: Jeden punkt prawdy — identyczny algorytm co karmazyn_fm._atom_id().
    Poprzednio: hexdigest()[:10] tutaj vs [:12] w FM — różne ID dla tego samego pliku.
    """
    import hashlib as _hl
    hid = _hl.sha1(os.path.abspath(path).encode()).hexdigest()[:ATOM_HASH_LEN]
    return f"file.{hid}"


def _resolve_bubble(bubbles: Any, name: str) -> Optional[str]:
    """Znajdź bubble_id po nazwie lub ID."""
    if bubbles is None: return None
    try:
        bid = bubbles.find_bubble_by_name(name)
        if bid: return bid
        # Może to bezpośredni ID?
        all_b = bubbles.list_bubbles()
        for b in all_b:
            if b.get("id") == name:
                return name
    except Exception:
        pass
    return None


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024: return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# ─────────────────────────────────────────────────────────────────────────────
# WARSTWA 1 — Filesystem
# ─────────────────────────────────────────────────────────────────────────────

def cmd_cp(args, runtime=None, bubbles=None, **_) -> str:
    """CP <src> <dst>   — kopiuj plik lub katalog (prawdziwy, nie atom)."""
    if len(args) < 2:
        return "Użycie: CP <źródło> <cel>"
    src = os.path.expanduser(args[0])
    dst = os.path.expanduser(args[1])
    if not os.path.exists(src):
        return f"Brak: {src}"
    try:
        if os.path.isdir(src):
            dst_path = os.path.join(dst, os.path.basename(src)) if os.path.isdir(dst) else dst
            try:
                shutil.copytree(src, dst_path, dirs_exist_ok=True)
            except TypeError:   # Python < 3.8
                if os.path.exists(dst_path): shutil.rmtree(dst_path)
                shutil.copytree(src, dst_path)
        else:
            shutil.copy2(src, dst)
        # Utwórz atom dla skopiowanego pliku
        if runtime and not os.path.isdir(src):
            _touch_file_atom(runtime, dst if not os.path.isdir(dst)
                             else os.path.join(dst, os.path.basename(src)))
        return f"OK: {src} → {dst}"
    except Exception as e:
        return f"Błąd CP: {e}"


def cmd_mv(args, runtime=None, bubbles=None, **_) -> str:
    """MV <src> <dst>   — przenieś plik lub zmień nazwę."""
    if len(args) < 2:
        return "Użycie: MV <źródło> <cel>"
    src = os.path.expanduser(args[0])
    dst = os.path.expanduser(args[1])
    if not os.path.exists(src):
        return f"Brak: {src}"
    try:
        shutil.move(src, dst)
        return f"OK: {src} → {dst}"
    except Exception as e:
        return f"Błąd MV: {e}"


def cmd_rm_file(args, runtime=None, bubbles=None, **_) -> str:
    """RMF <ścieżka>   — usuń plik (nie atom). RMF = RM File."""
    if not args:
        return "Użycie: RMF <ścieżka>"
    path = os.path.expanduser(args[0])
    force = "--force" in args or "-f" in args
    if not os.path.exists(path):
        return f"Brak: {path}"
    if not force:
        r = input(f"Usuń {path}? [T/N] ").strip().lower()
        if r not in ("t", "y", "tak", "yes"):
            return "Anulowano."
    try:
        if os.path.islink(path):
            os.unlink(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return f"Usunięto: {path}"
    except Exception as e:
        return f"Błąd RMF: {e}"


def cmd_touchf(args, runtime=None, bubbles=None, **_) -> str:
    """TOUCHF <ścieżka>   — utwórz pusty plik (nie atom φ-space)."""
    if not args:
        return "Użycie: TOUCHF <ścieżka>"
    path = os.path.expanduser(args[0])
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8"):
            os.utime(path, None)
        _touch_file_atom(runtime, path)
        return f"OK: {path}"
    except Exception as e:
        return f"Błąd TOUCHF: {e}"


def cmd_sete(args, runtime=None, **_) -> str:
    """SETE <atom_id> <emanacja>   — ustaw pole E (emanację) atomu."""
    if len(args) < 2:
        return "Użycie: SETE <atom_id> <nowa_emanacja>"
    if not runtime:
        return "Brak runtime."
    atom_id = args[0]
    new_e   = " ".join(args[1:])
    try:
        atom = runtime.get_atom(atom_id)
        if not atom:
            return f"Atom nie istnieje: {atom_id}"
        atom.E = new_e
        try: atom.touch()
        except Exception: pass
        return f"OK: {atom_id}.E = {new_e!r}"
    except Exception as e:
        return f"Błąd SETE: {e}"


def _touch_file_atom(runtime: Any, path: str) -> None:
    """Utwórz/zaktualizuj atom phi-space dla pliku."""
    if not runtime: return
    abs_path = os.path.abspath(path)
    # FIX v1.0.1: używamy _atom_id_for_path() — jeden punkt prawdy
    atom_id  = _atom_id_for_path(abs_path)
    try:
        size = os.path.getsize(path) if os.path.exists(path) else 0
        T    = _file_T(size)
        existing = runtime.get_atom(atom_id)
        if existing:
            existing.T = min(float(getattr(existing,"T_max",100)), T + 10)
            try: existing.touch()
            except Exception: pass
        else:
            name = os.path.basename(path)
            a = runtime.create_atom(atom_id, S=name, E=abs_path, T=T)
            if a:
                try: a.touch()
                except Exception: pass
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# WARSTWA 2 — Bubble management
# ─────────────────────────────────────────────────────────────────────────────

def cmd_mkb(args, runtime=None, bubbles=None, **_) -> str:
    """
    MKB <nazwa> [opis]   — utwórz nowy bąbel (Make Bubble).
    Bąbel to semantyczny kontener — może trzymać atomy, pliki, struktury.
    """
    if not args:
        return "Użycie: MKB <nazwa> [opis]"
    if not bubbles:
        return "Brak BubbleVFS."
    name = args[0]
    desc = " ".join(args[1:]) if len(args) > 1 else ""
    try:
        # Sprawdź czy już istnieje
        existing = _resolve_bubble(bubbles, name)
        if existing:
            return f"Bąbel już istnieje: {name} (id={existing})"
        bid = bubbles.create_bubble(name, description=desc)
        if not bid:
            # Spróbuj bez description
            bid = bubbles.create_bubble(name)
        # Atom reprezentujący bąbel w phi-space
        if runtime and bid:
            try:
                atom_id = f"bubble.{name}"
                a = runtime.create_atom(atom_id, S="bubble", E=str(bid), T=60.0)
                if a:
                    try: a.touch()
                    except Exception: pass
            except Exception:
                pass
        return f"OK: bąbel '{name}' utworzony (id={bid})"
    except Exception as e:
        return f"Błąd MKB: {e}"


def cmd_rmb(args, runtime=None, bubbles=None, **_) -> str:
    """RMB <nazwa>   — usuń bąbel (Remove Bubble)."""
    if not args:
        return "Użycie: RMB <nazwa>"
    if not bubbles:
        return "Brak BubbleVFS."
    name = args[0]
    bid  = _resolve_bubble(bubbles, name)
    if not bid:
        return f"Bąbel nie istnieje: {name}"
    try:
        r = input(f"Usuń bąbel '{name}'? Utracisz wszystkie dane. [T/N] ").strip().lower()
        if r not in ("t", "y", "tak", "yes"):
            return "Anulowano."
        # Usuń atom z phi-space
        if runtime:
            try:
                atom = runtime.get_atom(f"bubble.{name}")
                if atom:
                    runtime.matrix.delete(f"bubble.{name}")
            except Exception:
                pass
        # Usuń bąbel
        try:
            bubbles.delete_bubble(bid)
            return f"Usunięto: {name}"
        except AttributeError:
            # Fallback — usuń plik .soul bezpośrednio
            soul_path = getattr(bubbles, "_soul_path", None)
            if soul_path:
                path = os.path.join(soul_path, f"{bid}.soul")
                if os.path.exists(path):
                    os.remove(path)
                    return f"Usunięto: {name} ({path})"
            return f"BubbleVFS nie obsługuje delete_bubble() — usuń ręcznie {bid}.soul"
    except Exception as e:
        return f"Błąd RMB: {e}"


def cmd_lsb(args, runtime=None, bubbles=None, **_) -> str:
    """
    LSB [nazwa]   — listuj bąble lub zawartość konkretnego bąbla.
    Bez argumentu: pokaż wszystkie bąble.
    Z argumentem: pokaż zawartość bąbla.
    """
    if not bubbles:
        return "Brak BubbleVFS."

    if not args:
        # Lista wszystkich bąbli
        try:
            all_b = bubbles.list_bubbles()
        except Exception as e:
            return f"Błąd LSB: {e}"
        if not all_b:
            return "(brak bąbli)"
        lines = [f"  {'Nazwa':<25} {'ID':<16} {'Atomy':>6} {'Rozmiar':>8}"]
        lines.append("  " + "─" * 60)
        for b in sorted(all_b, key=lambda x: x.get("label","?")):
            name  = b.get("label", b.get("name", "?"))[:24]
            bid   = str(b.get("id", "?"))[:15]
            atoms = b.get("active_atoms", b.get("atoms", "?"))
            size  = b.get("size_bytes", "?")
            sz_s  = _fmt_size(size) if isinstance(size, int) else "?"
            lines.append(f"  {name:<25} {bid:<16} {atoms:>6} {sz_s:>8}")
        lines.append(f"  Razem: {len(all_b)} bąbli")
        return "\n".join(lines)

    # Zawartość konkretnego bąbla
    name = args[0]
    bid  = _resolve_bubble(bubbles, name)
    if not bid:
        return f"Bąbel nie istnieje: {name}"
    try:
        atoms = bubbles.get_active_atoms(bid)
    except Exception as e:
        return f"Błąd odczytu {name}: {e}"
    if not atoms:
        return f"Bąbel '{name}' jest pusty."

    lines = [f"  Bąbel: {name} (id={bid})",
             f"  {'ID':<30} {'S':<15} {'T':>6} {'Typ'}"]
    lines.append("  " + "─" * 65)
    for a in atoms:
        aid   = (a.get("id") if isinstance(a, dict) else getattr(a,"id","?"))
        S     = (a.get("S")  if isinstance(a, dict) else getattr(a,"S",""))[:14]
        T     = (a.get("T")  if isinstance(a, dict) else getattr(a,"T",0))
        E     = (a.get("E")  if isinstance(a, dict) else getattr(a,"E",""))
        # Wykryj typ zawartości
        if isinstance(E, str) and E.startswith("base64:"):
            kind = "embedded"
        elif isinstance(E, str) and os.path.exists(E):
            kind = _mime(E).split("/")[0]
        elif isinstance(E, str) and E:
            kind = "ref"
        else:
            kind = "atom"
        lines.append(f"  {str(aid):<30} {S:<15} {float(T):>6.1f} {kind}")
    lines.append(f"  Razem: {len(atoms)} wpisów")
    return "\n".join(lines)


def cmd_renb(args, runtime=None, bubbles=None, **_) -> str:
    """RENB <stara_nazwa> <nowa_nazwa>   — zmień nazwę bąbla."""
    if len(args) < 2:
        return "Użycie: RENB <stara_nazwa> <nowa_nazwa>"
    if not bubbles:
        return "Brak BubbleVFS."
    old_name, new_name = args[0], args[1]
    bid = _resolve_bubble(bubbles, old_name)
    if not bid:
        return f"Bąbel nie istnieje: {old_name}"
    try:
        bubbles.rename_bubble(bid, new_name)
        # Zaktualizuj atom φ-space
        if runtime:
            try:
                old_atom = runtime.get_atom(f"bubble.{old_name}")
                if old_atom:
                    old_atom.S = new_name
                    try: old_atom.touch()
                    except Exception: pass
            except Exception: pass
        return f"OK: '{old_name}' → '{new_name}'"
    except AttributeError:
        return "BubbleVFS nie obsługuje rename_bubble() — zaktualizuj BubbleVFS."
    except Exception as e:
        return f"Błąd RENB: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# WARSTWA 3 — Binary blob storage
# ─────────────────────────────────────────────────────────────────────────────

def cmd_bimport(args, runtime=None, bubbles=None, **_) -> str:
    """
    BIMPORT <plik> [bąbel] [--embed]
    Importuj plik do bąbla KarmazynOS.

    Małe pliki (< 256KB):   osadzone bezpośrednio (base64 w E)
    Duże pliki (>= 256KB):  referencja do ścieżki absolutnej
    --embed:                 wymuś osadzenie (max 4MB)

    Pole E atomu:
      base64:<dane>   → osadzony
      /ścieżka/...   → referencja
    """
    if not args:
        return "Użycie: BIMPORT <plik> [bąbel] [--embed]"
    if not bubbles:
        return "Brak BubbleVFS."

    path       = os.path.expanduser(args[0])
    force_embed= "--embed" in args
    bubble_name= next((a for a in args[1:]
                       if not a.startswith("--")), None)

    if not os.path.isfile(path):
        return f"Brak pliku: {path}"

    size      = os.path.getsize(path)
    mime      = _mime(path)
    sha256    = _sha256(path)
    abs_path  = os.path.abspath(path)
    filename  = os.path.basename(path)
    T         = _file_T(size)

    # Znajdź lub utwórz bąbel
    if bubble_name:
        bid = _resolve_bubble(bubbles, bubble_name)
        if not bid:
            bid = bubbles.create_bubble(bubble_name)
    else:
        # Domyślny bąbel według MIME
        cat        = mime.split("/")[0]   # image, audio, video, text, ...
        bname      = f"media.{cat}"
        bid        = _resolve_bubble(bubbles, bname) or bubbles.create_bubble(bname)
        bubble_name= bname

    if not bid:
        return "Nie można utworzyć bąbla docelowego."

    # Zdecyduj: embed czy referencja
    should_embed = force_embed or size < EMBED_THRESHOLD
    if force_embed and size > MAX_EMBED_SIZE:
        return (f"Plik zbyt duży do osadzenia ({_fmt_size(size)} > {_fmt_size(MAX_EMBED_SIZE)}). "
                f"Użyj referencji (bez --embed).")

    # FIX v1.0.1: używamy _atom_id_for_path() — identyczny hash co FM
    atom_id = _atom_id_for_path(abs_path)

    if should_embed:
        with open(path, "rb") as f:
            raw    = f.read()
        encoded = "base64:" + base64.b64encode(raw).decode("ascii")
        E_field = encoded
        storage = f"osadzony ({_fmt_size(size)})"
    else:
        E_field = abs_path
        storage = f"referencja ({_fmt_size(size)})"

    meta = json.dumps({
        "filename": filename,
        "mime":     mime,
        "size":     size,
        "sha256":   sha256,
        "added":    time.strftime("%Y-%m-%d %H:%M"),
        "embedded": should_embed,
    })

    # Zapisz do bąbla przez atom φ-space
    try:
        # Utwórz atom w runtime
        if runtime:
            a = runtime.get_atom(atom_id)
            if a:
                a.T = T; a.S = mime; a.E = E_field
                try: a.touch()
                except Exception: pass
            else:
                a = runtime.create_atom(atom_id, S=mime, E=E_field, T=T)
                if a:
                    try: a.touch()
                    except Exception: pass

        # Importuj atom do bąbla
        if runtime:
            try:
                bubbles.import_to_bubble(bid, atom_id, runtime)
            except Exception:
                pass

        return (f"OK: {filename} → bąbel '{bubble_name}'\n"
                f"  atom_id: {atom_id}\n"
                f"  MIME:    {mime}\n"
                f"  T:       {T:.1f}\n"
                f"  Tryb:    {storage}\n"
                f"  SHA256:  {sha256}")
    except Exception as e:
        return f"Błąd BIMPORT: {e}"


def cmd_bexport(args, runtime=None, bubbles=None, **_) -> str:
    """
    BEXPORT <atom_id> [ścieżka_docelowa]
    Eksportuj plik z bąbla.

    Osadzony: dekoduje base64 → plik
    Referencja: kopiuje z oryginalnej lokalizacji
    """
    if not args:
        return "Użycie: BEXPORT <atom_id> [ścieżka]"
    if not runtime:
        return "Brak runtime."

    atom_id  = args[0]
    dest     = os.path.expanduser(args[1]) if len(args) > 1 else "."
    atom     = runtime.get_atom(atom_id)
    if not atom:
        return f"Atom nie istnieje: {atom_id}"

    E    = str(getattr(atom, "E", ""))
    S    = str(getattr(atom, "S", ""))

    if E.startswith("base64:"):
        # Dekoduj
        raw      = base64.b64decode(E[7:])
        # Zgadnij rozszerzenie z MIME
        ext      = mimetypes.guess_extension(S) or ".bin"
        filename = f"{atom_id}{ext}".replace("file.", "").replace("/","_")
        out_path = os.path.join(dest, filename) if os.path.isdir(dest) else dest
        with open(out_path, "wb") as f:
            f.write(raw)
        return (f"OK: {atom_id} → {out_path}\n"
                f"  Rozmiar: {_fmt_size(len(raw))}")

    elif E and os.path.exists(E):
        # Kopiuj referencję
        filename = os.path.basename(E)
        out_path = os.path.join(dest, filename) if os.path.isdir(dest) else dest
        shutil.copy2(E, out_path)
        return f"OK: {E} → {out_path}"

    elif E:
        return f"Plik referencji nie istnieje: {E}"
    else:
        return f"Atom '{atom_id}' nie zawiera danych plikowych (E jest pusty)."


def cmd_binfo(args, runtime=None, **_) -> str:
    """BINFO <atom_id>   — informacje o pliku w bąblu."""
    if not args:
        return "Użycie: BINFO <atom_id>"
    if not runtime:
        return "Brak runtime."
    atom = runtime.get_atom(args[0])
    if not atom:
        return f"Atom nie istnieje: {args[0]}"
    E = str(getattr(atom, "E", ""))
    S = str(getattr(atom, "S", ""))
    T = float(getattr(atom, "T", 0))

    lines = [f"  Atom:  {args[0]}",
             f"  MIME:  {S}",
             f"  T:     {T:.1f}"]
    if E.startswith("base64:"):
        size = len(base64.b64decode(E[7:]))
        lines.append(f"  Tryb:  osadzony ({_fmt_size(size)})")
    elif E:
        exists = os.path.exists(E)
        size   = os.path.getsize(E) if exists else 0
        lines.append(f"  Tryb:  referencja → {E}")
        lines.append(f"  Plik:  {'istnieje' if exists else 'BRAK'}"
                     + (f" ({_fmt_size(size)})" if exists else ""))
    else:
        lines.append("  Tryb:  brak danych plikowych")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Rejestracja w shell.py
# ─────────────────────────────────────────────────────────────────────────────

def register_all(reg_fn, runtime=None, bubbles=None) -> None:
    """
    Zarejestruj wszystkie komendy w shellu KarmazynOS.

    Użycie w shell.py (blok programów systemowych):
        from karmazyn_shell_cmds import register_all
        register_all(reg, RUNTIME, BUBBLES)
    """
    def _wrap(fn):
        return lambda args: fn(args, runtime=runtime, bubbles=bubbles)

    # ── Filesystem ─────────────────────────────────────────────────────────────
    reg_fn("CP",     _wrap(cmd_cp),       "Kopiuj plik/katalog",         category="files")
    reg_fn("MV",     _wrap(cmd_mv),       "Przenieś/zmień nazwę",        category="files")
    reg_fn("RMF",    _wrap(cmd_rm_file),  "Usuń plik (nie atom φ)",      category="files")
    reg_fn("TOUCHF", _wrap(cmd_touchf),   "Utwórz pusty plik",           category="files")
    reg_fn("SETE",   _wrap(cmd_sete),     "Ustaw emanację atomu",        category="atoms")

    # ── Bubble management ─────────────────────────────────────────────────────
    reg_fn("MKB",    _wrap(cmd_mkb),      "Make Bubble (utwórz bąbel)",  category="bubbles")
    reg_fn("RMB",    _wrap(cmd_rmb),      "Remove Bubble",               category="bubbles")
    reg_fn("LSB",    _wrap(cmd_lsb),      "List Bubbles/zawartość",      category="bubbles")
    reg_fn("RENB",   _wrap(cmd_renb),     "Rename Bubble",               category="bubbles")

    # ── Binary storage ────────────────────────────────────────────────────────
    reg_fn("BIMPORT",_wrap(cmd_bimport),  "Import pliku do bąbla",       category="bubbles")
    reg_fn("BEXPORT",_wrap(cmd_bexport),  "Export pliku z bąbla",        category="bubbles")
    reg_fn("BINFO",  _wrap(cmd_binfo),    "Info o pliku w bąblu",        category="bubbles")


# ─────────────────────────────────────────────────────────────────────────────
# Test standalone
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("KarmazynOS Shell Commands v1.0.1")
    print("Zarejestrowane komendy:")
    cmds = [
        ("CP",      "Kopiuj plik/katalog"),
        ("MV",      "Przenieś/zmień nazwę"),
        ("RMF",     "Usuń plik"),
        ("TOUCHF",  "Utwórz pusty plik"),
        ("SETE",    "Ustaw emanację atomu"),
        ("MKB",     "Make Bubble"),
        ("RMB",     "Remove Bubble"),
        ("LSB",     "List Bubbles"),
        ("RENB",    "Rename Bubble"),
        ("BIMPORT", "Import pliku do bąbla (embed/ref)"),
        ("BEXPORT", "Export pliku z bąbla"),
        ("BINFO",   "Info o pliku"),
    ]
    for cmd, desc in cmds:
        print(f"  {cmd:10} {desc}")

    # Mini test binary storage
    print("\nTest BIMPORT (symulacja):")
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        tmp_path = f.name

    result = cmd_bimport(
        [tmp_path, "test.media"],
        runtime=None,
        bubbles=None,
    )
    print(f"  {result}")
    os.unlink(tmp_path)
    print("OK")