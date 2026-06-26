#!/usr/bin/env python3
"""Podstawowe komendy phi-space (LS, TOUCH, RM, FIND, ATOM, CONSOLIDATE, STABILIZUJ, DOTKNIJ).

v1.1 — każda komenda przyjmuje `runtime` (wstrzykiwany przez loader z programs.json
       jako context_kwargs {runtime: $RUNTIME}). Wcześniej funkcje brały tylko `args`,
       więc wywołanie cmd_ls(args, runtime=...) rzucało TypeError i phi było niewidoczne.
       Teraz runtime jest przyjmowany i ustawiany przez _init() przy pierwszym wywołaniu.
"""
import time
from karmazyn_phi import PhiSpace

_RUNTIME = None

def _init(runtime=None):
    global _RUNTIME
    if runtime is not None:
        _RUNTIME = runtime
    if _RUNTIME is None:
        raise RuntimeError("Runtime nie zainicjowany")

def _resolve_scope(token):
    """@<program> lub @me → nazwa programu (lub None gdy brak kontekstu procesu)."""
    name = token[1:]
    if name == "me":
        try:
            from karmazyn_process import current_process
            p = current_process()
            return p.name if p else None
        except Exception:
            return None
    return name or None

def _fmt_atom(a):
    t = max(0, int(a.T / 10))
    bar = "█" * t + "░" * (10 - t)
    return f"  {a.id:<30} [{bar}] {a.T:5.1f}° {a.state}"

def cmd_ls(args, runtime=None):
    _init(runtime)
    # Scoping hologramem: LS @<program> | LS @me → przestrzeń tego programu.
    # Bez @ → widok globalny (zachowanie bez zmian).
    if args and args[0].startswith("@"):
        scope = _resolve_scope(args[0])
        if not scope:
            return "LS @<program> | @me — brak kontekstu procesu"
        atoms = _RUNTIME.scoped_atoms(scope)
        if not atoms:
            return f"(przestrzeń @{scope}: pusto lub brak właściwego hologramu)"
        body = "\n".join(_fmt_atom(a) for a in sorted(atoms, key=lambda x: -x.T)[:20])
        return f"— @{scope} (scoped hologramem) —\n{body}"
    atoms = _RUNTIME.matrix.atoms()
    if not atoms:
        return "(brak atomów)"
    return "\n".join(_fmt_atom(a) for a in sorted(atoms, key=lambda x: -x.T)[:20])

def cmd_cd(args, runtime=None):
    return "phi-space nie ma warstw"

def cmd_pwd(args, runtime=None):
    _init(runtime)
    return f"phi-space: {len(_RUNTIME.matrix.atoms())} atomów"

def cmd_touch(args, runtime=None):
    _init(runtime)
    if not args: return "TOUCH <id> [S] [E] [T]"
    try:
        a = _RUNTIME.create_atom(args[0], S=args[1] if len(args)>1 else "",
                                 E=args[2] if len(args)>2 else "",
                                 T=float(args[3]) if len(args)>3 else 50.0)
        return f"OK: {a.id} T={a.T:.1f}"
    except Exception as e: return f"Błąd: {e}"

def cmd_rm(args, runtime=None):
    _init(runtime)
    if not args: return "RM <id>"
    ok = _RUNTIME.matrix.delete(args[0])
    return f"OK: usunięto {args[0]}" if ok else f"Brak: {args[0]}"

def cmd_find(args, runtime=None):
    _init(runtime)
    if not args: return "FIND [@program|@me] <query>"
    # Scoping hologramem: FIND @<program> <query> przeszukuje tylko przestrzeń
    # programu. Bez @ → szukanie globalne (substring, zachowanie bez zmian).
    scope = None
    if args[0].startswith("@"):
        scope = _resolve_scope(args[0]); args = args[1:]
        if not scope:
            return "FIND @<program> — brak kontekstu procesu"
        if not args:
            return "FIND @<program> <query>"
    q = " ".join(args).lower()
    pool = _RUNTIME.scoped_atoms(scope) if scope else _RUNTIME.matrix.atoms()
    hits = [a for a in pool
            if q in a.id.lower() or q in str(a.S).lower() or q in str(a.E).lower()]
    if not hits:
        tag = f"@{scope} " if scope else ""
        return f"Brak wyników {tag}dla: {q}"
    head = f"— @{scope} —\n" if scope else ""
    return head + "\n".join(f"  {a.id} T={a.T:.1f} {a.state}" for a in hits[:10])

def cmd_atom_status(args, runtime=None):
    _init(runtime)
    if not args: return "ATOM STATUS <id>"
    a = _RUNTIME.get_atom(args[0])
    if not a: return "Atom nie istnieje"
    return f"Atom {a.id}\n  S: {a.S}\n  E: {a.E}\n  T: {a.T:.1f}  {a.state}"

def cmd_consolidate(args, runtime=None):
    _init(runtime)
    if not args: return "CONSOLIDATE <id> [babel]"
    # uproszczona wersja – wymaga dostępu do BUBBLES, ale w tym module go nie mamy
    return "CONSOLIDATE wymaga BUBBLES – użyj pełnej wersji z karmazyn_shell_cmds"

def cmd_stabilizuj(args, runtime=None):
    _init(runtime)
    if not args: return "STABILIZUJ <id>"
    try:
        _RUNTIME.stabilize_atom(args[0])
        return f"Stabilizowano {args[0]}"
    except Exception as e: return str(e)

def cmd_dotknij_pustki(args, runtime=None):
    _init(runtime)
    if not args: return "DOTKNIJ PUSTKI <id>"
    try:
        _RUNTIME.corrupt_atom(args[0], 25)
        return f"Dotknięto {args[0]}"
    except Exception as e: return str(e)