# karmazyn_ui/states.py
# KarmazynOS — Φ-Space State → Visual Token Mapping
# STC-Φ-001 // v0.1
#
# ZASADA: Stan systemu determinuje wygląd.
# Kolor nie jest wyborem — jest wynikiem stanu.

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────
# STANY BĄBLI — enum formalnych stanów systemu
# ─────────────────────────────────────────────

class BubbleState(Enum):
    STABLE    = "stable"       # bąbel skonsolidowany, aktywny
    SIGNAL    = "signal"       # dane w ruchu, live stream
    THERMAL   = "thermal"      # wysoka temperatura, ostrzeżenie
    DECAY     = "decay"        # zanikający, nieaktywny
    GHOST     = "ghost"        # vacuum / bardzo nieaktywny
    PHI       = "phi"          # aktywny proces Φ — najwyższy priorytet
    EMBER     = "ember"        # alert niski / ciepły akcent


# ─────────────────────────────────────────────
# STATE_MAP — główna tablica mapowania
# stan → tokeny wizualne
# ─────────────────────────────────────────────

STATE_MAP = {

    BubbleState.STABLE: {
        "color":        "phi-stable",
        "border":       "phi-stable",        # rgba będzie w CSS z opacity
        "bg_alpha":     0.08,                # przezroczystość tła
        "glow":         "glow-stable",
        "animation":    None,
        "opacity":      1.0,
        "dot_pulse":    False,
        "label_color":  "phi-stable",
        "description":  "Skonsolidowany, zweryfikowany",
    },

    BubbleState.SIGNAL: {
        "color":        "phi-signal",
        "border":       "phi-signal",
        "bg_alpha":     0.08,
        "glow":         "glow-signal",
        "animation":    "pulse",             # pulsowanie 2s
        "opacity":      1.0,
        "dot_pulse":    True,
        "label_color":  "phi-signal",
        "description":  "Dane w ruchu / live stream",
    },

    BubbleState.THERMAL: {
        "color":        "phi-thermal",
        "border":       "phi-thermal",
        "bg_alpha":     0.10,
        "glow":         "glow-thermal",
        "animation":    "flicker",           # szybkie migotanie
        "opacity":      1.0,
        "dot_pulse":    False,
        "label_color":  "phi-thermal",
        "description":  "Wysoka temperatura / ostrzeżenie",
    },

    BubbleState.DECAY: {
        "color":        "phi-decay",
        "border":       "entropy-border",
        "bg_alpha":     0.0,
        "glow":         None,
        "animation":    "fade",              # powolne zanikanie
        "opacity":      0.6,
        "dot_pulse":    False,
        "label_color":  "phi-decay",
        "description":  "Zanikający / nieaktywny",
    },

    BubbleState.GHOST: {
        "color":        "phi-ghost",
        "border":       "phi-ghost",
        "bg_alpha":     0.0,
        "glow":         None,
        "animation":    None,
        "opacity":      0.3,
        "dot_pulse":    False,
        "label_color":  "type-muted",
        "description":  "Vacuum / bardzo nieaktywny",
    },

    BubbleState.PHI: {
        "color":        "phi-bright",
        "border":       "phi-core",
        "bg_alpha":     0.15,
        "glow":         "glow-phi",
        "animation":    "breathe",           # wolne pulsowanie
        "opacity":      1.0,
        "dot_pulse":    True,
        "label_color":  "phi-bright",
        "description":  "Aktywny proces Φ",
    },

    BubbleState.EMBER: {
        "color":        "phi-ember",
        "border":       "phi-ember",
        "bg_alpha":     0.10,
        "glow":         "glow-thermal",
        "animation":    None,
        "opacity":      1.0,
        "dot_pulse":    False,
        "label_color":  "phi-ember",
        "description":  "Alert niski / ciepły akcent",
    },
}


# ─────────────────────────────────────────────
# TEMPERATURE → STATE — automatyczne mapowanie
# temperatury termodynamicznej na stan wizualny
# ─────────────────────────────────────────────

def temp_to_state(temperature: float, entropy: float = 0.0) -> BubbleState:
    """
    Mapuje temperaturę bąbla (0.0–1.0) i entropię na stan wizualny.
    To jest most między termodynamiką HSS a warstwą UI.

    Progi (do kalibracji):
      temp > 0.80  → THERMAL
      temp > 0.60  → PHI (aktywny)
      temp > 0.30  → STABLE
      temp > 0.10  → DECAY
      temp ≤ 0.10  → GHOST
      entropy > 0.9 → GHOST (niezależnie od temp)
    """
    if entropy > 0.90:
        return BubbleState.GHOST
    if temperature > 0.80:
        return BubbleState.THERMAL
    if temperature > 0.60:
        return BubbleState.PHI
    if temperature > 0.30:
        return BubbleState.STABLE
    if temperature > 0.10:
        return BubbleState.DECAY
    return BubbleState.GHOST


# ─────────────────────────────────────────────
# BUBBLE DATA — struktura danych bąbla dla UI
# ─────────────────────────────────────────────

@dataclass
class BubbleData:
    """
    Minimalna struktura danych bąbla przekazywana do renderera.
    Niezależna od implementacji HSS — most między backendem a UI.
    """
    label:       str
    state:       BubbleState       = BubbleState.STABLE
    temperature: float             = 0.5
    entropy:     float             = 0.0
    age_ms:      int               = 0
    phi_id:      Optional[str]     = None
    tags:        list              = field(default_factory=list)

    @classmethod
    def from_temp(cls, label: str, temperature: float,
                  entropy: float = 0.0, **kwargs) -> "BubbleData":
        """Utwórz bąbel z automatycznym mapowaniem temperatury → stan."""
        state = temp_to_state(temperature, entropy)
        return cls(label=label, state=state,
                   temperature=temperature, entropy=entropy, **kwargs)
