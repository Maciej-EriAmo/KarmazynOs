"""karmazyn_lua.lexer — tokenizacja (z numerami linii)."""

from .values import LuaError, _wrap64


# =====================================================================
#  LEKSER
# =====================================================================
_KEYWORDS = {
    "and", "or", "not", "nil", "true", "false",
    "if", "then", "elseif", "else", "end",
    "while", "do", "for", "in", "function", "local", "return", "break",
    "repeat", "until", "goto", "global",  # Lua 5.2+ / 5.5
}
# operatory wielo- i jednoznakowe; dłuższe najpierw (… przed ..; :: przed :)
_SYMBOLS = [
    "...", "==", "~=", "<=", ">=", "..", "//", "<<", ">>", "::",
    "+", "-", "*", "/", "%", "^", "#", "&", "|", "~",
    "<", ">", "=", "(", ")", "{", "}", "[", "]", ".", ",", ";", ":",
]


class Tok:
    __slots__ = ("kind", "val", "pos", "line", "col")

    def __init__(self, kind, val, pos, line=1, col=1):
        self.kind = kind        # 'name' 'kw' 'num' 'str' 'sym' 'eof'
        self.val = val
        self.pos = pos
        self.line = line
        self.col = col

    def __repr__(self):
        return f"Tok({self.kind},{self.val!r},L{self.line})"


def line_col_at(src, pos):
    """(line, col) 1-based dla offsetu bajtowego pos w src."""
    if pos is None or pos < 0:
        return 1, 1
    line = src.count("\n", 0, pos) + 1
    last_nl = src.rfind("\n", 0, pos)
    col = pos + 1 if last_nl < 0 else pos - last_nl
    return line, col


def _long_bracket(src, i):
    """Jeśli od src[i] zaczyna się '[' '='* '[' -> (indeks_po_otwarciu, poziom); inaczej None."""
    n = len(src)
    if i >= n or src[i] != "[":
        return None
    j = i + 1
    level = 0
    while j < n and src[j] == "=":
        level += 1
        j += 1
    if j < n and src[j] == "[":
        return (j + 1, level)
    return None


def _find_long_close(src, start, level):
    """Szuka ']' '='*level ']' od start; zwraca indeks ZA zamknięciem albo None."""
    close = "]" + "=" * level + "]"
    idx = src.find(close, start)
    if idx < 0:
        return None
    return idx + len(close)


def tokenize(src):
    toks = []
    i, n = 0, len(src)
    line, col = 1, 1

    def advance_to(new_i):
        nonlocal i, line, col
        while i < new_i and i < n:
            if src[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
            i += 1

    def err(msg, at=None):
        ln, cl = (line, col) if at is None else line_col_at(src, at)
        raise LuaError(f"{ln}:{cl}: {msg}")

    def emit(kind, val, start_i, start_line, start_col):
        toks.append(Tok(kind, val, start_i, start_line, start_col))

    while i < n:
        c = src[i]
        # białe znaki
        if c in " \t\r\n":
            advance_to(i + 1)
            continue
        # komentarz: liniowy --... albo blokowy --[[ ]] / --[==[ ]==]
        if c == "-" and i + 1 < n and src[i + 1] == "-":
            j = i + 2
            lb = _long_bracket(src, j)
            if lb is not None:
                body_start, level = lb
                end = _find_long_close(src, body_start, level)
                if end is None:
                    err("niezamknięty komentarz blokowy", i)
                advance_to(end)
                continue
            while j < n and src[j] != "\n":
                j += 1
            advance_to(j)
            continue

        start_i, start_line, start_col = i, line, col

        # długi string [[ ]] / [==[ ]==]
        if c == "[":
            lb = _long_bracket(src, i)
            if lb is not None:
                body_start, level = lb
                end = _find_long_close(src, body_start, level)
                if end is None:
                    err("niezamknięty długi string", i)
                body = src[body_start:end - (level + 2)]
                if body.startswith("\n"):
                    body = body[1:]
                emit("str", body, start_i, start_line, start_col)
                advance_to(end)
                continue
        # string
        if c == '"' or c == "'":
            quote = c
            j = i + 1
            buf = []
            while j < n and src[j] != quote:
                if src[j] == "\\" and j + 1 < n:
                    esc = src[j + 1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r",
                                "\\": "\\", '"': '"', "'": "'", "0": "\0"}.get(esc, esc))
                    j += 2
                    continue
                buf.append(src[j])
                j += 1
            if j >= n:
                err("niezamknięty string", i)
            emit("str", "".join(buf), start_i, start_line, start_col)
            advance_to(j + 1)
            continue
        # hex
        if c == "0" and i + 1 < n and src[i + 1] in "xX":
            j = i + 2
            seen_dot = False
            seen_p = False
            while j < n:
                ch = src[j]
                if ch in "0123456789abcdefABCDEF":
                    j += 1
                    continue
                if ch == "." and not seen_dot and not seen_p:
                    if j + 1 < n and src[j + 1] == ".":
                        break
                    seen_dot = True
                    j += 1
                    continue
                if ch in "pP" and not seen_p:
                    seen_p = True
                    j += 1
                    if j < n and src[j] in "+-":
                        j += 1
                    continue
                break
            text = src[i:j]
            try:
                if seen_dot or seen_p:
                    val = float.fromhex(text if seen_p else text + "p0")
                else:
                    val = _wrap64(int(text, 16))
            except ValueError:
                err(f"zła liczba: {text!r}", i)
            emit("num", val, start_i, start_line, start_col)
            advance_to(j)
            continue
        # number
        if c.isdigit() or (c == "." and i + 1 < n and src[i + 1].isdigit()):
            j = i
            seen_dot = False
            seen_exp = False
            while j < n:
                ch = src[j]
                if ch.isdigit():
                    j += 1
                    continue
                if ch == "." and not seen_dot and not seen_exp:
                    if j + 1 < n and src[j + 1] == ".":
                        break
                    seen_dot = True
                    j += 1
                    continue
                if ch in "eE" and not seen_exp:
                    seen_exp = True
                    j += 1
                    if j < n and src[j] in "+-":
                        j += 1
                    continue
                break
            text = src[i:j]
            try:
                val = float(text) if (seen_dot or seen_exp) else int(text)
            except ValueError:
                err(f"zła liczba: {text!r}", i)
            emit("num", val, start_i, start_line, start_col)
            advance_to(j)
            continue
        # name / kw
        if c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            emit("kw" if word in _KEYWORDS else "name", word, start_i, start_line, start_col)
            advance_to(j)
            continue
        # symbol
        for s in _SYMBOLS:
            if src.startswith(s, i):
                emit("sym", s, start_i, start_line, start_col)
                advance_to(i + len(s))
                break
        else:
            err(f"nieznany znak: {c!r}", i)
    toks.append(Tok("eof", None, n, line, col))
    return toks
