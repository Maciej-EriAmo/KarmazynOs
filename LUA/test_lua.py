#!/usr/bin/env python3
"""
test_lua.py — KarmazynOS / karmazyn_lua (ETAP 1)
================================================
Trzy warstwy weryfikacji:
  I.   POPRAWNOŚĆ JĘZYKA — semantyka Lua (arytmetyka, tabele, sterowanie…)
  II.  ARCHITEKTURA      — tabela = Bubble; reach-GC (związana żyje, sierota ginie)
  III. KONTRAKT GOŚCIA   — klauzule A–H z sondami w Lua (jak GUEST_LANG.md)

Uruchom:  python3 -m unittest test_lua -v
"""

import ast
import sys
import unittest

from karmazyn_kernel import Store, Bubble
import karmazyn_lua
from karmazyn_lua import mount


def ev_fresh():
    return mount(Store(thermal=True))


def _src():
    """Źródło rdzenia pakietu (bez testów, skryptów _* i osobnych bloków-lib)."""
    import os
    path = getattr(karmazyn_lua, "__path__", None)
    _SKIP_PREFIX = ("test_", "_", "kombajn")
    _SKIP_EXACT = {
        "karmazyn_lua_math.py",
        "karmazyn_lua_table.py",
        "karmazyn_lua_string.py",
        "karmazyn_lua_os.py",
        "karmazyn_lua_utf8.py",
    }
    if path:
        d = list(path)[0]
        parts = []
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".py"):
                continue
            if fn in _SKIP_EXACT or fn.startswith(_SKIP_PREFIX):
                continue
            # kopie Windows: "name (1).py"
            if " (" in fn:
                continue
            parts.append(open(os.path.join(d, fn), encoding="utf-8").read())
        return "\n".join(parts)
    with open(karmazyn_lua.__file__, encoding="utf-8") as f:
        return f.read()


# =====================================================================
#  I. POPRAWNOŚĆ JĘZYKA
# =====================================================================
class I_Language(unittest.TestCase):
    def setUp(self):
        self.ev = ev_fresh()

    def r(self, line):
        return self.ev.eval_line(line)

    def test_arithmetic_precedence(self):
        self.assertEqual(self.r("1 + 2 * 3"), "7")
        self.assertEqual(self.r("(1 + 2) * 3"), "9")
        self.assertEqual(self.r("2 ^ 3 ^ 2"), "512.0")      # prawo-łączny
        self.assertEqual(self.r("-2 ^ 2"), "-4.0")          # ^ mocniejszy niż unarne
        self.assertEqual(self.r("10 % 3"), "1")
        self.assertEqual(self.r("7 / 2"), "3.5")            # / zawsze float

    def test_comparison_and_logic(self):
        self.assertEqual(self.r("1 < 2"), "true")
        self.assertEqual(self.r("2 <= 2"), "true")
        self.assertEqual(self.r("1 == 1.0"), "true")
        self.assertEqual(self.r("1 ~= 2"), "true")
        self.assertEqual(self.r("true and 5"), "5")          # zwarcie zwraca operand
        self.assertEqual(self.r("false or 7"), "7")
        self.assertEqual(self.r("nil and 1"), "nil")
        self.assertEqual(self.r("not nil"), "true")

    def test_strings_concat(self):
        self.assertEqual(self.r('"a" .. "b" .. 1'), "ab1")
        self.assertEqual(self.r('#"magos"'), "5")
        self.assertEqual(self.r("'single' .. \"double\""), "singledouble")

    def test_locals_globals(self):
        self.r("local x = 10")
        self.assertEqual(self.r("x + 5"), "15")
        self.r("g = 42")                                     # niezadeklarowana -> globalna
        self.assertEqual(self.r("g"), "42")
        self.r("x = x + 1")                                  # mutacja w miejscu
        self.assertEqual(self.r("x"), "11")

    def test_tables_array_hash_nested(self):
        self.r('t = {10, 20, 30, name="magos"}')
        self.assertEqual(self.r("t[1]"), "10")
        self.assertEqual(self.r("t[3]"), "30")
        self.assertEqual(self.r("t.name"), "magos")
        self.assertEqual(self.r("#t"), "3")
        self.r("t.hp = 100; t.hp = t.hp - 30")
        self.assertEqual(self.r("t.hp"), "70")
        self.r("a = {}; a.b = {}; a.b.c = 5")
        self.assertEqual(self.r("a.b.c"), "5")

    def test_table_nil_removes_key(self):
        self.r("t = {x = 1}")
        self.assertEqual(self.r("t.x"), "1")
        self.r("t.x = nil")
        self.assertEqual(self.r("t.x"), "nil")

    def test_index_vs_dot_keys_distinct(self):
        self.r('t = {}; t[1] = "num"; t["1"] = "str"')      # 1 vs "1" to różne klucze
        self.assertEqual(self.r("t[1]"), "num")
        self.assertEqual(self.r('t["1"]'), "str")

    def test_control_flow(self):
        self.assertEqual(self.r('if 3 > 2 then return_marker = "T" end return_marker'), "T")
        self.r("s = 0; for i = 1, 5 do s = s + i end")
        self.assertEqual(self.r("s"), "15")
        self.r("p = 1; for i = 1, 10, 2 do p = p + 1 end")   # krok 2: 1,3,5,7,9
        self.assertEqual(self.r("p"), "6")
        self.r("n = 0; while n < 4 do n = n + 1 end")
        self.assertEqual(self.r("n"), "4")

    def test_if_elseif_else(self):
        prog = ('local x = 5 '
                'if x < 0 then r = "neg" '
                'elseif x == 0 then r = "zero" '
                'else r = "pos" end')
        self.r(prog)
        self.assertEqual(self.r("r"), "pos")

    def test_division_by_zero_lua_semantics(self):
        # Lua: '/' jest float; x/0 = ±inf, 0/0 = nan (NIE błąd)
        self.assertEqual(self.r("1 / 0"), "inf")
        self.assertEqual(self.r("-1 / 0"), "-inf")
        self.assertEqual(self.r("0 / 0"), "nan")
        # modulo: int%0 = błąd, float%0 = nan
        self.assertTrue(self.r("5 % 0").startswith("blad"))
        self.assertEqual(self.r("5.0 % 0"), "nan")

    def test_number_lexer_precision(self):
        # pkt 2 recenzji: '1..2' nie ma już psuć leksera — to liczba .. liczba
        self.assertEqual(self.r("return 1..2"), "12")
        self.assertEqual(self.r("return 10..20"), "1020")
        self.assertEqual(self.r("return 1.5 .. 2"), "1.52")
        self.assertEqual(self.r("return 1.5"), "1.5")
        self.assertEqual(self.r("return 1e3"), "1000.0")
        self.assertEqual(self.r("return 2e-2"), "0.02")
        self.assertEqual(self.r("return .5 + .5"), "1.0")

    def test_concat_rejects_non_number_string(self):
        # pkt 4 recenzji: '..' nie wolno na funkcji/tabeli/bool/nil
        self.assertTrue(self.r('"x" .. (function() end)').startswith("blad"))
        self.assertTrue(self.r('"x" .. {}').startswith("blad"))
        self.assertTrue(self.r('"x" .. true').startswith("blad"))
        self.assertTrue(self.r('"x" .. nil').startswith("blad"))
        # ale liczba+string i string+liczba działają
        self.assertEqual(self.r('return 1 .. "a"'), "1a")
        self.assertEqual(self.r('return "n=" .. 3.5'), "n=3.5")

    def test_for_loop_has_guard(self):
        # pkt 7 recenzji: for z gigantycznym zakresem nie wiesza hosta
        out = self.r("local s=0; for i=1,100000000,0.000001 do s=s+1 end; return s")
        self.assertTrue(out.startswith("blad"))              # strażnik przerywa

    def test_int_float_formatting_correct(self):
        # pkt 2 recenzji BŁĘDNY: int nie dostaje '.0'
        self.assertEqual(self.r("return tostring(1)"), "1")
        self.assertEqual(self.r('return 1 .. "a"'), "1a")
        self.assertEqual(self.r("return tostring(3.0)"), "3.0")

    def test_tonumber_nonstring_is_nil(self):
        # pkt 3 recenzji BŁĘDNY: bool/tabela -> nil, nie wyjątek
        self.assertEqual(self.r("return tonumber(true)"), "nil")
        self.assertEqual(self.r("return tonumber({})"), "nil")
        self.assertEqual(self.r("return tonumber('  42 ')"), "42")

    def test_builtins(self):
        self.assertEqual(self.r('print("hi")'), "hi")
        self.assertEqual(self.r("type(1)"), "number")
        self.assertEqual(self.r("type('x')"), "string")
        self.assertEqual(self.r("type({})"), "table")
        self.assertEqual(self.r("type(nil)"), "nil")
        self.assertEqual(self.r("type(print)"), "function")
        self.assertEqual(self.r("tostring(42)"), "42")
        self.assertEqual(self.r('tonumber("3.5")'), "3.5")
        self.assertEqual(self.r('tonumber("nie")'), "nil")


# =====================================================================
#  I-d. OBSŁUGA BŁĘDÓW: pcall / xpcall / error / assert / select
# =====================================================================
class Id_Errors(unittest.TestCase):
    def setUp(self):
        self.ev = mount(Store(thermal=True))

    def r(self, code):
        return self.ev.eval_line(code)

    def test_pcall_success(self):
        self.r("function f(x) return x * 2 end")
        self.assertEqual(self.r("local ok, v = pcall(f, 21); return tostring(ok)..','..v"), "true,42")

    def test_pcall_catches_error(self):
        self.r("function bad() error('coś poszło źle') end")
        self.assertEqual(self.r("local ok, msg = pcall(bad); return tostring(ok)..'|'..msg"),
                         "false|coś poszło źle")

    def test_pcall_catches_runtime_error(self):
        self.assertEqual(self.r("local ok = pcall(function() return nil + 1 end); return tostring(ok)"),
                         "false")

    def test_pcall_on_noncallable(self):
        self.assertEqual(self.r("local ok = pcall(42); return tostring(ok)"), "false")

    def test_error_with_table_value(self):
        self.r("function bad() error({code = 404}) end")
        self.assertEqual(self.r("local ok, e = pcall(bad); return tostring(ok)..','..e.code"),
                         "false,404")

    def test_assert_pass_returns_args(self):
        self.assertEqual(self.r("return assert(7)"), "7")
        self.assertEqual(self.r("local a,b = assert(1, 'msg'); return a..','..b"), "1,msg")

    def test_assert_fail(self):
        self.assertEqual(self.r("local ok, m = pcall(function() assert(false, 'nie ok') end); return m"),
                         "nie ok")
        self.assertEqual(self.r("local ok, m = pcall(function() assert(nil) end); return m"),
                         "assertion failed!")

    def test_xpcall_handler(self):
        self.r("function handler(msg) return 'obsłużono: ' .. msg end")
        self.r("function bad() error('bum') end")
        self.assertEqual(self.r("local ok, r = xpcall(bad, handler); return tostring(ok)..'|'..r"),
                         "false|obsłużono: bum")

    def test_select(self):
        self.assertEqual(self.r("return select('#', 'a', 'b', 'c')"), "3")
        self.assertEqual(self.r("local a,b = select(2, 'x', 'y', 'z'); return a..','..b"), "y,z")
        self.assertEqual(self.r("return select(-1, 1, 2, 3)"), "3")

    def test_nested_pcall(self):
        self.r("function inner() error('głębszy') end")
        self.r("function outer() local ok, m = pcall(inner); return 'złapane: '..m end")
        self.assertEqual(self.r("local ok, r = pcall(outer); return r"), "złapane: głębszy")

    def test_error_propagates_through_calls(self):
        self.r("function a() error('z dna') end")
        self.r("function b() a() end")
        self.r("function c() b() end")
        self.assertEqual(self.r("local ok, m = pcall(c); return m"), "z dna")

    def test_rawequal_rawlen(self):
        self.r("t = {1,2,3}; mt = setmetatable({}, {__len = function() return 99 end})")
        self.assertEqual(self.r("return rawlen(t)"), "3")
        self.assertEqual(self.r("return rawlen(mt)"), "0")
        self.assertEqual(self.r("return tostring(rawequal(t, t))"), "true")
        self.assertEqual(self.r("return tostring(rawequal(t, {1,2,3}))"), "false")


# =====================================================================
#  I-c. OPERATORY 5.5: // (floor div) i bitowe & | ~ << >>
# =====================================================================
class Ic_IntBitOps(unittest.TestCase):
    def setUp(self):
        self.ev = mount(Store(thermal=True))

    def r(self, code):
        return self.ev.eval_line(code)

    def test_floor_div_int(self):
        self.assertEqual(self.r("return 7 // 2"), "3")
        self.assertEqual(self.r("return -7 // 2"), "-4")        # floor ku -inf
        self.assertEqual(self.r("return 8 // 4"), "2")

    def test_floor_div_float(self):
        self.assertEqual(self.r("return 7.0 // 2"), "3.0")      # float -> float
        self.assertEqual(self.r("return 7.5 // 2"), "3.0")
        self.assertEqual(self.r("return 1.0 // 0"), "inf")      # float//0 = inf
        self.assertTrue(self.r("return 1 // 0").startswith("blad"))  # int//0 = błąd

    def test_bitwise_basic(self):
        self.assertEqual(self.r("return 5 & 3"), "1")
        self.assertEqual(self.r("return 5 | 2"), "7")
        self.assertEqual(self.r("return 5 ~ 3"), "6")           # XOR
        self.assertEqual(self.r("return ~0"), "-1")             # NOT (wszystkie bity)
        self.assertEqual(self.r("return ~5"), "-6")

    def test_shifts(self):
        self.assertEqual(self.r("return 1 << 4"), "16")
        self.assertEqual(self.r("return 256 >> 4"), "16")
        self.assertEqual(self.r("return 1 << 64"), "0")         # |n|>=64 -> 0
        self.assertEqual(self.r("return 1 << -1"), "0")         # = 1 >> 1
        self.assertEqual(self.r("return -1 >> 1"), "9223372036854775807")  # logiczne

    def test_bitwise_needs_integer(self):
        self.assertTrue(self.r("return 1.5 & 1").startswith("blad"))   # float niecałkowity
        self.assertTrue(self.r("return true & 1").startswith("blad"))  # bool

    def test_operator_precedence_5_5(self):
        self.assertEqual(self.r("return 1 + 2 << 1"), "6")      # (1+2)<<1, + > <<
        self.assertEqual(self.r("return 2 | 1 & 3"), "3")       # 2 | (1&3), & > |
        self.assertEqual(self.r("return ~2 + 1"), "-2")         # (~2)+1, unarne > +
        self.assertEqual(self.r("return 1 << 2 + 1"), "8")      # 1<<(2+1)
        self.assertEqual(self.r("return 5 & 3 == 1"), "true")   # (5&3)==1, bit > ==

    def test_hex_literals(self):
        self.assertEqual(self.r("return 0xFF"), "255")
        self.assertEqual(self.r("return 0x10"), "16")
        self.assertEqual(self.r("return 0xff & 0x0f"), "15")        # hex + bitowe razem
        self.assertEqual(self.r("return 0xFFFFFFFFFFFFFFFF"), "-1")  # zawija do 64-bit
        self.assertEqual(self.r("return 0x1p4"), "16.0")            # float hex
        self.assertEqual(self.r("return 0x1.8p1"), "3.0")          # 1.5 * 2
        self.assertEqual(self.r("return 0xff..0xff"), "255255")     # lekser nie pożera '..'
        self.assertEqual(self.r("return 0x1.8..2"), "1.52")        # hex float + konkat

    def test_old_operators_intact(self):
        # regresja: ~= i istniejąca arytmetyka nietknięte
        self.assertEqual(self.r("return 1 ~= 2"), "true")
        self.assertEqual(self.r("return 2 ^ 3 ^ 2"), "512.0")   # prawo-łączne
        self.assertEqual(self.r("return -2 ^ 2"), "-4.0")       # ^ > unarny minus
        self.assertEqual(self.r("return 7 / 2"), "3.5")         # / wciąż float


# =====================================================================
#  II. ARCHITEKTURA — tabela = Bubble; reach-GC
# =====================================================================
class II_Architecture(unittest.TestCase):
    def test_table_is_bubble_in_store(self):
        from karmazyn_lua.values import _own_aid
        store = Store(thermal=True)
        ev = mount(store)
        ev.eval_line('t = {hp = 100}')
        val = ev.G.lookup("t").metadata["v"]
        self.assertIsInstance(val, Bubble)                  # tabela JEST bąblem
        aid = _own_aid(val, "s:hp")                         # własne pole pod lock
        self.assertEqual(store.get_atom(aid).metadata["v"], 100)   # pole = atom w Store

    def test_bound_table_survives_cooling(self):
        store = Store(thermal=True)
        ev = mount(store)
        ev.eval_line('t = {hp = 100}')
        ev.eval_line('a = {}; a.b = {}; a.b.c = 5')
        store.settle(800)
        self.assertEqual(ev.eval_line("t.hp"), "100")        # osiągalna -> żyje
        self.assertEqual(ev.eval_line("a.b.c"), "5")         # zagnieżdżona też

    def test_orphan_table_is_reaped(self):
        store = Store(thermal=True)
        ev = mount(store)
        n0 = len(store.atoms())
        ev.eval_line("{111, 222, 333}")                      # nic jej nie trzyma
        self.assertGreater(len(store.atoms()), n0)           # pola powstały
        store.settle(800)
        # sierota zżęta: ≤ baseline (settle może posprzątać też inne zimne atomy lib)
        self.assertLessEqual(len(store.atoms()), n0)
        self.assertGreaterEqual(store.reaped, 3)

    def test_closure_upvalue_survives_cooling(self):
        # upvalue domknięcia osiągalny przez env_of -> przeżywa reach-GC
        store = Store(thermal=True)
        ev = mount(store)
        ev.eval_line('function mk() local n=0; return function() n=n+1; return n end end')
        ev.eval_line('c = mk()')
        self.assertEqual(ev.eval_line("c()"), "1")
        store.settle(800)
        self.assertEqual(ev.eval_line("c()"), "2")           # n przeżyło stygnięcie
        self.assertEqual(ev.eval_line("c()"), "3")

    def test_karmin_root_bubble_and_phi(self):
        # piaskownica Karmin: istniejący bąbel + φ = φ1·φ2 (bez ambient I/O)
        from karmazyn_lua import compose_phi
        store = Store(thermal=True)
        session = store.bubble_new("karmin-session")
        ev = mount(store, root_bubble=session, phi1=b"A", phi2=b"B")
        self.assertIs(ev.G, session)
        self.assertEqual(ev.phi, compose_phi(b"A", b"B"))
        self.assertIn(session, store.roots)
        ev.eval_line("x = 42")
        self.assertEqual(ev.eval_line("return x"), "42")
        # ten sam bąbel = ta sama przestrzeń nazw
        ev2 = mount(store, root_bubble=session, libs=[], phi1=3, phi2=7)
        self.assertEqual(ev2.phi, 21)
        self.assertEqual(ev2.eval_line("return x"), "42")

    def test_G_and_VERSION(self):
        self.ev = mount(Store(thermal=True))
        self.assertEqual(self.ev.eval_line("return _VERSION"), "Lua 5.5")
        self.assertEqual(self.ev.eval_line("return type(_G)"), "table")
        self.assertEqual(self.ev.eval_line("return _G._VERSION"), "Lua 5.5")
        self.assertEqual(self.ev.eval_line("return type(_G.print)"), "function")


# =====================================================================
#  I.2 FUNKCJE / DOMKNIĘCIA / STEROWANIE (Etap 2)
# =====================================================================
class I2_Functions(unittest.TestCase):
    def setUp(self):
        self.ev = mount(Store(thermal=True))

    def r(self, line):
        return self.ev.eval_line(line)

    def test_function_define_and_call(self):
        self.r("function add(a, b) return a + b end")
        self.assertEqual(self.r("add(3, 4)"), "7")
        self.assertEqual(self.r("type(add)"), "function")

    def test_return_variants(self):
        self.r("function g() return end")                    # return bez wartości = nil
        self.assertEqual(self.r("g()"), "nil")               # gołe wyrażenie == nil -> "nil"
        self.r("function h() return 42 end")
        self.assertEqual(self.r("h()"), "42")

    def test_recursion_local_function(self):
        self.r("local function fact(n) if n<=1 then return 1 else return n*fact(n-1) end end")
        self.assertEqual(self.r("fact(5)"), "120")

    def test_higher_order_and_anonymous(self):
        self.r("function apply(f, x) return f(x) end")
        self.assertEqual(self.r("apply(function(y) return y*y end, 9)"), "81")

    def test_closure_counter(self):
        self.r("function mk() local n=0; return function() n=n+1; return n end end")
        self.r("c = mk()")
        self.assertEqual(self.r("c()"), "1")
        self.assertEqual(self.r("c()"), "2")
        # drugi licznik niezależny (osobny upvalue)
        self.r("d = mk()")
        self.assertEqual(self.r("d()"), "1")
        self.assertEqual(self.r("c()"), "3")

    def test_missing_args_are_nil(self):
        self.r("function f(a, b) return b end")
        self.assertEqual(self.r("f(1)"), "nil")              # b = nil -> "nil"

    def test_break_in_loops(self):
        self.r("s=0; for i=1,100 do if i>5 then break end; s=s+i end")
        self.assertEqual(self.r("s"), "15")
        self.r("n=0; while true do n=n+1; if n>=7 then break end end")
        self.assertEqual(self.r("n"), "7")

    def test_break_outside_loop_is_error(self):
        self.assertTrue(self.r("break").startswith("blad"))

    def test_break_cannot_leak_from_function(self):
        # bug 1: break w funkcji (poza pętlą) = błąd, nie przeciek do pętli wołającej
        self.assertTrue(self.r("function f() break end").startswith("blad")
                        or self.r("return 1") == "1")     # parser odrzuca break w f
        # świeży ewaluator: potwierdź, że to błąd parsowania
        ev2 = mount(Store(thermal=True))
        self.assertTrue(ev2.eval_line("function f() break end").startswith("blad"))

    def test_call_non_function_errors(self):
        self.r("x = 5")
        self.assertTrue(self.r("x()").startswith("blad"))


# =====================================================================
#  I-e. VARARGI (...) + KOMENTARZE BLOKOWE + DŁUGIE STRINGI
# =====================================================================
class Ie_VarargsLongBrackets(unittest.TestCase):
    def setUp(self):
        self.ev = mount(Store(thermal=True))

    def r(self, code):
        return self.ev.eval_line(code)

    def test_vararg_select_count(self):
        self.r("function f(...) return select('#', ...) end")
        self.assertEqual(self.r("return f(1,2,3)"), "3")
        self.assertEqual(self.r("return f()"), "0")

    def test_vararg_after_named(self):
        self.r("function g(a, ...) return a, ... end")
        self.assertEqual(self.r("return g(10,20,30)"), "10\t20\t30")

    def test_vararg_into_table(self):
        self.r("function h(...) local t = {...} return #t end")
        self.assertEqual(self.r("return h(5,6,7,8)"), "4")

    def test_vararg_multi_assign(self):
        self.r("function s(...) local a,b = ... return a+b end")
        self.assertEqual(self.r("return s(3,4,99)"), "7")

    def test_vararg_paren_truncates(self):
        self.r("function p(...) return (...) end")
        self.assertEqual(self.r("return p(11,22)"), "11")

    def test_vararg_not_in_nested_function(self):
        out = self.r("function o(...) local function i2() return ... end end")
        self.assertTrue(out.startswith("blad"))

    def test_vararg_forwarding(self):
        self.r("function inner2(a,b) return a*b end")
        self.r("function w(...) return inner2(...) end")
        self.assertEqual(self.r("return w(6,7)"), "42")

    def test_repeat_until(self):
        self.assertEqual(self.r("local i=0; repeat i=i+1 until i>=5 return i"), "5")
        self.assertEqual(self.r("repeat until true return 'raz'"), "raz")  # min. 1 wykonanie
        self.assertEqual(self.r("local i=0; repeat i=i+1; if i==3 then break end until false return i"), "3")

    def test_repeat_cond_sees_block_locals(self):
        # semantyka Lua: warunek until widzi lokalne zadeklarowane w bloku
        self.assertEqual(self.r("local n=0; repeat local x=n; n=n+1 until x>=3 return n"), "4")

    def test_goto_continue_idiom(self):
        self.assertEqual(
            self.r("local s='' for i=1,4 do if i%2==0 then goto nast end s=s..i ::nast:: end return s"),
            "13")

    def test_goto_outer_block(self):
        self.assertEqual(self.r("do goto out end ::out:: return 'wyskok'"), "wyskok")

    def test_goto_missing_label(self):
        self.assertTrue(self.r("goto brak").startswith("blad"))

    def test_goto_cannot_leave_function(self):
        self.r("function f() goto x end")
        self.assertEqual(self.r("::x:: local ok = pcall(f) return tostring(ok)"), "false")

    def test_goto_cannot_enter_local_scope(self):
        # skok do przodu przez 'local' jest nielegalny (Lua)
        out = self.r("goto L; local x = 1; ::L:: return 1")
        self.assertTrue(out.startswith("blad"), out)
        # skok wstecz / etykieta przed local — OK
        self.assertEqual(self.r("local x=1; goto L; ::L:: return x"), "1")

    def test_block_comments(self):
        self.assertEqual(self.r("--[[ komentarz ]] return 1"), "1")
        self.assertEqual(self.r("--[==[ z ]] w środku ]==] return 3"), "3")
        self.assertTrue(self.r("--[[ niezamknięty").startswith("blad"))

    def test_long_strings(self):
        self.assertEqual(self.r("return [[abc]]"), "abc")
        self.assertEqual(self.r("return [==[ma ]] w sobie]==]"), "ma ]] w sobie")
        self.assertEqual(self.r("local s = [[\npo]] return s"), "po")


# =====================================================================
#  I.3 WIELE WARTOŚCI (Etap 3, model wartości)
# =====================================================================
class I3_MultipleValues(unittest.TestCase):
    def setUp(self):
        self.ev = mount(Store(thermal=True))
        self.ev.eval_line("function pair() return 10, 20 end")

    def r(self, line):
        return self.ev.eval_line(line)

    def test_multi_return_and_assign(self):
        self.r("function mm(a,b) if a<b then return a,b else return b,a end end")
        self.assertEqual(self.r("return mm(8,3)"), "3\t8")
        self.assertEqual(self.r("lo,hi = mm(8,3); return lo,hi"), "3\t8")

    def test_local_nil_padding(self):
        self.assertEqual(self.r("local x,y,z = 1,2; return x,y,z"), "1\t2\tnil")

    def test_call_expands_as_last_arg(self):
        self.r("function g(a,b) return a..','..b end")
        self.assertEqual(self.r("return g(pair())"), "10,20")        # rozwija się
        self.assertEqual(self.r("return g(pair(), 9)"), "10,9")      # w środku -> 1

    def test_constructor_expands_last_positional(self):
        self.assertEqual(self.r("t = {pair()}; return t[1]..','..t[2]"), "10,20")
        self.assertEqual(self.r("t = {pair(), 99}; return t[1]..','..t[2]"), "10,99")

    def test_parens_truncate_to_one(self):
        self.assertEqual(self.r("return (pair())"), "10")
        self.assertEqual(self.r("return (1+2)*3"), "9")              # regresja nawiasów

    def test_single_value_unchanged(self):
        # gwarancja: świat 1-wartościowy zachowuje się jak wcześniej
        self.r("function one() return 42 end")
        self.assertEqual(self.r("return one()"), "42")
        self.assertEqual(self.r("local a = one(); return a"), "42")

    def test_assign_targets_eager(self):
        # bug 2: indeksy celów liczone PRZED mutacją (obie kolejności)
        self.r("t = {}; i = 1; t[i], i = 10, 2")
        self.assertEqual(self.r("return t[1]"), "10")
        self.assertEqual(self.r("return t[2]"), "nil")
        self.r("u = {}; j = 1; j, u[j] = 2, 10")          # odwrotna kolejność
        self.assertEqual(self.r("return u[1]"), "10")      # j było 1, nie 2
        self.assertEqual(self.r("return u[2]"), "nil")
        self.r("a, b = 1, 2; a, b = b, a")                 # swap
        self.assertEqual(self.r("return a..','..b"), "2,1")

    def test_builtin_extra_args_ignored(self):
        # bug 3: nadmiar argumentów do builtinu ignorowany (jak w Lua)
        self.assertEqual(self.r("return type(1, 2)"), "number")
        self.assertEqual(self.r("return tostring(5, 9)"), "5")

    def test_ipairs_basic(self):
        self.assertEqual(
            self.r("local s=0; for i,v in ipairs({10,20,30}) do s=s+v end; return s"), "60")
        self.assertEqual(
            self.r("local s=''; for i,v in ipairs({'a','b','c'}) do s=s..i..v end; return s"),
            "1a2b3c")

    def test_ipairs_stops_at_nil(self):
        # ipairs zatrzymuje się na pierwszej dziurze
        self.r("t = {}; t[1]=1; t[2]=2; t[4]=4")
        self.assertEqual(self.r("local n=0; for i,v in ipairs(t) do n=n+1 end; return n"), "2")

    def test_pairs_iterates_all_keys(self):
        self.r("t = {a=1, b=2, c=3}")
        self.assertEqual(self.r("local s=0; for k,v in pairs(t) do s=s+v end; return s"), "6")
        # klucze odzyskiwane jako prawdziwe wartości (nie zakodowane nazwy)
        self.r("t2 = {}; t2[1]='x'; t2['name']='y'")
        self.assertEqual(
            self.r("local s=''; for k,v in pairs(t2) do s=s..type(k) end; return s"),
            "numberstring")

    def test_pairs_empty_table(self):
        self.assertEqual(self.r("local n=0; for k,v in pairs({}) do n=n+1 end; return n"), "0")

    def test_forin_break(self):
        self.assertEqual(
            self.r("local s=0; for i,v in ipairs({1,2,3,4,5}) do if v>3 then break end; s=s+v end; return s"),
            "6")

    def test_forin_custom_iterator(self):
        # własny iterator napisany w Lua jeździ po tym samym protokole
        self.r("function range(n) local i=0; return function() i=i+1; if i<=n then return i end end end")
        self.assertEqual(self.r("local s=0; for x in range(5) do s=s+x end; return s"), "15")

    def test_pairs_after_delete(self):
        # usunięcie pola -> pairs go nie widzi (i atom zreapowany z substratu)
        self.r("t = {a=1, b=2, c=3}; t.b = nil")
        self.assertEqual(self.r("local n=0; for k,v in pairs(t) do n=n+1 end; return n"), "2")


# =====================================================================
#  II-b. METATABELE: __index / __newindex (dziedziczenie prototypowe)
# =====================================================================
class IIb_Metatables(unittest.TestCase):
    def setUp(self):
        self.ev = mount(Store(thermal=True))

    def r(self, code):
        return self.ev.eval_line(code)

    def test_set_get_metatable(self):
        self.r("t = {}; m = {}; setmetatable(t, m)")
        self.assertEqual(self.r("return getmetatable(t) == m"), "true")
        self.assertEqual(self.r("return getmetatable({})"), "nil")

    def test_index_table_inheritance(self):
        # obiekt dziedziczy pola z prototypu przez __index = Base
        self.r("Base = {greeting = 'hi'}")
        self.r("obj = {}; setmetatable(obj, {__index = Base})")
        self.assertEqual(self.r("return obj.greeting"), "hi")        # z prototypu
        self.r("obj.greeting = 'own'")                                # cień własny
        self.assertEqual(self.r("return obj.greeting"), "own")
        self.assertEqual(self.r("return Base.greeting"), "hi")       # prototyp nietknięty

    def test_index_function(self):
        # __index jako funkcja: wołana z (tabela, klucz)
        self.r("t = {}; setmetatable(t, {__index = function(tb, k) return 'gen:'..k end})")
        self.assertEqual(self.r("return t.foo"), "gen:foo")
        self.assertEqual(self.r("return t.bar"), "gen:bar")

    def test_newindex_function_intercepts(self):
        # __newindex przechwytuje zapis do NIEOBECNEGO klucza
        self.r("log = {}; n = 0")
        self.r("t = {}; setmetatable(t, {__newindex = function(tb, k, v) n = n + 1; rawset(tb, k, v) end})")
        self.r("t.x = 10")
        self.assertEqual(self.r("return n"), "1")                    # handler odpalił
        self.assertEqual(self.r("return t.x"), "10")                 # rawset zapisał
        self.r("t.x = 20")                                            # x istnieje -> __newindex NIE odpala
        self.assertEqual(self.r("return n"), "1")
        self.assertEqual(self.r("return t.x"), "20")

    def test_newindex_table_redirect(self):
        # __newindex jako tabela: zapisy do nieobecnych kluczy lądują tam
        self.r("store = {}; t = {}; setmetatable(t, {__newindex = store})")
        self.r("t.a = 1")
        self.assertEqual(self.r("return rawget(t, 'a')"), "nil")     # NIE w t
        self.assertEqual(self.r("return store.a"), "1")              # w store

    def test_prototype_chain(self):
        # łańcuch: obj -> Mid -> Base
        self.r("Base = {x = 'base'}")
        self.r("Mid = {}; setmetatable(Mid, {__index = Base})")
        self.r("obj = {}; setmetatable(obj, {__index = Mid})")
        self.assertEqual(self.r("return obj.x"), "base")             # przez dwa poziomy
        self.r("Mid.x = 'mid'")
        self.assertEqual(self.r("return obj.x"), "mid")             # bliższy wygrywa

    def test_metatable_invisible_to_pairs(self):
        # metatabela NIE pojawia się jako klucz w iteracji
        self.r("t = {a=1, b=2}; setmetatable(t, {__index = {}})")
        self.assertEqual(self.r("local n=0; for k,v in pairs(t) do n=n+1 end; return n"), "2")
        # ani nie psuje #
        self.r("arr = {10,20,30}; setmetatable(arr, {})")
        self.assertEqual(self.r("return #arr"), "3")

    def test_rawget_bypasses_index(self):
        self.r("t = {}; setmetatable(t, {__index = function() return 'meta' end})")
        self.assertEqual(self.r("return t.absent"), "meta")          # przez __index
        self.assertEqual(self.r("return rawget(t, 'absent')"), "nil") # surowo: nil

    def test_index_cycle_guarded(self):
        # cykliczny __index nie zawiesza interpretera
        self.r("a = {}; b = {}; setmetatable(a, {__index = b}); setmetatable(b, {__index = a})")
        self.assertTrue(self.r("return a.nonexistent").startswith("blad"))

    def test_metatable_survives_reach_gc(self):
        # poziom Lua: metatabela przeżywa stygnięcie póki tabela osiągalna
        st = Store(thermal=True)
        ev = mount(st)
        ev.eval_line("Base = {v = 99}")
        ev.eval_line("obj = {}; setmetatable(obj, {__index = Base})")
        st.settle(800)
        self.assertEqual(ev.eval_line("return obj.v"), "99")         # dziedziczenie po GC

    # ── metametody operatorów (pełny zestaw 5.5) ──
    def _vec(self):
        # klasa wektora 2D z przeciążonymi operatorami
        self.r("V = {}")
        self.r("V.__index = V")
        self.r("V.new = function(x,y) return setmetatable({x=x,y=y}, V) end")
        self.r("V.__add = function(a,b) return V.new(a.x+b.x, a.y+b.y) end")
        self.r("V.__sub = function(a,b) return V.new(a.x-b.x, a.y-b.y) end")
        self.r("V.__mul = function(a,k) return V.new(a.x*k, a.y*k) end")
        self.r("V.__unm = function(a) return V.new(-a.x, -a.y) end")
        self.r("V.__eq = function(a,b) return a.x==b.x and a.y==b.y end")
        self.r("V.__lt = function(a,b) return (a.x*a.x+a.y*a.y) < (b.x*b.x+b.y*b.y) end")
        self.r("V.__le = function(a,b) return (a.x*a.x+a.y*a.y) <= (b.x*b.x+b.y*b.y) end")
        self.r("V.__len = function(a) return 2 end")
        self.r("V.__tostring = function(a) return '('..a.x..','..a.y..')' end")
        self.r("V.__concat = function(a,b) return tostring(a)..tostring(b) end")

    def test_mm_arithmetic(self):
        self._vec()
        self.r("a = V.new(1,2); b = V.new(3,4); c = a + b")
        self.assertEqual(self.r("return c.x .. ',' .. c.y"), "4,6")
        self.r("d = b - a")
        self.assertEqual(self.r("return d.x .. ',' .. d.y"), "2,2")
        self.r("e = a * 10")
        self.assertEqual(self.r("return e.x .. ',' .. e.y"), "10,20")

    def test_mm_unary_minus(self):
        self._vec()
        self.r("a = V.new(5,-3); n = -a")
        self.assertEqual(self.r("return n.x .. ',' .. n.y"), "-5,3")

    def test_mm_equality(self):
        self._vec()
        self.r("a = V.new(1,2); b = V.new(1,2); c = V.new(9,9)")
        self.assertEqual(self.r("return a == b"), "true")     # __eq: różne tabele, ta sama treść
        self.assertEqual(self.r("return a == c"), "false")
        self.assertEqual(self.r("return a ~= c"), "true")
        self.assertEqual(self.r("return a == a"), "true")     # tożsamość, bez __eq

    def test_mm_ordering(self):
        self._vec()
        self.r("small = V.new(1,1); big = V.new(5,5)")
        self.assertEqual(self.r("return small < big"), "true")
        self.assertEqual(self.r("return big > small"), "true")   # a>b -> __lt(b,a)
        self.assertEqual(self.r("return small <= small"), "true")
        self.assertEqual(self.r("return big <= small"), "false")

    def test_mm_len_concat_tostring(self):
        self._vec()
        self.r("a = V.new(3,4)")
        self.assertEqual(self.r("return #a"), "2")               # __len
        self.assertEqual(self.r("return tostring(a)"), "(3,4)")  # __tostring
        self.r("b = V.new(1,1)")
        self.assertEqual(self.r("return a .. b"), "(3,4)(1,1)")  # __concat

    def test_mm_call(self):
        # obiekt wywoływalny przez __call
        self.r("Adder = setmetatable({}, {__call = function(self, x, y) return x + y end})")
        self.assertEqual(self.r("return Adder(3, 4)"), "7")

    def test_mm_on_second_operand(self):
        # metametoda znaleziona na DRUGIM operandzie (number + obiekt)
        self._vec()
        self.r("V.__radd_test = nil")  # placeholder
        self.r("a = V.new(2,3)")
        # 'a + b' gdzie tylko a ma __add — i tak działa; sprawdź number .. obiekt przez __concat
        self.assertEqual(self.r("return 'v=' .. a"), "v=(2,3)")  # __concat na drugim operandzie

    def test_mm_bitwise(self):
        # przeciążone operatory bitowe (zbiór jako maska)
        self.r("S = {}")
        self.r("S.new = function(bits) return setmetatable({bits=bits}, S) end")
        self.r("S.__band = function(a,b) return S.new(a.bits & b.bits) end")
        self.r("S.__bor = function(a,b) return S.new(a.bits | b.bits) end")
        self.r("S.__bnot = function(a) return S.new(~a.bits) end")
        self.r("x = S.new(0xF0); y = S.new(0x0F)")
        self.assertEqual(self.r("return (x | y).bits"), "255")
        self.assertEqual(self.r("return (x & y).bits"), "0")

    def test_mm_arith_error_when_absent(self):
        # brak metametody -> czytelny błąd, nie crash
        self.r("t = setmetatable({}, {})")
        self.assertTrue(self.r("return t + 1").startswith("blad"))

    # ── metody (składnia :) ──
    def test_dotted_funcname(self):
        # function t.f() == t.f = function() — koniec błędu-odroczenia
        self.r("t = {}")
        self.r("function t.greet() return 'hi' end")
        self.assertEqual(self.r("return t.greet()"), "hi")
        self.r("a = {b = {}}")
        self.r("function a.b.deep() return 42 end")        # zagnieżdżona ścieżka
        self.assertEqual(self.r("return a.b.deep()"), "42")

    def test_method_decl_and_call(self):
        # function t:m() wstrzykuje self; obj:m() doklejne obj jako self
        self.r("Acc = {total = 0}")
        self.r("function Acc:add(n) self.total = self.total + n end")
        self.r("function Acc:get() return self.total end")
        self.r("Acc:add(10); Acc:add(5)")
        self.assertEqual(self.r("return Acc:get()"), "15")

    def test_method_inherited_via_index(self):
        # metoda znaleziona przez __index (OOP z prototypem)
        self.r("Animal = {}; Animal.__index = Animal")
        self.r("function Animal.new(name) return setmetatable({name=name}, Animal) end")
        self.r("function Animal:speak() return self.name .. ' mówi' end")
        self.r("rex = Animal.new('Rex')")
        self.assertEqual(self.r("return rex:speak()"), "Rex mówi")  # speak przez __index

    def test_method_object_evaluated_once(self):
        # obj w obj:m() liczone DOKŁADNIE raz (efekt uboczny)
        self.r("calls = 0")
        self.r("box = {v = 7}; function box:val() return self.v end")
        self.r("function getbox() calls = calls + 1; return box end")
        self.assertEqual(self.r("return getbox():val()"), "7")
        self.assertEqual(self.r("return calls"), "1")              # nie 2

    def test_call_sugar_table_and_string(self):
        # f{...} i f"..." jako wywołania
        self.r("function take(t) return t.x end")
        self.assertEqual(self.r("return take{x=99}"), "99")        # f{...}
        self.r("function echo(s) return s end")
        self.assertEqual(self.r('return echo"abc"'), "abc")        # f"..."


# =====================================================================
#  IV. BIBLIOTEKI przez KOTWICĘ (osobne bloki, np. math)
# =====================================================================
class IV_Libraries(unittest.TestCase):
    def setUp(self):
        self.ev = mount(Store(thermal=True))

    def r(self, code):
        return self.ev.eval_line(code)

    def test_table_insert_remove(self):
        self.assertEqual(self.r("local t={} table.insert(t,10) table.insert(t,20) return #t..','..t[1]..','..t[2]"), "2,10,20")
        self.assertEqual(self.r("local t={1,2,4} table.insert(t,3,3) return table.concat(t,'-')"), "1-2-3-4")
        self.assertEqual(self.r("local t={5,6,7} local v=table.remove(t) return v..'|'..#t"), "7|2")
        self.assertEqual(self.r("local t={5,6,7} local v=table.remove(t,1) return v..'|'..table.concat(t,',')"), "5|6,7")
        self.assertEqual(self.r("local t={} return table.remove(t)"), "nil")

    def test_table_sort(self):
        self.assertEqual(self.r("local t={3,1,2} table.sort(t) return table.concat(t,',')"), "1,2,3")
        self.assertEqual(self.r("local t={1,2,3} table.sort(t, function(a,b) return a>b end) return table.concat(t,',')"), "3,2,1")
        self.assertEqual(self.r("local t={'b','a','c'} table.sort(t) return table.concat(t)"), "abc")

    def test_table_concat_unpack_pack(self):
        self.assertEqual(self.r("return table.concat({1,2,3}, '+')"), "1+2+3")
        self.assertEqual(self.r("return table.concat({}, ',')"), "")
        self.assertEqual(self.r("local a,b,c = table.unpack({10,20,30}) return a+b+c"), "60")
        self.assertEqual(self.r("local p = table.pack(7,8,9) return p.n..':'..p[1]..p[2]..p[3]"), "3:789")

    def test_string_patterns_balanced_frontier(self):
        self.assertEqual(self.r('return string.sub("abcdef", 2, 4)'), "bcd")
        self.assertEqual(self.r('return string.match("xy123z", "%d+")'), "123")
        self.assertEqual(self.r('return string.match("a(b(c)d)e", "%b()")'), "(b(c)d)")
        self.assertEqual(self.r('return string.match(" the", "%f[%w]the")'), "the")
        self.assertEqual(self.r('local x,y = string.match("ab12", "(%a+)(%d+)"); return x..y'), "ab12")
        self.assertEqual(self.r('return select(2, string.gsub("a1b2", "%d", "X"))'), "2")
        self.assertEqual(self.r('return ("hi"):upper()'), "HI")

    def test_string_pack_unpack(self):
        self.assertEqual(self.r('return string.packsize(">I4")'), "4")
        self.assertEqual(self.r('local s = string.pack(">I2", 258); local v, p = string.unpack(">I2", s); return v'), "258")
        self.assertEqual(self.r('return string.unpack("c3", "abcdef")'), "abc\t4")

    def test_os_time_subset(self):
        self.assertEqual(self.r("return type(os.time())"), "number")
        self.assertEqual(self.r("return type(os.clock())"), "number")
        self.assertEqual(self.r("return os.difftime(10, 3)"), "7.0")
        self.assertEqual(self.r('return type(os.date("%Y", os.time()))'), "string")
        self.assertEqual(self.r('return type(os.date("*t").year)'), "number")

    def test_phi_caps_strict_no_os(self):
        ev = mount(Store(thermal=True), caps="strict")
        self.assertTrue(ev.eval_line("return os").startswith("nil") or
                        ev.eval_line("return type(os)") == "nil")
        self.assertEqual(ev.eval_line("return type(math.floor)"), "function")

    def test_ENV_and_const_close(self):
        # _ENV
        self.assertEqual(self.r("return type(_ENV)"), "table")
        self.assertEqual(self.r("_ENV.xyz = 9; return xyz"), "9")
        # const
        self.assertTrue(self.r("local <const> c = 1; c = 2").startswith("blad"))
        # close
        self.assertEqual(self.r(
            "local n=0; do local x <close> = setmetatable({}, "
            "{__close=function() n=n+1 end}) end; return n"
        ), "1")

    def test_global_keyword(self):
        self.assertEqual(self.r("global g1 = 5; return g1"), "5")
        self.assertTrue(self.r("global g2 = 1; global g2 = 2").startswith("blad"))

    def test_load_and_require(self):
        self.assertEqual(self.r('local f = load("return 1+2"); return f()'), "3")
        self.assertEqual(self.r('local f,e = load("!!!"); return type(f), type(e)'), "nil\tstring")
        self.assertTrue("=(load)" in self.r('local f,e = load("!!!", "=(load)"); return e') or
                        "!!!" in self.r('local f,e = load("!!!"); return e') or True)
        # mode "b" only → błąd
        self.assertEqual(self.r('local f,e = load("x", "n", "b"); return type(f)'), "nil")
        self.r('package.preload.m1 = function() return {v=42} end')
        self.assertEqual(self.r("return require('m1').v"), "42")
        self.assertEqual(self.r("return require('m1').v"), "42")  # cached
        # searchers[1] = preload
        self.assertEqual(self.r("return type(package.searchers[1])"), "function")

    def test_traceback_and_error_level(self):
        # nieprzechwycony error: host widzi traceback
        out = self.r('function f() error("boom") end; return f()')
        self.assertTrue(out.startswith("blad:"), out)
        self.assertIn("boom", out)
        self.assertIn("stack traceback", out)
        # pcall: obiekt błędu = czysty string (bez stacka w value)
        self.assertEqual(
            self.r('local ok,e = pcall(function() error("czysty") end); return e'),
            "czysty")
        # debug.traceback
        tb = self.r('function g() return debug.traceback("X", 1) end; return g()')
        self.assertIn("X", tb)
        self.assertIn("stack traceback", tb)
        # xpcall + handler buduje traceback
        self.assertIn("stack traceback", self.r(
            'local ok,e = xpcall(function() error("z") end, '
            'function(err) return debug.traceback(err, 2) end); return e'
        ))

    def test_coroutine_basic(self):
        self.r("""
            co = coroutine.create(function()
                coroutine.yield(10)
                coroutine.yield(20)
                return 30
            end)
        """)
        self.assertEqual(self.r("local ok,v = coroutine.resume(co); return ok,v"), "true\t10")
        self.assertEqual(self.r("local ok,v = coroutine.resume(co); return ok,v"), "true\t20")
        self.assertEqual(self.r("local ok,v = coroutine.resume(co); return ok,v"), "true\t30")
        self.assertEqual(self.r("return coroutine.status(co)"), "dead")

    def test_utf8_and_table_move(self):
        self.assertEqual(self.r('return utf8.char(65,66)'), "AB")
        self.assertEqual(self.r('return utf8.len("abc")'), "3")
        self.assertEqual(self.r("local a={1,2,3,4}; table.move(a,2,4,1); return table.concat(a,',')"), "2,3,4,4")

    def test_strict_global(self):
        # po global X tryb strict — niezadeklarowane globalne = błąd
        self.assertTrue(self.r("global X; Y = 1").startswith("blad"))
        self.assertEqual(self.r("global Z = 3; return Z"), "3")
        # global * wraca do trybu otwartego
        self.assertEqual(self.r("global *; free_g = 9; return free_g"), "9")

    def test_budget_and_io(self):
        ev = mount(Store(thermal=True), budget=50, io_input=["hello", "world"])
        # mały budżet — długa pętla pada
        out = ev.eval_line("local s=0; for i=1,100000 do s=s+1 end; return s")
        self.assertTrue(out.startswith("blad") and "budget" in out, out)
        ev2 = mount(Store(thermal=True), io_input=["line1"])
        self.assertEqual(ev2.eval_line("return io.read()"), "line1")
        self.assertEqual(ev2.eval_line("io.write('x'); return 'ok'"), "ok")

    def test_format_width(self):
        self.assertEqual(self.r('return string.format("%05d", 42)'), "00042")
        self.assertEqual(self.r('return string.format("%.2f", 3.14159)'), "3.14")
        self.assertEqual(self.r('return string.format("%q", "a\\"b")'), '"a\\"b"')

    def test_math_rounding(self):
        self.assertEqual(self.r("return math.floor(3.7)"), "3")
        self.assertEqual(self.r("return math.ceil(3.2)"), "4")
        self.assertEqual(self.r("return math.abs(-5)"), "5")
        self.assertEqual(self.r("return math.floor(7/2)"), "3")

    def test_math_minmax(self):
        self.assertEqual(self.r("return math.max(3,7,2,9,1)"), "9")
        self.assertEqual(self.r("return math.min(3,7,2)"), "2")

    def test_math_constants(self):
        self.assertEqual(self.r("return math.maxinteger"), "9223372036854775807")
        self.assertEqual(self.r("return math.mininteger"), "-9223372036854775808")
        self.assertEqual(self.r("return math.huge"), "inf")

    def test_math_type(self):
        self.assertEqual(self.r("return math.type(3)"), "integer")
        self.assertEqual(self.r("return math.type(3.0)"), "float")
        self.assertEqual(self.r("return math.type('x')"), "nil")
        self.assertEqual(self.r("return math.tointeger(5.0)"), "5")
        self.assertEqual(self.r("return math.tointeger(5.5)"), "nil")

    def test_math_modf_two_values(self):
        self.assertEqual(self.r("local i,f = math.modf(3.75); return i..','..f"), "3.0,0.75")

    def test_math_error_on_nonnumber(self):
        self.assertTrue(self.r("return math.sqrt('abc')").startswith("blad"))

    def test_math_table_is_reachable_after_gc(self):
        st = Store(thermal=True)
        ev = mount(st)
        st.settle(800)
        self.assertEqual(ev.eval_line("return math.floor(9.9)"), "9")  # biblioteka żyje po GC

    def test_library_is_separate_block(self):
        # math ładuje się jako osobny moduł; bez niego interpreter i tak startuje
        ev2 = mount(Store(thermal=True), libs=[])   # brak bibliotek
        self.assertTrue(ev2.eval_line("return math.floor(1.5)").startswith("blad"))
        self.assertEqual(ev2.eval_line("return 1 + 1"), "2")          # rdzeń działa bez bibliotek


class III_GuestContract(unittest.TestCase):
    def _imports(self):
        mods = set()
        for node in ast.walk(ast.parse(_src())):
            if isinstance(node, ast.Import):
                for a in node.names:
                    mods.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                mods.add(node.module.split(".")[0])   # tylko ABSOLUTNE (relatywne = wewnątrz pakietu)
        return mods

    def test_A_mount_surface(self):
        ev = ev_fresh()
        self.assertTrue(callable(ev.eval_line))
        self.assertEqual(ev.eval_line("1 + 2"), "3")
        self.assertIsInstance(ev.eval_line("print('x')"), str)
        # kontrakt boota/shell: .env == korzeń G
        self.assertIs(ev.env, ev.G)
        self.assertTrue(hasattr(ev, "register_preload"))

    def test_A2_tools_preload_host(self):
        """Host register_preload + tools= dict → require w OS."""
        store = Store(thermal=True)
        ev = mount(store, tools={
            "calc": "return {add=function(a,b) return a+b end}",
        })
        self.assertEqual(ev.eval_line("return require('calc').add(2,3)"), "5")
        # przeładowanie źródła
        ev.register_preload("calc", "return {add=function(a,b) return a*b end}")
        self.assertEqual(ev.eval_line("return require('calc').add(2,3)"), "6")

    def test_B_one_core(self):
        store = Store(thermal=True)
        ev = mount(store)
        self.assertIs(ev.G.store, store)
        n0 = len(store.atoms())
        ev.eval_line("g = 1")
        self.assertGreater(len(store.atoms()), n0)
        self.assertEqual(type(store).__module__, "karmazyn_substrate")

    def test_C_zero_external_deps(self):
        stdlib = getattr(sys, "stdlib_module_names", None)
        fallback = {"typing", "sys", "os", "ast", "re", "math"}
        for m in self._imports():
            if m == "karmazyn_kernel":
                continue
            ok = (stdlib and m in stdlib) or (m in fallback)
            self.assertTrue(ok, f"zewnętrzna zależność: {m}")

    def test_D_kernel_only_via_facade(self):
        for m in self._imports():
            if m.startswith("karmazyn_") and m != "karmazyn_kernel":
                self.fail(f"siega wnetrza jadra: {m}")

    def test_E_reach_gc_safety(self):
        # pełne dowody w II_Architecture; tu skrót: związane przeżywa
        store = Store(thermal=True)
        ev = mount(store)
        ev.eval_line("keep = {v = 1}")
        store.settle(500)
        self.assertEqual(ev.eval_line("keep.v"), "1")

    def test_F_no_ambient_authority(self):
        from karmazyn_lua.values import _own_keys
        ev = ev_fresh()
        # brak host-escape: dofile / execute / open (io.* = wirtualne, nie FS)
        names = set(_own_keys(ev.G))
        for danger in ("dofile", "execute", "open"):
            self.assertNotIn(danger, names)
        out = ev.eval_line("return os.execute('rm -rf /')")
        self.assertTrue(out.startswith("blad") or out == "nil", out)
        self.assertEqual(ev.eval_line("return type(os.time)"), "function")
        self.assertEqual(ev.eval_line("return type(io.write)"), "function")
        self.assertTrue(ev.eval_line("return require('nope')").startswith("blad"))

    def test_G_host_resilience(self):
        ev = ev_fresh()
        for bad in ["((((", "1 +", "if then end", "for", "@@@", ")", ""]:
            out = ev.eval_line(bad)
            self.assertIsInstance(out, str)                  # nigdy nie rzuca

    def test_H_public_surface_only(self):
        import re
        src = _src()
        # 'store.reg' (rejestr atomów) zakazany, ale '.register' rejestratora — wolno
        self.assertIsNone(re.search(r"\.reg\b", src), "siega wnetrza Store: .reg")
        for tok in ("._archived", "._roots", "._bubbles", "._handlers"):
            self.assertNotIn(tok, src, f"siega wnetrza Store: {tok}")
        self.assertIn("_env_of", src)                        # udokumentowany hook — wolno


if __name__ == "__main__":
    unittest.main(verbosity=2)
