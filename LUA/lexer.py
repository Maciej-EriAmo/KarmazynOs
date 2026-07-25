"""karmazyn_lua.lexer — tokenizacja."""

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
    __slots__ = ("kind", "val", "pos")

    def __init__(self, kind, val, pos):
        self.kind = kind        # 'name' 'kw' 'num' 'str' 'sym' 'eof'
        self.val = val
        self.pos = pos

    def __repr__(self):
        return f"Tok({self.kind},{self.val!r})"


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
    while i < n:
        c = src[i]
        # białe znaki
        if c in " \t\r\n":
            i += 1
            continue
        # komentarz: liniowy --... albo blokowy --[[ ]] / --[==[ ]==] (poziomy)
        if c == "-" and i + 1 < n and src[i + 1] == "-":
            j = i + 2
            lb = _long_bracket(src, j)
            if lb is not None:
                body_start, level = lb
                end = _find_long_close(src, body_start, level)
                if end is None:
                    raise LuaError("niezamknięty komentarz blokowy")
                i = end
                continue
            while j < n and src[j] != "\n":
                j += 1
            i = j
            continue

        # długi string [[ ]] / [==[ ]==] (pierwsza nowa linia po otwarciu pomijana)
        if c == "[":
            lb = _long_bracket(src, i)
            if lb is not None:
                body_start, level = lb
                end = _find_long_close(src, body_start, level)
                if end is None:
                    raise LuaError("niezamknięty długi string")
                body = src[body_start:end - (level + 2)]
                if body.startswith("\n"):
                    body = body[1:]                     # Lua: pierwszy \n pomijany
                toks.append(Tok("str", body, i))
                i = end
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
                raise LuaError("niezamknięty string")
            toks.append(Tok("str", "".join(buf), i))
            i = j + 1
            continue
        # liczba szesnastkowa: 0x / 0X. Całkowite zawijają do 64-bit (0xFF...FF = -1),
        # z kropką lub wykładnikiem 'p' -> float hex (np. 0x1.8p3 = 12.0).
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
                        break                          # '..' to konkatenacja, nie liczba
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
                    val = _wrap64(int(text, 16))       # hex int -> 64-bit ze znakiem
            except ValueError:
                raise LuaError(f"zła liczba: {text!r}")
            toks.append(Tok("num", val, i))
            i = j
            continue
        # liczba: część całkowita, opcjonalnie JEDNA kropka, opcjonalny wykładnik.
        # Kluczowe: nie pochłaniaj '..' (operator konkatenacji) ani drugiej kropki.
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
                        break                        # '..' to konkatenacja, nie liczba
                    seen_dot = True
                    j += 1
                    continue
                if ch in "eE" and not seen_exp:
                    seen_exp = True
                    j += 1
                    if j < n and src[j] in "+-":      # znak wykładnika
                        j += 1
                    continue
                break
            text = src[i:j]
            try:
                val = float(text) if (seen_dot or seen_exp) else int(text)
            except ValueError:
                raise LuaError(f"zła liczba: {text!r}")
            toks.append(Tok("num", val, i))
            i = j
            continue
        # nazwa / słowo kluczowe
        if c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            toks.append(Tok("kw" if word in _KEYWORDS else "name", word, i))
            i = j
            continue
        # symbol
        for s in _SYMBOLS:
            if src.startswith(s, i):
                toks.append(Tok("sym", s, i))
                i += len(s)
                break
        else:
            raise LuaError(f"nieznany znak: {c!r}")
    toks.append(Tok("eof", None, n))
    return toks
