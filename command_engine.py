#!/usr/bin/env python3
"""
command_engine.py — Command Engine v1 dla KarmazynOS Shell
===========================================================
Dostarcza klasę Command, rejestr komend, walidację argumentów,
kontekstowe autocomplete oraz wsparcie dla HELP.
"""

import shlex
from typing import Callable, List, Optional, Dict, Any, Tuple


class Command:
    """Pojedyncza komenda shella."""

    def __init__(
        self,
        name: str,
        handler: Callable,
        help_text: str = "",
        category: str = "general",
        args_schema: Optional[List[Dict]] = None,  # np. [{"name":"id","required":True,"type":"str"}]
    ):
        self.name = name
        self.handler = handler
        self.help_text = help_text
        self.category = category
        self.args_schema = args_schema or []

    def validate_args(self, args: List[str]) -> Tuple[bool, str]:
        """
        Sprawdza poprawność argumentów na podstawie schematu.
        Zwraca (ok, komunikat_błędu).
        """
        # Prosta implementacja na początek:
        # - wymagane argumenty
        # - typy: str, int, float (opcjonalnie)
        for i, schema in enumerate(self.args_schema):
            if i >= len(args):
                if schema.get("required", False):
                    return False, f"Brak wymaganego argumentu: {schema['name']}"
                continue
            arg = args[i]
            typ = schema.get("type", "str")
            if typ == "int":
                try:
                    int(arg)
                except ValueError:
                    return False, f"Argument {schema['name']} powinien być liczbą całkowitą"
            elif typ == "float":
                try:
                    float(arg)
                except ValueError:
                    return False, f"Argument {schema['name']} powinien być liczbą"
            # str – zawsze OK
        return True, ""

    def format_help(self) -> str:
        """Zwraca sformatowany tekst pomocy dla tej komendy."""
        lines = [f"{self.name}"]
        if self.help_text:
            lines.append(f"  {self.help_text}")
        if self.args_schema:
            args_desc = []
            for s in self.args_schema:
                req = " (wymagany)" if s.get("required") else ""
                args_desc.append(f"    {s['name']}{req}: {s.get('type','str')}")
            lines.append("  Argumenty:")
            lines.extend(args_desc)
        return "\n".join(lines)


class CommandRegistry:
    """Rejestr komend – zarządza nazwami, kategoriami i wyszukiwaniem."""

    def __init__(self):
        self._commands: Dict[str, Command] = {}
        self._categories: Dict[str, List[str]] = {}

    def register(self, cmd: Command):
        """Dodaje komendę do rejestru."""
        self._commands[cmd.name] = cmd
        self._categories.setdefault(cmd.category, []).append(cmd.name)

    def get(self, name: str) -> Optional[Command]:
        """Zwraca komendę po nazwie (full name)."""
        return self._commands.get(name)

    def list_commands(self, category: Optional[str] = None) -> List[str]:
        """Zwraca listę nazw komend, opcjonalnie filtrując po kategorii."""
        if category:
            return sorted(self._categories.get(category, []))
        return sorted(self._commands.keys())

    def get_categories(self) -> List[str]:
        """Zwraca listę kategorii."""
        return sorted(self._categories.keys())

    def complete(self, text: str, state: int, current_token: str = "") -> List[str]:
        """
        Uproszczone autocomplete – zwraca listę pasujących nazw komend.
        W przyszłości można rozszerzyć o podpowiadanie argumentów.
        """
        if not text:
            matches = self.list_commands()
        else:
            matches = [cmd for cmd in self.list_commands() if cmd.lower().startswith(text.lower())]
        return matches[state] if state < len(matches) else None


# Przykładowy schemat argumentów (można rozbudować)
def make_arg_schema(name: str, required: bool = True, arg_type: str = "str") -> Dict:
    return {"name": name, "required": required, "type": arg_type}
