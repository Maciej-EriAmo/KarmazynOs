"""
KarmazynOS — Prymitywy Wizualne (ramki, paski, kropki)
Używa tokenów z theme.py
"""
from karmazyn_ui.theme import ansi_fg, ansi_bg, RESET, BOLD, DIM

def draw_frame(title: str, lines: list[str], style: str = "phi_core") -> str:
    """Rysuje sakralną ramkę z tytułem."""
    border_fg = ansi_fg(style)
    title_fg = ansi_fg("phi_bright")
    text_fg  = ansi_fg("phi_signal")
    width = max(len(title) + 4, max((len(line) for line in lines), default=40)) + 4

    top = f"{border_fg}╔{'═' * (width - 2)}╗{RESET}"
    mid = f"{border_fg}║{RESET} {title_fg}{BOLD}{title.center(width - 4)}{RESET} {border_fg}║{RESET}"
    sep = f"{border_fg}╠{'═' * (width - 2)}╣{RESET}"
    bod = []
    for line in lines:
        bod.append(f"{border_fg}║{RESET} {text_fg}{line.ljust(width - 4)}{RESET} {border_fg}║{RESET}")
    bot = f"{border_fg}╚{'═' * (width - 2)}╝{RESET}"

    return "\n".join([top, mid, sep] + bod + [bot])

def progress_bar(value: float, max_val: float, width: int = 20, fg: str = "phi_ember", bg: str = "entropy_raised") -> str:
    """Termodynamiczny pasek postępu (Żar)."""
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