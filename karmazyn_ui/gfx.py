"""
KarmazynOS — Prymitywy Wizualne (ramki, paski, kropki)
Używa tokenów z theme.py
"""
import re
from karmazyn_ui.theme import ansi_fg, ansi_bg, RESET, BOLD, DIM

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def draw_frame(title: str, lines: list[str], style: str = "phi_core") -> str:
    """Rysuje sakralną ramkę z tytułem."""
    border_fg = ansi_fg(style)
    title_fg = ansi_fg("phi_bright")
    text_fg  = ansi_fg("phi_signal")
    
    # Obliczamy szerokość ignorując ukryte znaki ANSI
    width = max(len(title) + 4, max((len(ANSI_ESCAPE.sub('', line)) for line in lines), default=40)) + 4

    top = f"{border_fg}╔{'═' * (width - 2)}╗{RESET}"
    mid = f"{border_fg}║{RESET} {title_fg}{BOLD}{title.center(width - 4)}{RESET} {border_fg}║{RESET}"
    sep = f"{border_fg}╠{'═' * (width - 2)}╣{RESET}"
    bod = []
    
    for line in lines:
        visible_len = len(ANSI_ESCAPE.sub('', line))
        padding = " " * (width - 4 - visible_len)
        bod.append(f"{border_fg}║{RESET} {text_fg}{line}{padding}{RESET} {border_fg}║{RESET}")
        
    bot = f"{border_fg}╚{'═' * (width - 2)}╝{RESET}"

    return "\n".join([top, mid, sep] + bod + [bot])

def progress_bar(value: float, max_val: float, width: int = 20, fg: str = "phi_ember", bg: str = "entropy_raised") -> str:
    """Termodynamiczny pasek postępu (Żar)."""
    if max_val <= 0:
        ratio = 0.0
    else:
        ratio = max(0, min(1, value / max_val))
        
    fill_chars = int(ratio * width)
    empty_chars = width - fill_chars
    bar = f"{ansi_bg(bg)}{ansi_fg(fg)}{'█' * fill_chars}{'░' * empty_chars}{RESET}"
    return bar

def status_dot(state: str) -> str:
    """Kropka stanu systemu."""
    mapping = {
        "active": ansi_fg("phi_stable") + "●" + RESET,
        "signal": ansi_fg("phi_signal") + "●" + RESET,
        "thermal": ansi_fg("phi_thermal") + "●" + RESET,
        "decay": ansi_fg("phi_decay") + "●" + RESET,
        "ghost": ansi_fg("phi_ghost") + "●" + RESET,
    }
    return mapping.get(state, " ")

def table(headers: list[str], rows: list[list[str]]) -> str:
    """Proste renderowanie tabeli tekstowej."""
    col_widths = []
    for i, h in enumerate(headers):
        max_len = len(ANSI_ESCAPE.sub('', h))
        for r in rows:
            if i < len(r):
                max_len = max(max_len, len(ANSI_ESCAPE.sub('', str(r[i]))))
        col_widths.append(max_len)

    res = []

    # Nagłówki
    header_row = " | ".join(h + " " * (col_widths[i] - len(ANSI_ESCAPE.sub('', h))) for i, h in enumerate(headers))
    res.append(f"{ansi_fg('phi_bright')}{BOLD}{header_row}{RESET}")
    res.append(f"{ansi_fg('phi_core')}{'-' * len(ANSI_ESCAPE.sub('', header_row))}{RESET}")

    # Wiersze
    for row in rows:
        formatted_row = []
        for i, col in enumerate(row):
            val = str(col)
            visible_len = len(ANSI_ESCAPE.sub('', val))
            padding = " " * (col_widths[i] - visible_len) if i < len(col_widths) else ""
            formatted_row.append(val + padding)
        res.append(" | ".join(formatted_row))

    return "\n".join(res)