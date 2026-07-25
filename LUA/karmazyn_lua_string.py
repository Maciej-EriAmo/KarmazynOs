"""
karmazyn_lua_string — biblioteka 'string' jako OSOBNY BLOK.

  • len/sub/byte/char/rep/reverse/lower/upper/format (podzbiór)
  • find/match/gmatch/gsub — silnik wzorców Lua (_lua_pattern):
    klasy, %bxy, %f[set], captures, *+?-
  • brak string.pack/unpack/dump (osobny blok binarny)

Ustawia metatabelę typu string z __index = string (s:sub(1,2) działa).
"""

import _lua_pattern as _lp


# ── pomocnicze indeksy 1-based (Lua) ──────────────────────────────────
def _pos(s, i, default=None):
    """Indeks Lua → 0-based Python; ujemny liczy od końca. None → default."""
    if i is None:
        return default
    if isinstance(i, float) and i.is_integer():
        i = int(i)
    if not isinstance(i, int) or isinstance(i, bool):
        return default
    n = len(s)
    if i < 0:
        i = n + i + 1
    return i


def _slice_bounds(s, i, j):
    """string.sub: i,j (1-based, ujemne OK) → (start0, end0 exclusive) lub empty."""
    n = len(s)
    i = _pos(s, 1 if i is None else i)
    j = _pos(s, n if j is None else j)
    if i is None:
        i = 1
    if j is None:
        j = n
    if i < 1:
        i = 1
    if j > n:
        j = n
    if i > j:
        return 0, 0
    return i - 1, j                                   # end exclusive = j (1-based end inclusive)


def register(lib):
    Error = lib.Error

    def need_str(v, who):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return lib.tostring(v)                     # Lua koercja number→string w string.*
        if not isinstance(v, str):
            raise Error(f"string.{who}: oczekiwano stringa, jest {lib.typename(v)}")
        return v

    def need_int(v, who, default=None):
        if v is None:
            return default
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise Error(f"string.{who}: oczekiwano liczby")
        if isinstance(v, float):
            if not v.is_integer():
                raise Error(f"string.{who}: niecałkowita")
            return int(v)
        return v

    t = lib.table()

    def b_len(s, *_):
        return len(need_str(s, "len"))

    def b_sub(s, i=None, j=None, *_):
        s = need_str(s, "sub")
        a, b = _slice_bounds(s, i, j)
        return s[a:b]

    def b_byte(s, i=None, j=None, *_):
        s = need_str(s, "byte")
        if i is None:
            i = 1
        if j is None:
            j = i
        a, b = _slice_bounds(s, i, j)
        if a >= b:
            return []
        return [ord(s[k]) for k in range(a, b)]

    def b_char(*codes):
        chars = []
        for c in codes:
            c = need_int(c, "char")
            if c < 0 or c > 255:
                # Lua 5.3+ używa wartości w zakresie bajtu / unicode — tu 0..255 jak klasycznie
                if c < 0 or c > 0x10FFFF:
                    raise Error("string.char: wartość poza zakresem")
            try:
                chars.append(chr(c))
            except ValueError:
                raise Error("string.char: wartość poza zakresem")
        return "".join(chars)

    def b_rep(s, n=None, sep=None, *_):
        s = need_str(s, "rep")
        n = need_int(n, "rep", 0)
        if n <= 0:
            return ""
        if n > 1_000_000:
            raise Error("string.rep: n zbyt duże")
        sep = "" if sep is None else need_str(sep, "rep")
        return sep.join([s] * n)

    def b_reverse(s, *_):
        return need_str(s, "reverse")[::-1]

    def b_lower(s, *_):
        return need_str(s, "lower").lower()

    def b_upper(s, *_):
        return need_str(s, "upper").upper()

    def b_format(fmt, *args):
        fmt = need_str(fmt, "format")
        # podzbiór: %s %d %i %f %g %G %q %% + proste flagi/szerokość
        out = []
        i, n, ai = 0, len(fmt), 0

        def take_arg():
            nonlocal ai
            if ai >= len(args):
                raise Error("string.format: za mało argumentów")
            v = args[ai]
            ai += 1
            return v

        while i < n:
            if fmt[i] != "%":
                out.append(fmt[i]); i += 1; continue
            if i + 1 < n and fmt[i + 1] == "%":
                out.append("%"); i += 2; continue
            j = i + 1
            # flags
            while j < n and fmt[j] in "-+ #0":
                j += 1
            # width
            while j < n and fmt[j].isdigit():
                j += 1
            if j < n and fmt[j] == ".":
                j += 1
                while j < n and fmt[j].isdigit():
                    j += 1
            if j >= n:
                raise Error("string.format: niekompletny specyfikator")
            spec = fmt[j]
            flags = fmt[i + 1:j]
            # uproszczone mapowanie na Python format
            arg = take_arg()
            # flags / width / precision → Python format mini
            # flags: - + # 0  space ; width; .prec
            fl = flags
            # wyodrębnij width i prec z fl (flags string bez cyfr na końcu jest w flags)
            # flags w naszej pętli to wszystko między % a spec: np. "08.2"
            m_flags = ""
            m_width = ""
            m_prec = ""
            k = 0
            while k < len(fl) and fl[k] in "-+ #0":
                m_flags += fl[k]; k += 1
            while k < len(fl) and fl[k].isdigit():
                m_width += fl[k]; k += 1
            if k < len(fl) and fl[k] == ".":
                k += 1
                while k < len(fl) and fl[k].isdigit():
                    m_prec += fl[k]; k += 1
            try:
                if spec == "s":
                    s = lib.tostring(arg)
                    if m_prec != "":
                        s = s[:int(m_prec)]
                    if m_width != "":
                        w = int(m_width)
                        if "-" in m_flags:
                            s = s.ljust(w)
                        else:
                            s = s.rjust(w)
                    out.append(s)
                elif spec == "q":
                    if arg is None:
                        out.append("nil")
                    elif arg is True:
                        out.append("true")
                    elif arg is False:
                        out.append("false")
                    elif isinstance(arg, (int, float)) and not isinstance(arg, bool):
                        if isinstance(arg, float):
                            out.append(f"{arg:.17g}")
                        else:
                            out.append(str(arg))
                    elif isinstance(arg, str):
                        esc = (arg.replace("\\", "\\\\").replace('"', '\\"')
                                  .replace("\n", "\\n").replace("\r", "\\r")
                                  .replace("\0", "\\0").replace("\t", "\\t"))
                        out.append('"' + esc + '"')
                    else:
                        out.append('"' + lib.tostring(arg) + '"')
                elif spec in "di":
                    num = int(arg)
                    py = "%"
                    if "-" in m_flags:
                        py += "-"
                    if "+" in m_flags:
                        py += "+"
                    if "0" in m_flags and "-" not in m_flags:
                        py += "0"
                    if m_width:
                        py += m_width
                    py += "d"
                    out.append(py % num)
                elif spec in "fFgGeE":
                    num = float(arg)
                    py = "%"
                    for ch in m_flags:
                        if ch in "-+#0 ":
                            py += ch
                    if m_width:
                        py += m_width
                    if m_prec != "":
                        py += "." + m_prec
                    elif spec in "fF" and m_prec == "":
                        py += ".6"                       # domyślna precyzja jak C
                    py += spec
                    out.append(py % num)
                elif spec == "c":
                    out.append(chr(int(arg) & 0xFF))
                elif spec in "xXo":
                    num = int(arg) & ((1 << 64) - 1)
                    py = "%"
                    if "#" in m_flags:
                        py += "#"
                    if "0" in m_flags:
                        py += "0"
                    if m_width:
                        py += m_width
                    py += spec
                    out.append(py % num)
                elif spec == "u":
                    num = int(arg) & ((1 << 64) - 1)
                    out.append(str(num))
                else:
                    raise Error(f"string.format: nieobsługiwany specyfikator %{spec}")
            except Error:
                raise
            except Exception as ex:
                raise Error(f"string.format: {ex}")
            i = j + 1
        return "".join(out)

    def _norm_init(s, init, who):
        n = len(s)
        init = need_int(init, who, 1)
        if init < 0:
            init = n + init + 1
        if init < 1:
            init = 1
        return init, n

    def _find_impl(s, pattern, init, plain, who):
        s = need_str(s, who)
        pattern = need_str(pattern, who)
        init, n = _norm_init(s, init, who)
        if init > n + 1:
            return None
        start0 = init - 1
        if plain:
            k = s.find(pattern, start0)
            if k < 0:
                return None
            return [k + 1, k + len(pattern)]
        try:
            r = _lp.search(s, pattern, start0)
        except ValueError as e:
            raise Error(f"string.{who}: {e}")
        if r is None:
            return None
        a, b, caps = r
        return [a + 1, b] + list(caps)

    def b_find(s, pattern, init=None, plain=None, *_):
        r = _find_impl(s, pattern, init, plain, "find")
        return r if r is not None else None

    def b_match(s, pattern, init=None, *_):
        s = need_str(s, "match")
        pattern = need_str(pattern, "match")
        init, n = _norm_init(s, init, "match")
        start0 = init - 1
        try:
            r = _lp.search(s, pattern, start0)
        except ValueError as e:
            raise Error(f"string.match: {e}")
        if r is None:
            return None
        a, b, caps = r
        if caps:
            return caps if len(caps) > 1 else caps[0]
        return s[a:b]

    def b_gmatch(s, pattern, init=None, *_):
        s = need_str(s, "gmatch")
        pattern = need_str(pattern, "gmatch")
        try:
            gen = _lp.find_all(s, pattern)
        except ValueError as e:
            raise Error(f"string.gmatch: {e}")
        it = iter(gen)

        def iterator(*_a):
            try:
                a, b, caps = next(it)
            except StopIteration:
                return [None]
            if caps:
                return list(caps)
            return [s[a:b]]

        return iterator

    def b_gsub(s, pattern, repl, n=None, *_):
        s = need_str(s, "gsub")
        pattern = need_str(pattern, "gsub")
        maxn = need_int(n, "gsub", None)
        count = 0
        out = []
        pos = 0
        nlen = len(s)
        try:
            while pos <= nlen:
                if maxn is not None and count >= maxn:
                    out.append(s[pos:])
                    break
                r = _lp.search(s, pattern, pos)
                if r is None:
                    out.append(s[pos:])
                    break
                a, b, caps = r
                out.append(s[pos:a])
                whole = s[a:b]
                count += 1
                # zamiennik
                if isinstance(repl, str):
                    parts = []
                    k, L = 0, len(repl)
                    while k < L:
                        if repl[k] == "%" and k + 1 < L:
                            d = repl[k + 1]
                            if d == "%":
                                parts.append("%"); k += 2; continue
                            if d.isdigit():
                                idx = int(d)
                                if idx == 0:
                                    parts.append(whole)
                                elif 1 <= idx <= len(caps):
                                    c = caps[idx - 1]
                                    parts.append(c if isinstance(c, str) else lib.tostring(c))
                                else:
                                    parts.append("")
                                k += 2
                                continue
                        parts.append(repl[k]); k += 1
                    out.append("".join(parts))
                elif lib.is_table(repl):
                    key = caps[0] if caps else whole
                    if not isinstance(key, str):
                        key = lib.tostring(key)
                    v = lib.get(repl, key)
                    if v is None or v is False:
                        out.append(whole)
                    else:
                        out.append(lib.tostring(v))
                elif callable(repl) or hasattr(repl, "params"):
                    args = list(caps) if caps else [whole]
                    res = lib.call(repl, args)
                    v = res[0] if res else None
                    if v is None or v is False:
                        out.append(whole)
                    else:
                        out.append(lib.tostring(v))
                else:
                    raise Error("string.gsub: zły typ zamiennika")
                if b == a:
                    if a < nlen:
                        out.append(s[a])
                        pos = b + 1
                    else:
                        pos = b + 1
                        break
                else:
                    pos = b
        except ValueError as e:
            raise Error(f"string.gsub: {e}")
        return ["".join(out), count]

    # ── string.pack / unpack / packsize (podzbiór §6.5.2) ──
    import struct as _struct

    def _pack_iter(fmt):
        """Yield (code, size_or_None, endian_prefix) for each option in fmt."""
        i, n = 0, len(fmt)
        endian = "@"  # native; map to struct: < > =
        while i < n:
            c = fmt[i]
            if c in " \t\n\r":
                i += 1
                continue
            if c == "<":
                endian = "<"; i += 1; continue
            if c == ">":
                endian = ">"; i += 1; continue
            if c == "=":
                endian = "="; i += 1; continue
            if c == "!":
                i += 1
                while i < n and fmt[i].isdigit():
                    i += 1
                continue  # alignment — ignored (podzbiór)
            if c == "x":
                yield ("x", 1, endian); i += 1; continue

            def _digits(ii):
                j = ii
                while j < n and fmt[j].isdigit():
                    j += 1
                if j == ii:
                    return None, ii
                return int(fmt[ii:j]), j

            if c in "bBhHiIlLqQfdTjn":
                i += 1
                num, i = _digits(i)
                # map with optional size (i4/I4 → 4-byte int)
                code_map = {
                    "b": ("b", 1), "B": ("B", 1),
                    "h": ("h", 2), "H": ("H", 2),
                    "i": ("i", 4), "I": ("I", 4),
                    "l": ("q", 8), "L": ("Q", 8),
                    "q": ("q", 8), "Q": ("Q", 8),
                    "f": ("f", 4), "d": ("d", 8),
                    "T": ("I", 4), "j": ("q", 8), "J": ("Q", 8), "n": ("d", 8),
                }
                sc, default_sz = code_map[c]
                size = num if num is not None else default_sz
                # explicit size for i/I: pick struct code by size
                if c in "iI" and num is not None:
                    signed = c == "i"
                    by_sz = {1: "bB", 2: "hH", 4: "iI", 8: "qQ"}
                    pair = by_sz.get(num)
                    if not pair:
                        raise Error(f"string.pack: zły rozmiar i/I ({num})")
                    sc = pair[0] if signed else pair[1]
                    size = num
                yield ("num", sc, size, endian)
                continue
            if c == "c":
                i += 1
                num, i = _digits(i)
                yield ("c", num or 1, endian); continue
            if c == "s":
                i += 1
                num, i = _digits(i)
                yield ("s", num, endian); continue
            if c == "z":
                yield ("z", None, endian); i += 1; continue
            raise Error(f"string.pack: nieobsługiwany format '{c}'")

    def _struct_code(sc, endian):
        pref = {"<": "<", ">": ">", "=": "=", "@": "@"}.get(endian, "@")
        return pref + sc

    def b_pack(fmt, *values):
        fmt = need_str(fmt, "pack")
        out = bytearray()
        vi = 0
        try:
            for item in _pack_iter(fmt):
                code = item[0]
                if code == "x":
                    out.append(0); continue
                if code == "c":
                    _, sz, endian = item
                    if vi >= len(values):
                        raise Error("string.pack: za mało argumentów")
                    s = need_str(values[vi], "pack"); vi += 1
                    raw = s.encode("latin-1", errors="replace")[:sz]
                    out.extend(raw.ljust(sz, b"\0")); continue
                if code == "s":
                    _, sz, endian = item
                    if vi >= len(values):
                        raise Error("string.pack: za mało argumentów")
                    s = need_str(values[vi], "pack"); vi += 1
                    raw = s.encode("latin-1", errors="replace")
                    if sz is None:
                        out.extend(_struct.pack(_struct_code("I", endian), len(raw)))
                        out.extend(raw)
                    else:
                        out.extend(raw[:sz].ljust(sz, b"\0"))
                    continue
                if code == "z":
                    if vi >= len(values):
                        raise Error("string.pack: za mało argumentów")
                    s = need_str(values[vi], "pack"); vi += 1
                    out.extend(s.encode("latin-1", errors="replace") + b"\0")
                    continue
                if code == "num":
                    _, sc, size, endian = item
                    if vi >= len(values):
                        raise Error("string.pack: za mało argumentów")
                    v = values[vi]; vi += 1
                    out.extend(_struct.pack(_struct_code(sc, endian),
                                            v if not isinstance(v, bool) else int(v)))
                    continue
        except Error:
            raise
        except Exception as ex:
            raise Error(f"string.pack: {ex}")
        return out.decode("latin-1")

    def b_packsize(fmt, *_):
        fmt = need_str(fmt, "packsize")
        total = 0
        for item in _pack_iter(fmt):
            code = item[0]
            if code == "x":
                total += 1
            elif code == "c":
                total += item[1]
            elif code == "s":
                if item[1] is None:
                    raise Error("string.packsize: format zmiennej długości")
                total += item[1]
            elif code == "z":
                raise Error("string.packsize: format zmiennej długości")
            elif code == "num":
                _, sc, size, endian = item
                total += _struct.calcsize(_struct_code(sc, endian))
        return total

    def b_unpack(fmt, s, pos=None, *_):
        fmt = need_str(fmt, "unpack")
        s = need_str(s, "unpack")
        data = s.encode("latin-1", errors="replace")
        pos = 1 if pos is None else need_int(pos, "unpack")
        if pos < 0:
            pos = len(data) + pos + 1
        i = pos - 1
        vals = []
        try:
            for item in _pack_iter(fmt):
                code = item[0]
                if code == "x":
                    i += 1; continue
                if code == "c":
                    _, sz, endian = item
                    chunk = data[i:i + sz]; i += sz
                    vals.append(chunk.decode("latin-1")); continue
                if code == "z":
                    j = data.find(b"\0", i)
                    if j < 0:
                        raise Error("string.unpack: brak terminatora z")
                    vals.append(data[i:j].decode("latin-1")); i = j + 1; continue
                if code == "s":
                    _, sz, endian = item
                    if sz is None:
                        sc = _struct_code("I", endian)
                        ln = _struct.unpack_from(sc, data, i)[0]
                        i += _struct.calcsize(sc)
                        vals.append(data[i:i + ln].decode("latin-1")); i += ln
                    else:
                        vals.append(data[i:i + sz].decode("latin-1")); i += sz
                    continue
                if code == "num":
                    _, sc, size, endian = item
                    scf = _struct_code(sc, endian)
                    v = _struct.unpack_from(scf, data, i)[0]
                    i += _struct.calcsize(scf)
                    vals.append(v)
        except Error:
            raise
        except Exception as ex:
            raise Error(f"string.unpack: {ex}")
        vals.append(i + 1)  # next position (1-based)
        return vals

    for name, fn in (
        ("len", b_len), ("sub", b_sub), ("byte", b_byte), ("char", b_char),
        ("rep", b_rep), ("reverse", b_reverse), ("lower", b_lower), ("upper", b_upper),
        ("format", b_format), ("find", b_find), ("match", b_match),
        ("gmatch", b_gmatch), ("gsub", b_gsub),
        ("pack", b_pack), ("unpack", b_unpack), ("packsize", b_packsize),
    ):
        lib.set(t, name, fn)

    lib.globalize("string", t)

    # metatabela typu string: __index = string  →  s:sub(1,2) działa
    mt = lib.table()
    lib.set(mt, "__index", t)
    lib.set_type_metatable("string", mt)
