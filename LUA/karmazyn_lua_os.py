"""
karmazyn_lua_os — wirtualny podzbiór biblioteki 'os' (piaskownica Karmin).

DOZWOLONE (czas, bez I/O hosta):
  os.clock, os.time, os.date, os.difftime

ZAKAZANE (ambient authority):
  execute, remove, rename, getenv, setlocale, tmpname, exit, …

Czas ściany z time.time() — to nie jest FS; host może podmienić zegar
przez lib.set / wstrzyknięcie. Zegar monotoniczny od mount: os.clock.
"""

import time as _time


def register(lib):
    Error = lib.Error
    t0 = _time.perf_counter()
    t = lib.table()

    def b_clock(*_):
        return _time.perf_counter() - t0

    def b_time(tbl=None, *_):
        if tbl is None:
            return int(_time.time())
        if not lib.is_table(tbl):
            raise Error("os.time: oczekiwano tabeli")
        # pola: year, month, day, hour, min, sec
        def gi(name, default=0):
            v = lib.get(tbl, name)
            if v is None:
                return default
            return int(v)
        try:
            import datetime
            dt = datetime.datetime(
                gi("year", 1970), gi("month", 1), gi("day", 1),
                gi("hour", 0), gi("min", 0), gi("sec", 0),
            )
            return int(dt.timestamp())
        except Exception as ex:
            raise Error(f"os.time: {ex}")

    def b_difftime(t2, t1, *_):
        return float(t2) - float(t1)

    def b_date(fmt=None, tsec=None, *_):
        if fmt is None:
            fmt = "%c"
        fmt = lib.tostring(fmt) if fmt is not None else "%c"
        if tsec is None:
            ts = _time.time()
        else:
            ts = float(tsec)
        # *t / !*t → tabela
        if fmt == "*t" or fmt == "!*t":
            utc = fmt.startswith("!")
            st = _time.gmtime(ts) if utc else _time.localtime(ts)
            tb = lib.table()
            for k, v in (
                ("year", st.tm_year), ("month", st.tm_mon), ("day", st.tm_mday),
                ("hour", st.tm_hour), ("min", st.tm_min), ("sec", st.tm_sec),
                ("wday", st.tm_wday + 1), ("yday", st.tm_yday),
                ("isdst", bool(st.tm_isdst) if st.tm_isdst >= 0 else None),
            ):
                lib.set(tb, k, v)
            return tb
        # mapowanie prostych tokenów Lua → strftime
        # %Y %m %d %H %M %S %w %j %c %x %X %%
        try:
            st = _time.localtime(ts) if not fmt.startswith("!") else _time.gmtime(ts)
            if fmt.startswith("!"):
                fmt = fmt[1:]
            # Lua %c ≈ locale; użyj asctime-like
            if fmt == "%c":
                return _time.strftime("%a %b %d %H:%M:%S %Y", st)
            return _time.strftime(fmt, st)
        except Exception as ex:
            raise Error(f"os.date: {ex}")

    for name, fn in (
        ("clock", b_clock),
        ("time", b_time),
        ("difftime", b_difftime),
        ("date", b_date),
    ):
        lib.set(t, name, fn)

    lib.globalize("os", t)
