#!/usr/bin/env python3
"""Komendy operujące na lokalnym systemie plików."""
import os
import pathlib

def cmd_cat(args):
    if not args: return "Użycie: CAT <plik>"
    path = args[0]
    if not os.path.exists(path): return f"Brak pliku: {path}"
    if os.path.isdir(path): return f"{path} to katalog"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e: return f"Błąd: {e}"

def cmd_mkdir(args):
    if not args: return "Użycie: MKDIR <katalog>"
    try:
        os.makedirs(args[0], exist_ok=True)
        return f"OK: {args[0]}"
    except Exception as e: return f"Błąd: {e}"

def cmd_echo(args): return " ".join(args)

def cmd_head(args):
    if not args: return "Użycie: HEAD <plik> [N]"
    path, n = args[0], int(args[1]) if len(args) > 1 else 10
    if not os.path.exists(path): return f"Brak pliku: {path}"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[:n])
    except Exception as e: return f"Błąd: {e}"

def cmd_wc(args):
    if not args: return "Użycie: WC <plik>"
    path = args[0]
    if not os.path.exists(path): return f"Brak pliku: {path}"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        lines = content.count("\n")
        words = len(content.split())
        bytes_ = len(content.encode())
        return f"{lines:6} {words:6} {bytes_:6} {path}"
    except Exception as e: return f"Błąd: {e}"

def cmd_cp(args):
    if len(args) < 2: return "CP <src> <dst>"
    # uproszczone kopiowanie plików
    import shutil
    try:
        shutil.copy2(args[0], args[1])
        return f"OK: {args[0]} → {args[1]}"
    except Exception as e: return f"Błąd: {e}"

def cmd_mv(args):
    if len(args) < 2: return "MV <src> <dst>"
    import shutil
    try:
        shutil.move(args[0], args[1])
        return f"OK: {args[0]} → {args[1]}"
    except Exception as e: return f"Błąd: {e}"

def cmd_sete(args):
    if len(args) < 2: return "SETE <id> <E>"
    return "SETE wymaga dostępu do phi-space – użyj w pełnej wersji"