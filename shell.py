#!/usr/bin/env python3
"""
KarmazynOS — Shell (ksh) v2.2
Lekka powłoka — logika w modułach.

Importy:
    runtime               — SanctuaryRuntime
    karmazyn_fs           — KarmazynFS  
    bedit                 — KarmazynIntegration (BubbleRuntime)
    mission_engine        — MissionEngine
    bubble_commands       — cmd_edit, cmd_import, cmd_gallery, cmd_export
    karmazyn_lang         — KarmazynExecutor (.karm)
    karmazyn_ui           — theme, gfx
"""
import json
import os
import sys
import time
import readline
from typing import Optional

from runtime import SanctuaryRuntime, SystemState
from karmazyn_fs import KarmazynFS
from karmazyn_ui import theme, gfx
from karmazyn_ui.embedder import LevelEmbedder

# ─── Bąble ───────────────────────────────────────────
from bedit import KarmazynIntegration as BubbleRuntime
BUBBLES = BubbleRuntime()

# ─── Misje ───────────────────────────────────────────
from mission_engine import MissionEngine, describe_cel

# ─── Komendy bąbli ───────────────────────────────────
from bubble_commands import (
    CTX as BUBBLE_CTX,
    cmd_edit, cmd_import, cmd_gallery, cmd_export,
    init as bubble_init,
)

# ─── KarmazynScript ──────────────────────────────────
try:
    from karmazyn_lang import KarmazynExecutor, parse_file
    KARM_LOADED = True
except ImportError:
    KARM_LOADED = False

# ═══════════════════════════════════════════
# INICJALIZACJA SYSTEMU
# ═══════════════════════════════════════════
RUNTIME = SanctuaryRuntime()
FS      = KarmazynFS(RUNTIME)
RUNTIME.start_loop()

# Podłącz referencje do bubble_commands
bubble_init(BUBBLES, RUNTIME)

# Misja
MISSION = MissionEngine(RUNTIME)

# KarmazynScript
KARM = KarmazynExecutor(RUNTIME) if KARM_LOADED else None

# ═══════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════

def _find_bubble_by_name(name: str) -> Optional[str]:
    """Znajduje ID bąbla po nazwie, używając istniejącego API."""
    for b in BUBBLES.list_bubbles():
        if b['name'].lower() == name.lower():
            return b['id']
    return None

def _memcost(n: int = 1) -> bool:
    """Sprawdza i pobiera koszt żywicy za operacje pamięciowe."""
    if not RUNTIME.current_mission:
        return True  # poza misją zapis jest darmowy
    if RUNTIME.resources.get("żywica", 0) >= n:
        RUNTIME.resources["żywica"] -= n
        return True
    return False

# ═══════════════════════════════════════════
# EVENTY MISJI
# ═══════════════════════════════════════════

def _log_to_kronika(status: str, data: dict):
    kid = _find_bubble_by_name("kronika")
    if not kid:
        kid = BUBBLES.create_bubble("kronika", "chronicle")
    m = RUNTIME.current_mission.get('nazwa', '?') if RUNTIME.current_mission else '?'
    BUBBLES.add_text(kid, f"{status}: {m} | czas={data.get('czas', 0):.1f}s")

def _on_mission_won(data):
    print(f"\n{theme.ansi_fg('phi_stable')}╔══════════════════╗")
    print(f"║  MISJA UKOŃCZONA  ║")
    print(f"╚══════════════════╝{theme.RESET}")
    print(f"Czas: {data.get('czas', 0):.1f}s")
    _log_to_kronika("WYGRANA", data)

def _on_mission_lost(data):
    print(f"\n{theme.ansi_fg('phi_bright')}╔═════════════════════════╗")
    print(f"║  CISZA OSTATECZNA       ║")
    print(f"╚═════════════════════════╝{theme.RESET}")
    print(f"Powód: {data.get('powód', data.get('czas', '?'))}")
    _log_to_kronika("PRZEGRANA", data)

RUNTIME.events.on("mission_won",  _on_mission_won)
RUNTIME.events.on("mission_lost", _on_mission_lost)

# ═══════════════════════════════════════════
# HUD
# ═══════════════════════════════════════════

def print_hud():
    s = RUNTIME.status_summary()
    hud = (f"{theme.ansi_fg('phi_stable')}HOT:{s['HOT']}{theme.RESET} "
           f"{theme.ansi_fg('phi_thermal')}WARM:{s['WARM']}{theme.RESET} "
           f"{theme.ansi_fg('phi_signal')}COLD:{s['COLD']}{theme.RESET} "
           f"{theme.ansi_fg('phi_ghost')}TOMB:{s['TOMB']}{theme.RESET}")

    if RUNTIME.current_mission and MISSION._active:
        e = MISSION.elapsed()
        limit = RUNTIME.current_mission.get("czas_misji", 0)
        if limit:
            hud += f"  ⏱ {max(0.0, limit - e):.0f}s"
        hud += f"  🌿{RUNTIME.resources.get('żywica', 0)}"

    if BUBBLE_CTX.current_bubble_name:
        atoms = BUBBLES.get_active_atoms(BUBBLE_CTX.current_bubble_id) if BUBBLE_CTX.current_bubble_id else []
        bubble = BUBBLES.get_bubble(BUBBLE_CTX.current_bubble_id)
        media = ""
        if bubble:
            stats = bubble.manifest.get('media_stats', {})
            parts = []
            if stats.get('image', 0):
                parts.append(f"🖼{stats['image']}")
            if stats.get('audio', 0):
                parts.append(f"🎵{stats['audio']}")
            if stats.get('document', 0):
                parts.append(f"📄{stats['document']}")
            if parts:
                media = f" [{','.join(parts)}]"
        hud += f"  🫧{BUBBLE_CTX.current_bubble_name}({len(atoms)}){media}"

    print(hud)

# ═══════════════════════════════════════════
# AUTOCOMPLETE
# ═══════════════════════════════════════════

COMMAND_LIST = [
    "LS", "CD", "PWD", "TOUCH", "RM", "CP", "MV", "SETE", "FIND",
    "MONITOR", "STABILIZUJ", "DOTKNIJ PUSTKI", "ATOM STATUS",
    "OBSERWUJ", "KRONIKA", "EDIT", "EXIT", "SNAPSHOT",
    "IMPORT", "GALLERY", "EXPORT", "RUN", "COMPILE",
    "SANKTUARIUM:START", "SANKTUARIUM:STATUS", "SANKTUARIUM:STOP",
    "SANKTUARIUM:LOAD",
]

def completer(text, state):
    options = [c for c in COMMAND_LIST if c.startswith(text.upper())]
    return options[state] if state < len(options) else None

readline.set_completer(completer)
readline.parse_and_bind("tab: complete")

# ═══════════════════════════════════════════
# KOMENDY SYSTEMOWE
# ═══════════════════════════════════════════

def cmd_ls(args):
    atoms = RUNTIME.matrix.atoms()
    if atoms:
        rows = []
        for a in atoms:
            bar = gfx.progress_bar(a.T, a.T_max, fg=SystemState.color_for(a))
            rows.append(f"{a.id:12} {bar} {a.T:5.1f}° {a.state}")
        return gfx.draw_frame("ATOMY", rows)
    return FS.ls(args[0] if args else None)

def cmd_cd(args):
    return FS.cd(args[0] if args else "HOT")

def cmd_pwd(args):
    return FS.pwd()

def cmd_touch(args):
    return FS.touch(*args) if len(args) >= 1 else "TOUCH <id> [S] [E] [T]"

def cmd_rm(args):
    return FS.rm(args[0]) if args else "RM <id>"

def cmd_cp(args):
    return FS.cp(args[0], args[1]) if len(args) > 1 else "CP <src> <dst>"

def cmd_mv(args):
    return FS.mv(args[0], args[1]) if len(args) > 1 else "MV <id> <warstwa>"

def cmd_sete(args):
    return FS.setE(args[0], args[1]) if len(args) > 1 else "SETE <id> <E>"

def cmd_find(args):
    return FS.find(" ".join(args)) if args else "FIND <zapytanie>"

def cmd_monitor(args):
    s = RUNTIME.status_summary()
    return gfx.draw_frame("MONITOR", [f"{k}: {v}" for k, v in s.items()])

def cmd_stabilizuj(args):
    if not args:
        return "STABILIZUJ <id>"
    if RUNTIME.current_mission and RUNTIME.resources.get("żywica", 0) <= 0:
        return "Brak Żywicy!"
    if RUNTIME.current_mission:
        RUNTIME.resources["żywica"] -= 1
    try:
        RUNTIME.stabilize_atom(args[0])
        zywica = RUNTIME.resources.get("żywica", "∞")
        return f"Stabilizowano {args[0]} (Żywica: {zywica})"
    except ValueError as e:
        return str(e)

def cmd_dotknij_pustki(args):
    if not args:
        return "DOTKNIJ PUSTKI <id>"
    try:
        RUNTIME.corrupt_atom(args[0], 25)
        atom = RUNTIME.get_atom(args[0])
        if atom:
            return f"Dotknięto Pustką {args[0]}. T={atom.T:.1f}"
        return f"Dotknięto {args[0]}"
    except ValueError as e:
        return str(e)

def cmd_atom_status(args):
    if not args:
        return "ATOM STATUS <id>"
    atom = RUNTIME.get_atom(args[0])
    if not atom:
        return "Atom nie istnieje."
    if atom.T > 70:
        color = "phi_thermal"
    elif atom.T > 30:
        color = "phi_signal"
    else:
        color = "phi_decay"
    survived = MISSION._survived.get(atom.id, 0.0)
    return gfx.draw_frame(f"ATOM {atom.id}", [
        f"S: {atom.S}   E: {atom.E}",
        f"T: {atom.T:.1f}   Stan: {atom.state}",
        f"Wiek: {atom.age}   Przeżyte: {survived:.0f}s",
        gfx.progress_bar(atom.T, atom.T_max, fg=color),
    ])

def cmd_obserwuj(args):
    print("Obserwuję (Ctrl+C = koniec)...")
    try:
        while True:
            rows = []
            for a in RUNTIME.matrix.atoms():
                if a.T > 70:
                    color = "phi_thermal"
                elif a.T > 30:
                    color = "phi_signal"
                else:
                    color = "phi_decay"
                bar = gfx.progress_bar(a.T, a.T_max, fg=color)
                survived = MISSION._survived.get(a.id, 0.0)
                rows.append(
                    f"{a.id:10} {bar} {a.T:5.1f}° {a.state}"
                    f"  ⏱{survived:.0f}s"
                )
            sys.stdout.write("\033[H\033[J")
            sys.stdout.write(gfx.draw_frame("OBSERWACJA", rows) + "\n")
            sys.stdout.flush()
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    return "Koniec"

def cmd_kronika(args):
    if not RUNTIME.current_mission:
        return "Brak misji. SANKTUARIUM:START"
    m = RUNTIME.current_mission
    cele = m.get("cele", [])
    lines = [
        m.get("nazwa", ""),
        m.get("opis_kroniki", ""),
        "",
        "WARUNEK WYGRANEJ:",
    ]
    for cel in cele:
        lines.append(f"  ✦ {describe_cel(cel, MISSION._survived)}")
    if m.get("limit_ciszy"):
        lines.append("")
        lines.append("WARUNEK PRZEGRANEJ:")
        lines.append(f"  ✗ {m['limit_ciszy']} atomów → Cisza Ostateczna")
    if m.get("czas_misji"):
        lines.append(f"  ✗ Upłynie {m['czas_misji']}s")
    return gfx.draw_frame("KRONIKA", lines)

def cmd_snapshot(args):
    name = args[0] if args else f"snapshot_{int(time.time())}"
    bid = _find_bubble_by_name(name)
    if not bid:
        bid = BUBBLES.create_bubble(name, "snapshot")

    if not _memcost(3):
        return "❌ Za mało Żywicy na snapshot (koszt: 3)"

    atoms = RUNTIME.matrix.atoms()
    if not atoms:
        return "Brak atomów"
    count = BUBBLES.snapshot_runtime(bid, atoms)
    if hasattr(BUBBLES, 'save_all'):
        BUBBLES.save_all()
    return f"📸 {count} atomów → 🫧{name}"

def cmd_run(args):
    if not KARM_LOADED:
        return "❌ karmazyn_lang.py nie znaleziony (pip install lark)"
    if not args:
        return "RUN <plik.karm>"
    if not os.path.isfile(args[0]):
        return f"❌ Plik: {args[0]}"
    try:
        KARM.run_file(args[0])
        return f"✅ {args[0]}"
    except Exception as e:
        return f"❌ {e}"

def cmd_compile(args):
    if not KARM_LOADED:
        return "❌ karmazyn_lang.py nie znaleziony"
    if not args:
        return "COMPILE <plik.karm>"
    if not os.path.isfile(args[0]):
        return f"❌ Plik: {args[0]}"
    try:
        program = parse_file(args[0])
        lines = [f"📜 AST: {args[0]}", "=" * 50]
        for i, stmt in enumerate(program.statements, 1):
            name = type(stmt).__name__
            fields = {
                k: v for k, v in stmt.__dict__.items()
                if not k.startswith('_')
            }
            lines.append(f"{i}. {name}: {fields}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ {e}"

# ═══════════════════════════════════════════
# SANKTUARIUM
# ═══════════════════════════════════════════

def _start_mission(mission: dict) -> str:
    MISSION.stop()
    RUNTIME.start_mission(mission)
    MISSION.start(mission)
    cele = mission.get("cele", [])
    return gfx.draw_frame("MISJA ROZPOCZĘTA", [
        f"Nazwa: {mission['nazwa']}",
        f"Atomów: {len(mission.get('relikwie', []))}",
        f"Czas: {mission.get('czas_misji', '∞')}s",
        f"Żywica: {RUNTIME.resources.get('żywica', 0)}",
        "",
        "CEL:",
    ] + [f"  ✦ {describe_cel(c, {})}" for c in cele] + [
        "",
        "LS, ATOM STATUS, OBSERWUJ, STABILIZUJ, DOTKNIJ PUSTKI, KRONIKA, SNAPSHOT",
    ])

def cmd_sanktuarium_start(args):
    words = args if args else ["iskra", "ciemność"]
    embedder = LevelEmbedder(mode="light")
    mission = embedder.generate_mission(words)
    return _start_mission(mission)

def cmd_sanktuarium_load(args):
    if not args:
        return "SANKTUARIUM:LOAD <plik.json>"
    if not os.path.isfile(args[0]):
        return f"Plik: {args[0]}"
    try:
        with open(args[0], encoding="utf-8") as f:
            mission = json.load(f)
        return _start_mission(mission)
    except Exception as e:
        return f"[BŁĄD] {e}"

def cmd_sanktuarium_status(args):
    if not RUNTIME.current_mission:
        return "Brak misji"
    s = RUNTIME.status_summary()
    lines = [
        f"Misja: {RUNTIME.current_mission.get('nazwa', '?')}",
        f"HOT:{s['HOT']} WARM:{s['WARM']} COLD:{s['COLD']} TOMB:{s['TOMB']}",
    ] + MISSION.status_lines()
    return gfx.draw_frame("SANKTUARIUM STATUS", lines)

def cmd_sanktuarium_stop(args):
    MISSION.stop()
    RUNTIME.stop_loop()
    return "Sanktuarium zatrzymane"

def cmd_sanktuarium(args):
    if not args:
        return "SANKTUARIUM:START|LOAD|STATUS|STOP"
    sub = args[0].upper()
    fn = COMMANDS.get(f"SANKTUARIUM:{sub}")
    if fn:
        return fn(args[1:])
    return f"Nieznane: SANKTUARIUM:{sub}"

# ═══════════════════════════════════════════
# PARSER
# ═══════════════════════════════════════════

COMMANDS = {
    "LS": cmd_ls,
    "CD": cmd_cd,
    "PWD": cmd_pwd,
    "TOUCH": cmd_touch,
    "RM": cmd_rm,
    "CP": cmd_cp,
    "MV": cmd_mv,
    "SETE": cmd_sete,
    "FIND": cmd_find,
    "MONITOR": cmd_monitor,
    "STABILIZUJ": cmd_stabilizuj,
    "OBSERWUJ": cmd_obserwuj,
    "KRONIKA": cmd_kronika,
    "SNAPSHOT": cmd_snapshot,
    "IMPORT": cmd_import,
    "GALLERY": cmd_gallery,
    "EXPORT": cmd_export,
    "RUN": cmd_run,
    "COMPILE": cmd_compile,
    "DOTKNIJ": {"PUSTKI": cmd_dotknij_pustki},
    "ATOM": {"STATUS": cmd_atom_status},
    "SANKTUARIUM": cmd_sanktuarium,
    "SANKTUARIUM:START": cmd_sanktuarium_start,
    "SANKTUARIUM:LOAD": cmd_sanktuarium_load,
    "SANKTUARIUM:STATUS": cmd_sanktuarium_status,
    "SANKTUARIUM:STOP": cmd_sanktuarium_stop,
    "EDIT": cmd_edit,
    "EXIT": lambda a: (
        BUBBLES.save_all() if hasattr(BUBBLES, 'save_all') else None,
        sys.exit(0),
    )[1],
}

# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    print(gfx.draw_frame(
        "KARMAZYN OS",
        [
            "Shell v2.2 — Cognitive Runtime",
            "Tab = autouzupełnianie",
        ],
        style="phi_core",
    ))

    bubbles = BUBBLES.list_bubbles()
    if bubbles:
        total = sum(b['active_atoms'] for b in bubbles)
        print(f"🫧 {len(bubbles)} bąbli ({total} atomów)", end="")
        imgs = sum(
            b.get('media_stats', {}).get('image', 0)
            for b in bubbles
        )
        if imgs:
            print(f", 🖼{imgs} obrazów", end="")
        print()

    if KARM_LOADED:
        print("📜 KarmazynScript gotowy")

    has_kronika = _find_bubble_by_name("kronika") is not None
    print(f"📖 Kronika: {'gotowa' if has_kronika else 'pusta'}\n")

    while True:
        try:
            line = input(
                f"{theme.ansi_fg('phi_signal')}ksh>{theme.RESET} "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nZamykanie...")
            MISSION.stop()
            if hasattr(BUBBLES, 'save_all'):
                BUBBLES.save_all()
            print("💾 Bąble zapisane")
            break

        if not line:
            continue

        parts = line.split()
        verb = parts[0].upper()
        args = parts[1:]
        handler = COMMANDS.get(verb)

        if handler is None:
            print(
                f"{theme.ansi_fg('phi_bright')}[BŁĄD]{theme.RESET} "
                f"Nieznana komenda: {verb}"
            )
            print_hud()
            continue

        try:
            if isinstance(handler, dict):
                sub = args[0].upper() if args else ""
                sub_handler = handler.get(sub)
                if sub_handler:
                    result = sub_handler(args[1:])
                else:
                    result = f"Nieznana podkomenda: {sub}"
            else:
                result = handler(args)
        except Exception as e:
            result = f"{theme.ansi_fg('phi_bright')}[BŁĄD]{theme.RESET} {e}"

        if result:
            print(result)
        print_hud()


if __name__ == "__main__":
    main()