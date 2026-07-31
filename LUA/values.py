"""karmazyn_lua.values — wartości, helpery, typy. JEDYNY moduł pakietu, który
importuje jądro (karmazyn_kernel). Reszta pakietu importuje stąd."""

from karmazyn_kernel import Store, Bubble
import math


_ERR_DEFAULT = object()


class LuaError(Exception):
    def __init__(self, message, value=_ERR_DEFAULT, traceback=None):
        super().__init__(message if isinstance(message, str) else str(message))
        # obiekt błędu Lua: zwykle string, ale error(v) rzuca DOWOLNĄ wartością
        self.lua_value = message if value is _ERR_DEFAULT else value
        # opcjonalny pełny stack (dla hosta / eval_line); pcall dostaje lua_value
        self.traceback = traceback


# =====================================================================
#  WARTOŚCI / POMOCNICZE
#  Tabela = Bubble. nil=None, boolean=bool, number=int|float, string=str.
# =====================================================================
# zarezerwowany klucz wiązania na metatabelę. '@'-prefiks NIE jest produkowany przez
# _keyname dla żadnego klucza użytkownika (te mają i:/f:/s:/b:/t:), więc nie koliduje.
_META_KEY = "@meta"
_TBC_KEY = "@tbc"          # lista atomów to-be-closed w zakresie (bąbel)


def _keyname(k):
    """Klucz tabeli -> nazwa wiązania w bąblu (rozróżnia typy; 1.0==1)."""
    if isinstance(k, bool):
        return "b:" + ("t" if k else "f")
    if isinstance(k, int):
        return "i:" + str(k)
    if isinstance(k, float):
        if k.is_integer():
            return "i:" + str(int(k))     # Lua: t[1.0] to ten sam klucz co t[1]
        return "f:" + repr(k)
    if isinstance(k, str):
        return "s:" + k
    if k is None:
        raise LuaError("indeks tabeli jest nil")
    if isinstance(k, Bubble):
        return "t:" + str(id(k))
    raise LuaError("zły typ klucza tabeli")


# ── dostęp do WŁASNYCH wiązań bąbla pod store.lock (Kernel FIX v1.1) ──
# Nie używać surowego bubble.bindings poza tymi helperami — omija RLock
# i race z tick() w tle. Bubble.lookup chodzi po parent chain (scope);
# tabele Lua mają parent=None, ale i tak czytamy TYLKO własne pola.

def _own_aid(tb, name):
    """Id atomu własnego wiązania albo None (bez parent, pod lock)."""
    lock = getattr(tb.store, "lock", None)
    if lock is not None:
        with lock:
            return tb.bindings.get(name)
    return tb.bindings.get(name)


def _own_atom(tb, name):
    """Atom własnego wiązania albo None (bez parent, bez heat — surowy)."""
    aid = _own_aid(tb, name)
    if aid is None:
        return None
    return tb.store.get_atom(aid)


def _own_has(tb, name):
    lock = getattr(tb.store, "lock", None)
    if lock is not None:
        with lock:
            return name in tb.bindings
    return name in tb.bindings


def _own_keys(tb, skip=None):
    """Snapshot kluczy własnych wiązań (pod lock)."""
    lock = getattr(tb.store, "lock", None)
    if lock is not None:
        with lock:
            keys = list(tb.bindings.keys())
    else:
        keys = list(tb.bindings.keys())
    if skip:
        keys = [k for k in keys if k not in skip]
    return keys


def _own_unbind(tb, name):
    """Usuń własne wiązanie — Bubble.unbind (z lock w Kernelu)."""
    return tb.unbind(name)


def _array_len(tb):
    """Długość sekwencji i:1..i:n (surowe własne wiązania)."""
    n = 0
    while _own_has(tb, "i:" + str(n + 1)):
        n += 1
    return n


def _truthy(v):
    return not (v is None or v is False)


def _type(v):
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, Bubble):
        return "table"
    if isinstance(v, LuaThread):
        return "thread"
    if isinstance(v, LuaFunction) or callable(v):
        return "function"
    return "userdata"


def _fmt_num(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    # float: Lua 5.3 gwarantuje kropkę/wykładnik; inf/nan jawnie
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    if math.isnan(v):
        return "nan"
    s = "%.14g" % v
    if "." not in s and "e" not in s and "E" not in s:
        s += ".0"
    return s


def _tostring(v):
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return _fmt_num(v)
    if isinstance(v, str):
        return v
    if isinstance(v, Bubble):
        return "table: 0x%08x" % (id(v) & 0xFFFFFFFF)
    if isinstance(v, LuaFunction):
        return "function: 0x%08x" % (id(v) & 0xFFFFFFFF)
    if callable(v):
        return "function: builtin"
    return str(v)


def _tonumber(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip()
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return None
    return None


def _arith_num(v, op):
    n = _tonumber(v) if isinstance(v, str) else v
    if isinstance(n, bool) or not isinstance(n, (int, float)):
        raise LuaError(f"próba arytmetyki ({op}) na {_type(v)}")
    return n


# ── operacje całkowite/bitowe: liczby całkowite Lua to 64-bit ze znakiem ──
_MASK64 = (1 << 64) - 1


def _to_int(v):
    """Do operacji bitowych: int, float-całkowity albo string-liczba; inaczej błąd."""
    if isinstance(v, bool):
        raise LuaError("operacja bitowa wymaga liczby całkowitej, nie boola")
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v.is_integer():
            return int(v)
        raise LuaError("liczba bez całkowitej reprezentacji do operacji bitowej")
    if isinstance(v, str):
        n = _tonumber(v)
        if n is not None:
            return _to_int(n)
    raise LuaError(f"operacja bitowa na {_type(v)}")


def _wrap64(n):
    """Zawinięcie do 64-bit ze znakiem (semantyka przepełnienia liczb Lua)."""
    n &= _MASK64
    if n >= (1 << 63):
        n -= (1 << 64)
    return n


def _idiv(a, b):
    """Dzielenie całkowite // : floor(a/b). int//int->int; z float->float (floor)."""
    ai = isinstance(a, int) and not isinstance(a, bool)
    bi = isinstance(b, int) and not isinstance(b, bool)
    if ai and bi:
        if b == 0:
            raise LuaError("dzielenie całkowite przez zero")
        return a // b                                  # Python floor == Lua floor
    fa, fb = float(a), float(b)
    if fb == 0.0:                                      # float // 0 = floor(±inf/nan)
        if fa == 0.0:
            return math.nan
        return math.inf if fa > 0 else -math.inf
    q = fa / fb
    if math.isinf(q) or math.isnan(q):
        return q
    return float(math.floor(q))


def _bitshift(l, r, left):
    """<< / >> : wypełnianie zerami; ujemne przesunięcie = w drugą stronę; |n|>=64 -> 0."""
    a = _to_int(l) & _MASK64                           # wzór 64-bit bez znaku
    n = _to_int(r)
    if not left:
        n = -n                                         # >> to << o -n
    if n <= -64 or n >= 64:
        return 0
    if n >= 0:
        return _wrap64((a << n) & _MASK64)
    return _wrap64(a >> (-n))                           # logiczne (a bez znaku)


# ── predykaty: czy SUROWA operacja numeryczna się nadaje (inaczej -> metametoda) ──
_BIT_OPS = {"&", "|", "~", "<<", ">>"}

# operator -> nazwa metametody (arytmetyczne + bitowe)
_ARITH_MM = {
    "+": "__add", "-": "__sub", "*": "__mul", "/": "__div",
    "%": "__mod", "^": "__pow", "//": "__idiv",
    "&": "__band", "|": "__bor", "~": "__bxor", "<<": "__shl", ">>": "__shr",
}


def _is_real_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_concatable(v):
    """Nadaje się do surowej konkatenacji: string albo liczba (nie bool/nil/tabela)."""
    return isinstance(v, str) or _is_real_num(v)


def _is_num_or_numstr(v):
    """Nadaje się do surowej arytmetyki: liczba albo string-liczba (Lua koercja)."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        return _tonumber(v) is not None
    return False


def _bitable(v):
    """Nadaje się do surowej operacji bitowej: int / float-całkowity / string-całkowity."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    if isinstance(v, float):
        return v.is_integer()
    if isinstance(v, str):
        n = _tonumber(v)
        return n is not None and _bitable(n)
    return False


def _raw_arith(op, a, b):
    """Surowa arytmetyka na liczbach (a, b już zwalidowane)."""
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        # Lua: '/' zawsze float; dzielenie przez zero = ±inf / nan (IEEE), nie błąd
        if b == 0:
            if a == 0:
                return math.nan
            return math.inf if a > 0 else -math.inf
        return a / b
    if op == "%":
        # Lua: a % b == a - floor(a/b)*b ; int%0 = błąd, float%0 = nan
        if b == 0:
            if isinstance(a, int) and isinstance(b, int):
                raise LuaError("integer modulo przez zero")
            return math.nan
        return a - (a // b) * b                         # semantyka Lua (znak dzielnika)
    if op == "//":
        return _idiv(a, b)
    if op == "^":
        return float(a) ** float(b)                     # Lua: '^' zawsze float
    raise LuaError(f"nieznany operator: {op}")


# wartownik: „instrukcja nie ma wartości do pokazania" (vs wyrażenie == nil)
_NOVAL = object()

# strażnik pętli (while i for): w hoście bez wywłaszczania nieskończona pętla
# gościa zawiesiłaby host. Stopgap; właściwe rozwiązanie = budżet instrukcji hosta.
_LOOP_GUARD = 1_000_000


class LuaFunction:
    """Domknięcie: ciało + przechwycone środowisko (bąbel). Osiągalność env
    niesie hak `env_of` — TEN SAM mechanizm, co dla tabel. Upvalue żyją tak
    długo, jak żyje domknięcie (reach-GC)."""
    __slots__ = ("params", "body", "env", "name")

    def __init__(self, params, body, env, name="?"):
        self.params = params      # lista nazw parametrów
        self.body = body          # lista instrukcji (blok)
        self.env = env            # przechwycony zakres definicji (Bubble)
        self.name = name


class LuaThread:
    """Wątek korutyny (coroutine). status: suspended|running|normal|dead."""
    __slots__ = ("fn", "status", "gen", "name", "closed")

    def __init__(self, fn, name="thread"):
        self.fn = fn
        self.status = "suspended"
        self.gen = None           # generator _call_gen po first resume
        self.name = name
        self.closed = False       # coroutine.close


def lua_env_of(v):
    """Hak env_of dla substratu: tabela=Bubble, domknięcie=fn.env.
    Kontrakt S1: Bubble | None (deep reach niepotrzebne — Lua nie trzyma
    list domknięć jako jednej wartości Store)."""
    if isinstance(v, Bubble):
        return v
    if isinstance(v, LuaFunction):
        return v.env
    return None


def compose_phi(phi1, phi2=None):
    """φ = φ1 · φ2 — iloczyn w przestrzeni φ (Karmin).

    - dwa ndarray (HRR): splot kołowy bind (karmazyn_kernel / hrr)
    - dwa bytes/bytearray: sha256(b'phi*' + p1 + p2)
    - dwie liczby: iloczyn arytmetyczny
    - inaczej: kanoniczny token (phi1, phi2) z atrybutem .product

    Gdy phi2 is None: zwraca phi1 bez zmian (tożsamość jednoargumentowa).
    """
    if phi2 is None:
        return phi1
    # HRR bind (importlib — bez zależności AST 'numpy' w kontrakcie gościa)
    try:
        import importlib
        kk = importlib.import_module("karmazyn_kernel")
        if getattr(kk, "HAS_HRR", False) and kk.bind is not None:
            np = importlib.import_module("numpy")
            if isinstance(phi1, np.ndarray) and isinstance(phi2, np.ndarray):
                return kk.bind(phi1, phi2)
    except Exception:
        pass
    # bytes
    if isinstance(phi1, (bytes, bytearray)) and isinstance(phi2, (bytes, bytearray)):
        import hashlib
        return hashlib.sha256(b"phi*" + bytes(phi1) + bytes(phi2)).digest()
    # numbers
    if isinstance(phi1, (int, float)) and isinstance(phi2, (int, float)) \
            and not isinstance(phi1, bool) and not isinstance(phi2, bool):
        return phi1 * phi2
    # token kanoniczny
    class _Phi:
        __slots__ = ("phi1", "phi2", "product")
        def __init__(self, a, b):
            self.phi1, self.phi2 = a, b
            self.product = (a, b)
        def __repr__(self):
            return f"phi({self.phi1!r}·{self.phi2!r})"
        def __eq__(self, other):
            return isinstance(other, _Phi) and self.product == other.product
    return _Phi(phi1, phi2)


class _Return(Exception):
    """Sterowanie: powrót z funkcji (niesie wartość)."""
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


class _Break(Exception):
    """Sterowanie: wyjście z najbliższej pętli."""
    pass


class _Goto(Exception):
    """Sterowanie: skok do etykiety ::name:: (łapany przez blok, który ją ma)."""
    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name
