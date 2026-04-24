# karmazyn_ui/__init__.py
# KarmazynOS UI Library v0.1
# Standard: STC-Φ-001

from .tokens import TOKEN_MAP, FONT_MAP, SPACING_MAP, MOTION_MAP
from .states import STATE_MAP, BubbleState, BubbleData, temp_to_state
from .renderer import BubbleRenderer, export_css, export_js_tokens

__version__ = "0.1.0"
__all__ = [
    "TOKEN_MAP", "FONT_MAP", "SPACING_MAP", "MOTION_MAP", "SHADOW_MAP",
    "STATE_MAP", "BubbleState", "BubbleData", "temp_to_state",
    "BubbleRenderer", "export_css", "export_js_tokens",
]
