# karmazyn_ui/tokens.py
# KarmazynOS Design Language — Token Definitions
# STC-Φ-001 // v0.1
#
# ZASADA: Ten plik jest jedynym źródłem prawdy dla wartości wizualnych.
# CSS, JS, HTML są GENEROWANE z tych struktur — nigdy pisane ręcznie.

# ─────────────────────────────────────────────
# KOLORY
# ─────────────────────────────────────────────

TOKEN_MAP = {

    # Φ-Core — tożsamość i aktywność systemu
    "phi-core":         "#C8102E",   # karmazyn bazowy — tożsamość
    "phi-bright":       "#FF1F45",   # aktywny / hover / focus
    "phi-deep":         "#8B0000",   # wciśnięty / border akcentu
    "phi-ember":        "#FF6B4A",   # ciepły akcent / alert niski

    # Entropy — warstwy tła i głębia przestrzeni
    "entropy-void":     "#080A0F",   # najgłębsze tło / modal backdrop
    "entropy-bg":       "#0E1118",   # tło aplikacji
    "entropy-surface":  "#161B26",   # karty / panele / sidebar
    "entropy-raised":   "#1E2535",   # elevated / dropdowns
    "entropy-border":   "#2A3347",   # wszystkie obramowania

    # Phi-Space — semantyczne stany systemu
    "phi-signal":       "#00E5FF",   # dane live / stream / output
    "phi-stable":       "#39FF14",   # stabilny / ok / verified
    "phi-thermal":      "#FF9900",   # ciepło / ostrzeżenie
    "phi-decay":        "#6B7FA3",   # zanikający / nieaktywny
    "phi-ghost":        "#2E3D5C",   # bardzo nieaktywny / vacuum

    # Type — typografia
    "type-primary":     "#E8ECF4",   # główny tekst
    "type-secondary":   "#8A9BBF",   # drugi plan
    "type-muted":       "#4A5870",   # wyciszony
    "type-accent":      "#FF1F45",   # akcent tekstowy
}

# ─────────────────────────────────────────────
# CZCIONKI
# ─────────────────────────────────────────────

FONT_MAP = {
    "display":  ("Rajdhani", "700", "sans-serif"),      # nagłówki, nazwy
    "body":     ("Exo 2",    "200", "sans-serif"),       # opisy, narracja
    "mono":     ("Share Tech Mono", "400", "monospace"), # dane, kod, output
    # fallback stack per rodzina
    "display-stack": "'Rajdhani', 'Exo 2', sans-serif",
    "body-stack":    "'Exo 2', sans-serif",
    "mono-stack":    "'Share Tech Mono', 'Courier New', monospace",
    # Google Fonts URL
    "google-url": (
        "https://fonts.googleapis.com/css2?"
        "family=Share+Tech+Mono"
        "&family=Rajdhani:wght@300;400;600;700"
        "&family=Exo+2:ital,wght@0,200;0,400;0,700;1,200"
        "&display=swap"
    ),
}

# ─────────────────────────────────────────────
# SPACING — jednostka bazowa 8px
# ─────────────────────────────────────────────

SPACING_MAP = {
    "micro":  "4px",    # unit × 0.5
    "xs":     "8px",    # unit × 1   — bazowa jednostka
    "sm":     "16px",   # unit × 2
    "md":     "24px",   # unit × 3
    "lg":     "32px",   # unit × 4
    "xl":     "48px",   # unit × 6
    "2xl":    "64px",   # unit × 8   — sekcje
    "3xl":    "96px",   # unit × 12  — strony
}

RADIUS_MAP = {
    "sm":   "3px",
    "md":   "6px",
    "lg":   "12px",
    "pill": "999px",
}

# ─────────────────────────────────────────────
# MOTION — prędkości i krzywe animacji
# ─────────────────────────────────────────────

MOTION_MAP = {
    # Prędkości
    "dur-fast":   "120ms",   # hover, feedback natychmiastowy
    "dur-mid":    "280ms",   # transitions, otwieranie paneli
    "dur-slow":   "500ms",   # decay, konsolidacja, zanikanie
    "dur-pulse":  "2000ms",  # pulsowanie aktywnych elementów

    # Krzywa Φ — własna krzywa Béziera systemu
    "ease-phi":   "cubic-bezier(0.23, 1, 0.32, 1)",
    "ease-decay": "cubic-bezier(0.55, 0, 1, 0.45)",  # przyspieszające zanikanie
    "ease-enter": "cubic-bezier(0, 0, 0.2, 1)",       # wchodzenie elementów
}

# ─────────────────────────────────────────────
# SHADOW / LIGHT — Mechanicum sacred engineering
# ─────────────────────────────────────────────

SHADOW_MAP = {
    # Poświaty (glow) per kolor semantyczny
    "glow-phi":     "0 0 12px rgba(200,16,46,0.35), 0 0 32px rgba(200,16,46,0.12)",
    "glow-signal":  "0 0 10px rgba(0,229,255,0.30), 0 0 24px rgba(0,229,255,0.08)",
    "glow-stable":  "0 0 10px rgba(57,255,20,0.30), 0 0 24px rgba(57,255,20,0.08)",
    "glow-thermal": "0 0 10px rgba(255,153,0,0.35), 0 0 28px rgba(255,153,0,0.10)",

    # Cienie głębi
    "shadow-lift":  "0 4px 16px rgba(0,0,0,0.50), 0 1px 0 rgba(255,255,255,0.04) inset",
    "shadow-deep":  "0 8px 32px rgba(0,0,0,0.70), 0 1px 0 rgba(255,255,255,0.03) inset",

    # Rim light — szczelina światła (Mechanicum)
    "rim-light":    "0 1px 0 rgba(255,255,255,0.06) inset, 0 -1px 0 rgba(0,0,0,0.40) inset",
    "rim-phi":      "0 1px 0 rgba(200,16,46,0.40) inset, 0 -1px 0 rgba(0,0,0,0.50) inset",
}
