"""
karmazyn_logo.py — LOGO KarmazynOS v4.0
========================================
Interpreter LOGO z integracją phi-space i workspace SDL.

Filozofia:
  LOGO jako język eksploracji przestrzeni przez żółwia.
  Każdy ruch = segment w phi-space (atom T=70).
  Kanwa LOGO zajmuje lewy panel SDL przez claim_left().
  RESET zwalnia panel — terminal wraca do full-screen.

Izomorfizm phi-space:
  Pozycja żółwia ≡ stan atomu (gdzie jest uwaga)
  Segment rysowany ≡ emanacja (ślad w przestrzeni)
  Temperatura kanwy ≡ intensywność aktywności LOGO

Komendy:
  LOGO RUN <kod>     — uruchom kod LOGO
  LOGO FILE <ścieżka>— wczytaj i uruchom plik
  LOGO RESET         — wyczyść kanwę, zwolnij panel
  LOGO HELP          — lista komend

Składnia LOGO:
  FD 100, BK 50     — ruch w przód/tył
  RT 90, LT 45      — obrót w prawo/lewo
  PU, PD            — podnieś/opuść pióro
  REPEAT N [ ... ]  — pętla
  TO nazwa ... END  — definicja procedury
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
karmazyn_logo.py — KarmazynLOGO v4.0
======================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Poprawki v4.0 względem v3.1:
  - Zero mock runtime — używa karmazyn_atom.Atom i karmazyn_phi.PhiSpace
  - Naprawiony scope chain: LogoBubble.parent to obiekt, nie string
  - StopSignal / OutputSignal jako wyjątki (jak _Return w KarmazynJS)
  - Poprawna asocjatywność operatorów (precedence climbing)
  - Atom leak naprawiony: stare atomy żółwia dostają kill() przed zastąpieniem
  - GC przez phi.tick() w pętli repeat co 50 iteracji
  - Nowe: ifelse, setxy, clearscreen, xcor, ycor, output
  - Procedure body/params w Atom.metadata (nie serializowane do E)

Architektura:
  PhiSpace     — zarządza atomami (create/get/tick/GC)
  LogoBubble   — scope z bindingami nazwa → atom.id i parent chain
  LogoEnv      — środowisko: phi + turtle_bubble + global_bubble
  LogoParser   — tokenizer + recursive descent
  LogoInterp   — wykonanie AST
"""

import math
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from karmazyn_atom import Atom
from karmazyn_phi  import PhiSpace

# ─── Stałe ───────────────────────────────────────────────────────────────────

SCREEN_W  = 60
SCREEN_H  = 30
T_VAR     = 50.0
T_PROC    = 55.0
T_TURTLE  = 65.0
GC_EVERY  = 50     # co ile iteracji repeat wywołujemy phi.tick()

_counter = 0
def _uid(prefix: str) -> str:
    global _counter
    _counter += 1
    return f"{prefix}_{_counter}"


# ─── LogoBubble — scope z parent chain ───────────────────────────────────────

class LogoBubble:
    """
    Scope LOGO jako bąbel phi-space.
    bindings: nazwa → atom.id  (nie referencja do obiektu — label)
    parent: LogoBubble lub None

    Zamiast MockBubble z runtime.bubbles — czysty Python obiekt
    bez rejestrowania w phi-space (scope to nie dane, to struktura).
    """
    __slots__ = ("label", "parent", "bindings")

    def __init__(self, label: str,
                 parent: Optional["LogoBubble"] = None):
        self.label    = label
        self.parent   = parent     # LogoBubble, nie string
        self.bindings: Dict[str, str] = {}

    def get_binding(self, name: str) -> Optional[str]:
        return self.bindings.get(name)

    def set_binding(self, name: str, atom_id: str) -> None:
        self.bindings[name] = atom_id

    def del_binding(self, name: str) -> None:
        self.bindings.pop(name, None)

    def __repr__(self) -> str:
        return f"<LogoBubble {self.label} n={len(self.bindings)}>"


# ─── Sygnały kontrolne ────────────────────────────────────────────────────────

class StopSignal(Exception):
    """Propaguje `stop` przez zagnieżdżone pętle i wywołania procedur."""
    pass

class OutputSignal(Exception):
    """Propaguje wartość zwracaną przez `output`."""
    def __init__(self, value: Any):
        self.value = value


# ─── LogoEnv — środowisko ────────────────────────────────────────────────────

class LogoEnv:
    """
    Środowisko żółwia i phi-space.

    Wszystkie atomy (zmienne, procedury, stan żółwia) żyją w phi.
    Scope chain = hierarchia LogoBubble (nie phi-space bubbles).
    Separacja: phi = storage, LogoBubble = scope lookup.

    display — opcjonalny KarmazynDisplay.
    Gdy podany: segmenty trafiają do display.logo_state (pikselowy canvas).
    Gdy None:   tryb ASCII (trail jako lista punktów) — bez zmian.
    """

    def __init__(self, display=None):
        self.phi           = PhiSpace()
        self.global_bubble = LogoBubble("logo_global")
        self.trail:  List[Tuple[float, float]] = []
        self._soul:  Dict[str, Any] = {}
        self.display = display   # KarmazynDisplay lub None
        self._init_turtle()

    # ── Żółw ─────────────────────────────────────────────────────────────────

    def _init_turtle(self) -> None:
        for name, val in [("x", 0.0), ("y", 0.0),
                          ("heading", 0.0), ("pendown", "true")]:
            self._set_turtle_var(name, val)

    def _set_turtle_var(self, name: str, value: Any) -> None:
        """
        Niemutowalność: stary atom dostaje kill(), nowy atom tworzony.
        Binding zaktualizowany do nowego id.
        """
        bubble = self.global_bubble
        old_id = bubble.get_binding(f"__turtle_{name}")
        if old_id:
            old_atom = self.phi.matrix.get(old_id)
            if old_atom:
                old_atom.kill()   # → TOMB → GC przy następnym tick()

        new_id   = _uid(f"turtle_{name}")
        new_atom = self.phi.create_atom(new_id, "turtle", str(value), T_TURTLE)
        bubble.set_binding(f"__turtle_{name}", new_id)

    def get_turtle(self) -> Dict[str, Any]:
        def val(name: str):
            aid  = self.global_bubble.get_binding(f"__turtle_{name}")
            atom = self.phi.matrix.get(aid) if aid else None
            return atom.E if atom else None
        return {
            "x":       float(val("x")       or 0.0),
            "y":       float(val("y")       or 0.0),
            "heading": float(val("heading") or 0.0),
            "pendown": (val("pendown") or "true").lower() == "true",
        }

    def set_turtle(self, x=None, y=None, heading=None, pendown=None) -> None:
        if x       is not None: self._set_turtle_var("x", x)
        if y       is not None: self._set_turtle_var("y", y)
        if heading is not None: self._set_turtle_var("heading", heading % 360.0)
        if pendown is not None:
            self._set_turtle_var("pendown", "true" if pendown else "false")
        # Synchronizuj logo_state w trybie graficznym
        if self.display and self.display.available:
            s = self.get_turtle()
            self.display.logo_state.set_turtle(
                s['x'], s['y'], s['heading'], s['pendown'])

    # ── Ślad ─────────────────────────────────────────────────────────────────

    def add_trail(self, x: float, y: float) -> None:
        self.trail.append((x, y))
        if len(self.trail) > 2000:
            self.trail = self.trail[-1500:]

    def clear_trail(self) -> None:
        self.trail = []
        if self.display and self.display.available:
            self.display.logo_state.clear()

    # ── Persystencja ──────────────────────────────────────────────────────────

    def save(self) -> None:
        self._soul["logo"] = {**self.get_turtle(), "trail": self.trail[:]}

    def load(self) -> bool:
        s = self._soul.get("logo")
        if not s:
            return False
        self.set_turtle(x=s["x"], y=s["y"],
                        heading=s["heading"], pendown=s["pendown"])
        self.trail = s.get("trail", [])
        return True


# ─── Parser LOGO ──────────────────────────────────────────────────────────────

class LogoParser:
    """
    Tokenizer + recursive descent parser.
    Wyrażenia: precedence climbing (poprawna asocjatywność).
    """

    PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}

    def __init__(self):
        self.tokens: List[Tuple[str, str]] = []
        self.pos = 0

    def tokenize(self, text: str) -> List[Tuple[str, str]]:
        import re
        patterns = [
            (r'\[',                     'LBRACK'),
            (r'\]',                     'RBRACK'),
            (r'\(',                     'LPAREN'),
            (r'\)',                     'RPAREN'),
            (r':[a-zA-Z_][a-zA-Z0-9_]*','COLON'),
            (r'[0-9]+(?:\.[0-9]+)?',    'NUMBER'),
            (r'[a-zA-Z_][a-zA-Z0-9_]*', 'WORD'),
            (r'[+\-*/]',                'OP'),
            (r'[<>=]',                  'CMP'),
        ]
        toks, i, n = [], 0, len(text)
        while i < n:
            if text[i].isspace(): i += 1; continue
            if text[i] == ';':    # komentarz do końca linii
                while i < n and text[i] != '\n': i += 1
                continue
            matched = False
            for pat, typ in patterns:
                import re as _re
                m = _re.match(pat, text[i:])
                if m:
                    toks.append((typ, m.group(0)))
                    i += len(m.group(0))
                    matched = True
                    break
            if not matched:
                i += 1
        return toks

    def parse(self, code: str) -> list:
        self.tokens = self.tokenize(code)
        self.pos    = 0
        stmts = []
        while self.pos < len(self.tokens):
            s = self._stmt()
            if s is not None:
                stmts.append(s)
        return stmts

    def _peek(self) -> Optional[Tuple[str, str]]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _consume(self, expected_type: str = None) -> Tuple[str, str]:
        tok = self._peek()
        if tok is None:
            raise SyntaxError("Nieoczekiwany koniec wejścia")
        if expected_type and tok[0] != expected_type:
            raise SyntaxError(f"Oczekiwano {expected_type}, got {tok}")
        self.pos += 1
        return tok

    def _eat(self, typ: str, val: str = None) -> bool:
        t = self._peek()
        if t and t[0] == typ and (val is None or t[1].lower() == val):
            self.pos += 1
            return True
        return False

    def _stmt(self) -> Optional[tuple]:
        tok = self._peek()
        if not tok:
            return None
        typ, val = tok
        if typ == 'WORD':
            cmd = val.lower()
            dispatch = {
                'forward': self._s_forward, 'fd': self._s_forward,
                'back':    self._s_back,    'bk': self._s_back,
                'right':   self._s_right,   'rt': self._s_right,
                'left':    self._s_left,    'lt': self._s_left,
                'penup':   self._s_penup,   'pu': self._s_penup,
                'pendown': self._s_pendown, 'pd': self._s_pendown,
                'repeat':  self._s_repeat,
                'make':    self._s_make,
                'print':   self._s_print,
                'to':      self._s_def,
                'stop':    self._s_stop,
                'output':  self._s_output,
                'ifelse':  self._s_ifelse,
                'if':      self._s_if,
                'setxy':   self._s_setxy,
                'clearscreen': self._s_clearscreen,
                'cs':      self._s_clearscreen,
            }
            if cmd in dispatch:
                return dispatch[cmd]()
            # Wywołanie procedury
            self._consume('WORD')
            args = []
            while self._peek() and self._peek()[0] not in ('RBRACK',):
                # Zatrzymaj przy następnym słowie kluczowym
                t2 = self._peek()
                if t2 and t2[0] == 'WORD' and t2[1].lower() in (
                    'end','else','stop','output'
                ):
                    break
                args.append(self._expr())
            return ('call', cmd, args)
        elif typ == 'LBRACK':
            return self._block()
        # Nierozpoznany token (NUMBER, OP itp.) — parsuj jako wyrażenie
        # Zapobiega infinite loop gdy _stmt nie konsumuje tokenu
        try:
            return ('expr', self._expr())
        except Exception:
            self._consume()   # wymuś postęp
            return None

    def _block(self) -> list:
        self._consume('LBRACK')
        stmts = []
        while self._peek() and self._peek()[0] != 'RBRACK':
            s = self._stmt()
            if s is not None:
                stmts.append(s)
        self._consume('RBRACK')
        return stmts

    def _s_forward(self):
        self._consume(); return ('forward', self._expr())
    def _s_back(self):
        self._consume(); return ('back', self._expr())
    def _s_right(self):
        self._consume(); return ('right', self._expr())
    def _s_left(self):
        self._consume(); return ('left', self._expr())
    def _s_penup(self):
        self._consume(); return ('penup',)
    def _s_pendown(self):
        self._consume(); return ('pendown',)
    def _s_stop(self):
        self._consume(); return ('stop',)
    def _s_clearscreen(self):
        self._consume(); return ('clearscreen',)
    def _s_setxy(self):
        self._consume()
        return ('setxy', self._expr(), self._expr())
    def _s_output(self):
        self._consume(); return ('output', self._expr())
    def _s_print(self):
        self._consume(); return ('print', self._expr())
    def _s_make(self):
        self._consume()
        name = self._consume('WORD')[1]
        return ('make', name, self._expr())

    def _s_repeat(self):
        self._consume()
        count = self._expr()
        if not self._peek() or self._peek()[0] != 'LBRACK':
            raise SyntaxError("repeat wymaga bloku [...]")
        block = self._block()
        return ('repeat', count, block)

    def _s_if(self):
        self._consume()
        cond = self._expr()
        then = self._block()
        return ('if', cond, then)

    def _s_ifelse(self):
        self._consume()
        cond  = self._expr()
        then  = self._block()
        else_ = self._block()
        return ('ifelse', cond, then, else_)

    def _s_def(self):
        self._consume()
        name   = self._consume('WORD')[1]
        params = []
        while self._peek() and self._peek()[0] == 'COLON':
            params.append(self._consume('COLON')[1][1:])
        body = []
        while self._peek():
            t = self._peek()
            if t[0] == 'WORD' and t[1].lower() == 'end':
                self._consume()
                break
            s = self._stmt()
            if s is not None:
                body.append(s)
        return ('def', name, params, body)

    # ── Wyrażenia (precedence climbing) ──────────────────────────────────────

    def _expr(self, min_prec: int = 0) -> tuple:
        left = self._atom()
        while True:
            t = self._peek()
            if not t:
                break
            if t[0] == 'OP':
                prec = self.PRECEDENCE.get(t[1], 0)
                if prec <= min_prec:
                    break
                op = self._consume('OP')[1]
                right = self._expr(prec)   # prawa rekurencja z progiem = prec
                left  = ('op', left, op, right)
            elif t[0] == 'CMP':
                op = self._consume('CMP')[1]
                right = self._expr(0)
                left  = ('cmp', left, op, right)
            else:
                break
        return left

    def _atom(self) -> tuple:
        tok = self._consume()
        typ, val = tok
        if typ == 'NUMBER':
            return ('num', float(val))
        if typ == 'COLON':
            return ('var', val[1:])
        if typ == 'WORD':
            # xcor / ycor jako wyrażenia
            if val.lower() == 'xcor':   return ('xcor',)
            if val.lower() == 'ycor':   return ('ycor',)
            if val.lower() == 'true':   return ('num', 1.0)
            if val.lower() == 'false':  return ('num', 0.0)
            # Wywołanie procedury jako wyrażenie: podwoj 7
            # Zbierz argumenty aż do napotkania operatora/ogranicznika
            cmd = val.lower()
            if cmd not in ('end','else','stop','output','to','repeat',
                           'if','ifelse','make','print','forward','fd',
                           'back','bk','right','rt','left','lt',
                           'penup','pu','pendown','pd','setxy','clearscreen','cs'):
                args = []
                while self._peek() and self._peek()[0] in ('NUMBER','COLON'):
                    args.append(self._atom())
                if args:
                    return ('call_expr', cmd, args)
            return ('word', val)
        if typ == 'LBRACK':
            # lista — zwróć jako listę wyrażeń
            items = []
            while self._peek() and self._peek()[0] != 'RBRACK':
                items.append(self._atom())
            self._consume('RBRACK')
            return ('list', items)
        if typ == 'LPAREN':
            # Grupowanie (expr) lub wywołanie procedury (proc args...)
            # Sprawdź czy pierwsze jest WORD (procedure call)
            t = self._peek()
            if t and t[0] == 'WORD' and t[1].lower() not in (
                'end','else','stop','output','to','repeat',
                'if','ifelse','make','print','forward','fd',
                'back','bk','right','rt','left','lt',
                'penup','pu','pendown','pd','setxy','clearscreen','cs',
                'true','false','xcor','ycor'
            ):
                # Wywołanie procedury — czytaj args aż do RPAREN
                cmd = self._consume('WORD')[1].lower()
                args = []
                while self._peek() and self._peek()[0] != 'RPAREN':
                    args.append(self._expr(0))
                    if self._peek() and self._peek()[0] == 'RPAREN':
                        break
                self._eat('RPAREN')
                return ('call_expr', cmd, args)
            else:
                # Grupowanie — (expr)
                e = self._expr(0)
                self._eat('RPAREN')
                return e

        raise SyntaxError(f"Nieoczekiwany token w wyrażeniu: {typ} {val!r}")


# ─── Interpreter ─────────────────────────────────────────────────────────────

class LogoInterp:
    """
    Interpreter LOGO.
    Scope chain przez hierarchię LogoBubble.
    Atomy w phi.
    StopSignal/OutputSignal jako wyjątki kontrolne.
    """

    def __init__(self, env: LogoEnv):
        self.env     = env
        self.parser  = LogoParser()
        self.bubble  = env.global_bubble
        self._iter_n = 0   # licznik dla GC w repeat

    # ── Lookup zmiennych ──────────────────────────────────────────────────────

    def _find(self, name: str) -> Optional[Atom]:
        bubble = self.bubble
        while bubble:
            aid  = bubble.get_binding(name)
            atom = self.env.phi.matrix.get(aid) if aid else None
            if atom and not atom.is_dead():
                atom.touch()
                return atom
            bubble = bubble.parent
        return None

    def _find_binding_bubble(self, name: str) -> Optional[LogoBubble]:
        """Znajdź bąbel gdzie zmienna jest bindowana (dla make UCBLogo)."""
        bubble = self.bubble
        while bubble:
            aid = bubble.get_binding(name)
            if aid:
                atom = self.env.phi.matrix.get(aid)
                if atom and not atom.is_dead():
                    return bubble
            bubble = bubble.parent
        return None

    # ── Ewaluacja wyrażeń ─────────────────────────────────────────────────────

    def _eval(self, expr: tuple) -> Any:
        op = expr[0]

        if op == 'num':
            return expr[1]

        if op == 'var':
            atom = self._find(expr[1])
            if atom is None:
                raise NameError(f"Zmienna '{expr[1]}' niezdefiniowana")
            if atom.S == "procedure":
                raise TypeError(f"'{expr[1]}' to procedura, nie wartość")
            try:    return float(atom.E)
            except: return atom.E

        if op == 'word':
            return expr[1]

        if op == 'xcor':
            return self.env.get_turtle()["x"]

        if op == 'ycor':
            return self.env.get_turtle()["y"]

        if op == 'call_expr':
            # Wywołanie procedury jako wyrażenie (zwraca wartość przez output)
            _, name, arg_exprs = expr
            args = [self._eval(a) for a in arg_exprs]
            result = self._call_proc(name, args)
            if result is None:
                raise ValueError(f"Procedura '{name}' nie zwraca wartości (brak output)")
            return result

        if op == 'op':
            _, l, operator, r = expr
            lv = self._eval(l)
            rv = self._eval(r)
            return {
                '+': lv + rv, '-': lv - rv,
                '*': lv * rv, '/': lv / rv if rv != 0 else float('inf'),
            }[operator]

        if op == 'cmp':
            _, l, operator, r = expr
            lv, rv = self._eval(l), self._eval(r)
            return 1.0 if {
                '<': lv < rv, '>': lv > rv, '=': lv == rv,
            }.get(operator, False) else 0.0

        if op == 'list':
            return [self._eval(e) for e in expr[1]]

        raise SyntaxError(f"Nieznane wyrażenie: {op}")

    # ── Wykonanie instrukcji ──────────────────────────────────────────────────

    def _exec(self, stmt) -> None:
        if isinstance(stmt, list):
            for s in stmt:
                self._exec(s)
            return

        op = stmt[0]

        if op == 'forward':
            self._move(self._eval(stmt[1]))

        elif op == 'back':
            self._move(-self._eval(stmt[1]))

        elif op == 'right':
            self._rotate(-self._eval(stmt[1]))

        elif op == 'left':
            self._rotate(self._eval(stmt[1]))

        elif op == 'penup':
            self.env.set_turtle(pendown=False)

        elif op == 'pendown':
            self.env.set_turtle(pendown=True)

        elif op == 'setxy':
            _, xex, yex = stmt
            self.env.set_turtle(x=self._eval(xex), y=self._eval(yex))

        elif op == 'clearscreen':
            self.env.clear_trail()
            self.env.set_turtle(x=0.0, y=0.0, heading=0.0, pendown=True)

        elif op == 'stop':
            raise StopSignal()

        elif op == 'output':
            raise OutputSignal(self._eval(stmt[1]))

        elif op == 'print':
            print(self._eval(stmt[1]))

        elif op == 'make':
            _, name, expr = stmt
            value = self._eval(expr)
            existing = self._find(name)
            if existing and existing.S == "procedure":
                raise NameError(f"'{name}' to procedura — użyj innej nazwy")
            aid = _uid(f"var_{name}")
            self.env.phi.create_atom(aid, "variable", str(value), T_VAR)
            # UCBLogo semantyka: jeśli zmienna istnieje w scope chain → zaktualizuj tam
            # Jeśli nie istnieje → utwórz w global scope
            target_bubble = self._find_binding_bubble(name)
            if target_bubble is None:
                target_bubble = self.env.global_bubble
            target_bubble.set_binding(name, aid)

        elif op == 'def':
            _, name, params, body = stmt
            existing = self._find(name)
            if existing and existing.S == "variable":
                raise NameError(f"'{name}' to zmienna — użyj innej nazwy")
            aid  = _uid(f"proc_{name}")
            atom = self.env.phi.create_atom(aid, "procedure", name, T_PROC)
            atom.metadata['params'] = params
            atom.metadata['body']   = body
            self.env.global_bubble.set_binding(name, aid)

        elif op == 'call':
            _, name, arg_exprs = stmt
            args = [self._eval(a) for a in arg_exprs]
            self._call_proc(name, args)

        elif op == 'repeat':
            _, count_expr, body = stmt
            count = int(self._eval(count_expr))
            for i in range(count):
                try:
                    for s in body:
                        self._exec(s)
                except StopSignal:
                    break
                self._iter_n += 1
                if self._iter_n % GC_EVERY == 0:
                    self.env.phi.tick()

        elif op == 'if':
            _, cond, then = stmt
            if self._eval(cond):
                try:
                    for s in then:
                        self._exec(s)
                except StopSignal:
                    raise

        elif op == 'ifelse':
            _, cond, then, else_ = stmt
            branch = then if self._eval(cond) else else_
            try:
                for s in branch:
                    self._exec(s)
            except StopSignal:
                raise

        elif op == 'expr':
            # Wyrażenie jako instrukcja — ewaluuj (efekty uboczne) i ignoruj wynik
            self._eval(stmt[1])

        else:
            raise SyntaxError(f"Nieznana instrukcja: {op}")

    def _call_proc(self, name: str, args: List[Any]) -> Any:
        """Wywołanie procedury z własnym scope (LogoBubble jako frame)."""
        atom = self._find(name)
        if atom is None or atom.S != "procedure":
            raise NameError(f"Procedura '{name}' niezdefiniowana")

        params = atom.metadata.get('params', [])
        body   = atom.metadata.get('body',   [])

        if len(args) != len(params):
            raise TypeError(
                f"'{name}' oczekuje {len(params)} arg, dostało {len(args)}"
            )

        # Nowy frame — rodzic = bieżący scope (poprawiona wersja)
        frame      = LogoBubble(f"frame_{name}_{_uid('')}", parent=self.bubble)
        old_bubble = self.bubble
        self.bubble = frame

        # Binduj parametry
        for param, val in zip(params, args):
            aid = _uid(f"param_{param}")
            self.env.phi.create_atom(aid, "variable", str(val), T_VAR)
            frame.set_binding(param, aid)

        result = None
        try:
            for s in body:
                self._exec(s)
        except StopSignal:
            pass
        except OutputSignal as out:
            result = out.value
        finally:
            self.bubble = old_bubble

        return result

    # ── Ruch żółwia ───────────────────────────────────────────────────────────

    def _move(self, distance: float) -> None:
        state = self.env.get_turtle()
        rad   = math.radians(state['heading'])
        dx    = distance * math.cos(rad)
        dy    = distance * math.sin(rad)
        new_x = state['x'] + dx
        new_y = state['y'] + dy

        if state['pendown']:
            d = self.env.display
            if d and d.available:
                # Tryb graficzny: jeden segment = jedna linia na canvas
                d.logo_state.add_segment(
                    state['x'], state['y'], new_x, new_y)
            else:
                # Tryb ASCII: interpolacja punktów (bez zmian)
                steps = max(int(abs(distance)), 1)
                for i in range(1, steps + 1):
                    self.env.add_trail(
                        state['x'] + dx * i / steps,
                        state['y'] + dy * i / steps,
                    )

        half_w = SCREEN_W / 2
        half_h = SCREEN_H / 2
        self.env.set_turtle(
            x = max(-half_w, min(half_w, new_x)),
            y = max(-half_h, min(half_h, new_y)),
        )

    def _rotate(self, angle: float) -> None:
        state = self.env.get_turtle()
        self.env.set_turtle(heading=(state['heading'] + angle) % 360.0)

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> str:
        state = self.env.get_turtle()
        grid  = [[' '] * SCREEN_W for _ in range(SCREEN_H)]

        for (x, y) in self.env.trail:
            ix = int(round(x)) + SCREEN_W // 2
            iy = SCREEN_H - 1 - (int(round(y)) + SCREEN_H // 2)
            if 0 <= ix < SCREEN_W and 0 <= iy < SCREEN_H:
                grid[iy][ix] = '.'

        tx = int(round(state['x'])) + SCREEN_W // 2
        ty = SCREEN_H - 1 - (int(round(state['y'])) + SCREEN_H // 2)
        h  = state['heading']
        ch = '▲' if 45<=h<135 else '◄' if 135<=h<225 else '▼' if 225<=h<315 else '►'
        if 0 <= tx < SCREEN_W and 0 <= ty < SCREEN_H:
            grid[ty][tx] = ch

        return '\n'.join(''.join(row) for row in grid)

    # ── Publiczny interfejs ───────────────────────────────────────────────────

    def run(self, code: str) -> None:
        ast = self.parser.parse(code)
        for stmt in ast:
            self._exec(stmt)

    def reset(self) -> None:
        """Reset żółwia i zmiennych użytkownika (procedury zachowane)."""
        self.env._init_turtle()
        self.env.clear_trail()
        self.bubble = self.env.global_bubble
        # Usuń zmienne (zachowaj procedury)
        to_del = []
        for name, aid in list(self.bubble.bindings.items()):
            atom = self.env.phi.matrix.get(aid)
            if atom and atom.S == "variable":
                to_del.append(name)
        for name in to_del:
            self.bubble.del_binding(name)

    def phi_stats(self) -> Dict[str, Any]:
        return self.env.phi.snapshot()


# ─── Powłoka ─────────────────────────────────────────────────────────────────

class LogoShell:
    """Powłoka LOGO — przyjmuje komendy, zarządza workspace SDL."""
    def __init__(self, display=None):
        self.env      = LogoEnv(display=display)
        self.interp   = LogoInterp(self.env)
        self._display = display
        # Podepnij phi-space LOGO do display (phi-map pokazuje atomy LOGO)
        if display is not None and hasattr(display, 'bind_phi'):
            display.bind_phi(self.env.phi)
        # NIE zajmuj lewego panelu przy init — tylko gdy użytkownik uruchomi RUN

    def _claim_workspace(self) -> None:
        """Zajmij lewy panel dla kanwy LOGO."""
        d = self._display
        if d and d.available and d.renderer:
            # Zdefiniuj draw_fn czytający z logo_state (immediate mode)
            from karmazyn_display import draw_logo, DrawCtx
            import pygame

            def _draw_logo_panel(ctx: DrawCtx) -> None:
                # flush segmentów w main thread
                d.logo_state.flush_segments()
                draw_logo(ctx, d.logo_state)

            d.renderer.claim_left(_draw_logo_panel, "LOGO")

    def _release_workspace(self) -> None:
        """Zwolnij lewy panel — terminal wraca do full-screen."""
        d = self._display
        if d and d.available and d.renderer:
            d.renderer.release_left()

    def cmd(self, args: List[str]) -> str:
        if not args:
            self._repl(); return ""
        sub = args[0].upper()

        if sub == "RUN":
            code = ' '.join(args[1:])
            try:
                self._claim_workspace()
                self.interp.run(code)
                if self._display and self._display.available:
                    return "OK — rysunek w oknie graficznym"
                return self.interp.render()
            except Exception as e:
                return f"Błąd: {e}"

        if sub == "FILE":
            if len(args) < 2:
                return "LOGO FILE <ścieżka>"
            try:
                code = open(args[1], encoding='utf-8').read()
                self.interp.run(code)
                if self._display and self._display.available:
                    return "OK — rysunek w oknie graficznym"
                return self.interp.render()
            except Exception as e:
                return f"Błąd: {e}"

        if sub == "RESET":
            self.interp.reset()
            self._release_workspace()
            return "Reset."

        if sub == "SAVE":
            self.env.save(); return "Zapisano."

        if sub == "LOAD":
            return "Wczytano." if self.env.load() else "Brak stanu."

        if sub == "SHOW":
            return self.interp.render()

        if sub == "PHI":
            s = self.interp.phi_stats()
            return '\n'.join(f"  {k}: {v}" for k, v in s.items())

        return "Opcje: RUN, FILE, RESET, SAVE, LOAD, SHOW, PHI"

    def _repl(self) -> None:
        print("KarmazynLOGO v4.0. 'exit' aby wyjść, 'show' aby zobaczyć ekran.")
        while True:
            try:
                line = input("LOGO> ").strip()
                if line.lower() in ('exit', 'quit'):
                    break
                if not line:
                    continue
                if line.lower() == 'show':
                    print(self.interp.render()); continue
                try:
                    self.interp.run(line)
                except Exception as e:
                    print(f"Błąd: {e}")
            except EOFError:
                break


# ─── Punkt wejścia ───────────────────────────────────────────────────────────

_SHELL: Optional[LogoShell] = None

def cmd_logo(args: List[str], display=None) -> str:
    global _SHELL
    if _SHELL is None:
        _SHELL = LogoShell(display=display)
    elif display is not None and _SHELL._display is None:
        # Podpięcie display post-factum
        _SHELL._display = display
        _SHELL.env.display = display
    return _SHELL.cmd(args)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(cmd_logo(sys.argv[1:]))
    else:
        cmd_logo([])