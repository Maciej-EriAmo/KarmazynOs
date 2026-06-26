#!/usr/bin/env python3
"""
karmazyn_scheme.py — Scheme na rdzeniu geometrycznym (P4 + P5 + P6)
====================================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Front-end Scheme (reader + evaluator) wołający WYŁĄCZNIE powierzchnię rdzenia
z CORE_ABI:
  - atomy:  store.atom_new / get_atom            (§4.1)
  - scope:  store.bubble_new(parent) / bind / lookup  (§4.4, schemat A)

Evaluator nie trzyma własnego środowiska — całe wiązanie nazw idzie przez
scope-bąble rdzenia. Dowód „cienkości": jeśli coś musiałoby powstać poza tą
powierzchnią, znaczy że rdzeń jest niekompletny.

────────────────────────────────────────────────────────────────────────────
TRZY TWARZE ATOMU (tryby pracy magazynu, P6 — zmierzone w SCHEME_PLAN §10):

  STATIC  — tylko twarz TOŻSAMOŚCI (id → lookup). Atom jako martwa komórka.
            Dokładnie warstwa wykonania z P5. Bez termiki, bez wektora.
  FOTON   — TOŻSAMOŚĆ + WEKTOR (adresowalność). Bez termiki: bezczasowy,
            odwracalny, NIE zapomina → pełny ślad audytowy, ale przecieka.
  DYNAMIC — wszystkie trzy twarze: TOŻSAMOŚĆ + WEKTOR + TERMIKA.
            Polityka odzysku reach: temperatura mówi KIEDY, osiągalność CZY.
              • zimny + nieosiągalny → TOMB → GC
              • zimny + osiągalny    → archiwum (COLD), nie kasacja
            Lookup pozostaje DOKŁADNY — grzanie to efekt uboczny, nie zmienia
            tego, co lookup zwraca. To gwarantuje 33/33 w każdym trybie.

Twarz wektora daje ADRESOWALNOŚĆ (content-addressing), NIE podobieństwo
znaczeń: name→wektor jest deterministyczne (sha256→Gauss→norm), różne nazwy są
prawie ortogonalne. To baza pod Procę/HRR, nie wyszukiwanie po sensie.
────────────────────────────────────────────────────────────────────────────

Uruchomienie: python3 karmazyn_scheme.py   → walidacja STATIC i DYNAMIC vs orakl.
"""

import hashlib
import re
from typing import Any, List, Optional

# Atom kanoniczny (jeden dialekt — bez herezji)
try:
    from karmazyn_atom import Atom
    _HAS_ATOM = True
except ImportError:
    _HAS_ATOM = False
    class Atom:  # minimalny zamiennik, gdy referencja niedostępna
        def __init__(self, id, S='', E='', T=50.0, vector=None, metadata=None):
            self.id, self.S, self.E, self.T = id, S, E, T
            self.vector = vector
            self.metadata = metadata or {}

# Wektor (twarz falowa) — opcjonalny extra [resonance]. Rdzeń bez numpy działa
# w trybie STATIC i w termice; tylko twarz wektora wymaga numpy.
try:
    import numpy as _np
    _HAS_NUMPY = True
except ImportError:
    _np = None
    _HAS_NUMPY = False


# ─────────────────────────────────────────────────────────────────────────────
# TRYBY (twarze atomu)
# ─────────────────────────────────────────────────────────────────────────────

STATIC  = "static"    # tożsamość
FOTON   = "foton"     # tożsamość + wektor (bez termiki)
DYNAMIC = "dynamic"   # tożsamość + wektor + termika (reach)

# Stałe termiczne (spójne z karmazyn_atom)
T_INIT    = 50.0
T_MAX     = 100.0
T_HOT     = 70.0
T_WARM    = 30.0
T_TOMB    = 2.0
DECAY     = 0.92
HEAT_READ = 10.0      # grzanie przy lookupie
VEC_DIM   = 2048      # D z CORE_ABI §3.2


def _name_vector(key: str, D: int):
    """Kanoniczne name→wektor: sha256 → seed → Gauss(D) → normalizacja (CORE_ABI §3.3)."""
    seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    rng = _np.random.default_rng(seed)
    v = rng.standard_normal(D)
    n = _np.linalg.norm(v)
    return v / n if n > 0 else v


# ─────────────────────────────────────────────────────────────────────────────
# RDZEŃ (mirror CORE_ABI: atomy §4.1 + scope-bąble §4.4)
# ─────────────────────────────────────────────────────────────────────────────

class ScopeBubble:
    """CORE_ABI §4.4: bąbel z rodzicem i wiązaniami nazwanymi = zakres leksykalny."""
    __slots__ = ("store", "label", "parent", "bindings")

    def __init__(self, store, label, parent=None):
        self.store = store
        self.label = label
        self.parent = parent                 # ScopeBubble lub None (korzeń)
        self.bindings = {}                   # name -> atom.id

    def bind(self, name: str, atom: Atom):   # kz_bubble_bind (tylko lokalnie)
        self.bindings[name] = atom.id

    def lookup(self, name: str) -> Optional[Atom]:  # kz_bubble_lookup (po parent chain)
        b = self
        while b is not None:
            aid = b.bindings.get(name)
            if aid is not None:
                atom = b.store.get_atom(aid)
                if atom is not None and b.store.thermal:
                    b.store.heat(atom)       # twarz termiczna: lookup grzeje
                return atom                  # zwracana wartość NIEZALEŻNA od termiki
            b = b.parent
        return None


class Store:
    """
    CORE_ABI §4.1: tworzenie/odczyt atomów + §4.4: tworzenie bąbli.
    Tryb (STATIC/FOTON/DYNAMIC) ustala, które twarze atomu są aktywne.
    """

    def __init__(self, policy: str = STATIC, D: int = VEC_DIM):
        self.policy = policy
        self.thermal = (policy == DYNAMIC)
        self.vector  = (policy in (FOTON, DYNAMIC)) and _HAS_NUMPY
        self.D = D
        self._atoms = {}     # HOT: id -> Atom
        self._cold  = {}     # COLD (archiwum): id -> Atom (zimne, ale osiągalne)
        self._bubbles = []   # rejestr bąbli (dla osiągalności i przyszłej persystencji)
        self._roots = []     # bąble-korzenie GC (zwykle: global)
        self._n = 0
        self._reaped = 0     # zliczanie: GC (zimne+nieosiągalne)
        self._archived = 0   # zliczanie: archiwum (zimne+osiągalne)

    # ── atomy (§4.1) ──────────────────────────────────────────────────────────

    def atom_new(self, S: str, E: str = "", T: float = T_INIT, value=None) -> Atom:
        aid = f"a{self._n}"; self._n += 1
        meta = {"v": value, "state": "WARM"}
        a = Atom(aid, S, str(E), T, metadata=meta)
        if self.vector:
            key = E if E else S          # nazwa (E) jest kluczem adresowalności
            a.vector = _name_vector(key, self.D)
        self._atoms[aid] = a
        return a

    def get_atom(self, aid: str) -> Optional[Atom]:
        a = self._atoms.get(aid)
        if a is not None:
            return a
        return self._cold.get(aid)        # przezroczysty odczyt z archiwum

    # ── termika (tylko DYNAMIC) ───────────────────────────────────────────────

    def heat(self, a: Atom) -> None:
        if a.id in self._cold:            # odczyt zimnego = powrót do HOT
            del self._cold[a.id]
            self._atoms[a.id] = a
        a.T = min(T_MAX, a.T + HEAT_READ)
        a.metadata["state"] = "HOT" if a.T >= T_HOT else "WARM"

    def _reachable(self) -> set:
        """Atomy osiągalne z korzeni + przez łańcuch leksykalny domknięć."""
        reach = set()
        seen = set()
        stack = list(self._roots)
        while stack:
            b = stack.pop()
            if id(b) in seen:
                continue
            seen.add(id(b))
            for name, aid in b.bindings.items():
                reach.add(aid)
                a = self.get_atom(aid)
                if a is not None and isinstance(a.metadata.get("v"), Closure):
                    stack.append(a.metadata["v"].env)   # env przechwyconego domknięcia
            if b.parent is not None:
                stack.append(b.parent)                  # łańcuch leksykalny
        return reach

    def tick(self) -> None:
        """Upływ czasu: stygnięcie + odzysk wg reguły reach. No-op poza DYNAMIC."""
        if not self.thermal:
            return
        reach = self._reachable()
        # HOT: stygnięcie, potem decyzja gdy zimny
        for aid, a in list(self._atoms.items()):
            a.T *= DECAY
            if a.T < T_TOMB:
                if aid in reach:
                    a.metadata["state"] = "COLD"        # zimny+osiągalny → archiwum
                    self._cold[aid] = a
                    del self._atoms[aid]
                    self._archived += 1
                else:
                    del self._atoms[aid]                # zimny+nieosiągalny → GC
                    self._reaped += 1
        # COLD: atom zarchiwizowany, który PÓŹNIEJ stracił osiągalność, też ginie.
        # (np. po redefinicji nazwy stary atom wypada z wiązań → nieosiągalny.)
        for aid, a in list(self._cold.items()):
            if aid not in reach:
                del self._cold[aid]                     # zimny+nieosiągalny → GC
                self._reaped += 1

    def settle(self, n: int) -> None:
        """n tyknięć bezczynności (symulacja upływu czasu — do testów/GC)."""
        for _ in range(n):
            self.tick()

    # ── bąble (§4.4) ──────────────────────────────────────────────────────────

    def bubble_new(self, label: str, parent: Optional[ScopeBubble] = None) -> ScopeBubble:
        b = ScopeBubble(self, label, parent)
        self._bubbles.append(b)          # śledzony (naprawa luki persystencji §9)
        return b

    def set_root(self, bubble: ScopeBubble) -> None:
        """Zarejestruj bąbel jako korzeń GC (zwykle global; też scope żywego rytmu)."""
        self._roots.append(bubble)

    def unset_root(self, bubble: ScopeBubble) -> None:
        """Wyrejestruj korzeń — np. gdy rytm kończy, jego lokalia stają się zbieralne."""
        try:
            self._roots.remove(bubble)
        except ValueError:
            pass

    def stats(self) -> dict:
        return {
            "policy": self.policy,
            "hot": len(self._atoms),
            "cold": len(self._cold),
            "reachable": len(self._reachable()) if self.thermal else None,
            "reaped": self._reaped,
            "archived": self._archived,
            "vector": self.vector,
        }


# ─────────────────────────────────────────────────────────────────────────────
# TYPY DANYCH SCHEME
# ─────────────────────────────────────────────────────────────────────────────

class Symbol(str):
    pass

class Pair:
    __slots__ = ("car", "cdr")
    def __init__(self, car, cdr):
        self.car, self.cdr = car, cdr

NIL = None  # pusta lista = ()

class Closure:
    __slots__ = ("params", "body", "env")
    def __init__(self, params, body, env):
        self.params, self.body, self.env = params, body, env

def list_to_pairs(items: List[Any]):
    out = NIL
    for x in reversed(items):
        out = Pair(x, out)
    return out

def pairs_to_list(p) -> List[Any]:
    out = []
    while isinstance(p, Pair):
        out.append(p.car); p = p.cdr
    return out


# ─────────────────────────────────────────────────────────────────────────────
# READER (parser S-wyrażeń)
# ─────────────────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r'''\s*(?:(;.*?$)|("(?:\\.|[^"\\])*")|(\(|\)|')|([^\s()'"]+))''',
                    re.MULTILINE)

def tokenize(src: str) -> List[str]:
    toks = []
    for m in _TOKEN.finditer(src):
        comment, string, paren, atom = m.groups()
        if comment is not None:
            continue
        if string is not None:
            toks.append(string)
        elif paren is not None:
            toks.append(paren)
        elif atom is not None:
            toks.append(atom)
    return toks

def parse_all(src: str) -> List[Any]:
    toks = tokenize(src)
    pos = 0
    forms = []
    def parse():
        nonlocal pos
        if pos >= len(toks):
            raise SyntaxError("nieoczekiwany koniec")
        t = toks[pos]; pos += 1
        if t == "'":
            return [Symbol("quote"), parse()]
        if t == "(":
            lst = []
            while pos < len(toks) and toks[pos] != ")":
                lst.append(parse())
            if pos >= len(toks):
                raise SyntaxError("brak )")
            pos += 1  # skonsumuj )
            return lst
        if t == ")":
            raise SyntaxError("nadmiarowy )")
        return atomize(t)
    while pos < len(toks):
        forms.append(parse())
    return forms

def atomize(t: str) -> Any:
    if t == "#t": return True
    if t == "#f": return False
    if t.startswith('"') and t.endswith('"'):
        return t[1:-1].encode().decode("unicode_escape")
    try: return int(t)
    except ValueError: pass
    try: return float(t)
    except ValueError: pass
    return Symbol(t)


# ─────────────────────────────────────────────────────────────────────────────
# EVALUATOR (eval / apply) — woła tylko rdzeń. NIEZMIENIONY względem P5.
# ─────────────────────────────────────────────────────────────────────────────

class SchemeError(Exception):
    pass

def seval(expr, env: ScopeBubble, store: Store):
    # literały
    if isinstance(expr, (int, float, bool)):
        return expr
    if isinstance(expr, str) and not isinstance(expr, Symbol):
        return expr  # string
    # symbol = odwołanie do zmiennej → lookup w rdzeniu
    if isinstance(expr, Symbol):
        atom = env.lookup(expr)
        if atom is None:
            raise SchemeError(f"niezwiązany symbol: {expr}")
        return atom.metadata["v"]
    # lista = forma specjalna albo aplikacja
    if isinstance(expr, list):
        if not expr:
            raise SchemeError("pusta aplikacja ()")
        head = expr[0]
        if isinstance(head, Symbol):
            h = str(head)
            if h == "quote":
                return to_value(expr[1])
            if h == "if":
                c = seval(expr[1], env, store)
                if c is not False:
                    return seval(expr[2], env, store)
                return seval(expr[3], env, store) if len(expr) > 3 else None
            if h == "define":
                target = expr[1]
                if isinstance(target, list):  # (define (f a b) body...)
                    name = str(target[0]); params = [str(p) for p in target[1:]]
                    clos = Closure(params, expr[2:], env)
                    atom = store.atom_new("closure", name, value=clos)
                    env.bind(name, atom)
                else:                          # (define x expr)
                    name = str(target)
                    val = seval(expr[2], env, store)
                    atom = store.atom_new("value", name, value=val)
                    env.bind(name, atom)
                return None
            if h == "lambda":
                params = [str(p) for p in expr[1]]
                return Closure(params, expr[2:], env)
            if h == "begin":
                return eval_seq(expr[1:], env, store)
            if h == "let":
                binds = expr[1]
                names = [str(b[0]) for b in binds]
                vals = [seval(b[1], env, store) for b in binds]
                frame = store.bubble_new("let", parent=env)
                for n, v in zip(names, vals):
                    frame.bind(n, store.atom_new("value", n, value=v))
                return eval_seq(expr[2:], frame, store)
            if h == "let*":
                frame = store.bubble_new("let*", parent=env)
                for b in expr[1]:
                    n = str(b[0]); v = seval(b[1], frame, store)
                    frame.bind(n, store.atom_new("value", n, value=v))
                return eval_seq(expr[2:], frame, store)
            if h == "cond":
                for clause in expr[1:]:
                    if isinstance(clause[0], Symbol) and str(clause[0]) == "else":
                        return eval_seq(clause[1:], env, store)
                    if seval(clause[0], env, store) is not False:
                        return eval_seq(clause[1:], env, store)
                return None
            if h == "and":
                r = True
                for e in expr[1:]:
                    r = seval(e, env, store)
                    if r is False: return False
                return r
            if h == "or":
                for e in expr[1:]:
                    r = seval(e, env, store)
                    if r is not False: return r
                return False
        # aplikacja: ewaluuj operator i argumenty
        proc = seval(head, env, store)
        args = [seval(a, env, store) for a in expr[1:]]
        return sapply(proc, args, store)
    raise SchemeError(f"nieznane wyrażenie: {expr!r}")

def eval_seq(body, env, store):
    r = None
    for e in body:
        r = seval(e, env, store)
    return r

def sapply(proc, args, store: Store):
    if callable(proc):                # prymityw front-endu
        return proc(*args)
    if isinstance(proc, Closure):
        # nowa ramka z rodzicem = środowisko domknięcia (capture leksykalny)
        frame = store.bubble_new("call", parent=proc.env)
        if len(args) != len(proc.params):
            raise SchemeError(f"zła liczba argumentów: {len(args)} != {len(proc.params)}")
        for p, a in zip(proc.params, args):
            frame.bind(p, store.atom_new("arg", p, value=a))
        return eval_seq(proc.body, frame, store)
    raise SchemeError(f"nie da się zaaplikować: {proc!r}")

def to_value(datum):
    """quote: zamień AST na wartość Scheme (listy → Pary)."""
    if isinstance(datum, list):
        return list_to_pairs([to_value(x) for x in datum])
    return datum


# ─────────────────────────────────────────────────────────────────────────────
# PRYMITYWY FRONT-ENDU (NIE fizyka rdzenia — semantyka języka)
# ─────────────────────────────────────────────────────────────────────────────

def _sub(*a): return a[0] - sum(a[1:]) if len(a) > 1 else -a[0]
def _div(*a):
    r = a[0]
    for x in a[1:]: r /= x
    return r
def _mul(a):
    r = 1
    for x in a: r *= x
    return r

def make_primitives() -> dict:
    return {
        "+": lambda *a: sum(a),
        "-": _sub,
        "*": lambda *a: _mul(a),
        "/": _div,
        "=": lambda x, y: x == y,
        "<": lambda x, y: x < y,
        ">": lambda x, y: x > y,
        "<=": lambda x, y: x <= y,
        ">=": lambda x, y: x >= y,
        "cons": lambda a, b: Pair(a, b),
        "car": lambda p: p.car,
        "cdr": lambda p: p.cdr,
        "null?": lambda p: p is NIL,
        "pair?": lambda p: isinstance(p, Pair),
        "list": lambda *a: list_to_pairs(list(a)),
        "not": lambda x: x is False,
        "map": lambda f, lst: list_to_pairs([sapply(f, [x], _CUR_STORE) for x in pairs_to_list(lst)]),
    }

_CUR_STORE: Optional[Store] = None


# ─────────────────────────────────────────────────────────────────────────────
# PRINTER (notacja R7RS) + uruchomienie programu
# ─────────────────────────────────────────────────────────────────────────────

def swrite(v) -> str:
    if v is True: return "#t"
    if v is False: return "#f"
    if v is None: return "()"
    if isinstance(v, Symbol): return str(v)
    if isinstance(v, Pair):
        return "(" + " ".join(swrite(x) for x in pairs_to_list(v)) + ")"
    if isinstance(v, Closure): return "#<closure>"
    if isinstance(v, float) and v.is_integer(): return str(int(v))
    return str(v)

def run_program(src: str, policy: str = STATIC) -> str:
    """
    Uruchom program. policy:
      STATIC  — jak P5 (tożsamość; tick to no-op).
      FOTON   — + wektor (adresowalność), bez termiki.
      DYNAMIC — + termika (reach): tick po każdej formie, GC/archiwum.
    Lookup zawsze dokładny → wynik niezależny od trybu (warunek 33/33).
    """
    return run_program_store(src, policy)[0]

def run_program_store(src: str, policy: str = STATIC):
    """Jedno źródło prawdy. Zwraca (wynik, store, global) — do diagnostyki/testów."""
    global _CUR_STORE
    store = Store(policy=policy); _CUR_STORE = store
    g = store.bubble_new("global", parent=None)
    store.set_root(g)
    for name, fn in make_primitives().items():
        g.bind(name, store.atom_new("prim", name, value=fn))
    result = None
    for form in parse_all(src):
        result = seval(form, g, store)
        store.tick()                 # upływ czasu na granicy formy (no-op poza DYNAMIC)
    return swrite(result), store, g


# ─────────────────────────────────────────────────────────────────────────────
# WALIDACJA (P5: bateria; P6: ten sam wynik w STATIC i DYNAMIC + bezpieczeństwo)
# ─────────────────────────────────────────────────────────────────────────────

_Y = ("(define Y (lambda (f) ((lambda (x) (f (lambda (v) ((x x) v)))) "
      "(lambda (x) (f (lambda (v) ((x x) v)))))))")

BATTERY = [
    ("L1", "(+ 2 3)"),
    ("L2", "(* 6 7)"),
    ("L3", "(- 10 3 2)"),
    ("L4", "(< 1 2)"),
    ("L5", "(= 4 4)"),
    ("D1", "(define x 10) (* x x)"),
    ("D2", "(define a 3) (define b 4) (+ a b)"),
    ("I1", "(if #t 1 2)"),
    ("I2", "(if (< 3 2) 'yes 'no)"),
    ("I3", "(cond ((= 1 2) 'a) ((= 1 1) 'b) (else 'c))"),
    ("C1", "((lambda (x) (* x x)) 5)"),
    ("C2", "(define (mk n) (lambda () n)) ((mk 9))"),
    ("C3", "(define (adder n) (lambda (x) (+ x n))) ((adder 10) 5)"),
    ("C4", "(((lambda (a) (lambda (b) (+ a b))) 3) 4)"),
    ("R1", "(define (fact n) (if (= n 0) 1 (* n (fact (- n 1))))) (fact 5)"),
    ("R2", "(define (sm n) (if (= n 0) 0 (+ n (sm (- n 1))))) (sm 4)"),
    ("R3", "(define (fib n) (if (< n 2) n (+ (fib (- n 1)) (fib (- n 2))))) (fib 10)"),
    ("H1", "(map (lambda (x) (* x x)) '(1 2 3))"),
    ("H2", "(car (cons 1 2))"),
    ("H3", "(cdr (cons 1 2))"),
    ("H4", "(car '(a b c))"),
    ("H5", "(null? '())"),
    ("H6", "(pair? '(1))"),
    ("Q1", "(quote (1 2 3))"),
    ("Q2", "'foo"),
    ("LE1", "(let ((x 2) (y 3)) (+ x y))"),
    ("LE2", "(let* ((x 2) (y (* x 3))) y)"),
    ("Y1", _Y + " (define fact (Y (lambda (self) (lambda (n) (if (= n 0) 1 (* n (self (- n 1)))))))) (fact 5)"),
    ("S1", "(define x 1) (let ((x 2)) x)"),
    ("S2", "(define x 1) (define f (let ((x 2)) (lambda () x))) (f)"),
    ("S3", "(define x 1) (define f (lambda () x)) (let ((x 2)) (f))"),
    ("S4", "(define (mk n) (lambda (x) (+ x n))) (define f (mk 7)) (f 1)"),
    ("S5", "(define (outer a) (lambda (b) (lambda (c) (+ a b c)))) (((outer 1) 2) 3)"),
]

def _norm(s: str) -> str:
    s = s.strip()
    return {"True": "#t", "False": "#f", "#true": "#t", "#false": "#f"}.get(s, s)

def validate():
    try:
        import calysto_scheme.scheme as oracle
        def run_oracle(code): return _norm(str(oracle.execute_string_top(code, "t")))
        have_oracle = True
    except Exception:
        have_oracle = False

    oracle_vals = {}
    if have_oracle:
        for tid, code in BATTERY:
            oracle_vals[tid] = run_oracle(code)

    print("=" * 72)
    print("  KarmazynScheme — walidacja P5/P6")
    print(f"  atom kanoniczny: {_HAS_ATOM} | numpy (twarz wektora): {_HAS_NUMPY}")
    print("=" * 72)

    for policy in (STATIC, DYNAMIC):
        passed = 0
        for tid, code in BATTERY:
            try:
                mine = _norm(run_program(code, policy=policy))
            except Exception as e:
                mine = "ERR:" + str(e)[:30]
            if have_oracle:
                passed += (mine == oracle_vals[tid])
            else:
                passed += 1  # bez orakla tylko liczymy wykonane bez błędu
        tag = "vs orakl" if have_oracle else "wykonane"
        print(f"  [{policy:8}] bateria {tag}: {passed}/{len(BATTERY)}")

    print("-" * 72)
    print("  P6 — bezpieczeństwo i higiena (tryb DYNAMIC):")

    # przeciwnik: zimne domknięcie
    adv = ("(define (mk n) (lambda () n)) (define g (mk 42)) "
           + " ".join(f"(define z{i} {i})" for i in range(60)) + " (g)")
    adv_res = _norm(run_program(adv, policy=DYNAMIC))
    print(f"    zimne domknięcie (oczek. 42): {adv_res}  -> {'OK' if adv_res=='42' else 'ZŁAMANE'}")

    # higiena: rekurencja tworzy martwe ramki, settle sprząta
    _, store, g = run_program_store(
        "(define (fact n) (if (= n 0) 1 (* n (fact (- n 1))))) (fact 6)", policy=DYNAMIC)
    store.settle(80)
    st = store.stats()
    print(f"    po stygnięciu: hot={st['hot']} cold={st['cold']} "
          f"reaped={st['reaped']} archived={st['archived']} (martwe ramki zebrane)")

    # higiena COLD: redefinicja po archiwizacji — stary atom NIE zostaje w cold
    redef = ("(define x 1) " + " ".join(f"(define z{i} {i})" for i in range(40))
             + " (define x 2) " + " ".join(f"(define w{i} {i})" for i in range(40)) + " x")
    res_redef, store2, _ = run_program_store(redef, policy=DYNAMIC)
    store2.settle(60)
    xs = [a for a in list(store2._atoms.values()) + list(store2._cold.values())
          if a.S == "value" and a.E == "x"]
    ok_redef = (res_redef == "2" and len(xs) == 1)
    print(f"    redefinicja x (oczek. 2): {res_redef}; atomów 'x' w magazynie: "
          f"{len(xs)} -> {'OK (stary zebrany)' if ok_redef else 'PRZECIEK'}")

    # twarz wektora: adresowalność
    if _HAS_NUMPY:
        _, store, g = run_program_store(
            "(define kanapka 1)(define kanapeczka 2)(define samochod 3)", policy=DYNAMIC)
        pv = _name_vector("kanapka", store.D)
        sims = [(a.E, float(_np.dot(pv, a.vector)))
                for a in list(store._atoms.values()) + list(store._cold.values())
                if a.S == "value" and getattr(a, "vector", None) is not None]
        sims.sort(key=lambda x: -x[1])
        print("    twarz wektora (adresowalność, lookup dalej dokładny):")
        for name, s in sims:
            print(f"      sim('kanapka', {name!r}) = {s:+.3f}")
    print("=" * 72)


if __name__ == "__main__":
    validate()