#!/usr/bin/env python3
"""
bubble_commands.py — Komendy Babli dla shell.py v2.1 (Fix #7)
=============================================================
Przebudowany na model fundamentalny karmazyn_core.py.
Uzywa runtime._bubbles bezposrednio — brak zaleznosci od bedit.BubbleRuntime.

Fix #7 (2026-05-27):
  - Kompatybilność z różnymi runtime'ami (SanctuaryRuntime vs KarmazynOS vs PhiSpace).
  - _bubble_new używa create_atom/write z wykrywaniem sygnatury.

Komendy dostepne w shell:
  BUBBLE LS                    — lista Babli ze stanem Psi/Theta
  BUBBLE NEW <nazwa> [LIB]     — tworz Babl (WORKSPACE lub LIBRARY)
  BUBBLE STATUS <nazwa>        — szczegoly Babla
  BUBBLE RESONATE <a> <b>      — sprawdz rezonans miedzy dwoma Bablami
  BUBBLE TICK <nazwa>          — wykonaj krok Psi (update_psi)
  BUBBLE DECAY <nazwa>         — oznacz Babl do zaniku
  BUBBLE SAVE                  — zapisz wszystkie Bable do .soul
  BUBBLE COPY <nazwa>         — kopiuj do schowka
  BUBBLE PASTE [nazwa]        — wklej ze schowka
  BUBBLE CLIPBOARD            — podglad schowka
  EDIT <nazwa>                 — otworz/stworz Babl i ustaw kontekst CTX
  IMPORT <tresc>               — dodaj tekst do aktywnego Babla
  VIEW                         — pokaz zawartosc aktywnego Babla
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np

from karmazyn_core import BubbleMode


# ─── Kontekst sesji ──────────────────────────────────────────────────────────

@dataclass
class BubbleContext:
    """Biezacy aktywny Babl w sesji shella."""
    current_label:       Optional[str] = None
    current_bubble_id:   Optional[str] = None   # alias dla kompatybilnosci
    current_bubble_name: Optional[str] = None   # alias dla kompatybilnosci
    current_prism:       str = 'CORE'


CTX = BubbleContext()

# Referencje ustawiane przez shell przy starcie
RUNTIME = None   # SanctuaryRuntime


def init(runtime):
    """Inicjalizuje referencje — wolane z shell.py po imporcie."""
    global RUNTIME
    RUNTIME = runtime


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _require_runtime() -> Optional[str]:
    if RUNTIME is None:
        return "Brak runtime. Wywolaj init(runtime) przed uzyciem komend."
    return None

def _require_ctx() -> Optional[str]:
    err = _require_runtime()
    if err:
        return err
    if CTX.current_label is None:
        return "Brak aktywnego Babla. Uzyj: EDIT <nazwa>"
    if CTX.current_label not in RUNTIME._bubbles:
        return f"Babl '{CTX.current_label}' nie istnieje w runtime."
    return None

def _bubble_summary(label: str) -> str:
    """Jednolinijkowe podsumowanie Babla."""
    b = RUNTIME._bubbles.get(label)
    if b is None:
        return f"{label}: BRAK"
    mode  = "WS" if b.mode == BubbleMode.WORKSPACE else "LIB"
    psi   = f"{b.psi:.4f}" if not b._psi_stale else "?"
    coll  = " [ROZPAD]" if (not b._psi_stale and b.is_collapsed()) else ""
    return f"{label} [{mode}] psi={psi} theta={b.theta:.3f} dist={b.base_distance:.3f}{coll}"


# ─── KOMENDY BUBBLE ───────────────────────────────────────────────────────────

def cmd_bubble(args) -> str:
    """
    Router dla komend BUBBLE <subkomenda> [args].
    Dispatcher dla shell.py.
    """
    if not args:
        return _help_bubble()

    sub = args[0].upper()
    rest = args[1:]

    dispatch = {
        "LS":        _bubble_ls,
        "NEW":       _bubble_new,
        "STATUS":    _bubble_status,
        "RESONATE":  _bubble_resonate,
        "TICK":      _bubble_tick,
        "DECAY":     _bubble_decay,
        "SAVE":      _bubble_save,
        "COPY":      cmd_copy,
        "PASTE":     cmd_paste,
        "CLIPBOARD": cmd_clipboard,
    }

    handler = dispatch.get(sub)
    if handler is None:
        return f"Nieznana subkomenda BUBBLE: {sub}\n{_help_bubble()}"
    return handler(rest)


def _help_bubble() -> str:
    return (
        "BUBBLE LS                   — lista Babli\n"
        "BUBBLE NEW <nazwa> [LIB]    — nowy Babl (WORKSPACE lub LIBRARY)\n"
        "BUBBLE STATUS <nazwa>       — szczegoly\n"
        "BUBBLE RESONATE <a> <b>     — rezonans miedzy Bablami\n"
        "BUBBLE TICK <nazwa> [n]     — n krokow Psi\n"
        "BUBBLE DECAY <nazwa>        — oznacz do zaniku\n"
        "BUBBLE SAVE                 — zapisz do .soul"
    )


def _bubble_ls(args) -> str:
    err = _require_runtime()
    if err:
        return err

    bubbles = RUNTIME._bubbles
    if not bubbles:
        return "Brak Babli. Uzyj: BUBBLE NEW <nazwa>"

    lines = ["Bable w systemie:"]
    lines.append(f"  {'Nazwa':<20} {'Tryb':<5} {'Psi':>8} {'Theta':>7} {'Dist':>7}  Stan")
    lines.append("  " + "-" * 60)

    for label in sorted(bubbles):
        b = bubbles[label]
        mode  = "WS" if b.mode == BubbleMode.WORKSPACE else "LIB"
        psi   = f"{b.psi:.4f}" if not b._psi_stale else "     ?"
        theta = f"{b.theta:.4f}"
        dist  = f"{b.base_distance:.4f}"
        if b._psi_stale:
            stan = "NIEZAINICJOWANY"
        elif b.is_collapsed():
            stan = "ROZPAD"
        else:
            margin = b.theta - b.psi
            stan   = f"OK (margines={margin:.4f})"
        lines.append(f"  {label:<20} {mode:<5} {psi:>8} {theta:>7} {dist:>7}  {stan}")

    lines.append(f"\nLacznie: {len(bubbles)} Babli")
    return "\n".join(lines)


def _bubble_new(args) -> str:
    """Tworzy nowy Babl. Fix #7: kompatybilne tworzenie atomu."""
    err = _require_runtime()
    if err:
        return err

    if not args:
        return "Uzycie: BUBBLE NEW <nazwa> [LIB]"

    label = args[0]
    mode  = BubbleMode.LIBRARY if len(args) > 1 and args[1].upper() == "LIB" else BubbleMode.WORKSPACE

    if label in RUNTIME._bubbles:
        return f"Babl '{label}' juz istnieje."

    # Atom z ta sama etykieta co Babl — consolidate uzyje jej jako klucza
    if not RUNTIME.has_atom(label):
        # ── Fix #7: Kompatybilność z różnymi runtime'ami ─────────────────
        if hasattr(RUNTIME, 'create_atom'):
            # SanctuaryRuntime / PhiSpace
            try:
                RUNTIME.create_atom(label, S=label, E="bubble_init", T=50.0)
            except TypeError:
                try:
                    RUNTIME.create_atom(label, label, "bubble_init", 50.0)
                except Exception:
                    pass
        elif hasattr(RUNTIME, 'write'):
            # KarmazynOS lub inne API z write()
            import inspect
            try:
                sig = inspect.signature(RUNTIME.write)
                if len(sig.parameters) >= 4:
                    # SanctuaryRuntime.write(name, S, E, T)
                    RUNTIME.write(label, label, "bubble_init", 1.0)
                else:
                    # KarmazynOS.write(content, auto_consolidate=0)
                    RUNTIME.write(label)
            except Exception:
                pass
        # ─────────────────────────────────────────────────────────────────

    RUNTIME.consolidate(label)

    b = RUNTIME._bubbles.get(label)
    if b is None:
        return f"Blad: nie udalo sie stworzyc Babla '{label}'."

    b.mode = mode
    mode_str = "Workspace" if mode == BubbleMode.WORKSPACE else "Biblioteka"
    return f"Stworzono Babl '{label}' [{mode_str}]"


def _bubble_status(args) -> str:
    err = _require_runtime()
    if err:
        return err

    if not args:
        return "Uzycie: BUBBLE STATUS <nazwa>"

    label = args[0]
    b = RUNTIME._bubbles.get(label)
    if b is None:
        return f"Babl '{label}' nie istnieje."

    mode_str = "Workspace" if b.mode == BubbleMode.WORKSPACE else "Biblioteka"

    # Pobierz rezonujace Atomy
    atoms    = RUNTIME.list_atoms()
    tau      = 0.6
    rez_ids  = []
    for a in atoms:
        try:
            if b.resonates_with(a, tau):
                rez_ids.append(a.id)
        except Exception:
            pass

    psi_str = f"{b.psi:.6f}" if not b._psi_stale else "niezainicjowany (wywolaj BUBBLE TICK)"
    collapsed_str = "TAK" if (not b._psi_stale and b.is_collapsed()) else "NIE"

    lines = [
        f"Babl: {label}",
        f"  Tryb:          {mode_str}",
        f"  Psi:           {psi_str}",
        f"  Theta (prog):  {b.theta:.6f}",
        f"  Dist(phi1,phi2): {b.base_distance:.6f}",
        f"  Rozpad:        {collapsed_str}",
        f"  Czas zycia:    {b.time_lived:.0f} taktow",
        f"  Atomy (tau>={tau}): {', '.join(rez_ids) if rez_ids else 'brak'}",
    ]
    return "\n".join(lines)


def _bubble_resonate(args) -> str:
    err = _require_runtime()
    if err:
        return err

    if len(args) < 2:
        return "Uzycie: BUBBLE RESONATE <babl_a> <babl_b>"

    label_a, label_b = args[0], args[1]
    ba = RUNTIME._bubbles.get(label_a)
    bb = RUNTIME._bubbles.get(label_b)

    if ba is None:
        return f"Babl '{label_a}' nie istnieje."
    if bb is None:
        return f"Babl '{label_b}' nie istnieje."

    # Rezonans: kosinusowe podobienstwo phi1 obu Babli
    from karmazyn_core import PhiSpace
    from core.phi_math import PhiPhysics

    space   = PhiPhysics.get_space()
    phi_a   = ba.phi1.signature
    phi_b   = bb.phi1.signature
    cos_sim = float(np.dot(phi_a, phi_b))
    dist    = space.metric(phi_a, phi_b)

    tau_levels = [0.9, 0.8, 0.7, 0.6, 0.5]
    rezonuje_przy = [t for t in tau_levels if cos_sim >= t]

    lines = [
        f"Rezonans '{label_a}' <-> '{label_b}':",
        f"  Podobienstwo kosinusowe: {cos_sim:.6f}",
        f"  Metryka phi:             {dist:.6f}",
        f"  Rezonuje przy tau:       {rezonuje_przy if rezonuje_przy else 'brak (cos < 0.5)'}",
    ]
    return "\n".join(lines)


def _bubble_tick(args) -> str:
    err = _require_runtime()
    if err:
        return err

    if not args:
        return "Uzycie: BUBBLE TICK <nazwa> [n_krokow]"

    label  = args[0]
    n      = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
    b      = RUNTIME._bubbles.get(label)

    if b is None:
        return f"Babl '{label}' nie istnieje."

    # Pobierz aktywne Atomy ktore rezonuja (tau=0.5)
    atoms       = RUNTIME.list_atoms()
    active_rez  = [a for a in atoms if b.resonates_with(a, tau=0.5)]

    psi_before = b.psi
    for _ in range(n):
        b.update_psi(active_rez)

    collapsed = b.is_collapsed()
    return (
        f"TICK Babla '{label}' x{n}: "
        f"psi {psi_before:.4f} -> {b.psi:.4f} / theta={b.theta:.4f}"
        + (" [ROZPAD!]" if collapsed else "")
    )


def _bubble_decay(args) -> str:
    err = _require_runtime()
    if err:
        return err

    if not args:
        return "Uzycie: BUBBLE DECAY <nazwa>"

    label = args[0]
    ok    = RUNTIME.mark_bubble_for_decay(label, rate=0.05)
    if ok:
        return f"Babl '{label}' oznaczony do zaniku (rate=0.05)."
    return f"Nie mozna oznaczyc '{label}' (nie istnieje)."


def _bubble_save(args) -> str:
    err = _require_runtime()
    if err:
        return err

    # Zapisz stan do .soul JSONL (prosta serializacja)
    import json
    import os

    save_dir = ".bubbles/soul_data"
    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, "session.soul")

    records = []
    for label, b in RUNTIME._bubbles.items():
        records.append({
            "type":          "bubble",
            "id":            label,
            "phi":           b.phi1.signature.tolist(),
            "phi2":          b.phi2.tolist(),
            "mode":          b.mode.value,
            "theta":         b.theta,
            "psi":           b.psi if not b._psi_stale else 0.0,
            "base_distance": b.base_distance,
            "time_lived":    b.time_lived,
        })

    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return f"Zapisano {len(records)} Babli → {path}"


# ─── KOMENDY EDIT / IMPORT / VIEW (kontekst CTX) ─────────────────────────────

def cmd_edit(args) -> str:
    """
    EDIT <nazwa>     — otworz lub stworz Babl, ustaw jako aktywny CTX
    EDIT             — pokaz aktywny Babl
    """
    err = _require_runtime()
    if err:
        return err

    if not args:
        if CTX.current_label is None:
            return "Brak aktywnego Babla. Uzyj: EDIT <nazwa>"
        return _bubble_summary(CTX.current_label)

    label = args[0]

    if label not in RUNTIME._bubbles:
        # Tworzymy nowy Babl
        _bubble_new([label])

    CTX.current_label       = label
    CTX.current_bubble_id   = label
    CTX.current_bubble_name = label
    b = RUNTIME._bubbles.get(label)
    if b is None:
        return f"Blad: nie mozna otworzyc Babla '{label}'."

    mode_str = "Workspace" if b.mode == BubbleMode.WORKSPACE else "Biblioteka"
    return (
        f"Otworto Babl: {label} [{mode_str}]\n"
        f"  Uzyj: IMPORT <tekst>  |  VIEW  |  BUBBLE TICK {label}"
    )


def cmd_import(args) -> str:
    """
    IMPORT <tresc>  — dodaj tekst do aktywnego Babla jako Atom.
    Atom jest tworzony i probuje wejsc przez rezonans.
    """
    err = _require_ctx()
    if err:
        return err

    if not args:
        return "Uzycie: IMPORT <tresc>"

    text   = " ".join(args)
    label  = CTX.current_label
    bubble = RUNTIME._bubbles[label]

    # Koszmar żywicy podczas misji (zachowana kompatybilnosc)
    if RUNTIME.current_mission:
        if RUNTIME.resources.get("zywica", 0) <= 0:
            return "Brak Zywicy!"
        RUNTIME.resources["zywica"] -= 1

    # Tworz Atom z teksci
    import hashlib
    atom_id = f"imp_{hashlib.md5(text.encode()).hexdigest()[:8]}"
    atom    = RUNTIME.create_atom(atom_id, text[:64], label, T=80.0)

    # Proba wejscia przez rezonans
    result  = RUNTIME.consolidate_to_bubble(atom, bubble)
    zywica  = RUNTIME.resources.get("zywica", "nieskonczona") if RUNTIME.current_mission else "n/d"

    if result.get("status") == "absorbed":
        return f"Zaabsorbowano '{text[:40]}...' → Babl '{label}' (Zywica: {zywica})"

    coh    = result.get("coherence", 0)
    reason = result.get("reason", "phase_mismatch")
    return (
        f"Odrzucono '{text[:40]}...' — nie rezonuje z Bablem '{label}'\n"
        f"  Koherencja: {coh:.4f}  Powod: {reason}"
    )


def cmd_view(args) -> str:
    """VIEW — pokaz stan aktywnego Babla."""
    err = _require_ctx()
    if err:
        return err

    label  = CTX.current_label
    b      = RUNTIME._bubbles[label]
    atoms  = RUNTIME.list_atoms()
    tau    = 0.5
    rez    = [a for a in atoms if b.resonates_with(a, tau)]

    lines = [
        f"Babl: {label}",
        f"  Tryb:    {'Workspace' if b.mode == BubbleMode.WORKSPACE else 'Biblioteka'}",
        f"  Psi/Theta: {b.psi:.4f} / {b.theta:.4f}",
        f"  Rezonujace Atomy (tau>={tau}): {len(rez)}",
    ]
    for a in rez[:5]:
        lines.append(f"    [{a.state}] {a.id}: {a.S[:30]}")
    if len(rez) > 5:
        lines.append(f"    ... i {len(rez)-5} wiecej")

    return "\n".join(lines)


# ─── STUBY KOMPATYBILNOSCI (shell.py v3.0) ───────────────────────────────────

def cmd_gallery(args) -> str:
    """GALLERY — pokaz Bable i ich stan semantyczny."""
    err = _require_runtime()
    if err:
        return err

    if CTX.current_label:
        return cmd_view([])

    # Bez aktywnego Babla — lista wszystkich
    return _bubble_ls([])


def cmd_export(args) -> str:
    """EXPORT — zapisz Bable do .soul JSONL."""
    return _bubble_save(args)