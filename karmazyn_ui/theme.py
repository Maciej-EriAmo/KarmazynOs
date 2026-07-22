"""
KarmazynOS — Sakralna Paleta Barw
STC-Φ-001 | Mapowanie tokenów CSS na kody ANSI True Color

Nazwy tokenów: kanonicznie z podkreślnikiem (phi_stable).
Aliasy z myślnikiem (phi-stable) — zgodność z tokens.py / states.py.
"""

# ═══════════════════════════════════════════
# TOKENY KOLORÓW (zgodne z Design Language)
# ═══════════════════════════════════════════
_TOKENS_CANON = {
    # Φ-Core — aktywność i tożsamość systemu
    "phi_core": (200, 16, 46),
    "phi_bright": (255, 31, 69),
    "phi_deep": (139, 0, 0),
    "phi_ember": (255, 107, 74),

    # Entropy — tła i głębia
    "entropy_void": (8, 10, 15),
    "entropy_bg": (14, 17, 24),
    "entropy_surface": (22, 27, 38),
    "entropy_raised": (30, 37, 53),
    "entropy_border": (42, 51, 71),

    # Φ-Space — semantyczne stany systemu
    "phi_signal": (0, 229, 255),
    "phi_stable": (57, 255, 20),
    "phi_thermal": (255, 153, 0),
    "phi_decay": (107, 127, 163),
    "phi_ghost": (46, 61, 92),
}

# Aliasy hyphen (tokens.py / states.py) + kanoniczne underscore
TOKENS = dict(_TOKENS_CANON)
for _k, _v in _TOKENS_CANON.items():
    TOKENS[_k.replace("_", "-")] = _v

# Fallback przy nieznanym tokenie — phi_core (tożsamość systemu)
_FALLBACK_RGB = _TOKENS_CANON["phi_core"]

RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"


def _resolve_rgb(token: str):
    """Rozwiązuje token (underscore lub hyphen); przy braku → fallback."""
    if token in TOKENS:
        return TOKENS[token]
    alt = token.replace("-", "_") if "-" in token else token.replace("_", "-")
    return TOKENS.get(alt, _FALLBACK_RGB)


def ansi_fg(token: str) -> str:
    """Zwraca kod ANSI ustawiający kolor pierwszoplanowy (True Color)."""
    r, g, b = _resolve_rgb(token)
    return f"\033[38;2;{r};{g};{b}m"


def ansi_bg(token: str) -> str:
    """Zwraca kod ANSI ustawiający kolor tła (True Color)."""
    r, g, b = _resolve_rgb(token)
    return f"\033[48;2;{r};{g};{b}m"
