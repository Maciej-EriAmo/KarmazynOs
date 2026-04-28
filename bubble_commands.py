# ============================================================
# bubble_commands.py — Komendy bąbli dla shell.py
# ============================================================
# Wycięte z shell.py, zależne od:
#     bedit.BubbleRuntime (BUBBLES)
#     runtime.SanctuaryRuntime (RUNTIME)
#     karmazyn_ui.theme, gfx (theme, gfx)
# ============================================================

import os
import time
from dataclasses import dataclass
from typing import Optional

from media_types import MediaType


# ═══════════════════════════════════════════
# KONTEKST BĄBLA
# ═══════════════════════════════════════════

@dataclass
class BubbleContext:
    """Bezpieczny stan sesji bąbla (importowany przez shell)"""
    current_bubble_id: Optional[str] = None
    current_bubble_name: Optional[str] = None
    current_prism: str = 'CORE'

CTX = BubbleContext()

# Referencje ustawiane przez shell przy starcie
BUBBLES = None  # BubbleRuntime
RUNTIME = None  # SanctuaryRuntime


def init(bubbles, runtime):
    """Inicjalizuje referencje — wołane z shell.py po imporcie"""
    global BUBBLES, RUNTIME
    BUBBLES = bubbles
    RUNTIME = runtime


# ═══════════════════════════════════════════
# KOMENDY
# ═══════════════════════════════════════════

def cmd_import(args) -> str:
    """
    IMPORT <ścieżka> [ALL] — importuje plik lub katalog do bąbla.
    """
    if not CTX.current_bubble_id:
        return "❌ Najpierw otwórz bąbel: EDIT <nazwa>"
    if not args:
        return "Użycie: IMPORT <ścieżka> [ALL]"

    path = args[0]
    recursive = len(args) > 1 and args[1].upper() == "ALL"

    if not os.path.exists(path):
        return f"❌ Nie znaleziono: {path}"

    # Koszt żywicy podczas misji
    if RUNTIME and RUNTIME.current_mission:
        koszt = 2 if os.path.isdir(path) else 1
        if RUNTIME.resources.get("żywica", 0) < koszt:
            return f"❌ Brak Żywicy! Import kosztuje {koszt}."
        RUNTIME.resources["żywica"] -= koszt

    if os.path.isfile(path):
        atom_id = BUBBLES.add_file(CTX.current_bubble_id, path)
        if atom_id:
            atom_type = MediaType.from_filename(path)
            żywica = RUNTIME.resources.get("żywica", "∞") if RUNTIME else "∞"
            return f"✅ [{atom_type}] {os.path.basename(path)} → {atom_id} (Żywica: {żywica})"
        return "❌ Błąd importu"

    elif os.path.isdir(path):
        added = BUBBLES.add_directory(CTX.current_bubble_id, path, recursive)
        if added:
            żywica = RUNTIME.resources.get("żywica", "∞") if RUNTIME else "∞"
            return f"✅ Zaimportowano {len(added)} plików (Żywica: {żywica})"
        return "❌ Brak plików"

    return "❌ Nieobsługiwana ścieżka"


def cmd_gallery(args) -> str:
    """GALLERY — pokazuje multimedia w otwartym bąblu."""
    if not CTX.current_bubble_id:
        return "❌ Najpierw otwórz bąbel"

    gallery = BUBBLES.get_media_gallery(CTX.current_bubble_id)
    bubble = BUBBLES.get_bubble(CTX.current_bubble_id)

    if bubble:
        stats = bubble.manifest.get('media_stats', {})
        stats_line = " | ".join(f"{k}:{v}" for k, v in stats.items() if v > 0)
        header = f"🖼️ GALERIA: {CTX.current_bubble_name}\n{'='*50}\n📊 {stats_line}\n{'='*50}"
    else:
        header = f"🖼️ GALERIA: {CTX.current_bubble_name}"

    return f"{header}\n{gallery}\n{'='*50}" if gallery else f"{header}\n(brak mediów)"


def cmd_export(args) -> str:
    """EXPORT [katalog] — eksportuje multimedia z bąbla do plików."""
    if not CTX.current_bubble_id:
        return "❌ Najpierw otwórz bąbel"

    output_dir = args[0] if args else f"./export_{CTX.current_bubble_name}"
    files = BUBBLES.export_files(CTX.current_bubble_id, output_dir)

    return f"📦 Wyeksportowano {len(files)} plików do: {output_dir}" if files else "Brak plików do eksportu"


def cmd_edit(args) -> str:
    """
    EDIT — Edytor bąbli.
    EDIT                    — interaktywny edytor
    EDIT <nazwa>            — stwórz/otwórz bąbel
    EDIT append <tekst>     — dodaj tekst
    EDIT view               — pokaż zawartość
    EDIT list               — lista bąbli
    EDIT search <słowo>     — szukaj
    EDIT refresh            — odśwież energię
    EDIT save               — zapisz
    EDIT snapshot           — snapshot runtime
    """
    if not args:
        from bedit import BubbleEditor
        try:
            editor = BubbleEditor()
            editor.cmdloop()
        except Exception as e:
            return f"[BŁĄD] Edytor: {e}"
        return ""

    sub = args[0].lower()

    if sub == "list":
        bubbles = BUBBLES.list_bubbles()
        if not bubbles:
            return "Brak bąbli."
        lines = ["🫧 BĄBLE:"]
        for b in bubbles:
            stats = b.get('media_stats', {})
            media = ""
            if stats.get('image'): media += f" 🖼{stats['image']}"
            if stats.get('audio'): media += f" 🎵{stats['audio']}"
            if stats.get('document'): media += f" 📄{stats['document']}"
            lines.append(f"  {b['name']} ({b['active_atoms']} atomów{media}) [{b['type']}]")
        return "\n".join(lines)

    elif sub == "search":
        if len(args) < 2: return "EDIT search <słowo>"
        results = BUBBLES.search(" ".join(args[1:]))
        return "\n".join(f"🫧 {b['name']} ({b['active_atoms']} atomów)" for b in results) if results else "Brak wyników"

    elif sub == "append":
        if not CTX.current_bubble_id: return "❌ Najpierw otwórz bąbel"
        if len(args) < 2: return "EDIT append <tekst>"
        if RUNTIME and RUNTIME.current_mission:
            if RUNTIME.resources.get("żywica", 0) <= 0:
                return "❌ Brak Żywicy!"
            RUNTIME.resources["żywica"] -= 1
        text = " ".join(args[1:])
        BUBBLES.add_text(CTX.current_bubble_id, text)
        żywica = RUNTIME.resources.get("żywica", "∞") if RUNTIME else "∞"
        return f"✅ Dodano (Żywica: {żywica}): {text[:60]}..."

    elif sub == "view":
        if not CTX.current_bubble_id: return "❌ Najpierw otwórz bąbel"
        content = BUBBLES.assemble(CTX.current_bubble_id, CTX.current_prism)
        atoms = BUBBLES.get_active_atoms(CTX.current_bubble_id)
        return f"🫧 {CTX.current_bubble_name} ({len(atoms)} atomów)\n{'─'*40}\n{content or '(pusty)'}\n{'─'*40}"

    elif sub == "refresh":
        if not CTX.current_bubble_id: return "❌ Najpierw otwórz bąbel"
        count = BUBBLES.refresh_bubble(CTX.current_bubble_id)
        return f"⚡ Odświeżono {count} atomów"

    elif sub == "save":
        BUBBLES.save_all()
        return "💾 Zapisane"

    elif sub == "snapshot":
        if not CTX.current_bubble_id: return "❌ Najpierw otwórz bąbel"
        if not RUNTIME: return "❌ Brak runtime"
        atoms = RUNTIME.matrix.atoms()
        if not atoms: return "Brak atomów w runtime"
        count = BUBBLES.snapshot_runtime(CTX.current_bubble_id, atoms)
        return f"📸 Snapshot: {count} atomów → 🫧{CTX.current_bubble_name}"

    else:
        bubble_name = sub
        bubble_id = BUBBLES.find_bubble_by_name(bubble_name)

        if bubble_id:
            CTX.current_bubble_id = bubble_id
            CTX.current_bubble_name = bubble_name
            content = BUBBLES.assemble(bubble_id, "CORE")
            preview = content[:200] if content else "(pusty)"
            active = len(BUBBLES.get_active_atoms(bubble_id))
            return (
                f"📂 Otwarto: {bubble_name} ({active} atomów)\n"
                f"   {'─'*40}\n   {preview}\n   {'─'*40}\n"
                f"   EDIT append | IMPORT | GALLERY | EXPORT"
            )
        else:
            CTX.current_bubble_id = BUBBLES.create_bubble(bubble_name)
            CTX.current_bubble_name = bubble_name
            return f"🫧 Stworzono: {bubble_name}\n   EDIT append <tekst> | IMPORT <plik>"
