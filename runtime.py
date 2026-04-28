
---

## 3. Nowy `runtime.py` — z klasą `SystemState`

```python
"""
KarmazynOS — SanctuaryRuntime
Jedno źródło prawdy o stanie systemu, EventBus, pętla systemowa,
oraz SystemState — most między STC-Φ-001 a kodem.
"""
import threading
import time
from hss_karmazyn_matrix import HSSMatrix
from karmazyn_ui import gfx, audio

# ═══════════════════════════════════════════
# MAPOWANIE STANÓW (STC-Φ-001, sekcja 08)
# ═══════════════════════════════════════════
STATE_MAP = {
    "active":  {"color": "phi_stable", "sound": "tick",         "dot": "active"},
    "thermal": {"color": "phi_thermal","sound": "tick",         "dot": "thermal"},
    "decay":   {"color": "phi_decay",  "sound": "vacuum_decay", "dot": "decay"},
    "corrupt": {"color": "phi_bright", "sound": "corruption",   "dot": "thermal"},
    "ghost":   {"color": "phi_ghost",  "sound": None,           "dot": "ghost"},
}

class SystemState:
    """Most między tokenami STC a kodem wykonawczym."""
    @staticmethod
    def classify(atom) -> str:
        if atom.state == "TOMB" or atom.T <= 0:
            return "ghost"
        if hasattr(atom, "splamiony") and atom.splamiony:
            return "corrupt"
        if atom.T > 70:
            return "active"
        if atom.T > 30:
            return "thermal"
        return "decay"

    @staticmethod
    def color_for(atom) -> str:
        return STATE_MAP[SystemState.classify(atom)]["color"]

    @staticmethod
    def sound_for(atom) -> str | None:
        return STATE_MAP[SystemState.classify(atom)]["sound"]

    @staticmethod
    def dot_for(atom) -> str:
        return STATE_MAP[SystemState.classify(atom)]["dot"]


# ═══════════════════════════════════════════
# EVENT BUS
# ═══════════════════════════════════════════
class EventBus:
    def __init__(self):
        self._handlers = {}
    def on(self, event: str, handler):
        self._handlers.setdefault(event, []).append(handler)
    def emit(self, event: str, *args):
        for h in self._handlers.get(event, []):
            h(*args)


# ═══════════════════════════════════════════
# RUNTIME
# ═══════════════════════════════════════════
class SanctuaryRuntime:
    def __init__(self):
        self.matrix = HSSMatrix()
        self.resources = {"żywica": 10}
        self.current_mission = None
        self.lock = threading.RLock()
        self.events = EventBus()
        self.audio = audio.AudioEngine()
        self._running = False
        self._thread = None

        # Podłączamy audio do zdarzeń
        self.events.on("tick", lambda atom: self.audio.tick(atom.T))
        self.events.on("vacuum_decay", lambda atom: self.audio.vacuum_decay())
        self.events.on("stabilized", lambda atom: self.audio.mandala_harmony())
        self.events.on("corruption", lambda atom: self.audio.corruption())

    def start_mission(self, mission_spec: dict):
        with self.lock:
            self.current_mission = mission_spec
            self.resources["żywica"] = mission_spec.get("startowa_zywica", 10)
            for rel in mission_spec["relikwie"]:
                if not self.matrix.has_atom(rel["id"]):
                    self.matrix.create_atom(rel["id"], rel["S"], rel["E"], rel["T_start"])
            self.events.emit("mission_started", mission_spec)

    def get_atom(self, atom_id: str):
        return self.matrix.get_atom(atom_id)

    def step(self):
        changes = self.matrix.step()
        for atom, event_type in changes:
            if event_type == "decay":
                self.events.emit("vacuum_decay", atom)
            elif event_type == "tick":
                self.events.emit("tick", atom)
            elif event_type == "warm":
                self.events.emit("warm_threshold", atom)

    def start_system_loop(self, interval=0.2):
        if self._running:
            return
        self._running = True
        def loop():
            while self._running:
                self.step()
                time.sleep(interval)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop_system_loop(self):
        self._running = False
