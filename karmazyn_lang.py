"""
karmazyn_lang.py — Język .karm dla KarmazynOS v1.0.0
=====================================================
Pełna integracja z karmazyn.py (KarmazynOS v1.3.x).

Mapowanie języka → runtime:
  atom       → runtime.write() + runtime.consolidate()
  hologram   → runtime.archive_bubbles_to_hologram()
  idea       → runtime.generate_from_idea() / archive_bubbles_to_hologram()
  spawn      → runtime.write() + opcjonalnie consolidate()
  prism      → runtime.derive_agent() z listą prismów
  session    → runtime.derive_agent() + runtime.read_as_agent()
  schedule   → rejestracja interwałów (uruchomienie przez ScheduleRunner)
  monitor    → rejestracja monitorowania liveliness bąbla
  step       → runtime.step(n)
  recall     → runtime.recall()
  import     → __import__() / importlib
"""

import importlib
import threading
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from lark import Lark, Transformer, v_args, Token, Tree

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

    // ── atom ──────────────────────────────────────────────────────────
    atom_def: "atom" NAME "{" atom_body "}"
    atom_body: atom_field+
    atom_field: ATOM_KEY "=" value
    ATOM_KEY.2:  "S" | "E" | "T" | "decay"

    // ── hologram ──────────────────────────────────────────────────────
    hologram_def: "hologram" NAME "=" hologram_expr "{" hologram_body? "}"
    hologram_expr: NAME ("+" NAME)*
    hologram_body: hologram_field+
    hologram_field: HOLO_KEY ":" value
    HOLO_KEY.2: "strength" | "prism" | "temp" | "description"

    // ── idea ──────────────────────────────────────────────────────────
    idea_def: "idea" STRING "from" hologram_expr "{" idea_body "}"
    idea_body: idea_action+
    idea_action: IDEA_GEN    STRING
               | IDEA_TEMP   NUMBER
               | IDEA_CONS
    IDEA_GEN.2:  "gen"
    IDEA_TEMP.2: "temp"
    IDEA_CONS.2: "consolidate"

    // ── spawn ─────────────────────────────────────────────────────────
    spawn_stmt: "spawn" NAME "with" STRING ("{" spawn_options? "}")?
    spawn_options: spawn_option+
    spawn_option: SPAWN_TEMP NUMBER | SPAWN_CONS
    SPAWN_TEMP.2: "temp"
    SPAWN_CONS.2: "consolidate"

    // ── prism ─────────────────────────────────────────────────────────
    prism_def: "prism" NAME "{" prism_body "}"
    prism_body: prism_field+
    prism_field: PRISM_KEY "=" value
    PRISM_KEY.2: "mask" | "visibility" | "privileges"

    // ── session ───────────────────────────────────────────────────────
    session_def: "session" NAME "{" session_body "}"
    session_body: session_field+
    session_field: SESS_PRISM      ":" STRING
                 | SESS_VIS        ":" STRING
                 | SESS_RUN        NAME ("with" "{" dict_body "}")?
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
    monitor_stmt: "monitor" "liveliness" "of" NAME "{" monitor_body "}"
    monitor_body: monitor_field+
    monitor_field: MON_ALERT ":" NUMBER
                 | MON_ACT   ":" STRING
    MON_ALERT.2: "alert_below"
    MON_ACT.2:   "action"

    // ── step / recall / import ────────────────────────────────────────
    step_stmt:   "step"   NUMBER
    recall_stmt: "recall" NAME ("every" NUMBER TIME_UNIT)?
    import_stmt: "import" NAME ("." NAME)*

    // ── wartości ──────────────────────────────────────────────────────
    value: STRING | NUMBER | NAME | SPECIAL_VAL
    SPECIAL_VAL: "immortal" | "ALL" | "CORE" | "IN" | "OUT"

    NAME:      /[a-zA-Z_][a-zA-Z0-9_]*/
    STRING:    /"[^"]*"/
    NUMBER:    /\d+(\.\d+)?/

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
    name: str
    S: str
    E: str
    T: float = 0.9
    decay: float = 0.01

@dataclass
class HologramDef(Node):
    name: str
    components: List[str]
    strength: str = "medium"
    prism: str = "CORE"
    temp: float = 0.4
    description: Optional[str] = None

@dataclass
class IdeaDef(Node):
    prompt: str
    components: List[str]
    gen_prompt: Optional[str] = None
    temp: float = 0.5
    consolidate: bool = False

@dataclass
class SpawnDef(Node):
    name: str
    content: str
    temp: float = 0.7
    consolidate: bool = False

@dataclass
class PrismDef(Node):
    name: str
    mask: str = "ALL"
    visibility: str = "OUT"
    privileges: str = "IN"

@dataclass
class SessionDef(Node):
    name: str
    prism: str = "CORE"
    visibility: str = "OUT"
    run_targets: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class ScheduleRule(Node):
    interval_seconds: float
    statements: List[Node]

@dataclass
class ScheduleDef(Node):
    rules: List[ScheduleRule]

@dataclass
class MonitorDef(Node):
    target: str
    alert_below: float = 0.3
    action: str = "log"

@dataclass
class StepDef(Node):
    n: int

@dataclass
class RecallDef(Node):
    name: str
    interval_seconds: Optional[float] = None

@dataclass
class ImportDef(Node):
    module_path: str

@dataclass
class ProgramAST:
    statements: List[Node]

# =====================================================================
# TRANSFORMER  lark → AST
# =====================================================================

class KarmazynTransformer(Transformer):

    # ── terminale ────────────────────────────────────────────────────

    def STRING(self, s):
        return str(s)[1:-1]          # strip cudzysłowów

    def NUMBER(self, n):
        v = float(n)
        return int(v) if v == int(v) else v

    def NAME(self, n):
        return str(n)

    def TIME_UNIT(self, t):
        return str(t)

    def SPECIAL_VAL(self, t):
        return str(t)

    # Nowe terminale dla kluczy (zamiast reguł *_key)
    def ATOM_KEY(self, t):   return str(t)
    def HOLO_KEY(self, t):   return str(t)
    def PRISM_KEY(self, t):  return str(t)
    def SESS_PRISM(self, t): return "prism"
    def SESS_VIS(self, t):   return "visibility"
    def SESS_RUN(self, t):   return "run"
    def MON_ALERT(self, t):  return "alert_below"
    def MON_ACT(self, t):    return "action"
    def IDEA_GEN(self, t):   return "gen"
    def IDEA_TEMP(self, t):  return "temp"
    def IDEA_CONS(self, t):  return "consolidate"
    def SPAWN_TEMP(self, t): return "temp"
    def SPAWN_CONS(self, t): return "consolidate"

    def value(self, children):
        return children[0]

    # ── atom ─────────────────────────────────────────────────────────

    def atom_field(self, children):
        # children = [ATOM_KEY (str), value]
        return (children[0], children[1])

    def atom_body(self, children):
        return dict(children)

    def atom_def(self, children):
        name = children[0]
        body = children[1]
        # T może być "immortal" (SPECIAL_VAL) — obsługujemy jako float domyślny
        raw_T = body.get("T", 0.9)
        try:
            t_val = float(raw_T)
        except (ValueError, TypeError):
            t_val = 0.9   # "immortal" w T traktujemy jako max stabilność
        return AtomDef(
            name=name,
            S=str(body.get("S", "")),
            E=str(body.get("E", "")),
            T=t_val,
            decay=float(body.get("decay", 0.01)),
        )

    # ── hologram ─────────────────────────────────────────────────────

    def hologram_expr(self, children):
        return [str(c) for c in children]

    def hologram_field(self, children):
        # children = [HOLO_KEY (str), value]
        return (children[0], children[1])

    def hologram_body(self, children):
        return dict(children)

    def hologram_def(self, children):
        name = children[0]
        components = children[1]
        body = children[2] if len(children) > 2 else {}
        return HologramDef(
            name=name,
            components=components,
            strength=str(body.get("strength", "medium")),
            prism=str(body.get("prism", "CORE")),
            temp=float(body.get("temp", 0.4)),
            description=str(body["description"]) if "description" in body else None,
        )

    # ── idea ─────────────────────────────────────────────────────────

    def idea_action(self, children):
        # children[0] to już str po konwersji terminala IDEA_GEN/TEMP/CONS
        kw = str(children[0])
        if kw == "gen":
            return ("gen", children[1])
        elif kw == "temp":
            return ("temp", float(children[1]))
        elif kw == "consolidate":
            return ("consolidate", True)
        raise ValueError(f"Nieznana idea_action: {kw}")

    def idea_body(self, children):
        return children

    def idea_def(self, children):
        prompt = children[0]
        components = children[1]
        actions = children[2]
        gen_prompt = None
        temp = 0.5
        consolidate = False
        for act in actions:
            if act[0] == "gen":
                gen_prompt = act[1]
            elif act[0] == "temp":
                temp = act[1]
            elif act[0] == "consolidate":
                consolidate = True
        return IdeaDef(
            prompt=prompt,
            components=components,
            gen_prompt=gen_prompt,
            temp=temp,
            consolidate=consolidate,
        )

    # ── spawn ─────────────────────────────────────────────────────────

    def spawn_option(self, children):
        # children[0] = str z SPAWN_TEMP lub SPAWN_CONS
        kw = str(children[0])
        if kw == "temp":
            return ("temp", float(children[1]))
        elif kw == "consolidate":
            return ("consolidate", True)
        raise ValueError(f"Nieznana spawn_option: {kw}")

    def spawn_options(self, children):
        return dict(children)

    def spawn_stmt(self, children):
        name = children[0]
        content = children[1]
        opts = children[2] if len(children) > 2 else {}
        return SpawnDef(
            name=name,
            content=content,
            temp=float(opts.get("temp", 0.7)),
            consolidate=bool(opts.get("consolidate", False)),
        )

    # ── prism ─────────────────────────────────────────────────────────

    def prism_field(self, children):
        # children = [PRISM_KEY (str), value]
        return (children[0], children[1])

    def prism_body(self, children):
        return dict(children)

    def prism_def(self, children):
        name = children[0]
        body = children[1]
        return PrismDef(
            name=name,
            mask=str(body.get("mask", "ALL")),
            visibility=str(body.get("visibility", "OUT")),
            privileges=str(body.get("privileges", "IN")),
        )

    # ── session ───────────────────────────────────────────────────────

    def dict_pair(self, children):
        return (children[0], children[1])

    def dict_body(self, children):
        return dict(children)

    def session_field(self, children):
        # children[0] = str z SESS_PRISM / SESS_VIS / SESS_RUN
        kw = str(children[0])
        if kw == "prism":
            return ("prism", children[1])
        elif kw == "visibility":
            return ("visibility", children[1])
        elif kw == "run":
            target = str(children[1])
            kwargs = children[2] if len(children) > 2 else {}
            return ("run", {"target": target, "kwargs": kwargs})
        raise ValueError(f"Nieznany session_field: {kw}")

    def session_body(self, children):
        prism = "CORE"
        visibility = "OUT"
        run_targets = []
        for item in children:
            k, v = item
            if k == "prism":
                prism = v
            elif k == "visibility":
                visibility = v
            elif k == "run":
                run_targets.append(v)
        return {"prism": prism, "visibility": visibility, "run_targets": run_targets}

    def session_def(self, children):
        name = children[0]
        body = children[1]
        return SessionDef(
            name=name,
            prism=body["prism"],
            visibility=body["visibility"],
            run_targets=body["run_targets"],
        )

    # ── schedule ──────────────────────────────────────────────────────

    def schedule_rule(self, children):
        num = float(children[0])
        unit = str(children[1])
        statements = list(children[2:])
        if unit == "s":
            interval = num
        elif unit == "m":
            interval = num * 60.0
        elif unit == "h":
            interval = num * 3600.0
        else:
            raise ValueError(f"Nieznana jednostka czasu: {unit}")
        return ScheduleRule(interval_seconds=interval, statements=statements)

    def schedule_stmt(self, children):
        return ScheduleDef(rules=list(children))

    # ── monitor ───────────────────────────────────────────────────────

    def monitor_field(self, children):
        # children[0] = str z MON_ALERT lub MON_ACT
        kw = str(children[0])
        if kw == "alert_below":
            return ("alert_below", float(children[1]))
        elif kw == "action":
            return ("action", str(children[1]))
        raise ValueError(f"Nieznany monitor_field: {kw}")

    def monitor_body(self, children):
        return dict(children)

    def monitor_stmt(self, children):
        target = str(children[0])
        body = children[1]
        return MonitorDef(
            target=target,
            alert_below=float(body.get("alert_below", 0.3)),
            action=str(body.get("action", "log")),
        )

    # ── step / recall / import ────────────────────────────────────────

    def step_stmt(self, children):
        return StepDef(n=int(children[0]))

    def recall_stmt(self, children):
        name = str(children[0])
        interval = None
        if len(children) == 3:
            num = float(children[1])
            unit = str(children[2])
            if unit == "s":
                interval = num
            elif unit == "m":
                interval = num * 60.0
            elif unit == "h":
                interval = num * 3600.0
        return RecallDef(name=name, interval_seconds=interval)

    def import_stmt(self, children):
        return ImportDef(module_path=".".join(str(c) for c in children))

    # ── statement / start ─────────────────────────────────────────────

    def statement(self, children):
        return children[0]

    def start(self, children):
        return ProgramAST(statements=list(children))


# =====================================================================
# SCHEDULE RUNNER  — osobne wątki dla każdej reguły
# =====================================================================

class ScheduleRunner:
    """Uruchamia reguły schedule w tle przy użyciu wątków."""

    def __init__(self, executor: "KarmazynExecutor"):
        self._executor = executor
        self._threads: List[threading.Thread] = []
        self._stop_event = threading.Event()

    def register(self, rule: ScheduleRule):
        t = threading.Thread(
            target=self._loop,
            args=(rule,),
            daemon=True,
            name=f"karm-schedule-{int(rule.interval_seconds)}s",
        )
        self._threads.append(t)
        t.start()
        print(f"  [SCHEDULE] Zarejestrowano regułę co {rule.interval_seconds}s "
              f"({len(rule.statements)} stmt)")

    def _loop(self, rule: ScheduleRule):
        while not self._stop_event.is_set():
            time.sleep(rule.interval_seconds)
            if self._stop_event.is_set():
                break
            try:
                for stmt in rule.statements:
                    self._executor.execute(stmt)
            except Exception as e:
                print(f"  [SCHEDULE ERROR] {e}")

    def stop(self):
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads.clear()
        print("  [SCHEDULE] Zatrzymano wszystkie reguły")


# =====================================================================
# EXECUTOR  — Node → KarmazynOS runtime
# =====================================================================

class KarmazynExecutor:
    """
    Tłumaczy węzły AST na wywołania KarmazynOS runtime.

    runtime — instancja KarmazynOS z karmazyn.py
    """

    def __init__(self, runtime):
        self.runtime = runtime
        self._scheduler = ScheduleRunner(self)
        # rejestr: name → label (zwrócony przez runtime.write)
        self._labels: Dict[str, str] = {}
        # rejestr: name → (pid, s_agent)
        self._agents: Dict[str, tuple] = {}
        # rejestr: name → hologram_id
        self._holograms: Dict[str, str] = {}
        # lista aktywnych monitorów
        self._monitors: List[MonitorDef] = []

    # ── publiczne API ─────────────────────────────────────────────────

    def execute(self, node: Node):
        """Wykonuje pojedynczy węzeł AST."""
        method = getattr(self, f"_exec_{type(node).__name__}", None)
        if method is None:
            raise NotImplementedError(
                f"Brak handlera dla węzła: {type(node).__name__}"
            )
        method(node)

    def run_program(self, program: ProgramAST):
        """Wykonuje cały program."""
        for stmt in program.statements:
            self.execute(stmt)

    def run_file(self, filepath: str):
        """Parsuje i wykonuje plik .karm."""
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
        self.run_source(source)

    def run_source(self, source: str):
        """Parsuje i wykonuje kod źródłowy jako string."""
        tree = _parser.parse(source)
        program = KarmazynTransformer().transform(tree)
        self.run_program(program)

    def stop_scheduler(self):
        """Zatrzymuje wszystkie wątki schedule."""
        self._scheduler.stop()

    def check_monitors(self):
        """
        Sprawdza wszystkie aktywne monitory.
        Wywołuj periodycznie (np. w pętli głównej).
        """
        epoch = self.runtime.phi.epoch
        for mon in self._monitors:
            b = self.runtime.bubbles.get_by_label(mon.target)
            if b is None:
                print(f"  [MONITOR] '{mon.target}' — brak bąbla")
                continue
            liv = b.liveliness(epoch)
            if liv < mon.alert_below:
                print(f"  [MONITOR ALERT] '{mon.target}' liveliness={liv:.4f} "
                      f"< {mon.alert_below} → {mon.action}")
                self._handle_monitor_action(mon, b, liv)

    # ── prywatne handlery ─────────────────────────────────────────────

    def _exec_AtomDef(self, node: AtomDef):
        # S zawiera treść semantyczną, E — kontekst/opis
        content = node.S
        if node.E:
            content = f"{node.S} | {node.E}"
        label = self.runtime.write(content, auto_consolidate=0)
        self._labels[node.name] = label
        print(f"  [ATOM] '{node.name}' → {label}  T={node.T}")

        # Jeśli decay ustawiony inaczej niż domyślny — rejestrujemy
        if node.decay != 0.01:
            self.runtime.mark_bubble_for_decay(label, rate=node.decay)

    def _exec_HologramDef(self, node: HologramDef):
        # Zbieramy etykiety składowych
        component_labels = []
        for comp_name in node.components:
            lbl = self._labels.get(comp_name)
            if lbl is None:
                print(f"  [WARN] Hologram '{node.name}': nieznany komponent "
                      f"'{comp_name}' — pomijam")
                continue
            # Konsoliduj jeśli bąbel nie istnieje
            if self.runtime.bubbles.get_by_label(lbl) is None:
                self.runtime.consolidate(lbl)
            component_labels.append(lbl)

        if not component_labels:
            print(f"  [WARN] Hologram '{node.name}': brak składowych — pomijam")
            return

        hid = self.runtime.archive_bubbles_to_hologram(
            topic=node.name,
            bubble_labels=component_labels,
            remove_originals=False,
        )
        self._holograms[node.name] = hid
        print(f"  [HOLOGRAM] '{node.name}' → {hid}  "
              f"({len(component_labels)} składowych)")

    def _exec_IdeaDef(self, node: IdeaDef):
        # Szukamy hologramu po pierwszym komponencie lub po prompt
        hid = None
        for comp_name in node.components:
            hid = self._holograms.get(comp_name)
            if hid:
                break

        if hid is None:
            # Tworzymy hologram na żądanie z dostępnych składowych
            component_labels = []
            for comp_name in node.components:
                lbl = self._labels.get(comp_name)
                if lbl:
                    if self.runtime.bubbles.get_by_label(lbl) is None:
                        self.runtime.consolidate(lbl)
                    component_labels.append(lbl)
            if component_labels:
                hid = self.runtime.archive_bubbles_to_hologram(
                    topic=f"idea_{node.prompt[:20]}",
                    bubble_labels=component_labels,
                )
                print(f"  [IDEA] Utworzono tymczasowy hologram → {hid}")

        if hid is None:
            print(f"  [WARN] Idea '{node.prompt}': brak hologramu — pomijam")
            return

        vec = self.runtime.generate_from_idea(
            hid,
            node.gen_prompt or node.prompt,
            temperature=node.temp,
        )
        if vec is None:
            print(f"  [WARN] generate_from_idea zwrócił None dla '{node.prompt}'")
            return

        new_label = self.runtime.phi.add_semantic_vector(
            vec,
            label=f"idea_{node.prompt[:20].replace(' ', '_')}",
        )
        self._labels[node.prompt] = new_label

        if node.consolidate:
            self.runtime.consolidate(new_label)

        print(f"  [IDEA] '{node.prompt}' → {new_label}  "
              f"temp={node.temp} consolidate={node.consolidate}")

    def _exec_SpawnDef(self, node: SpawnDef):
        label = self.runtime.write(node.content, auto_consolidate=0)
        self._labels[node.name] = label
        print(f"  [SPAWN] '{node.name}' → {label}  content='{node.content[:40]}'")

        if node.consolidate:
            self.runtime.consolidate(label)
            print(f"  [SPAWN] Skonsolidowano '{node.name}'")

    def _exec_PrismDef(self, node: PrismDef):
        # Mapujemy visibility/privileges na listę prismów dla derive_agent
        prisms = self._prism_str_to_list(node.visibility)
        pid, s_agent = self.runtime.derive_agent(
            name=node.name,
            task=f"prism:{node.name}",
            prisms=prisms,
        )
        self._agents[node.name] = (pid, s_agent)
        print(f"  [PRISM] '{node.name}' → PID={pid}  "
              f"visibility={node.visibility}  prisms={prisms}")

    def _exec_SessionDef(self, node: SessionDef):
        prisms = self._prism_str_to_list(node.prism)
        pid, s_agent = self.runtime.derive_agent(
            name=node.name,
            task=f"session:{node.name}",
            prisms=prisms,
        )
        self._agents[node.name] = (pid, s_agent)
        print(f"  [SESSION] '{node.name}' → PID={pid}  prisms={prisms}")

        for run_info in node.run_targets:
            target = run_info["target"]
            lbl = self._labels.get(target)
            if lbl is None:
                print(f"  [WARN] Session.run: nieznana etykieta '{target}' — pomijam")
                continue
            result = self.runtime.read_as_agent(lbl, pid, s_agent)
            print(f"  [SESSION.run] '{target}' → {result}")

    def _exec_ScheduleDef(self, node: ScheduleDef):
        for rule in node.rules:
            self._scheduler.register(rule)

    def _exec_ScheduleRule(self, node: ScheduleRule):
        # Bezpośrednie wykonanie (np. z wnętrza schedule loop)
        for stmt in node.statements:
            self.execute(stmt)

    def _exec_MonitorDef(self, node: MonitorDef):
        self._monitors.append(node)
        print(f"  [MONITOR] Zarejestrowano nadzór '{node.target}' "
              f"alert_below={node.alert_below}  action='{node.action}'")

    def _exec_StepDef(self, node: StepDef):
        stats = self.runtime.step(node.n)
        print(f"  [STEP] +{node.n} epok → {stats}")

    def _exec_RecallDef(self, node: RecallDef):
        results = self.runtime.recall(node.name, k=5)
        print(f"  [RECALL] '{node.name}' ({len(results)} wyników):")
        for r in results:
            layer = r.get("layer", "?")
            score = r.get("score", 0.0)
            lbl = r.get("label", "")
            print(f"    [{layer}] score={score:.4f}  label='{lbl}'")

        if node.interval_seconds is not None:
            rule = ScheduleRule(
                interval_seconds=node.interval_seconds,
                statements=[node],
            )
            self._scheduler.register(rule)

    def _exec_ImportDef(self, node: ImportDef):
        try:
            mod = importlib.import_module(node.module_path)
            print(f"  [IMPORT] Załadowano moduł '{node.module_path}'")
            return mod
        except ImportError as e:
            print(f"  [WARN] Import '{node.module_path}' nieudany: {e}")

    # ── pomocnicze ────────────────────────────────────────────────────

    @staticmethod
    def _prism_str_to_list(prism_str: str) -> List[str]:
        """
        Zamienia wartość pola prism/visibility na listę prismów
        akceptowaną przez derive_agent().
        """
        mapping = {
            "ALL":  ["core", "in", "out"],
            "CORE": ["core"],
            "IN":   ["in"],
            "OUT":  ["out"],
        }
        return mapping.get(str(prism_str).upper(), ["core", "in", "out"])

    def _handle_monitor_action(self, mon: MonitorDef, bubble, liveliness: float):
        action = mon.action.lower()
        if action == "log":
            pass  # już wydrukowano w check_monitors
        elif action == "refresh":
            ok = self.runtime.refresh_bubble(mon.target)
            print(f"  [MONITOR] refresh '{mon.target}' → {ok}")
        elif action == "revoke":
            ok = self.runtime.revoke_bubble(mon.target)
            print(f"  [MONITOR] revoke '{mon.target}' → Warp Oblivion={ok}")
        elif action == "step":
            self.runtime.step(1)
            print(f"  [MONITOR] step wywołany przez monitor '{mon.target}'")
        else:
            print(f"  [MONITOR] Nieznana akcja '{action}' dla '{mon.target}'")


# =====================================================================
# INICJALIZACJA PARSERA  (lazy — raz przy imporcie)
# =====================================================================

_parser = Lark(GRAMMAR, start="start", parser="lalr", lexer="contextual")


# =====================================================================
# FUNKCJE POMOCNICZE
# =====================================================================

def parse_file(filepath: str) -> ProgramAST:
    """Parsuje plik .karm i zwraca ProgramAST (bez wykonania)."""
    with open(filepath, encoding="utf-8") as f:
        source = f.read()
    return parse_source(source)


def parse_source(source: str) -> ProgramAST:
    """Parsuje kod źródłowy i zwraca ProgramAST (bez wykonania)."""
    tree = _parser.parse(source)
    return KarmazynTransformer().transform(tree)


# =====================================================================
# __main__ — szybki test bez karmazyn.py
# =====================================================================

if __name__ == "__main__":
    # Minimalny mock runtime do testowania parsera i transformera
    class _MockRuntime:
        class phi:
            epoch = 0
            _sem = {}
            _rc = {}

            @staticmethod
            def add(content, auto_consolidate=0):
                lbl = f"mock_{hash(content) % 10000}"
                print(f"    [mock.write] content='{content[:30]}' → {lbl}")
                return lbl

            @staticmethod
            def add_semantic_vector(vec, label=""):
                print(f"    [mock.phi.add_semantic_vector] label='{label}'")
                return label

        class bubbles:
            @staticmethod
            def get_by_label(lbl): return None
            @staticmethod
            def mark_for_decay(lbl, start_epoch, rate): pass

        @staticmethod
        def write(content, auto_consolidate=0):
            lbl = f"mock_{abs(hash(content)) % 10000}"
            print(f"    [mock.write] '{content[:30]}' → {lbl}")
            return lbl

        @staticmethod
        def consolidate(lbl, metadata=None):
            print(f"    [mock.consolidate] {lbl}")
            return f"bubble_{lbl}"

        @staticmethod
        def recall(query, k=5):
            print(f"    [mock.recall] query='{query}'")
            return []

        @staticmethod
        def step(n=1):
            print(f"    [mock.step] +{n}")
            return {"atoms": 0, "epoch": n}

        @staticmethod
        def derive_agent(name, task, prisms):
            print(f"    [mock.derive_agent] name='{name}' prisms={prisms}")
            return (42, b"fake_s_agent")

        @staticmethod
        def read_as_agent(label, pid, s_agent, from_bubble=False):
            return {"core": {"signal": True, "status": "✓ SYGNAŁ (mock)"}}

        @staticmethod
        def archive_bubbles_to_hologram(topic, bubble_labels, remove_originals=False, n_components=5):
            hid = f"idea_{topic}_0_mock"
            print(f"    [mock.archive_bubbles_to_hologram] topic='{topic}' → {hid}")
            return hid

        @staticmethod
        def generate_from_idea(hid, prompt, temperature=0.3):
            import numpy as np
            print(f"    [mock.generate_from_idea] hid='{hid}' prompt='{prompt}'")
            return np.zeros(64, dtype="float32")

        @staticmethod
        def mark_bubble_for_decay(label, rate=0.01):
            print(f"    [mock.mark_bubble_for_decay] '{label}' rate={rate}")
            return True

        @staticmethod
        def refresh_bubble(label):
            return True

        @staticmethod
        def revoke_bubble(label):
            return True

    SAMPLE = r"""
    // Testowy program .karm

    atom memory_kernel {
        S = "thermodynamic memory with bubble isolation"
        E = "core cognitive layer"
        T = 0.95
        decay = 0.005
    }

    atom phi_identity {
        S = "node identity phi-space vector"
        E = "identity anchor"
        T = "immortal"
    }

    hologram core_mind = memory_kernel + phi_identity {
        strength: "high"
        prism: "CORE"
        temp: 0.3
        description: "unified cognitive hologram"
    }

    spawn agent_a with "Agent A — primary perception layer" {
        temp 0.8
        consolidate
    }

    prism secure_view {
        mask = "CORE"
        visibility = "OUT"
        privileges = "IN"
    }

    session main_session {
        prism: "CORE"
        visibility: "OUT"
        run agent_a
    }

    schedule {
        every 60 s {
            step 1
            recall memory_kernel
        }
    }

    monitor liveliness of agent_a {
        alert_below: 0.2
        action: "refresh"
    }

    step 3

    recall memory_kernel

    import karmazyn.bridge
    """

    print("=" * 60)
    print("  karmazyn_lang.py — self-test")
    print("=" * 60)

    program = parse_source(SAMPLE)
    print(f"\nParsowanie OK — {len(program.statements)} statement(ów)\n")

    executor = KarmazynExecutor(_MockRuntime())
    executor.run_program(program)

    print("\n[check_monitors]")
    executor.check_monitors()

    executor.stop_scheduler()
    print("\nDone.")
