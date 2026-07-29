"""karmazyn_lua.parser — zejście rekurencyjne + wspinaczka po priorytetach."""

from .values import LuaError


# =====================================================================
#  PARSER (zejście rekurencyjne + wspinaczka po priorytetach)
#  AST = krotki z tagiem. Wyrażenia / instrukcje opisane w docstringu.
# =====================================================================
# priorytety dwuargumentowe (lewe binding power)
_BINPOW = {
    "or": 1, "and": 2,
    "<": 3, ">": 3, "<=": 3, ">=": 3, "~=": 3, "==": 3,
    "|": 4,                       # bitowe OR
    "~": 5,                       # bitowe XOR (binarne; unarne ~ to NOT)
    "&": 6,                       # bitowe AND
    "<<": 7, ">>": 7,             # przesunięcia
    "..": 8,                      # prawo-łączny
    "+": 9, "-": 9,
    "*": 10, "/": 10, "//": 10, "%": 10,
    "^": 14,                      # prawo-łączny, mocniejszy niż unarne
}
_RIGHT = {"..", "^"}
_UNARY_BP = 12                    # unarne (not # - ~) mocniejsze niż * / // %, słabsze niż ^


class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0
        self.loop_depth = 0          # legalność 'break' (tylko wewnątrz pętli)
        self.in_vararg = True        # legalność '...' (chunk główny JEST vararg)

    def peek(self):
        return self.toks[self.i]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def _err(self, msg, tok=None):
        """Błąd parse z lokalizacją line:col (1-based)."""
        t = tok if tok is not None else self.peek()
        ln = getattr(t, "line", None) or 1
        cl = getattr(t, "col", None) or 1
        raise LuaError(f"{ln}:{cl}: {msg}")

    def accept(self, kind, val=None):
        t = self.peek()
        if t.kind == kind and (val is None or t.val == val):
            return self.next()
        return None

    def expect(self, kind, val=None):
        t = self.accept(kind, val)
        if t is None:
            got = self.peek()
            self._err(f"oczekiwano {val or kind}, jest {got.val!r}", got)
        return t

    def at_kw(self, *words):
        t = self.peek()
        return t.kind == "kw" and t.val in words

    def at_sym(self, *syms):
        t = self.peek()
        return t.kind == "sym" and t.val in syms

    # ── blok = lista instrukcji aż do terminatora ──
    _BLOCK_END = {"end", "else", "elseif", "until"}

    def parse_chunk(self):
        block = self.parse_block()
        if self.peek().kind != "eof":
            self._err(f"nadmiarowy token: {self.peek().val!r}")
        return block

    def parse_block(self):
        stmts = []
        while True:
            t = self.peek()
            if t.kind == "eof":
                break
            if t.kind == "kw" and t.val in self._BLOCK_END:
                break
            if self.accept("sym", ";"):
                continue
            stmts.append(self.parse_statement())
        self._validate_gotos(stmts)
        return stmts

    def _validate_gotos(self, stmts):
        """Lua: goto nie może wejść w zakres zmiennej local (w tym samym bloku).

        Reguła praktyczna (niski dług): skok do przodu, który omija 'local' /
        'localfunc' i ląduje na etykiecie za nimi, jest błędem.
        Skoki wstecz i poza blok (etykieta w bloku zewnętrznym) — OK tu;
        brak etykiety w bloku = runtime (propagacja do rodzica).
        """
        labels = {}
        for i, s in enumerate(stmts):
            if s[0] == "label":
                name = s[1]
                if name in labels:
                    self._err(f"etykieta '::{name}::' już zdefiniowana w bloku")
                labels[name] = i
        for i, s in enumerate(stmts):
            if s[0] != "goto":
                continue
            name = s[1]
            j = labels.get(name)
            if j is None or j <= i:
                continue                              # wstecz lub etykieta na zewnątrz
            for k in range(i + 1, j):
                sk = stmts[k]
                if sk[0] == "local":
                    nm = sk[1][0] if sk[1] else "?"
                    self._err(
                        f"<goto {name}> jumps into the scope of local '{nm}'"
                    )
                if sk[0] == "localfunc":
                    self._err(
                        f"<goto {name}> jumps into the scope of local '{sk[1]}'"
                    )

    # ── instrukcje ──
    def parse_statement(self):
        if self.at_kw("local"):
            # 'local function NAME' vs zwykłe 'local NAME' / atrybuty
            nxt = self.toks[self.i + 1]
            if nxt.kind == "kw" and nxt.val == "function":
                self.next(); self.next()                 # 'local' 'function'
                name = self.expect("name").val
                params, body = self.parse_funcbody()
                return ("localfunc", name, params, body)
            return self.parse_local()
        if self.at_kw("global"):
            return self.parse_global()
        if self.at_kw("function"):
            self.next()
            # funcname ::= Name {'.' Name} [':' Name]
            target = ("name", self.expect("name").val)
            is_method = False
            while self.at_sym("."):
                self.next()
                target = ("index", target, ("str", self.expect("name").val))
            if self.at_sym(":"):
                self.next()
                target = ("index", target, ("str", self.expect("name").val))
                is_method = True
            params, body = self.parse_funcbody()
            if is_method:
                params = ["self"] + params            # 'function t:m()' wstrzykuje self
            # cukier: function NAZWA(...) == NAZWA = function(...)
            return ("assign", [target], [("function", params, body)])
        if self.at_kw("return"):
            self.next()
            t = self.peek()
            ends = (t.kind == "eof"
                    or (t.kind == "kw" and t.val in self._BLOCK_END)
                    or (t.kind == "sym" and t.val == ";"))
            if ends:
                return ("return", [])
            return ("return", self.parse_exprlist())
        if self.at_kw("break"):
            self.next()
            if self.loop_depth == 0:
                self._err("'break' poza pętlą")
            return ("break",)
        if self.at_kw("if"):
            return self.parse_if()
        if self.at_kw("while"):
            return self.parse_while()
        if self.at_kw("repeat"):
            # repeat block until expr — warunek WIDZI lokalne z bloku (zakres Lua)
            self.next()
            self.loop_depth += 1
            block = self.parse_block()
            self.loop_depth -= 1
            self.expect("kw", "until")
            cond = self.parse_expr()
            return ("repeat", block, cond)
        if self.at_kw("goto"):
            self.next()
            return ("goto", self.expect("name").val)
        if self.at_sym("::"):
            self.next()
            name = self.expect("name").val
            self.expect("sym", "::")
            return ("label", name)
        if self.at_kw("for"):
            return self.parse_for()
        if self.at_kw("do"):
            self.next()
            block = self.parse_block()
            self.expect("kw", "end")
            return ("do", block)
        # przypisanie (wielokrotne) albo wyrażenie-instrukcja, albo gołe wyr. (REPL)
        expr = self.parse_expr()
        if self.at_sym(",") or self.at_sym("="):
            targets = [expr]
            while self.accept("sym", ","):
                targets.append(self.parse_expr())
            self.expect("sym", "=")
            rhs = self.parse_exprlist()
            for t in targets:
                if t[0] not in ("name", "index"):
                    self._err("nieprawidłowy cel przypisania")
            return ("assign", targets, rhs)
        return ("exprstat", expr)

    def parse_exprlist(self):
        exprs = [self.parse_expr()]
        while self.accept("sym", ","):
            exprs.append(self.parse_expr())
        return exprs

    def parse_funcbody(self):
        """ '(' [namelist [',' '...'] | '...'] ')' block 'end' -> (params, body)
        Vararg: '...' może być tylko OSTATNIM parametrem; znacznik '...' w params."""
        self.expect("sym", "(")
        params = []
        if not self.at_sym(")"):
            if self.at_sym("..."):
                self.next()
                params.append("...")
            else:
                params.append(self.expect("name").val)
                while self.accept("sym", ","):
                    if self.at_sym("..."):
                        self.next()
                        params.append("...")
                        break                       # '...' kończy listę
                    params.append(self.expect("name").val)
        self.expect("sym", ")")
        saved = self.loop_depth
        saved_va = self.in_vararg
        self.loop_depth = 0                 # break NIE przekracza granicy funkcji
        self.in_vararg = "..." in params    # '...' legalne tylko w funkcji vararg
        body = self.parse_block()
        self.loop_depth = saved
        self.in_vararg = saved_va
        self.expect("kw", "end")
        return params, body

    def parse_attrib(self):
        """ '<' Name '>' → 'const' | 'close' """
        self.expect("sym", "<")
        name = self.expect("name").val
        self.expect("sym", ">")
        if name not in ("const", "close"):
            self._err(f"nieznany atrybut <{name}>")
        return name

    def parse_attnamelist(self):
        """[attrib] Name [attrib] {',' Name [attrib]} → (names, attrs)"""
        leading = None
        if self.at_sym("<"):
            leading = self.parse_attrib()
        names, attrs = [], []
        while True:
            names.append(self.expect("name").val)
            if self.at_sym("<"):
                attrs.append(self.parse_attrib())
            else:
                attrs.append(leading)
            if not self.accept("sym", ","):
                break
        return names, attrs

    def parse_local(self):
        self.expect("kw", "local")
        names, attrs = self.parse_attnamelist()
        # co najwyżej jeden <close>
        if sum(1 for a in attrs if a == "close") > 1:
            self._err("co najwyżej jedna zmienna <close> na listę")
        inits = []
        if self.accept("sym", "="):
            inits = self.parse_exprlist()
        return ("local", names, inits, attrs)

    def parse_global(self):
        """global [attrib] '*' | global attnamelist ['=' explist]  (Lua 5.5 subset)"""
        self.expect("kw", "global")
        if self.accept("sym", "*"):
            return ("global_star",)                      # global * — deklaracja zbiorcza
        names, attrs = self.parse_attnamelist()
        inits = []
        if self.accept("sym", "="):
            inits = self.parse_exprlist()
        return ("global", names, inits, attrs)

    def parse_if(self):
        self.expect("kw", "if")
        branches = []
        cond = self.parse_expr()
        self.expect("kw", "then")
        branches.append((cond, self.parse_block()))
        while self.at_kw("elseif"):
            self.next()
            c = self.parse_expr()
            self.expect("kw", "then")
            branches.append((c, self.parse_block()))
        els = None
        if self.accept("kw", "else"):
            els = self.parse_block()
        self.expect("kw", "end")
        return ("if", branches, els)

    def parse_while(self):
        self.expect("kw", "while")
        cond = self.parse_expr()
        self.expect("kw", "do")
        self.loop_depth += 1
        block = self.parse_block()
        self.loop_depth -= 1
        self.expect("kw", "end")
        return ("while", cond, block)

    def parse_for(self):
        self.expect("kw", "for")
        names = [self.expect("name").val]
        while self.accept("sym", ","):
            names.append(self.expect("name").val)
        if self.accept("sym", "="):
            # pętla NUMERYCZNA: dokładnie jedna zmienna
            if len(names) != 1:
                self._err("pętla numeryczna 'for' wymaga jednej zmiennej")
            name = names[0]
            start = self.parse_expr()
            self.expect("sym", ",")
            limit = self.parse_expr()
            step = None
            if self.accept("sym", ","):
                step = self.parse_expr()
            self.expect("kw", "do")
            self.loop_depth += 1
            block = self.parse_block()
            self.loop_depth -= 1
            self.expect("kw", "end")
            return ("fornum", name, start, limit, step, block)
        # pętla GENERYCZNA: for namelist in explist do ... end
        self.expect("kw", "in")
        exprs = self.parse_exprlist()
        self.expect("kw", "do")
        self.loop_depth += 1
        block = self.parse_block()
        self.loop_depth -= 1
        self.expect("kw", "end")
        return ("forin", names, exprs, block)

    # ── wyrażenia ──
    def parse_expr(self, rbp=0):
        left = self.parse_unary()
        while True:
            t = self.peek()
            if t.kind == "kw" and t.val in ("and", "or"):
                op = t.val
            elif t.kind == "sym" and t.val in _BINPOW:
                op = t.val
            else:
                break
            lbp = _BINPOW[op]
            if lbp <= rbp:
                break
            self.next()
            # prawo-łączne: rbp = lbp-1, by przyciągnąć równy priorytet w prawo
            next_rbp = lbp - 1 if op in _RIGHT else lbp
            right = self.parse_expr(next_rbp)
            left = ("binop", op, left, right)
        return left

    def parse_unary(self):
        t = self.peek()
        if (t.kind == "kw" and t.val == "not") or (t.kind == "sym" and t.val in ("-", "#", "~")):
            self.next()
            operand = self.parse_expr(_UNARY_BP)
            return ("unop", t.val, operand)
        return self.parse_postfix()

    def _parse_args(self):
        """Argumenty wywołania w trzech formach: (e,...) | "str" | {tabela}.
        Zwraca listę argumentów albo None gdy to nie jest wywołanie."""
        if self.at_sym("("):
            self.next()
            args = []
            if not self.at_sym(")"):
                args.append(self.parse_expr())
                while self.accept("sym", ","):
                    args.append(self.parse_expr())
            self.expect("sym", ")")
            return args
        if self.peek().kind == "str":
            return [("str", self.next().val)]       # cukier: f"x" == f("x")
        if self.at_sym("{"):
            return [self.parse_table()]             # cukier: f{...} == f({...})
        return None

    def parse_postfix(self):
        e = self.parse_primary()
        while True:
            if self.accept("sym", "."):
                key = self.expect("name").val
                e = ("index", e, ("str", key))
            elif self.accept("sym", "["):
                k = self.parse_expr()
                self.expect("sym", "]")
                e = ("index", e, k)
            elif self.at_sym(":"):
                self.next()
                method = self.expect("name").val
                args = self._parse_args()
                if args is None:
                    self._err("oczekiwano argumentów po ':metoda'")
                e = ("methodcall", e, method, args)  # obj:m(..) — obj liczone RAZ
            else:
                args = self._parse_args()
                if args is None:
                    break
                e = ("call", e, args)
        return e

    def parse_primary(self):
        t = self.peek()
        if t.kind == "num":
            self.next()
            return ("num", t.val)
        if t.kind == "str":
            self.next()
            return ("str", t.val)
        if t.kind == "kw" and t.val in ("nil", "true", "false"):
            self.next()
            return (t.val,)
        if t.kind == "name":
            self.next()
            return ("name", t.val)
        if t.kind == "kw" and t.val == "function":
            self.next()
            params, body = self.parse_funcbody()
            return ("function", params, body)
        if self.at_sym("..."):
            self.next()
            if not self.in_vararg:
                self._err("'...' poza funkcją vararg")
            return ("vararg",)
        if self.at_sym("("):
            self.next()
            e = self.parse_expr()
            self.expect("sym", ")")
            return ("paren", e)                  # nawiasy obcinają do 1 wartości
        if self.at_sym("{"):
            return self.parse_table()
        self._err(f"nieoczekiwany token: {t.val!r}", t)

    def parse_table(self):
        self.expect("sym", "{")
        fields = []          # (keyexpr_or_None, valexpr)
        while not self.at_sym("}"):
            if self.accept("sym", "["):
                k = self.parse_expr()
                self.expect("sym", "]")
                self.expect("sym", "=")
                v = self.parse_expr()
                fields.append((k, v))
            elif self.peek().kind == "name" and self.toks[self.i + 1].kind == "sym" \
                    and self.toks[self.i + 1].val == "=":
                key = self.next().val
                self.next()  # '='
                v = self.parse_expr()
                fields.append((("str", key), v))
            else:
                v = self.parse_expr()
                fields.append((None, v))
            if not (self.accept("sym", ",") or self.accept("sym", ";")):
                break
        self.expect("sym", "}")
        return ("table", fields)
