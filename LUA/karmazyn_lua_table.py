"""
karmazyn_lua_table — biblioteka 'table' jako OSOBNY BLOK dla interpretera KarmazynLua.

Rejestruje się przez kotwicę LuaLib. Importuje wyłącznie stdlib — nie sięga
do jądra ani wnętrza interpretera (kontrakt gościa).

Zgodność Lua 5.4/5.5: insert, remove, concat, sort (z komparatorem),
unpack, pack (z polem n).
"""


def register(lib):
    Error = lib.Error

    def need_table(t, who):
        if not lib.is_table(t):
            raise Error(f"table.{who}: oczekiwano tabeli, jest {lib.typename(t)}")
        return t

    t = lib.table()

    def b_insert(tbl, a=None, b=None, *_):
        need_table(tbl, "insert")
        n = lib.arraylen(tbl)
        if b is None:
            # insert(t, v) -> na koniec
            lib.set(tbl, n + 1, a)
        else:
            # insert(t, pos, v) -> wstaw, przesuwając w prawo
            pos = int(a)
            if pos < 1 or pos > n + 1:
                raise Error("table.insert: pozycja poza zakresem")
            for i in range(n, pos - 1, -1):
                lib.set(tbl, i + 1, lib.rawget(tbl, i))
            lib.set(tbl, pos, b)
        return None

    def b_remove(tbl, pos=None, *_):
        need_table(tbl, "remove")
        n = lib.arraylen(tbl)
        if n == 0 and pos is None:
            return None
        p = n if pos is None else int(pos)
        if n > 0 and (p < 1 or p > n + 1):
            raise Error("table.remove: pozycja poza zakresem")
        val = lib.rawget(tbl, p)
        for i in range(p, n):
            lib.set(tbl, i, lib.rawget(tbl, i + 1))
        if n > 0:
            lib.set(tbl, n, None)                    # usuń ostatni (nil = delete)
        return val

    def b_concat(tbl, sep=None, i=None, j=None, *_):
        need_table(tbl, "concat")
        sep = "" if sep is None else str(sep)
        lo = 1 if i is None else int(i)
        hi = lib.arraylen(tbl) if j is None else int(j)
        parts = []
        for k in range(lo, hi + 1):
            v = lib.rawget(tbl, k)
            if not isinstance(v, (str, int, float)) or isinstance(v, bool):
                raise Error(f"table.concat: element {k} nie jest stringiem/liczbą")
            parts.append(lib.tostring(v))
        return sep.join(parts)

    def b_sort(tbl, comp=None, *_):
        need_table(tbl, "sort")
        n = lib.arraylen(tbl)
        vals = [lib.rawget(tbl, k) for k in range(1, n + 1)]
        if comp is None:
            # domyślnie: rosnąco (liczby lub stringi jednorodnie)
            try:
                vals.sort()
            except TypeError:
                raise Error("table.sort: nieporównywalne elementy (podaj komparator)")
        else:
            import functools

            def cmp(a, b):
                r = lib.call(comp, [a, b])
                if r and r[0]:
                    return -1                        # comp(a,b) true -> a przed b
                r2 = lib.call(comp, [b, a])
                if r2 and r2[0]:
                    return 1
                return 0

            vals.sort(key=functools.cmp_to_key(cmp))
        for k, v in enumerate(vals, 1):
            lib.set(tbl, k, v)
        return None

    def b_unpack(tbl, i=None, j=None, *_):
        need_table(tbl, "unpack")
        lo = 1 if i is None else int(i)
        hi = lib.arraylen(tbl) if j is None else int(j)
        return [lib.rawget(tbl, k) for k in range(lo, hi + 1)]   # wiele wartości

    def b_pack(*args):
        p = lib.table()
        for k, v in enumerate(args, 1):
            lib.set(p, k, v)
        lib.set(p, "n", len(args))                   # Lua: pole n = liczba argumentów
        return p

    def b_move(a1, f=None, e=None, t_idx=None, a2=None, *_):
        """table.move(a1, f, e, t [, a2]) — Lua 5.3+"""
        need_table(a1, "move")
        f, e, t_idx = int(f), int(e), int(t_idx)
        dest = a1 if a2 is None else need_table(a2, "move")
        if e < f:
            return dest
        n = e - f + 1
        if dest is a1 and t_idx > f and t_idx <= e:
            buf = [lib.rawget(a1, f + i) for i in range(n)]
            for i, v in enumerate(buf):
                lib.set(dest, t_idx + i, v)
        else:
            for i in range(n):
                lib.set(dest, t_idx + i, lib.rawget(a1, f + i))
        return dest

    for name, fn in (
        ("insert", b_insert), ("remove", b_remove), ("concat", b_concat),
        ("sort", b_sort), ("unpack", b_unpack), ("pack", b_pack), ("move", b_move),
    ):
        lib.set(t, name, fn)

    lib.globalize("table", t)
    lib.globalize("unpack", b_unpack)                # alias globalny (kompatybilność)
