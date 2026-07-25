"""Silnik wzorców Lua (§6.5.1) — własny matcher z backtrackingiem.

Obsługa: . ^ $ [] %a%d%w%s%l%u%p%c%x%g%z (i dopełnienia) %bxy %f[set]
captures () w tym pozycyjne (), quantifiers * + - ?, backref %1..%9.
"""


def _is_class(ch, c):
    low = ch.lower()
    if low == "a":
        ok = ("A" <= c <= "Z") or ("a" <= c <= "z")
    elif low == "c":
        o = ord(c)
        ok = o < 32 or o == 127
    elif low == "d":
        ok = "0" <= c <= "9"
    elif low == "g":
        o = ord(c)
        ok = o > 32 and o != 127 and c not in " \t\n\r\f\v"
    elif low == "l":
        ok = "a" <= c <= "z"
    elif low == "p":
        o = ord(c)
        ok = o > 32 and o != 127 and not c.isalnum() and c not in " \t\n\r\f\v"
    elif low == "s":
        ok = c in " \t\n\r\f\v"
    elif low == "u":
        ok = "A" <= c <= "Z"
    elif low == "w":
        ok = c.isalnum() and ord(c) < 128
    elif low == "x":
        ok = c in "0123456789abcdefABCDEF"
    elif low == "z":
        ok = c == "\0"
    else:
        return c == ch
    return ok if ch.islower() else not ok


def _in_set(c, body, neg):
    i, n = 0, len(body)
    hit = False
    while i < n:
        if body[i] == "%" and i + 1 < n:
            if _is_class(body[i + 1], c):
                hit = True
                break
            i += 2
            continue
        if i + 2 < n and body[i + 1] == "-" and body[i + 2] != "]":
            if body[i] <= c <= body[i + 2]:
                hit = True
                break
            i += 3
            continue
        if body[i] == c:
            hit = True
            break
        i += 1
    return (not hit) if neg else hit


def _parse_set(pat, i):
    n = len(pat)
    i += 1
    neg = False
    if i < n and pat[i] == "^":
        neg = True
        i += 1
    body = []
    if i < n and pat[i] == "]":
        body.append("]")
        i += 1
    while i < n and pat[i] != "]":
        if pat[i] == "%" and i + 1 < n:
            body.append("%")
            body.append(pat[i + 1])
            i += 2
        else:
            body.append(pat[i])
            i += 1
    if i >= n:
        raise ValueError("malformed pattern (missing ']')")
    return "".join(body), neg, i + 1


def compile_pattern(pat, gmatch=False):
    """→ list of items. Item = atom | ('rep', atom, '*|+|-|?') | anchors as atoms bol/eol."""
    items = []
    i, n = 0, len(pat)
    if i < n and pat[i] == "^":
        if not gmatch:
            items.append(("bol",))
        i += 1
    while i < n:
        if pat[i] == "$" and i == n - 1:
            items.append(("eol",))
            i += 1
            break
        c = pat[i]
        if c == "%":
            if i + 1 >= n:
                raise ValueError("malformed pattern (ends with '%')")
            nch = pat[i + 1]
            if nch == "b":
                if i + 3 >= n:
                    raise ValueError("malformed pattern (missing arguments to '%b')")
                atom = ("bal", pat[i + 2], pat[i + 3])
                i += 4
            elif nch == "f":
                if i + 2 >= n or pat[i + 2] != "[":
                    raise ValueError("missing '[' after '%f' in pattern")
                body, neg, j = _parse_set(pat, i + 2)
                atom = ("front", body, neg)
                i = j
            elif nch.isdigit():
                atom = ("bref", int(nch))
                i += 2
            elif nch.lower() in "acdglpsuwxz":
                atom = ("cls", nch)
                i += 2
            else:
                atom = ("lit", nch)
                i += 2
        elif c == ".":
            atom = ("any",)
            i += 1
        elif c == "[":
            body, neg, j = _parse_set(pat, i)
            atom = ("set", body, neg)
            i = j
        elif c == "(":
            if i + 1 < n and pat[i + 1] == ")":
                atom = ("pos",)
                i += 2
            else:
                atom = ("capopen",)
                i += 1
        elif c == ")":
            atom = ("capclose",)
            i += 1
        else:
            atom = ("lit", c)
            i += 1
        if i < n and pat[i] in "*+?-":
            if atom[0] in ("bol", "eol", "capopen", "capclose", "pos", "front"):
                # front/pos are zero-width; quantifier illegal in real Lua for some
                if atom[0] in ("bol", "eol", "capopen", "capclose"):
                    raise ValueError("malformed pattern")
            mode = pat[i]
            i += 1
            items.append(("rep", atom, mode))
        else:
            items.append(atom)
    return items


class _State:
    __slots__ = ("s", "caps", "level", "cap_init")

    def __init__(self, s):
        self.s = s
        self.caps = []       # finished: (a,b) or int
        self.level = []      # open capture starts (pos)
        self.cap_init = []   # parallel: index in caps when opened


def _try_atom(st, atom, pos):
    """Jedna próba atomu (bez rep). Zwraca nową pos lub None. Mutuje st przy cap."""
    s, n = st.s, len(st.s)
    t = atom[0]
    if t == "bol":
        return pos if pos == 0 else None
    if t == "eol":
        return pos if pos == n else None
    if t == "lit":
        return pos + 1 if pos < n and s[pos] == atom[1] else None
    if t == "any":
        return pos + 1 if pos < n else None
    if t == "cls":
        return pos + 1 if pos < n and _is_class(atom[1], s[pos]) else None
    if t == "set":
        return pos + 1 if pos < n and _in_set(s[pos], atom[1], atom[2]) else None
    if t == "bal":
        op, cl = atom[1], atom[2]
        if pos >= n or s[pos] != op:
            return None
        d = 1
        j = pos + 1
        while j < n:
            if s[j] == op:
                d += 1
            elif s[j] == cl:
                d -= 1
                if d == 0:
                    return j + 1
            j += 1
        return None
    if t == "front":
        body, neg = atom[1], atom[2]
        prev = s[pos - 1] if pos > 0 else "\0"
        curr = s[pos] if pos < n else "\0"
        if (not _in_set(prev, body, neg)) and _in_set(curr, body, neg):
            return pos
        return None
    if t == "pos":
        st.caps.append(pos + 1)
        return pos
    if t == "capopen":
        st.level.append(pos)
        st.cap_init.append(len(st.caps))
        st.caps.append(None)
        return pos
    if t == "capclose":
        if not st.level:
            raise ValueError("invalid pattern capture")
        start = st.level.pop()
        idx = st.cap_init.pop()
        st.caps[idx] = (start, pos)
        return pos
    if t == "bref":
        k = atom[1]
        if k < 1 or k > len(st.caps):
            return None
        cap = st.caps[k - 1]
        if not isinstance(cap, tuple):
            return None
        a, b = cap
        frag = s[a:b]
        if s.startswith(frag, pos):
            return pos + len(frag)
        return None
    return None


def _match(st, items, ii, pos):
    """Backtracking: items[ii:] od pos → end lub None."""
    if ii >= len(items):
        return pos
    it = items[ii]
    if it[0] != "rep":
        # snapshot
        caps, level, cinit = list(st.caps), list(st.level), list(st.cap_init)
        np_ = _try_atom(st, it, pos)
        if np_ is None:
            st.caps, st.level, st.cap_init = caps, level, cinit
            return None
        r = _match(st, items, ii + 1, np_)
        if r is None:
            st.caps, st.level, st.cap_init = caps, level, cinit
        return r

    # rep
    atom, mode = it[1], it[2]
    # zbierz pozycje po 0,1,2,... dopasowaniach atomu
    positions = [pos]
    caps0, level0, cinit0 = list(st.caps), list(st.level), list(st.cap_init)
    p = pos
    max_rep = len(st.s) - pos + 1
    for _ in range(max_rep):
        caps_b, level_b, cinit_b = list(st.caps), list(st.level), list(st.cap_init)
        np_ = _try_atom(st, atom, p)
        if np_ is None or np_ == p:
            st.caps, st.level, st.cap_init = caps_b, level_b, cinit_b
            break
        positions.append(np_)
        p = np_
        if mode == "?":
            break

    # które długości legalne
    if mode == "+":
        cands = positions[1:]
    else:
        cands = positions
    if mode == "-":
        order = cands                    # non-greedy: shortest first
    else:
        order = list(reversed(cands))    # greedy

    for end in order:
        # odtwórz stan: od caps0 powtórz atom do end
        st.caps = list(caps0)
        st.level = list(level0)
        st.cap_init = list(cinit0)
        p = pos
        ok = True
        while p < end:
            np_ = _try_atom(st, atom, p)
            if np_ is None:
                ok = False
                break
            p = np_
        if not ok or p != end:
            continue
        r = _match(st, items, ii + 1, end)
        if r is not None:
            return r
    st.caps, st.level, st.cap_init = caps0, level0, cinit0
    return None


def search(s, pat, init=0, gmatch=False):
    """(start, end, captures) lub None. start/end 0-based; captures: str|int.
    ^ kotwiczy do początku CAŁEGO s (pozycja 0), nie do init.
    """
    items = compile_pattern(pat, gmatch=gmatch)
    n = len(s)
    if init < 0:
        init = 0
    if init > n:
        return None
    has_bol = bool(items and items[0][0] == "bol")
    # z ^ tylko start w 0 ma sens; jeśli init>0 — brak dopasowania
    if has_bol:
        if init > 0:
            return None
        starts = (0,)
    else:
        starts = range(init, n + 1)
    for st_pos in starts:
        st = _State(s)
        end = _match(st, items, 0, st_pos)
        if end is not None:
            return _finish(s, st_pos, end, st)
    return None


def _finish(s, start, end, st):
    outs = []
    for c in st.caps:
        if c is None:
            continue
        if isinstance(c, int):
            outs.append(c)
        else:
            a, b = c
            outs.append(s[a:b])
    return start, end, outs


def find_all(s, pat):
    pos = 0
    n = len(s)
    while pos <= n:
        r = search(s, pat, pos, gmatch=True)
        if r is None:
            return
        st, end, caps = r
        yield st, end, caps
        pos = end + 1 if end == st else end
