"""
karmazyn_lua_math — biblioteka 'math' jako OSOBNY BLOK dla interpretera KarmazynLua.

Rejestruje się przez kotwicę LuaLib (register(lib)). Importuje WYŁĄCZNIE stdlib
(math, random) — nie sięga do jądra KarmazynOS ani do wnętrza interpretera,
więc spełnia kontrakt gościa i nie powiększa rdzenia interpretera.

Zgodność: Lua 5.4/5.5 — math.type/tointeger (podtypy int/float), floor/ceil
zwracają liczby całkowite, maxinteger/mininteger 64-bit, brak math.pow/atan2
(usunięte w 5.3/5.4).
"""

import math as _m
import random as _r

_MAXINT = (1 << 63) - 1
_MININT = -(1 << 63)


def register(lib):
    Error = lib.Error

    def num(v, who):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise Error(f"math.{who}: oczekiwano liczby, jest {lib.typename(v)}")
        return v

    t = lib.table()

    # stałe
    lib.set(t, "pi", _m.pi)
    lib.set(t, "huge", _m.inf)
    lib.set(t, "maxinteger", _MAXINT)
    lib.set(t, "mininteger", _MININT)

    def b_abs(x, *_):
        return abs(num(x, "abs"))

    def b_ceil(x, *_):
        return _m.ceil(num(x, "ceil"))                 # int (5.3+)

    def b_floor(x, *_):
        return _m.floor(num(x, "floor"))               # int (5.3+)

    def b_sqrt(x, *_):
        return _m.sqrt(num(x, "sqrt"))                 # float

    def b_sin(x, *_):
        return _m.sin(num(x, "sin"))

    def b_cos(x, *_):
        return _m.cos(num(x, "cos"))

    def b_tan(x, *_):
        return _m.tan(num(x, "tan"))

    def b_asin(x, *_):
        return _m.asin(num(x, "asin"))

    def b_acos(x, *_):
        return _m.acos(num(x, "acos"))

    def b_atan(y, x=None, *_):
        y = num(y, "atan")
        return _m.atan2(y, num(x, "atan")) if x is not None else _m.atan(y)

    def b_exp(x, *_):
        return _m.exp(num(x, "exp"))

    def b_log(x, base=None, *_):
        x = num(x, "log")
        return _m.log(x, num(base, "log")) if base is not None else _m.log(x)

    def b_fmod(x, y, *_):
        return _m.fmod(num(x, "fmod"), num(y, "fmod"))

    def b_modf(x, *_):
        frac, intp = _m.modf(num(x, "modf"))
        return [intp, frac]                            # Lua: (całkowita, ułamkowa) oba float

    def b_max(*args):
        if not args:
            raise Error("math.max: brak argumentów")
        m = num(args[0], "max")
        for a in args[1:]:
            a = num(a, "max")
            if a > m:
                m = a
        return m

    def b_min(*args):
        if not args:
            raise Error("math.min: brak argumentów")
        m = num(args[0], "min")
        for a in args[1:]:
            a = num(a, "min")
            if a < m:
                m = a
        return m

    def b_type(x, *_):
        if isinstance(x, bool):
            return None
        if isinstance(x, int):
            return "integer"
        if isinstance(x, float):
            return "float"
        return None                                    # nie-liczba -> nil

    def b_tointeger(x, *_):
        if isinstance(x, bool):
            return None
        if isinstance(x, int):
            return x
        if isinstance(x, float) and x.is_integer():
            return int(x)
        return None

    def b_ult(a, b, *_):                               # unsigned less-than (64-bit)
        ua = int(num(a, "ult")) & ((1 << 64) - 1)
        ub = int(num(b, "ult")) & ((1 << 64) - 1)
        return ua < ub

    # PRNG: własny stan (nie ambient authority — żadnego I/O ani fs, tylko liczby)
    rng = _r.Random()

    def b_random(m=None, n=None, *_):
        if m is None:
            return rng.random()                        # [0,1)
        m = int(num(m, "random"))
        if n is None:
            if m == 0:
                return rng.getrandbits(63)             # Lua: random(0) = pełny zakres int
            return rng.randint(1, m)
        return rng.randint(m, int(num(n, "random")))

    def b_randomseed(x=None, *_):
        rng.seed(x if x is not None else None)
        return None

    for name, fn in (
        ("abs", b_abs), ("ceil", b_ceil), ("floor", b_floor), ("sqrt", b_sqrt),
        ("sin", b_sin), ("cos", b_cos), ("tan", b_tan),
        ("asin", b_asin), ("acos", b_acos), ("atan", b_atan),
        ("exp", b_exp), ("log", b_log), ("fmod", b_fmod), ("modf", b_modf),
        ("max", b_max), ("min", b_min), ("type", b_type), ("tointeger", b_tointeger),
        ("ult", b_ult), ("random", b_random), ("randomseed", b_randomseed),
    ):
        lib.set(t, name, fn)

    lib.globalize("math", t)
