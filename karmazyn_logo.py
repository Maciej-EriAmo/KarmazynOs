#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
karmazyn_logo.py — KarmazynLOGO v3.1 (phi‑space native, binding abstraction)
==============================================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Poprawki:
- bindings: bąbel przechowuje mapę nazwa → label atomu (nie referencję do obiektu)
- atomy są niemutowalne (zmiana wartości tworzy nowy atom, stary stygnie)
- parent chain bezpieczny (brak rzutowania w trakcie lookup)
- repeat wymaga bloku [...]
- procedury i zmienne mają oddzielne przestrzenie logiczne (ale współdzielą nazwy)
- [FIX] Prawdziwa niemutowalność dla atomów stanu żółwia.
- [FIX] Generowanie unikalnych etykiet, zapobiegające kolizjom i nadpisywaniu w słowniku runtime.
"""

import math
import sys
import time
import readline
from typing import Any, Dict, List, Optional, Tuple

def _uid(prefix: str) -> str:
    """Generuje globalnie unikalną etykietę dla atomu lub bąbla."""
    return f"{prefix}_{time.monotonic_ns()}"

# ----------------------------------------------------------------------
# Poprawiony mock runtime (phi‑space z bindingami)
# ----------------------------------------------------------------------
try:
    from karmazyn_shell import runtime
except ImportError:
    class MockAtom:
        __slots__ = ('label', 'S', 'E', 'T')
        def __init__(self, label: str, S: str, E: Any, T: float):
            self.label = label
            self.S = S
            self.E = E
            self.T = T

    class MockBubble:
        __slots__ = ('label', 'parent', 'bindings')
        def __init__(self, label: str, parent=None):
            self.label = label
            self.parent = parent   # referencja do innego MockBubble lub None
            self.bindings: Dict[str, str] = {}   # nazwa → label atomu

        def get_binding(self, name: str) -> Optional[str]:
            return self.bindings.get(name)

        def set_binding(self, name: str, atom_label: str) -> None:
            self.bindings[name] = atom_label

        def __repr__(self):
            return f"<Bubble {self.label}>"

    class MockRuntime:
        def __init__(self):
            self.atoms: Dict[str, MockAtom] = {}
            self.bubbles: Dict[str, MockBubble] = {}
            self.soul_store: Dict[str, Any] = {}

        def create_atom(self, label: str, S: str, E: Any, T: float) -> MockAtom:
            atom = MockAtom(label, S, E, T)
            self.atoms[label] = atom
            return atom

        def get_atom(self, label: str) -> Optional[MockAtom]:
            return self.atoms.get(label)

        def create_bubble(self, label: str, parent=None) -> MockBubble:
            parent_bubble = None
            if parent is not None and isinstance(parent, str):
                parent_bubble = self.bubbles.get(parent)
            bubble = MockBubble(label, parent_bubble)
            self.bubbles[label] = bubble
            return bubble

        def get_bubble(self, label: str) -> Optional[MockBubble]:
            return self.bubbles.get(label)

        def import_to_bubble(self, bubble_label: str, atom_label: str) -> None:
            bubble = self.bubbles.get(bubble_label)
            if bubble:
                bubble.bindings[atom_label] = atom_label   

        def consolidate(self, atom_label: str) -> None:
            pass   

        def tick(self) -> None:
            pass # Hook dla GC i stygnięcia atomów

    runtime = MockRuntime()

# Stałe
SCREEN_WIDTH = 60
SCREEN_HEIGHT = 30
T_VAR = 50.0
T_PROC = 55.0
T_TURTLE = 65.0

# ----------------------------------------------------------------------
# Środowisko LOGO (phi‑space z bindingami)
# ----------------------------------------------------------------------
class LogoEnvironment:
    def __init__(self):
        self.global_bubble = runtime.create_bubble("logo_global")
        self.turtle_bubble = runtime.create_bubble("logo_turtle", parent="logo_global")
        self._init_turtle()
        self.trail: List[Tuple[float, float]] = []

    def _init_turtle(self):
        for name, default in [("x", 0.0), ("y", 0.0), ("heading", 0.0), ("pendown", "true")]:
            self._update_turtle_var(name, default)

    def _update_turtle_var(self, name: str, value: Any):
        """Pomocnicza metoda tworząca nowy, unikalny atom stanu, egzekwująca niemutowalność."""
        label = _uid(f"turtle_{name}")
        new_atom = runtime.create_atom(label, "turtle", str(value), T_TURTLE)
        self.turtle_bubble.set_binding(name, new_atom.label)

    def get_turtle_state(self) -> dict:
        bubble = self.turtle_bubble
        def get_val(name):
            atom_label = bubble.get_binding(name)
            if atom_label:
                atom = runtime.get_atom(atom_label)
                return atom.E if atom else None
            return None
        return {
            'x': float(get_val("x") or 0.0),
            'y': float(get_val("y") or 0.0),
            'heading': float(get_val("heading") or 0.0),
            'pendown': (get_val("pendown") or "true").lower() == "true"
        }

    def set_turtle_state(self, x=None, y=None, heading=None, pendown=None):
        if x is not None:
            self._update_turtle_var("x", x)
        if y is not None:
            self._update_turtle_var("y", y)
        if heading is not None:
            self._update_turtle_var("heading", heading % 360.0)
        if pendown is not None:
            self._update_turtle_var("pendown", "true" if pendown else "false")

    def add_trail_point(self, x: float, y: float):
        self.trail.append((x, y))
        if len(self.trail) > 2000:
            self.trail = self.trail[-1500:]

    def clear_trail(self):
        self.trail = []

    def save_state(self) -> bool:
        state = {**self.get_turtle_state(), 'trail': self.trail[:]}
        runtime.soul_store['logo_state'] = state
        return True

    def load_state(self) -> bool:
        state = runtime.soul_store.get('logo_state')
        if state:
            self.set_turtle_state(x=state['x'], y=state['y'],
                                  heading=state['heading'], pendown=state['pendown'])
            self.trail = state.get('trail', [])
            return True
        return False

# ----------------------------------------------------------------------
# Parser LOGO (z wymuszonym blokiem repeat)
# ----------------------------------------------------------------------
class LogoParser:
    def __init__(self):
        self.tokens = []
        self.pos = 0

    def tokenize(self, text: str):
        import re
        patterns = [
            (r'\[', 'LBRACK'), (r'\]', 'RBRACK'),
            (r'[a-zA-Z_][a-zA-Z0-9_]*', 'WORD'),
            (r'[0-9]+(\.[0-9]+)?', 'NUMBER'),
            (r':[a-zA-Z_][a-zA-Z0-9_]*', 'COLON'),
            (r'[+\-*/]', 'OPERATOR'),
            (r'[^ \t\n\r\f\v]+', 'UNKNOWN')
        ]
        tokens = []
        i = 0
        n = len(text)
        while i < n:
            if text[i].isspace():
                i += 1
                continue
            matched = False
            for pat, typ in patterns:
                m = re.match(pat, text[i:])
                if m:
                    val = m.group(0)
                    tokens.append((typ, val))
                    i += len(val)
                    matched = True
                    break
            if not matched:
                i += 1
        return tokens

    def parse(self, code: str):
        self.tokens = self.tokenize(code)
        self.pos = 0
        statements = []
        while self.pos < len(self.tokens):
            stmt = self._parse_statement()
            if stmt is not None:
                statements.append(stmt)
        return statements

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _consume(self, expected_type=None):
        tok = self._peek()
        if tok is None:
            raise SyntaxError("Unexpected end of input")
        if expected_type and tok[0] != expected_type:
            raise SyntaxError(f"Expected {expected_type}, got {tok[0]}")
        self.pos += 1
        return tok

    def _parse_statement(self):
        tok = self._peek()
        if not tok:
            return None
        typ, val = tok
        if typ == 'WORD':
            cmd = val.lower()
            if cmd in ('forward','fd'): return self._parse_forward()
            if cmd in ('back','bk'): return self._parse_back()
            if cmd in ('right','rt'): return self._parse_right()
            if cmd in ('left','lt'): return self._parse_left()
            if cmd in ('penup','pu'): self._consume('WORD'); return ('penup',)
            if cmd in ('pendown','pd'): self._consume('WORD'); return ('pendown',)
            if cmd == 'repeat': return self._parse_repeat()
            if cmd == 'make': return self._parse_make()
            if cmd == 'print': return self._parse_print()
            if cmd == 'to': return self._parse_procedure()
            if cmd == 'stop': self._consume('WORD'); return ('stop',)
            self._consume('WORD')
            args = []
            while self._peek() and self._peek()[0] not in ('RBRACK', None):
                args.append(self._parse_expr())
            return ('call', cmd, args)
        elif typ == 'LBRACK':
            self._consume('LBRACK')
            block = []
            while self._peek() and self._peek()[0] != 'RBRACK':
                block.append(self._parse_statement())
            self._consume('RBRACK')
            return block
        else:
            return ('expr', self._parse_expr())

    def _parse_repeat(self):
        self._consume('WORD')
        count_expr = self._parse_expr()
        if self._peek() is None or self._peek()[0] != 'LBRACK':
            raise SyntaxError("repeat requires a block [...]")
        block = self._parse_statement()
        if not isinstance(block, list):
            raise SyntaxError("repeat block must be a list of statements")
        return ('repeat', count_expr, block)

    def _parse_forward(self):
        self._consume('WORD')
        return ('forward', self._parse_expr())
    def _parse_back(self):
        self._consume('WORD')
        return ('back', self._parse_expr())
    def _parse_right(self):
        self._consume('WORD')
        return ('right', self._parse_expr())
    def _parse_left(self):
        self._consume('WORD')
        return ('left', self._parse_expr())
    def _parse_make(self):
        self._consume('WORD')
        name_tok = self._consume('WORD')
        var_name = name_tok[1]
        expr = self._parse_expr()
        return ('make', var_name, expr)
    def _parse_print(self):
        self._consume('WORD')
        return ('print', self._parse_expr())
    def _parse_procedure(self):
        self._consume('WORD')
        name_tok = self._consume('WORD')
        proc_name = name_tok[1]
        params = []
        while self._peek() and self._peek()[0] == 'COLON':
            p = self._consume('COLON')[1][1:]
            params.append(p)
        body = []
        while self._peek() and not (self._peek()[0] == 'WORD' and self._peek()[1].lower() == 'end'):
            stmt = self._parse_statement()
            if stmt is not None:
                body.append(stmt)
        self._consume('WORD')
        return ('def', proc_name, params, body)
    def _parse_expr(self):
        left = self._parse_atom()
        if self._peek() and self._peek()[0] == 'OPERATOR':
            op = self._consume('OPERATOR')[1]
            right = self._parse_expr()
            return ('op', left, op, right)
        return left
    def _parse_atom(self):
        tok = self._consume()
        typ, val = tok
        if typ == 'NUMBER':
            return ('num', float(val))
        if typ == 'COLON':
            return ('var', val[1:])
        if typ == 'WORD':
            return ('word', val)
        raise SyntaxError(f"Unexpected token in expression: {typ}")

# ----------------------------------------------------------------------
# Interpreter z binding abstraction
# ----------------------------------------------------------------------
class LogoInterpreter:
    def __init__(self, env: LogoEnvironment):
        self.env = env
        self.parser = LogoParser()
        self.current_bubble = env.global_bubble

    def _resolve_var(self, name: str):
        bubble = self.current_bubble
        while bubble:
            atom_label = bubble.get_binding(name)
            if atom_label:
                atom = runtime.get_atom(atom_label)
                if atom:
                    return atom
            bubble = bubble.parent
        return None

    def eval_expr(self, expr):
        op = expr[0]
        if op == 'num':
            return expr[1]
        elif op == 'var':
            var_name = expr[1]
            atom = self._resolve_var(var_name)
            if atom is None:
                raise NameError(f"Variable {var_name} not defined")
            if atom.S == "procedure":
                raise TypeError(f"Cannot use procedure '{var_name}' as a value")
            try:
                return float(atom.E)
            except ValueError:
                return atom.E
        elif op == 'op':
            _, left, operator, right = expr
            l = self.eval_expr(left)
            r = self.eval_expr(right)
            if operator == '+': return l + r
            if operator == '-': return l - r
            if operator == '*': return l * r
            if operator == '/': return l / r if r != 0 else float('inf')
            raise ValueError(f"Unknown operator {operator}")
        elif op == 'word':
            return expr[1]
        else:
            raise SyntaxError(f"Unknown expression {op}")

    def exec_stmt(self, stmt):
        op = stmt[0]
        if op == 'forward':
            _, dist_expr = stmt
            dist = self.eval_expr(dist_expr)
            self._move_turtle(dist)
        elif op == 'back':
            _, dist_expr = stmt
            dist = self.eval_expr(dist_expr)
            self._move_turtle(-dist)
        elif op == 'right':
            _, angle_expr = stmt
            angle = self.eval_expr(angle_expr)
            self._rotate_turtle(-angle)
        elif op == 'left':
            _, angle_expr = stmt
            angle = self.eval_expr(angle_expr)
            self._rotate_turtle(angle)
        elif op == 'penup':
            self.env.set_turtle_state(pendown=False)
        elif op == 'pendown':
            self.env.set_turtle_state(pendown=True)
        elif op == 'repeat':
            _, count_expr, body = stmt
            count = int(self.eval_expr(count_expr))
            for i in range(count):
                for sub in body:
                    self.exec_stmt(sub)
                
                # Dodano oddech systemu, by zapobiec OOM przy pętlach
                if hasattr(runtime, 'tick') and i % 100 == 0:
                    runtime.tick()
        elif op == 'make':
            _, var_name, expr = stmt
            value = self.eval_expr(expr)
            existing = self._resolve_var(var_name)
            if existing and existing.S == "procedure":
                raise NameError(f"Cannot redefine procedure '{var_name}' with make")
            
            label = _uid(f"var_{var_name}")
            new_atom = runtime.create_atom(label, "variable", str(value), T_VAR)
            self.current_bubble.set_binding(var_name, new_atom.label)
        elif op == 'print':
            _, expr = stmt
            val = self.eval_expr(expr)
            print(val)
        elif op == 'def':
            _, name, params, body = stmt
            existing = self._resolve_var(name)
            if existing and existing.S != "procedure":
                raise NameError(f"Cannot define procedure '{name}'; a variable with that name exists")
            proc_label = _uid(f"proc_{name}")
            proc_atom = runtime.create_atom(proc_label, "procedure", (params, body), T_PROC)
            self.env.global_bubble.set_binding(name, proc_atom.label)
        elif op == 'call':
            _, name, args_expr = stmt
            args = [self.eval_expr(a) for a in args_expr]
            atom = self._resolve_var(name)
            if atom is None or atom.S != "procedure":
                raise NameError(f"Procedure {name} not defined")
            params, body = atom.E
            if len(args) != len(params):
                raise TypeError(f"Procedure {name} expects {len(params)} arguments, got {len(args)}")
            
            frame_label = _uid(f"frame_{name}")
            frame = runtime.create_bubble(frame_label, parent=self.current_bubble)
            old_bubble = self.current_bubble
            self.current_bubble = frame
            for p, a in zip(params, args):
                param_label = _uid(f"param_{p}")
                param_atom = runtime.create_atom(param_label, "variable", str(a), T_VAR)
                self.current_bubble.set_binding(p, param_atom.label)
            try:
                for sub in body:
                    self.exec_stmt(sub)
                    if sub[0] == 'stop':
                        break
            finally:
                self.current_bubble = old_bubble
        elif op == 'stop':
            return
        elif isinstance(stmt, list):
            for s in stmt:
                self.exec_stmt(s)
        else:
            raise SyntaxError(f"Unknown statement {op}")

    def _move_turtle(self, distance: float):
        state = self.env.get_turtle_state()
        heading_rad = math.radians(state['heading'])
        dx = distance * math.cos(heading_rad)
        dy = distance * math.sin(heading_rad)
        new_x = state['x'] + dx
        new_y = state['y'] + dy
        if state['pendown']:
            steps = max(int(abs(distance)), 1)
            for i in range(1, steps+1):
                ix = state['x'] + dx * i / steps
                iy = state['y'] + dy * i / steps
                self.env.add_trail_point(ix, iy)
        max_x = SCREEN_WIDTH / 2
        max_y = SCREEN_HEIGHT / 2
        new_x = max(-max_x, min(max_x, new_x))
        new_y = max(-max_y, min(max_y, new_y))
        self.env.set_turtle_state(x=new_x, y=new_y)

    def _rotate_turtle(self, angle: float):
        state = self.env.get_turtle_state()
        new_heading = (state['heading'] + angle) % 360.0
        self.env.set_turtle_state(heading=new_heading)

    def run(self, code: str):
        ast = self.parser.parse(code)
        for stmt in ast:
            self.exec_stmt(stmt)

    def reset(self):
        self.env._init_turtle()
        self.env.clear_trail()
        self.current_bubble = self.env.global_bubble
        to_delete = [name for name, label in self.current_bubble.bindings.items()
                     if runtime.get_atom(label) and runtime.get_atom(label).S == "variable"]
        for name in to_delete:
            del self.current_bubble.bindings[name]

    def render_turtle(self) -> str:
        state = self.env.get_turtle_state()
        grid = [[' ' for _ in range(SCREEN_WIDTH)] for _ in range(SCREEN_HEIGHT)]
        for (x, y) in self.env.trail:
            ix = int(round(x)) + SCREEN_WIDTH // 2
            iy = SCREEN_HEIGHT - 1 - (int(round(y)) + SCREEN_HEIGHT // 2)
            if 0 <= ix < SCREEN_WIDTH and 0 <= iy < SCREEN_HEIGHT:
                grid[iy][ix] = '.'
        tx = int(round(state['x'])) + SCREEN_WIDTH // 2
        ty = SCREEN_HEIGHT - 1 - (int(round(state['y'])) + SCREEN_HEIGHT // 2)
        heading = state['heading']
        if 45 <= heading < 135:
            ch = '▲'
        elif 135 <= heading < 225:
            ch = '◄'
        elif 225 <= heading < 315:
            ch = '▼'
        else:
            ch = '►'
        if 0 <= tx < SCREEN_WIDTH and 0 <= ty < SCREEN_HEIGHT:
            grid[ty][tx] = ch
        return '\n'.join(''.join(row) for row in grid)

# ----------------------------------------------------------------------
# Powłoka LOGO (bez zmian)
# ----------------------------------------------------------------------
class LogoShell:
    def __init__(self):
        self.env = LogoEnvironment()
        self.interp = LogoInterpreter(self.env)

    def cmd_logo(self, args: List[str]) -> str:
        if not args:
            self._repl()
            return ""
        sub = args[0].upper()
        if sub == "RUN":
            code = ' '.join(args[1:])
            try:
                self.interp.run(code)
            except Exception as e:
                return f"Błąd: {e}"
            return self.interp.render_turtle()
        elif sub == "FILE":
            if len(args) < 2:
                return "LOGO FILE <ścieżka>"
            try:
                with open(args[1], 'r', encoding='utf-8') as f:
                    code = f.read()
                self.interp.run(code)
                return self.interp.render_turtle()
            except Exception as e:
                return f"Błąd pliku: {e}"
        elif sub == "RESET":
            self.interp.reset()
            return "Stan LOGO zresetowany."
        elif sub == "SAVE":
            self.env.save_state()
            return "Stan zapisany."
        elif sub == "LOAD":
            if self.env.load_state():
                return "Stan wczytany."
            else:
                return "Brak zapisanego stanu."
        elif sub == "SHOW":
            return self.interp.render_turtle()
        else:
            return "Nieznana opcja. Dostępne: RUN, FILE, RESET, SAVE, LOAD, SHOW"

    def _repl(self):
        print("KarmazynLOGO REPL. Wpisz 'exit' aby wyjść.")
        while True:
            try:
                line = input("LOGO> ").strip()
                if line.lower() in ('exit','quit'):
                    break
                if not line:
                    continue
                self.interp.run(line)
                print(self.interp.render_turtle())
            except EOFError:
                break
            except Exception as e:
                print(f"Błąd: {e}")

def cmd_logo(args: List[str]) -> str:
    if not hasattr(cmd_logo, "_shell"):
        cmd_logo._shell = LogoShell()
    return cmd_logo._shell.cmd_logo(args)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(cmd_logo(sys.argv[1:]))
    else:
        cmd_logo([])
