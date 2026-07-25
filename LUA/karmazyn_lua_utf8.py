"""
karmazyn_lua_utf8 — biblioteka utf8 (Lua 5.3+) jako osobny blok.
"""


def register(lib):
    Error = lib.Error
    t = lib.table()
    lib.set(t, "charpattern", "[\0-\x7F\xC2-\xF4][\x80-\xBF]*")

    def b_len(s, i=None, j=None, *_):
        if not isinstance(s, str):
            raise Error("utf8.len: oczekiwano stringa")
        # uproszczenie: len code points w całym stringu / sub
        if i is None and j is None:
            try:
                return len(s)  # Python str = code points
            except Exception:
                return None
        # i,j 1-based like string.sub
        n = len(s)
        i = 1 if i is None else int(i)
        j = n if j is None else int(j)
        if i < 0:
            i = n + i + 1
        if j < 0:
            j = n + j + 1
        if i < 1:
            i = 1
        if j > n:
            j = n
        if i > j:
            return 0
        return j - i + 1

    def b_char(*codes):
        chars = []
        for c in codes:
            c = int(c)
            if c < 0 or c > 0x10FFFF:
                raise Error("utf8.char: wartość poza zakresem")
            chars.append(chr(c))
        return "".join(chars)

    def b_codes(s, *_):
        if not isinstance(s, str):
            raise Error("utf8.codes: oczekiwano stringa")
        # iterator: pos, code
        state = [0]
        n = len(s)

        def it(*_a):
            i = state[0]
            if i >= n:
                return [None]
            state[0] = i + 1
            return [i + 1, ord(s[i])]

        return it

    def b_codepoint(s, i=None, j=None, *_):
        if not isinstance(s, str):
            raise Error("utf8.codepoint: oczekiwano stringa")
        n = len(s)
        i = 1 if i is None else int(i)
        j = i if j is None else int(j)
        if i < 0:
            i = n + i + 1
        if j < 0:
            j = n + j + 1
        if i < 1 or j > n or i > j:
            return []
        return [ord(s[k]) for k in range(i - 1, j)]

    def b_offset(s, n=None, i=None, *_):
        if not isinstance(s, str):
            raise Error("utf8.offset: oczekiwano stringa")
        n = 0 if n is None else int(n)
        i = 1 if i is None else int(i)
        L = len(s)
        if i < 0:
            i = L + i + 1
        if n == 0:
            return i if 1 <= i <= L + 1 else None
        if n > 0:
            pos = i + n - 1
            return pos if pos <= L + 1 else None
        pos = i + n
        return pos if pos >= 1 else None

    for name, fn in (
        ("len", b_len), ("char", b_char), ("codes", b_codes),
        ("codepoint", b_codepoint), ("offset", b_offset),
    ):
        lib.set(t, name, fn)
    lib.globalize("utf8", t)
