"""
karmazyn_lang.py — Język .karm dla KarmazynOS v1.1.0
=====================================================
Parser LALR + Transformer + Executor.
Executor woła SanctuaryRuntime v1.2 bezpośrednio — zero adapterów.

Wymagania:
    pip install lark --break-system-packages
    runtime.py v1.2 (SanctuaryRuntime)

Użycie:
    from runtime import SanctuaryRuntime
    from karmazyn_lang import KarmazynExecutor

    rt = SanctuaryRuntime()
    ex = KarmazynExecutor(rt)
    ex.run_file("program.karm")
"""

import importlib
import threading
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from lark import Lark, Transformer

# =====================================================================
# GRAMATYKA
# =====================================================================

GRAMMAR = r"""
    start: statement+

    statement: atom_def
             | hologram_def
             | idea_def
             | spawn_stmt
             | prism_def
             | session_def
             | schedule_stmt
             | monitor_stmt
             | step_stmt
             | recall_stmt
             | import_stmt

    // ── atom ─────────────────────────────────────────────────────────
    atom_def:   "atom" NAME "{" atom_body "}"
    atom_body:  atom_field+
    atom_field: ATOM_KEY "=" value
    ATOM_KEY.2: "S" | "E" | "T" | "decay"

    // ── hologram ─────────────────────────────────────────────────────
    hologram_def:  "hologram" NAME "=" hologram_expr "{" hologram_body? "}"
    hologram_expr: NAME ("+" NAME)*
    hologram_body: hologram_field+
    hologram_field: HOLO_KEY ":" value
    HOLO_KEY.2: "strength" | "prism" | "temp" | "description"

    // ── idea ─────────────────────────────────────────────────────────
    idea_def:    "idea" STRING "from" hologram_expr "{" idea_body "}"
    idea_body:   idea_action+
    idea_action: IDEA_GEN STRING
               | IDEA_TEMP NUMBER
               | IDEA_CONS
    IDEA_GEN.2:  "gen"
    IDEA_TEMP.2: "temp"
    IDEA_CONS.2: "consolidate"

    // ── spawn ─────────────────────────────────────────────────────────
    spawn_stmt:   "spawn" NAME "with" STRING ("{" spawn_options? "}")?
    spawn_options: spawn_option+
    spawn_option: SPAWN_TEMP NUMBER | SPAWN_CONS
    SPAWN_TEMP.2: "temp"
    SPAWN_CONS.2: "consolidate"

    // ── prism ─────────────────────────────────────────────────────────
    prism_def:   "prism" NAME "{" prism_body "}"
    prism_body:  prism_field+
    prism_field: PRISM_KEY "=" value
    PRISM_KEY.2: "mask" | "visibility" | "privileges"

    // ── session ───────────────────────────────────────────────────────
    session_def:  "session" NAME "{" session_body "}"
    session_body: session_field+
    session_field: SESS_PRISM ":" STRING
                 | SESS_VIS   ":" STRING
                 | SESS_RUN   NAME ("with" "{" dict_body "}")?
    SESS_PRISM.2: "prism"
    SESS_VIS.2:   "visibility"
    SESS_RUN.2:   "run"

    dict_body: dict_pair+
    dict_pair: NAME ":" value

    // ── schedule ──────────────────────────────────────────────────────
    schedule_stmt: "schedule" "{" schedule_rule+ "}"
    schedule_rule: "every" NUMBER TIME_UNIT "{" statement+ "}"
    TIME_UNIT.2: "s" | "m" | "h"

    // ── monitor ───────────────────────────────────────────────────────
    monitor_stmt:  "monitor" "liveliness" "of" NAME "{" monitor_body "}"
    monitor_body:  monitor_field+
    monitor_field: MON_ALERT ":" NUMBER
                 | MON_ACT   ":" STRING
    MON_ALERT.2: "alert_below"
    MON_ACT.2:   "action"

    // ── step / recall / import ────────────────────────────────────────
    step_stmt:   "step"   NUMBER
    recall_stmt: "recall" NAME ("every" NUMBER TIME_UNIT)?
    import_stmt: "import" NAME ("." NAME)*

    // ── wartości ─────────────────────────────────────────────────────
    value:        STRING | NUMBER | NAME | SPECIAL_VAL
    SPECIAL_VAL.2: "immortal" | "ALL" | "CORE" | "IN" | "OUT"

    NAME:   /[a-zA-Z_][a-zA-Z0-9_]*/
    STRING: /"[^"]*"/
    NUMBER: /\d+(\.\d+)?/

    %import common.WS
    %ignore WS
    %ignore /\/\/[^\n]*/
"""

# =====================================================================
# WĘZŁY AST
# =====================================================================

@dataclass
class Node:
    pass

@dataclass
class AtomDef(Node):
    name:  str
    S:     str
    E:     str
    T:     float = 0.9
    decay: float = 0.01

@dataclass
class HologramDef(Node):
    name:        str
    components:  List[str]
    strength:    str            = "medium"
    prism:       str            = "CORE"
    temp:        float          = 0.4
    description: Optional[str] = None

@dataclass
class IdeaDef(Node):
    prompt:     str
    components: List[str]
    gen_prompt: Optional[str] = None
    temp:       float         = 0.5
    consolidate: bool         = False

@dataclass
class SpawnDef(Node):
    name:       str
    content:    str
    temp:       float = 0.7
    consolidate: bool = False

@dataclass
class PrismDef(Node):
    name:       str
    mask:       str = "ALL"
    visibility: str = "OUT"
    privileges: str = "IN"

@dataclass
class SessionDef(Node):
    name:        str
    prism:       str              = "CORE"
    visibility:  str              = "OUT"
    run_targets: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class ScheduleRule(Node):
    interval_seconds: float
    statements:       List[Node]

@dataclass
class ScheduleDef(Node):
    rules: List[ScheduleRule]

@dataclass
class MonitorDef(Node):
    target:      str
    alert_below: float = 0.3
    action:      str   = "log"

@dataclass
class StepDef(Node):
    n: int

@dataclass
class RecallDef(Node):
    name:             str
    interval_seconds: Optional[float] = None

@dataclass
class ImportDef(Node):
    module_path: str

@dataclass
class ProgramAST:
    statements: List[Node]

# =====================================================================
# TRANSFORMER
# =====================================================================

class KarmazynTransformer(Transformer):

    # ── terminale ────────────────────────────────────────────────────

    def STRING(self, s):       return str(s)[1:-1]
    def NAME(self, n):         return str(n)
    def TIME_UNIT(self, t):    return str(t)
    def ATOM_KEY(self, t):     return str(t)
    def HOLO_KEY(self, t):     return str(t)
    def PRISM_KEY(self, t):    return str(t)
    def SESS_PRISM(self, t):   return "prism"
    def SESS_VIS(self, t):     return "visibility"
    def SESS_RUN(self, t):     return "run"
    def MON_ALERT(self, t):    return "alert_below"
    def MON_ACT(self, t):      return "action"
    def IDEA_GEN(self, t):     return "gen"
    def IDEA_TEMP(self, t):    return "temp"
    def IDEA_CONS(self, t):    return "consolidate"
    def SPAWN_TEMP(self, t):   return "temp"
    def SPAWN_CONS(self, t):   return "consolidate"
    def SPECIAL_VAL(self, t):  return str(t)

    def NUMBER(self, n):
        v = float(n)
        return int(v) if v == int(v) else v

    def value(self, children):
        return children[0]

    # ── atom ─────────────────────────────────────────────────────────

    def atom_field(self, c):   return (c[0], c[1])
    def atom_body(self, c):    return dict(c)

    def atom_def(self, c):
        name = c[0]
        body = c[1]
        raw_T = body.get("T", 0.9)
        try:
            t_val = float(raw_T)
        except (ValueError, TypeError):
            t_val = 0.9     # "immortal" → domyślna wysoka stabilność
        return AtomDef(
            name=name,
            S=str(body.get("S", "")),
            E=str(body.get("E", "")),
            T=t_val,
            decay=float(body.get("decay", 0.01)),
        )

    # ── hologram ─────────────────────────────────────────────────────

    def hologram_expr(self, c):    return [str(x) for x in c]
    def hologram_field(self, c):   return (c[0], c[1])
    def hologram_body(self, c):    return dict(c)

    def hologram_def(self, c):
        name       = c[0]
        components = c[1]
        body       = c[2] if len(c) > 2 else {}
        return HologramDef(
            name=name,
            components=components,
            strength=str(body.get("strength", "medium")),
            prism=str(body.get("prism", "CORE")),
            temp=float(body.get("temp", 0.4)),
            description=str(body["description"]) if "description" in body else None,
        )

    # ── idea ─────────────────────────────────────────────────────────

    def idea_action(self, c):
        kw = str(c[0])
        if kw == "gen":          return ("gen", c[1])
        if kw == "temp":         return ("temp", float(c[1]))
        if kw == "consolidate":  return ("consolidate", True)
        raise ValueError(f"idea_action: {kw}")

    def idea_body(self, c):  return list(c)

    def idea_def(self, c):
        prompt     = c[0]
        components = c[1]
        actions    = c[2]
        gen_prompt = None
        temp       = 0.5
        consolidate = False
        for k, v in actions:
            if k == "gen":         gen_prompt = v
            elif k == "temp":      temp = v
            elif k == "consolidate": consolidate = True
        return IdeaDef(prompt=prompt, components=components,
                       gen_prompt=gen_prompt, temp=temp,
                       consolidate=consolidate)

    # ── spawn ─────────────────────────────────────────────────────────

    def spawn_option(self, c):
        kw = str(c[0])
        if kw == "temp":         return ("temp", float(c[1]))
        if kw == "consolidate":  return ("consolidate", True)
        raise ValueError(f"spawn_option: {kw}")

    def spawn_options(self, c):  return dict(c)

    def spawn_stmt(self, c):
        name    = c[0]
        content = c[1]
        opts    = c[2] if len(c) > 2 else {}
        return SpawnDef(
            name=name, content=content,
            temp=float(opts.get("temp", 0.7)),
            consolidate=bool(opts.get("consolidate", False)),
        )

    # ── prism ─────────────────────────────────────────────────────────

    def prism_field(self, c):  return (c[0], c[1])
    def prism_body(self, c):   return dict(c)

    def prism_def(self, c):
        name = c[0]
        body = c[1]
        return PrismDef(
            name=name,
            mask=str(body.get("mask", "ALL")),
            visibility=str(body.get("visibility", "OUT")),
            privileges=str(body.get("privileges", "IN")),
        )

    # ── session ───────────────────────────────────────────────────────

    def dict_pair(self, c):    return (c[0], c[1])
    def dict_body(self, c):    return dict(c)

    def session_field(self, c):
        kw = str(c[0])
        if kw == "prism":      return ("prism", c[1])
        if kw == "visibility": return ("visibility", c[1])
        if kw == "run":
            target = str(c[1])
            kwargs = c[2] if len(c) > 2 else {}
            return ("run", {"target": target, "kwargs": kwargs})
        raise ValueError(f"session_field: {kw}")

    def session_body(self, c):
        prism = "CORE"; visibility = "OUT"; runs = []
        for k, v in c:
            if k == "prism":      prism = v
            elif k == "visibility": visibility = v
            elif k == "run":      runs.append(v)
        return {"prism": prism, "visibility": visibility, "run_targets": runs}

    def session_def(self, c):
        name = c[0]; body = c[1]
        return SessionDef(name=name, prism=body["prism"],
                          visibility=body["visibility"],
                          run_targets=body["run_targets"])

    # ── schedule ──────────────────────────────────────────────────────

    def schedule_rule(self, c):
        num  = float(c[0])
        unit = str(c[1])
        stmts = list(c[2:])
        intervals = {"s": 1.0, "m": 60.0, "h": 3600.0}
        if unit not in intervals:
            raise ValueError(f"Nieznana jednostka: {unit}")
        return ScheduleRule(interval_seconds=num * intervals[unit],
                            statements=stmts)

    def schedule_stmt(self, c):
        return ScheduleDef(rules=list(c))

    # ── monitor ───────────────────────────────────────────────────────

    def monitor_field(self, c):
        kw = str(c[0])
        if kw == "alert_below": return ("alert_below", float(c[1]))
        if kw == "action":      return ("action", str(c[1]))
        raise ValueError(f"monitor_field: {kw}")

    def monitor_body(self, c):  return dict(c)

    def monitor_stmt(self, c):
        target = str(c[0]); body = c[1]
        return MonitorDef(
            target=target,
            alert_below=float(body.get("alert_below", 0.3)),
            action=str(body.get("action", "log")),
        )

    # ── step / recall / import ────────────────────────────────────────

    def step_stmt(self, c):
        return StepDef(n=int(c[0]))

    def recall_stmt(self, c):
        name = str(c[0])
        interval = None
        if len(c) == 3:
            num  = float(c[1])
            unit = str(c[2])
            intervals = {"s": 1.0, "m": 60.0, "h": 3600.0}
            interval = num * intervals.get(unit, 1.0)
        return RecallDef(name=name, interval_seconds=interval)

    def import_stmt(self, c):
        return ImportDef(module_path=".".join(str(x) for x in c))

    # ── statement / start ─────────────────────────────────────────────

    def statement(self, c):  return c[0]
    def start(self, c):      return ProgramAST(statements=list(c))


# =====================================================================
# SCHEDULE RUNNER
# =====================================================================

class ScheduleRunner:
    def __init__(self, executor):
        self._executor = executor
        self._threads:  List[threading.Thread] = []
        self._stop_evt = threading.Event()

    def register(self, rule: ScheduleRule):
        t = threading.Thread(
            target=self._loop,
            args=(rule,),
            daemon=True,
            name=f"karm-sched-{int(rule.interval_seconds)}s",
        )
        self._threads.append(t)
        t.start()
        print(f"  [SCHEDULE] Reguła co {rule.interval_seconds}s "
              f"({len(rule.statements)} stmt)")

    def _loop(self, rule: ScheduleRule):
        while not self._stop_evt.is_set():
            self._stop_evt.wait(rule.interval_seconds)
            if self._stop_evt.is_set():
                break
            try:
                for stmt in rule.statements:
                    self._executor.execute(stmt)
            except Exception as e:
                print(f"  [SCHEDULE ERROR] {e}")

    def stop(self):
        self._stop_evt.set()
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads.clear()
        print("  [SCHEDULE] Zatrzymano wszystkie reguły")


# =====================================================================
# EXECUTOR — bezpośrednio na SanctuaryRuntime v1.2
# =====================================================================

class KarmazynExecutor:
    """
    Tłumaczy węzły AST na wywołania SanctuaryRuntime.
    runtime — instancja SanctuaryRuntime v1.2.
    """

    def __init__(self, runtime):
        self.runtime   = runtime
        self._scheduler = ScheduleRunner(self)
        self._monitors: List[MonitorDef] = []
        # pid → (pid, s_agent) — lokalny cache, stan w runtime._agents
        self._agent_cache: Dict[str, tuple] = {}

    # ── publiczne API ─────────────────────────────────────────────────

    def execute(self, node: Node):
        method = getattr(self, f"_exec_{type(node).__name__}", None)
        if method is None:
            raise NotImplementedError(f"Brak handlera: {type(node).__name__}")
        method(node)

    def run_program(self, program: ProgramAST):
        for stmt in program.statements:
            self.execute(stmt)

    def run_file(self, filepath: str):
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
        self.run_source(source)

    def run_source(self, source: str):
        tree    = _parser.parse(source)
        program = KarmazynTransformer().transform(tree)
        self.run_program(program)

    def stop_scheduler(self):
        self._scheduler.stop()

    def check_monitors(self):
        """
        Sprawdza monitory.
        liveliness = atom.T / atom.T_max — prosto z SanctuaryRuntime.matrix.
        """
        for mon in self._monitors:
            atom_id = self.runtime.atom_id_for(mon.target)
            if atom_id is None:
                print(f"  [MONITOR] '{mon.target}' — atom nieznany")
                continue
            atom  = self.runtime.get_atom(atom_id)
            if atom is None:
                print(f"  [MONITOR] '{mon.target}' — atom usunięty")
                continue
            t_max = getattr(atom, "T_max", 100.0)
            liv   = atom.T / t_max if t_max > 0 else 0.0
            if liv < mon.alert_below:
                print(f"  [MONITOR ALERT] '{mon.target}' "
                      f"liveliness={liv:.4f} < {mon.alert_below} "
                      f"→ {mon.action}")
                self._handle_monitor_action(mon, atom_id)

    # ── handlery węzłów ───────────────────────────────────────────────

    def _exec_AtomDef(self, node: AtomDef):
        # .karm T ∈ [0,1] → runtime T ∈ [0,100]
        atom_id = self.runtime.write(
            name=node.name,
            S=node.S,
            E=node.E,
            T=node.T * 100.0,
        )
        print(f"  [ATOM] '{node.name}' → {atom_id}  T={node.T}")
        # decay ≠ domyślny → inicjuj zanik
        if node.decay != 0.01:
            self.runtime.mark_bubble_for_decay(atom_id, rate=node.decay)

    def _exec_HologramDef(self, node: HologramDef):
        atom_ids = []
        for comp_name in node.components:
            aid = self.runtime.atom_id_for(comp_name)
            if aid is None:
                print(f"  [WARN] Hologram '{node.name}': "
                      f"brak '{comp_name}' — pomijam")
                continue
            # Konsoliduj jeśli bąbel nie istnieje
            if self.runtime.get_bubble(aid) is None:
                self.runtime.consolidate(aid)
            atom_ids.append(aid)

        if not atom_ids:
            print(f"  [WARN] Hologram '{node.name}': brak składowych")
            return

        hid = self.runtime.archive_to_hologram(
            topic=node.name,
            atom_ids=atom_ids,
            remove_originals=False,
        )
        # Rejestruj nazwę hologramu → hid
        self.runtime._name_to_id[node.name] = hid
        print(f"  [HOLOGRAM] '{node.name}' → {hid} "
              f"({len(atom_ids)} składowych)")

    def _exec_IdeaDef(self, node: IdeaDef):
        # Szukaj hologramu wśród komponentów
        hid = None
        for comp_name in node.components:
            candidate = self.runtime._name_to_id.get(comp_name)
            if candidate and candidate in self.runtime._holograms:
                hid = candidate
                break

        # Nie ma hologramu — twórz tymczasowy z komponentów
        if hid is None:
            atom_ids = []
            for comp_name in node.components:
                aid = self.runtime.atom_id_for(comp_name)
                if aid:
                    if self.runtime.get_bubble(aid) is None:
                        self.runtime.consolidate(aid)
                    atom_ids.append(aid)
            if atom_ids:
                hid = self.runtime.archive_to_hologram(
                    topic=f"idea_{node.prompt[:20]}",
                    atom_ids=atom_ids,
                )
                print(f"  [IDEA] Tymczasowy hologram → {hid}")

        if hid is None:
            print(f"  [WARN] Idea '{node.prompt}': brak hologramu")
            return

        vec = self.runtime.generate_from_idea(
            hid,
            node.gen_prompt or node.prompt,
            temperature=node.temp,
        )
        if vec is None:
            print(f"  [WARN] generate_from_idea zwrócił None")
            return

        # Rejestruj wektor w PhiSpace
        idea_name = f"idea_{node.prompt[:20].replace(' ', '_')}"
        self.runtime.phi.add_vector(idea_name, vec)
        self.runtime._name_to_id[node.prompt] = idea_name

        if node.consolidate:
            # Utwórz atom dla idei jeśli nie istnieje
            if not self.runtime.has_atom(idea_name):
                self.runtime.create_atom(
                    idea_name, node.prompt[:60], "", 70.0
                )
            self.runtime.consolidate(idea_name)

        print(f"  [IDEA] '{node.prompt}' → {idea_name} "
              f"temp={node.temp} consolidate={node.consolidate}")

    def _exec_SpawnDef(self, node: SpawnDef):
        atom_id = self.runtime.write(
            name=node.name,
            S=node.content[:80],
            E="",
            T=node.temp * 100.0,
        )
        print(f"  [SPAWN] '{node.name}' → {atom_id} "
              f"content='{node.content[:40]}'")
        if node.consolidate:
            self.runtime.consolidate(atom_id)
            print(f"  [SPAWN] Skonsolidowano '{node.name}'")

    def _exec_PrismDef(self, node: PrismDef):
        prisms      = _prism_to_list(node.visibility)
        pid, s_agent = self.runtime.derive_agent(
            name=node.name,
            task=f"prism:{node.name}",
            prisms=prisms,
        )
        self._agent_cache[node.name] = (pid, s_agent)
        print(f"  [PRISM] '{node.name}' → PID={pid} "
              f"visibility={node.visibility} prisms={prisms}")

    def _exec_SessionDef(self, node: SessionDef):
        prisms      = _prism_to_list(node.prism)
        pid, s_agent = self.runtime.derive_agent(
            name=node.name,
            task=f"session:{node.name}",
            prisms=prisms,
        )
        self._agent_cache[node.name] = (pid, s_agent)
        print(f"  [SESSION] '{node.name}' → PID={pid} prisms={prisms}")

        for run_info in node.run_targets:
            target  = run_info["target"]
            atom_id = self.runtime.atom_id_for(target)
            if atom_id is None:
                print(f"  [WARN] Session.run: '{target}' nieznany — pomijam")
                continue
            result = self.runtime.read_as_agent(atom_id, pid, s_agent)
            print(f"  [SESSION.run] '{target}' → {result}")

    def _exec_ScheduleDef(self, node: ScheduleDef):
        for rule in node.rules:
            self._scheduler.register(rule)

    def _exec_ScheduleRule(self, node: ScheduleRule):
        for stmt in node.statements:
            self.execute(stmt)

    def _exec_MonitorDef(self, node: MonitorDef):
        self._monitors.append(node)
        print(f"  [MONITOR] Zarejestrowano '{node.target}' "
              f"alert_below={node.alert_below} action='{node.action}'")

    def _exec_StepDef(self, node: StepDef):
        stats = self.runtime.step(node.n)
        print(f"  [STEP] +{node.n} → {stats}")

    def _exec_RecallDef(self, node: RecallDef):
        # recall może przyjąć treść lub atom_id — używamy nazwy
        atom_id = self.runtime.atom_id_for(node.name) or node.name
        results = self.runtime.recall(atom_id, k=5)
        print(f"  [RECALL] '{node.name}' ({len(results)} wyników):")
        for r in results:
            print(f"    [{r.get('layer','?')}] "
                  f"score={r.get('score', 0.0):.4f} "
                  f"label='{r.get('label','')}'")
        if node.interval_seconds is not None:
            rule = ScheduleRule(
                interval_seconds=node.interval_seconds,
                statements=[node],
            )
            self._scheduler.register(rule)

    def _exec_ImportDef(self, node: ImportDef):
        try:
            importlib.import_module(node.module_path)
            print(f"  [IMPORT] '{node.module_path}'")
        except ImportError as e:
            print(f"  [WARN] Import '{node.module_path}': {e}")

    # ── monitor action ────────────────────────────────────────────────

    def _handle_monitor_action(self, mon: MonitorDef, atom_id: str):
        action = mon.action.lower()
        if action == "log":
            pass
        elif action == "refresh":
            ok = self.runtime.refresh_bubble(atom_id)
            print(f"  [MONITOR] refresh '{atom_id}' → {ok}")
        elif action == "revoke":
            ok = self.runtime.revoke_bubble(atom_id)
            print(f"  [MONITOR] revoke '{atom_id}' → Warp Oblivion={ok}")
        elif action == "step":
            self.runtime.step(1)
            print(f"  [MONITOR] step z monitora '{atom_id}'")
        else:
            print(f"  [MONITOR] Nieznana akcja '{action}'")


# =====================================================================
# HELPERS
# =====================================================================

def _prism_to_list(prism_str: str) -> List[str]:
    return {
        "ALL":  ["core", "in", "out"],
        "CORE": ["core"],
        "IN":   ["in"],
        "OUT":  ["out"],
    }.get(str(prism_str).upper(), ["core", "in", "out"])


# =====================================================================
# PARSER — singleton, tworzony raz przy imporcie
# =====================================================================

_parser = Lark(GRAMMAR, start="start", parser="lalr", lexer="contextual")


# =====================================================================
# PUBLICZNE API
# =====================================================================

def parse_source(source: str) -> ProgramAST:
    tree = _parser.parse(source)
    return KarmazynTransformer().transform(tree)


def parse_file(filepath: str) -> ProgramAST:
    with open(filepath, encoding="utf-8") as f:
        source = f.read()
    return parse_source(source)