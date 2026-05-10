"""
karmazyn/core/bubble.py
Ujednolicony model bąbla i atomu – jedno źródło prawdy dla całego systemu.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import math


@dataclass
class Atom:
    """Pojedynczy atom – wskaźnik/bufor pamięci roboczej Φ. NIE JEST to trwała baza danych."""
    id: str
    content: str
    energy: float = 1.0          # 0..1, wpływa na liveliness
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    
    def get_stability(self) -> float:
        """Stabilność = energia (0..1). Dla kompatybilności z kernel."""
        return self.energy
    
    def refresh(self, strength: float = 0.15):
        """Podnosi energię (odświeżenie)."""
        self.energy = min(1.0, self.energy + strength)


@dataclass
class Bubble:
    """Bąbel – hermetyczna przestrzeń wykonawcza (Dynamic Holographic Task Memory Space) z kryptograficzną membraną."""
    id: str
    name: str
    atoms: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    manifest: Dict[str, Any] = field(default_factory=lambda: {
        "version": "1.0",
        "type": "document",
        "media_stats": {"image": 0, "audio": 0, "document": 0},
        "prism_default": "CORE",
        "tags": [],
        "description": ""
    })
    
    def add_atom(self, atom: Atom):
        self.atoms.append(atom)
        # aktualizacja statystyk mediów (uproszczona)
        if atom.content.startswith(("http://", "https://")):
            self.manifest["media_stats"]["image"] += 1
        elif atom.content.endswith((".mp3", ".wav")):
            self.manifest["media_stats"]["audio"] += 1
        else:
            self.manifest["media_stats"]["document"] += 1
    
    def get_active_atoms(self) -> list:
        """Zwraca atomy z energią > 0.05."""
        return [a for a in self.atoms if a.energy > 0.05]
    
    def assemble_content(self, prism: str = "CORE") -> str:
        """
        Składa treść bąbla według pryzmatu.
        # Context Binding: składanie odbywa się w ramach wydzielonego pryzmatu dostępu
        """
        if prism == "CORE":
            return "\n".join(a.content for a in self.atoms)
        elif prism == "IN":
            return " | ".join(f"[E:{a.energy:.2f}] {a.content[:80]}" for a in self.atoms)
        elif prism == "OUT":
            return " | ".join(f"[atom:{a.id}]" for a in self.atoms)
        return ""
