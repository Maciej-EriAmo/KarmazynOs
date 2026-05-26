#!/usr/bin/env python3
"""Edytor emanacji (EDIT)."""
def cmd_emanation_edit(args):
    if len(args) < 2:
        return "EDIT <babel> <atom_id>"
    # W pełnej implementacji wywołuje edytor TUI
    return f"Edycja emanacji: {args[0]}::{args[1]} (wymaga pełnej implementacji)"