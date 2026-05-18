# karmazyn_ui/renderer.py
# KarmazynOS — UI Renderer
# STC-Φ-001 // v0.1
#
# ZASADA: Renderer nie ma opinii wizualnych.
# Generuje CSS/HTML jako projekcję TOKEN_MAP i STATE_MAP.
# Logika wizualna żyje w tokens.py i states.py — nie tutaj.

import json
from typing import List, Optional

from .tokens import TOKEN_MAP, FONT_MAP, SPACING_MAP, RADIUS_MAP, MOTION_MAP, SHADOW_MAP
from .states import STATE_MAP, BubbleState, BubbleData


# ─────────────────────────────────────────────
# CSS EXPORTER
# ─────────────────────────────────────────────

def export_css(include_animations: bool = True) -> str:
    """
    Generuje kompletny plik CSS z TOKEN_MAP, SPACING_MAP, MOTION_MAP.
    To jest jedyna metoda tworzenia CSS — nigdy ręcznie.

    Użycie:
        css = export_css()
        with open("karmazyn.css", "w") as f:
            f.write(css)
    """
    lines = [
        "/* ═══════════════════════════════════════════════════ */",
        "/* KarmazynOS Design Language — GENERATED             */",
        "/* STC-Φ-001 // NIE EDYTUJ RĘCZNIE                   */",
        "/* Źródło: karmazyn_ui/tokens.py                     */",
        "/* ═══════════════════════════════════════════════════ */",
        "",
        f'@import url("{FONT_MAP["google-url"]}");',
        "",
        ":root {",
        "  /* — Kolory — */",
    ]

    # Tokeny kolorów
    for name, value in TOKEN_MAP.items():
        lines.append(f"  --{name}: {value};")

    lines.append("")
    lines.append("  /* — Typografia — */")
    lines.append(f'  --font-display: {FONT_MAP["display-stack"]};')
    lines.append(f'  --font-body: {FONT_MAP["body-stack"]};')
    lines.append(f'  --font-mono: {FONT_MAP["mono-stack"]};')

    lines.append("")
    lines.append("  /* — Spacing — */")
    for name, value in SPACING_MAP.items():
        lines.append(f"  --space-{name}: {value};")

    lines.append("")
    lines.append("  /* — Radius — */")
    for name, value in RADIUS_MAP.items():
        lines.append(f"  --radius-{name}: {value};")

    lines.append("")
    lines.append("  /* — Motion — */")
    for name, value in MOTION_MAP.items():
        lines.append(f"  --{name}: {value};")

    lines.append("")
    lines.append("  /* — Shadow / Light (Mechanicum) — */")
    for name, value in SHADOW_MAP.items():
        lines.append(f"  --{name}: {value};")

    lines.append("}")

    # Bazowe style reset
    lines += [
        "",
        "/* — Base reset — */",
        "*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }",
        "",
        "body {",
        "  background: var(--entropy-void);",
        "  color: var(--type-primary);",
        "  font-family: var(--font-body);",
        "  font-weight: 200;",
        "  min-height: 100vh;",
        "}",
        "",
        "/* — Scanline texture (Mechanicum) — */",
        "body::before {",
        "  content: '';",
        "  position: fixed; inset: 0;",
        "  background: repeating-linear-gradient(",
        "    0deg, transparent, transparent 2px,",
        "    rgba(0,0,0,0.035) 2px, rgba(0,0,0,0.035) 4px",
        "  );",
        "  pointer-events: none;",
        "  z-index: 9999;",
        "}",
        "",
        "/* — Ambient Φ glow — */",
        "body::after {",
        "  content: '';",
        "  position: fixed;",
        "  top: -20%; left: 50%; transform: translateX(-50%);",
        "  width: 60%; height: 40%;",
        "  background: radial-gradient(ellipse at center,",
        "    rgba(200,16,46,0.07) 0%, rgba(139,0,0,0.03) 40%, transparent 70%",
        "  );",
        "  pointer-events: none;",
        "  z-index: 0;",
        "}",
    ]

    # Animacje
    if include_animations:
        lines += [
            "",
            "/* — Animacje systemowe — */",
            "@keyframes phi-pulse {",
            "  0%, 100% { opacity: 1; }",
            "  50%       { opacity: 0.35; }",
            "}",
            "@keyframes phi-breathe {",
            "  0%, 100% { opacity: 1; transform: scale(1); }",
            "  50%       { opacity: 0.7; transform: scale(0.97); }",
            "}",
            "@keyframes phi-flicker {",
            "  0%, 100% { opacity: 1; }",
            "  25%       { opacity: 0.8; }",
            "  50%       { opacity: 1; }",
            "  75%       { opacity: 0.6; }",
            "}",
            "@keyframes phi-fade {",
            "  from { opacity: 1; }",
            "  to   { opacity: 0; }",
            "}",
        ]

    return "\n".join(lines)


# ─────────────────────────────────────────────
# JS TOKEN EXPORTER
# ─────────────────────────────────────────────

def export_js_tokens() -> str:
    """
    Generuje JavaScript/JSON z tokenami — do użycia w canvas/WebGL
    lub jako import w skryptach frontendowych.
    """
    data = {
        "colors":   TOKEN_MAP,
        "spacing":  SPACING_MAP,
        "radius":   RADIUS_MAP,
        "motion":   MOTION_MAP,
        "shadows":  SHADOW_MAP,
        "fonts": {
            "display": FONT_MAP["display-stack"],
            "body":    FONT_MAP["body-stack"],
            "mono":    FONT_MAP["mono-stack"],
        },
        "_meta": {
            "version":   "0.1.0",
            "standard":  "STC-Φ-001",
            "generated": True,
            "note":      "NIE EDYTUJ RĘCZNIE — generowane z karmazyn_ui/tokens.py",
        }
    }
    return f"const KARMAZYN_TOKENS = {json.dumps(data, indent=2, ensure_ascii=False)};"


# ─────────────────────────────────────────────
# BUBBLE RENDERER
# ─────────────────────────────────────────────

class BubbleRenderer:
    """
    Renderuje bąble Φ jako HTML na bazie STATE_MAP i TOKEN_MAP.
    Nie ma tu żadnej logiki wizualnej — tylko projekcja stanu.
    """

    def render_bubble_chip(self, bubble: BubbleData) -> str:
        """
        Renderuje bąbel jako chip/tag HTML.
        Użycie: w listach, nagłówkach, statusach.
        """
        visual = STATE_MAP[bubble.state]
        color_token = visual["color"]
        color_hex   = TOKEN_MAP.get(color_token, "#ffffff")
        border_hex  = TOKEN_MAP.get(visual["border"], color_hex)
        bg_alpha    = visual["bg_alpha"]
        opacity     = visual["opacity"]
        glow        = SHADOW_MAP.get(visual["glow"], "none") if visual["glow"] else "none"
        anim        = self._animation_css(visual["animation"])

        # RGB z hex dla rgba()
        r, g, b = self._hex_to_rgb(color_hex)

        style = (
            f"display:inline-flex;align-items:center;gap:6px;"
            f"padding:4px 10px;border-radius:20px;"
            f"font-family:{FONT_MAP['mono-stack']};"
            f"font-size:10px;letter-spacing:1px;"
            f"color:{color_hex};"
            f"background:rgba({r},{g},{b},{bg_alpha});"
            f"border:1px solid rgba({r},{g},{b},0.35);"
            f"box-shadow:{glow};"
            f"opacity:{opacity};"
            f"{anim}"
        )

        dot = ""
        if visual["dot_pulse"]:
            dot = (
                f'<span style="width:6px;height:6px;border-radius:50%;'
                f'background:{color_hex};'
                f'box-shadow:0 0 6px {color_hex};'
                f'animation:phi-pulse {MOTION_MAP["dur-pulse"]} ease-in-out infinite;'
                f'flex-shrink:0"></span>'
            )

        temp_str = f"{bubble.temperature:.2f}°" if bubble.temperature else ""
        label_html = f"{bubble.label}"
        if temp_str:
            label_html += (
                f' <span style="opacity:0.6;font-size:9px">{temp_str}</span>'
            )

        return f'<span style="{style}">{dot}{label_html}</span>'

    def render_thermal_bar(self, bubble: BubbleData,
                            show_label: bool = True) -> str:
        """
        Renderuje pasek termodynamiczny dla bąbla.
        Szerokość = temperatura, kolor = stan.
        """
        visual     = STATE_MAP[bubble.state]
        color_hex  = TOKEN_MAP.get(visual["color"], "#ffffff")
        fill_pct   = int(bubble.temperature * 100)
        r, g, b    = self._hex_to_rgb(color_hex)

        label_html = ""
        if show_label:
            label_html = (
                f'<div style="display:flex;justify-content:space-between;'
                f'font-family:{FONT_MAP["mono-stack"]};font-size:10px;'
                f'color:{TOKEN_MAP["type-muted"]};margin-bottom:6px">'
                f'<span>{bubble.label}</span>'
                f'<span style="color:{color_hex}">{bubble.temperature:.2f}°</span>'
                f'</div>'
            )

        track = (
            f'<div style="height:4px;background:{TOKEN_MAP["entropy-raised"]};'
            f'border-radius:2px;overflow:hidden">'
            f'<div style="height:100%;width:{fill_pct}%;border-radius:2px;'
            f'background:linear-gradient(90deg,rgba({r},{g},{b},0.6),{color_hex});'
            f'transition:width {MOTION_MAP["dur-slow"]} {MOTION_MAP["ease-phi"]}"></div>'
            f'</div>'
        )

        return label_html + track

    def render_status_dot(self, bubble: BubbleData) -> str:
        """Renderuje kropkę statusu z etykietą."""
        visual    = STATE_MAP[bubble.state]
        color_hex = TOKEN_MAP.get(visual["color"], "#ffffff")
        anim_css  = ""
        if visual["dot_pulse"]:
            anim_css = (
                f"animation:phi-pulse {MOTION_MAP['dur-pulse']} "
                f"ease-in-out infinite;"
            )

        dot = (
            f'<span style="width:8px;height:8px;border-radius:50%;'
            f'background:{color_hex};'
            f'box-shadow:0 0 8px {color_hex},0 0 16px rgba('
            f'{",".join(str(x) for x in self._hex_to_rgb(color_hex))},0.25);'
            f'flex-shrink:0;{anim_css}"></span>'
        )

        label = (
            f'<span style="font-family:{FONT_MAP["mono-stack"]};'
            f'font-size:12px;color:{color_hex}">'
            f'{bubble.label.upper()}</span>'
        )

        return (
            f'<div style="display:flex;align-items:center;gap:10px">'
            f'{dot}{label}</div>'
        )

    def render_bubble_list(self, bubbles: List[BubbleData]) -> str:
        """Renderuje listę bąbli jako live view."""
        items = []
        for b in bubbles:
            chip = self.render_bubble_chip(b)
            bar  = self.render_thermal_bar(b, show_label=False)
            items.append(
                f'<div style="padding:12px 16px;'
                f'background:{TOKEN_MAP["entropy-surface"]};'
                f'border:1px solid {TOKEN_MAP["entropy-border"]};'
                f'border-radius:{RADIUS_MAP["md"]};'
                f'box-shadow:{SHADOW_MAP["shadow-lift"]};'
                f'margin-bottom:8px">'
                f'{chip}'
                f'<div style="margin-top:8px">{bar}</div>'
                f'</div>'
            )
        return "\n".join(items)

    # ── helpers ──────────────────────────────

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple:
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def _animation_css(animation: Optional[str]) -> str:
        anim_map = {
            "pulse":   f"animation:phi-pulse {MOTION_MAP['dur-pulse']} ease-in-out infinite;",
            "breathe": f"animation:phi-breathe 3000ms ease-in-out infinite;",
            "flicker": f"animation:phi-flicker 800ms ease-in-out infinite;",
            "fade":    f"animation:phi-fade {MOTION_MAP['dur-slow']} {MOTION_MAP['ease-decay']} forwards;",
        }
        return anim_map.get(animation, "")
