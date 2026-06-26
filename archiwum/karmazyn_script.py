#!/usr/bin/env python3
"""Wykonywanie skryptów .karm."""
import os

_RUNTIME = None
_KARM = None

def _init(runtime=None, karm_executor=None):
    global _RUNTIME, _KARM
    if runtime is not None: _RUNTIME = runtime
    if karm_executor is not None: _KARM = karm_executor

def cmd_run(args):
    if not _KARM: return "KarmazynScript niedostępny"
    if not args: return "RUN <plik.karm>"
    if not os.path.isfile(args[0]): return f"Brak pliku: {args[0]}"
    try:
        _KARM.run_file(args[0])
        return f"OK {args[0]}"
    except Exception as e: return f"Błąd: {e}"

def cmd_compile(args):
    if not _KARM: return "KarmazynScript niedostępny"
    if not args: return "COMPILE <plik.karm>"
    if not os.path.isfile(args[0]): return f"Brak pliku: {args[0]}"
    try:
        from karmazyn_lang import parse_file
        program = parse_file(args[0])
        lines = [f"AST: {args[0]}", "="*50]
        for i, stmt in enumerate(program.statements, 1):
            fields = {k:v for k,v in stmt.__dict__.items() if not k.startswith('_')}
            lines.append(f"{i}. {type(stmt).__name__}: {fields}")
        return "\n".join(lines)
    except Exception as e: return f"Błąd: {e}"