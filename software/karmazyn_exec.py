"""
karmazyn_exec.py — WARSTWA WYKONAWCZA KarmazynOS (mini-Lisp na Store)
====================================================================
Maciej Mazur, Warsaw 2026

Po boocie: prompt, w ktory wpisujesz kod — i on sie wykonuje. To jest jezyk
do robienia narzedzi: ma `lambda`/domkniecia, wiec mozesz budowac abstrakcje.

Niezbywalne wlasciwosci (zgodne z cala architektura):
  - ZERO ZALEZNOSCI: czysty stdlib. Dziala w obrazie bez numpy.
  - ZMIENNE = ATOMY: `define`/argumenty tworza atomy; wartosc jezykowa w
    `atom.metadata["v"]`. Scope = babel (`Bubble`); lookup idzie po lancuchu
    leksykalnym (parent).
  - ZYCIE POD REACH-GC: globalny env jest korzeniem. Zmienne zlapane w
    DOMKNIECIU sa osiagalne przez hook `env_of` w `Store` — wiec reach-GC ich
    nie skasuje, nawet gdy ostygna w nie-korzeniowym bablu. To jest kuracja P6
    dla closure: `env_of(closure) -> babel-srodowiska closure`.
  - RAMKI W LOCIE POD REACH-GC (FIX v1.1): ramka wywolania jest TYMCZASOWYM
    korzeniem na czas `_apply` (set_root → eval → unset_root w finally).
    Wczesniej ramka w locie NIE byla osiagalna z korzeni — scheduler tykajacy
    w tle podczas dlugiego obliczenia moglby zreapowac atomy argumentow
    (potwierdzone sonda: bind w ramce + settle(60) → atom znikal). To jest
    siostra kuracji P6: domkniecia leczy env_of, ramki w locie — temp-root.

SZEW MONTAZU: boot oczekuje obiektu z `eval_line(str) -> str`. Bogatszy
front-end (np. karmazyn_scheme) podpina sie tak samo.

Formy: liczby, symbole, literaly `#t`/`#f`, `define`, `set!`, `if`, `begin`,
`lambda`, arytmetyka `+ - * /`, porownania `= < > <= >=`, `not`,
`and`/`or` (formy specjalne, short-circuit, zwracaja wartosc), `print`.

ZMIANY SEMANTYKI v1.1 (audyt 2026-07):
  1. `define`/`set!` zwracaja PRZYPISANA WARTOSC, nie string-komunikat.
     Wczesniej `(+ 1 (set! n 7))` wybuchalo (string w domenie wartosci);
     teraz `(define x 5)` → 5, `(set! n 7)` → 7 — komponowalne.
  2. `print` PISZE na stdout (side effect) i zwraca None. Wczesniej zwracal
     string i nic nie drukowal — `(begin (print 111) 222)` gubilo 111.
  3. SHADOWING SPOJNY: rozwiazywanie symboli idzie env → builtins (w tej
     kolejnosci) w KAZDEJ pozycji. Po `(define + 5)` zarowno `+` jak i
     `(+ 1 2)` widza 5 (aplikacja: "nie da sie wywolac"). Wczesniej
     aplikacja widziala builtin (3), a goly symbol — 5.
  4. Komentarz `;` dziala tez INLINE: `(+ 1 2) ; uwaga` → 3.
"""

from typing import Any, List


# ─── Reader: tekst -> S-wyrazenie ─────────────────────────────────────────────
def tokenize(src: str) -> List[str]:
    return src.replace("(", " ( ").replace(")", " ) ").split()


def read(tokens: List[str]):
    if not tokens:
        raise SyntaxError("nieoczekiwany koniec wejscia")
    tok = tokens.pop(0)
    if tok == "(":
        lst = []
        while tokens and tokens[0] != ")":
            expr, tokens = read(tokens)
            lst.append(expr)
        if not tokens:
            raise SyntaxError("brak ')' — niezamknieta lista")
        tokens.pop(0)
        return lst, tokens
    if tok == ")":
        raise SyntaxError("nieoczekiwane ')'")
    return _atomize(tok), tokens


def _atomize(tok: str) -> Any:
    if tok == "#t":
        return True
    if tok == "#f":
        return False
    try:
        return int(tok)
    except ValueError:
        pass
    try:
        return float(tok)
    except ValueError:
        return tok


def parse(src: str):
    tokens = tokenize(src)
    if not tokens:
        return None
    expr, rest = read(tokens)
    if rest:
        raise SyntaxError(f"nadmiarowe tokeny: {' '.join(map(str, rest))}")
    return expr


# ─── Domkniecie: kod + zlapane srodowisko (babel) ─────────────────────────────
class Closure:
    __slots__ = ("params", "body", "env")

    def __init__(self, params, body, env):
        self.params = params
        self.body = body
        self.env = env                       # Bubble — widziany przez env_of -> reach-GC

    def __repr__(self):
        return f"<closure ({' '.join(self.params)})>"


# ─── Ewaluator na Store ───────────────────────────────────────────────────────
class Evaluator:
    def __init__(self, store, env_label: str = "repl"):
        self.store = store
        self.env = store.bubble_new(env_label)
        store.set_root(self.env)             # globalne zmienne osiagalne
        # KURACJA P6 DLA CLOSURE: ucz rdzen, jak czytac osiagalnosc z wartosci.
        # Rdzen sam nie zna jezyka; podajemy mu hook (udokumentowany punkt rozszerzen).
        store._env_of = lambda v: v.env if isinstance(v, Closure) else None
        self._builtins = {
            "+": lambda *a: _fold(lambda x, y: x + y, a),
            "-": lambda *a: (-a[0] if len(a) == 1 else _fold(lambda x, y: x - y, a)),
            "*": lambda *a: _fold(lambda x, y: x * y, a, start=1),
            "/": lambda *a: _fold(_safediv, a),
            "=": lambda x, y: x == y,
            "<": lambda x, y: x < y,
            ">": lambda x, y: x > y,
            "<=": lambda x, y: x <= y,
            ">=": lambda x, y: x >= y,
            "not": lambda x: not _truthy(x),
            # and/or sa formami specjalnymi (short-circuit) — patrz _eval
            "print": _builtin_print,         # FIX v1.1: realny stdout, zwraca None
        }

    # publiczny szew dla boota / innych shellow
    def eval_line(self, line: str) -> str:
        line = (line or "")
        # FIX v1.1 pkt 4: `;` zaczyna komentarz takze inline (jezyk nie ma
        # stringow, wiec obciecie po pierwszym `;` jest bezpieczne).
        line = line.split(";", 1)[0].strip()
        if not line:
            return ""
        try:
            expr = parse(line)
            return "" if expr is None else _fmt(self._eval(expr, self.env))
        except Exception as e:
            return f"blad: {type(e).__name__}: {e}"

    # ── jadro ewaluacji (parametryzowane srodowiskiem) ──
    def _eval(self, x: Any, env) -> Any:
        if isinstance(x, (int, float)):
            return x
        if isinstance(x, str):                       # symbol -> zmienna
            # FIX v1.1 pkt 3: env PRZED builtins — shadowing spojny w kazdej
            # pozycji. Builtins to fallback, nie priorytet.
            atom = env.lookup(x)
            if atom is not None:
                return atom.metadata["v"]
            if x in self._builtins:
                return self._builtins[x]
            raise NameError(f"'{x}' nieznane")
        if not isinstance(x, list) or not x:
            raise SyntaxError(f"nie umiem wykonac: {x!r}")

        head = x[0]

        # ── formy specjalne ──
        if head == "define":
            if len(x) != 3 or not isinstance(x[1], str):
                raise SyntaxError("uzycie: (define nazwa wyrazenie)")
            val = self._eval(x[2], env)
            atom = self.store.atom_new("var", x[1], value=val)
            env.bind(x[1], atom)                     # w BIEZACYM env (globalny lub lokalny)
            return val                               # FIX v1.1 pkt 1: wartosc, nie string
        if head == "set!":
            if len(x) != 3 or not isinstance(x[1], str):
                raise SyntaxError("uzycie: (set! nazwa wyrazenie)")
            atom = env.lookup(x[1])                   # znajdz istniejace wiazanie (po lancuchu)
            if atom is None:
                raise NameError(f"set!: '{x[1]}' nie istnieje")
            val = self._eval(x[2], env)
            atom.metadata["v"] = val                  # mutacja w miejscu (ten sam atom/id)
            return val                                # FIX v1.1 pkt 1: wartosc, nie string
        if head == "if":
            if len(x) not in (3, 4):
                raise SyntaxError("uzycie: (if warunek to [else])")
            if _truthy(self._eval(x[1], env)):
                return self._eval(x[2], env)
            return self._eval(x[3], env) if len(x) == 4 else None
        if head == "begin":
            result = None
            for sub in x[1:]:
                result = self._eval(sub, env)
            return result
        if head == "lambda":
            if len(x) != 3 or not isinstance(x[1], list):
                raise SyntaxError("uzycie: (lambda (params...) cialo)")
            if not all(isinstance(p, str) for p in x[1]):
                raise SyntaxError("parametry lambda musza byc symbolami")
            return Closure(x[1], x[2], env)          # domkniecie lapie BIEZACY env
        if head == "and":
            # short-circuit: zwraca ostatnia wartosc prawdy lub pierwsze falszywe
            result = True
            for sub in x[1:]:
                result = self._eval(sub, env)
                if not _truthy(result):
                    return result
            return result
        if head == "or":
            # short-circuit: zwraca pierwsze prawdziwe lub ostatnie falszywe
            result = False
            for sub in x[1:]:
                result = self._eval(sub, env)
                if _truthy(result):
                    return result
            return result

        # ── zastosowanie ──
        # FIX v1.1 pkt 3: glowa ZAWSZE przez _eval (env → builtins) — jedna
        # sciezka rozwiazywania. Builtin to zwykla wartosc-callable.
        fn = self._eval(head, env)
        args = [self._eval(a, env) for a in x[1:]]
        if isinstance(fn, Closure):
            return self._apply(fn, args)
        if callable(fn):
            return fn(*args)
        raise SyntaxError(f"nie da sie wywolac: {head!r}")

    def _apply(self, clo: "Closure", args: list) -> Any:
        if len(args) != len(clo.params):
            raise TypeError(f"zla liczba argumentow: oczekiwano {len(clo.params)}, "
                            f"podano {len(args)}")
        # FIX v1.1: montaz ramki ATOMOWO (store.lock) i ramka jako TYMCZASOWY
        # korzen — atomy argumentow osiagalne przez caly czas wykonania ciala,
        # nawet gdy scheduler tyka w tle. Po powrocie ramka przestaje byc
        # korzeniem; jesli zlapalo ja domkniecie, zyje dalej przez env_of.
        with self.store.lock:
            local = self.store.bubble_new("call", parent=clo.env)   # nowy scope, rodzic = env closure
            self.store.set_root(local)
            for p, val in zip(clo.params, args):
                atom = self.store.atom_new("arg", p, value=val)
                local.bind(p, atom)
        try:
            return self._eval(clo.body, local)
        finally:
            self.store.unset_root(local)


# ─── pomocnicze ───────────────────────────────────────────────────────────────
def _builtin_print(*a):
    """FIX v1.1 pkt 2: print jako SIDE EFFECT — pisze na stdout, zwraca None.
    Wczesniej zwracal string bez drukowania; wewnatrz `begin` output ginal."""
    print(" ".join(_fmt(x) for x in a))
    return None


def _fold(op, args, start=None):
    vals = list(args)
    if start is None:
        if not vals:
            return 0
        acc, rest = vals[0], vals[1:]
    else:
        acc, rest = start, vals
    for a in rest:
        acc = op(acc, a)
    return acc


def _safediv(x, y):
    if y == 0:
        raise ZeroDivisionError("dzielenie przez zero")
    return x / y


def _truthy(v) -> bool:
    return not (v is False or v is None or v == 0)


def _fmt(v) -> str:
    if v is True:
        return "#t"
    if v is False:
        return "#f"
    if v is None:
        return "()"
    if isinstance(v, Closure):
        return repr(v)
    if callable(v):
        return "<builtin>"                   # FIX v1.1: builtin jako wartosc
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


if __name__ == "__main__":
    from karmazyn_kernel import Store
    s = Store(thermal=True)
    ev = Evaluator(s)
    tests = [
        "(define x 10)", "(define y (+ x 5))", "(+ x y)",
        "((lambda (a b) (* a b)) 6 7)",                 # 42 — lambda natychmiastowa
        "(define add (lambda (a) (lambda (b) (+ a b))))",
        "(define add10 (add 10))", "(add10 5)",         # 15 — domkniecie lapie a=10
        "(define fact (lambda (n) (if (< n 2) 1 (* n (fact (- n 1))))))",
        "(fact 5)",                                     # 120 — rekurencja
        "(define mk (lambda () (begin (define n 0) (lambda () (begin (set! n (+ n 1)) n)))))",
        "(define c (mk))", "(c)", "(c)", "(c)",         # 1,2,3 — licznik ze stanem
        "(or 0 5)", "(and 1 2 3)", "(if #t 1 0)", "(if #f 1 0)",  # special forms / literaly
        "(+ 1 (set! x 7))",                             # 8 — set! zwraca wartosc (v1.1)
        "(begin (print 111) 222)",                      # drukuje 111, zwraca 222 (v1.1)
        "(+ 2 3) ; komentarz inline",                   # 5 — komentarz inline (v1.1)
    ]
    for t in tests:
        print(f"> {t}\n  {ev.eval_line(t)}")