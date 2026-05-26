#!/usr/bin/env python3
"""Podstawowe komendy phi-space (LS, TOUCH, RM, FIND, ATOM, CONSOLIDATE, STABILIZUJ, DOTKNIJ)."""
import time
from karmazyn_phi import PhiSpace

_RUNTIME = None

def _init(runtime=None):
    global _RUNTIME
    if runtime is not None:
        _RUNTIME = runtime
    if _RUNTIME is None:
        raise RuntimeError("Runtime nie zainicjowany")

def cmd_ls(args):
    atoms = _RUNTIME.matrix.atoms()
    if not atoms: return "(brak atomów)"
    lines = []
    for a in sorted(atoms, key=lambda x: -x.T)[:20]:
        bar = "█" * max(0,int(a.T/10)) + "░"*(10-max(0,int(a.T/10)))
        lines.append(f"  {a.id:<30} [{bar}] {a.T:5.1f}° {a.state}")
    return "\n".join(lines)

def cmd_cd(args): return "phi-space nie ma warstw"
def cmd_pwd(args): return f"phi-space: {len(_RUNTIME.matrix.atoms())} atomów"

def cmd_touch(args):
    if not args: return "TOUCH <id> [S] [E] [T]"
    try:
        a = _RUNTIME.create_atom(args[0], S=args[1] if len(args)>1 else "",
                                 E=args[2] if len(args)>2 else "",
                                 T=float(args[3]) if len(args)>3 else 50.0)
        return f"OK: {a.id} T={a.T:.1f}"
    except Exception as e: return f"Błąd: {e}"

def cmd_rm(args):
    if not args: return "RM <id>"
    ok = _RUNTIME.matrix.delete(args[0])
    return f"OK: usunięto {args[0]}" if ok else f"Brak: {args[0]}"

def cmd_find(args):
    if not args: return "FIND <query>"
    q = " ".join(args).lower()
    hits = [a for a in _RUNTIME.matrix.atoms()
            if q in a.id.lower() or q in str(a.S).lower() or q in str(a.E).lower()]
    if not hits: return f"Brak wyników dla: {q}"
    return "\n".join(f"  {a.id} T={a.T:.1f} {a.state}" for a in hits[:10])

def cmd_atom_status(args):
    if not args: return "ATOM STATUS <id>"
    a = _RUNTIME.get_atom(args[0])
    if not a: return "Atom nie istnieje"
    return f"Atom {a.id}\n  S: {a.S}\n  E: {a.E}\n  T: {a.T:.1f}  {a.state}"

def cmd_consolidate(args):
    if not args: return "CONSOLIDATE <id> [babel]"
    # uproszczona wersja – wymaga dostępu do BUBBLES, ale w tym module go nie mamy
    return "CONSOLIDATE wymaga BUBBLES – użyj pełnej wersji z karmazyn_shell_cmds"

def cmd_stabilizuj(args):
    if not args: return "STABILIZUJ <id>"
    try:
        _RUNTIME.stabilize_atom(args[0])
        return f"Stabilizowano {args[0]}"
    except Exception as e: return str(e)

def cmd_dotknij_pustki(args):
    if not args: return "DOTKNIJ PUSTKI <id>"
    try:
        _RUNTIME.corrupt_atom(args[0], 25)
        return f"Dotknięto {args[0]}"
    except Exception as e: return str(e)