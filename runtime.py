"""
KarmazynOS — SanctuaryRuntime v1.1 (Kontrakt Systemowy)
Jedyne źródło prawdy. Każda operacja przechodzi przez runtime i emituje zdarzenie.
"""
import threading, time
from typing import Optional, List, Dict, Any
from hss_karmazyn_matrix import HSSMatrix
from karmazyn_ui import audio, gfx

# ═══════════════════════════════════════════
# MAPOWANIE STANÓW (STC-Φ-001)
# ═══════════════════════════════════════════
STATE_MAP = {
    "active":  {"color": "phi_stable", "sound": "tick",         "dot": "active"},
    "thermal": {"color": "phi_thermal","sound": "tick",         "dot": "thermal"},
    "decay":   {"color": "phi_decay",  "sound": "vacuum_decay", "dot": "decay"},
    "corrupt": {"color": "phi_bright", "sound": "corruption",   "dot": "thermal"},
    "ghost":   {"color": "phi_ghost",  "sound": None,           "dot": "ghost"},
}

class SystemState:
    @classmethod
    def classify(cls, atom) -> str:
        if atom.state == "TOMB" or atom.T <= 0: return "ghost"
        if hasattr(atom,'splamiony') and atom.splamiony: return "corrupt"
        if atom.T > 70: return "active"
        if atom.T > 30: return "thermal"
        return "decay"
    @classmethod
    def color_for(cls, atom): return STATE_MAP[cls.classify(atom)]["color"]
    @classmethod
    def sound_for(cls, atom): return STATE_MAP[cls.classify(atom)]["sound"]

class EventBus:
    def __init__(self): self._handlers = {}
    def on(self, e, h): self._handlers.setdefault(e, []).append(h)
    def emit(self, e, *a):
        for h in self._handlers.get(e, []): h(*a)

class SanctuaryRuntime:
    def __init__(self):
        self.matrix = HSSMatrix()
        self.events = EventBus()
        self.audio_engine = audio.AudioEngine()
        self._running = False
        # Podłączamy audio do zdarzeń systemowych
        self.events.on("tick", lambda a: self.audio_engine.tick(a.T))
        self.events.on("vacuum_decay", lambda a: self.audio_engine.vacuum_decay())
        self.events.on("atom_stabilized", lambda a: self.audio_engine.mandala_harmony())
        self.events.on("atom_corrupted", lambda a: self.audio_engine.corruption())

    # ─── API PUBLICZNE (jedyne dozwolone operacje) ───
    def create_atom(self, id: str, S: str, E: str, T: float):
        if self.matrix.has_atom(id): raise ValueError(f"Atom {id} już istnieje")
        atom = self.matrix.create_atom(id, S, E, T)
        self.events.emit("atom_created", atom)
        return atom

    def delete_atom(self, id: str):
        atom = self.matrix.get_atom(id)
        if not atom: raise ValueError(f"Atom {id} nie istnieje")
        atom.state = "TOMB"
        self.events.emit("atom_deleted", atom)
        return atom

    def stabilize_atom(self, id: str):
        atom = self.matrix.get_atom(id)
        if not atom: raise ValueError(f"Atom {id} nie istnieje")
        atom.T = atom.T_max
        atom.state = "HOT"
        self.events.emit("atom_stabilized", atom)
        return atom

    def corrupt_atom(self, id: str, amount: float = 25):
        """Obniża T atomu z pełną kontrolą przejść."""
        atom = self.matrix.get_atom(id)
        if not atom: raise ValueError(f"Atom {id} nie istnieje")
        atom.T = max(0, atom.T - amount)
        self.events.emit("atom_corrupted", atom)
        if atom.T <= 0:
            atom.state = "TOMB"
            self.events.emit("vacuum_decay", atom)
        return atom

    def update_atom(self, id: str, **kwargs):
        atom = self.matrix.get_atom(id)
        if not atom: raise ValueError(f"Atom {id} nie istnieje")
        for k, v in kwargs.items():
            if hasattr(atom, k): setattr(atom, k, v)
        self.events.emit("atom_updated", atom)
        return atom

    def clone_atom(self, src_id: str, dst_id: str):
        src = self.matrix.get_atom(src_id)
        if not src: raise ValueError(f"Źródło {src_id} nie istnieje")
        if self.matrix.has_atom(dst_id): raise ValueError(f"Cel {dst_id} już istnieje")
        return self.create_atom(dst_id, src.S, src.E, src.T)

    def get_atom(self, id: str): return self.matrix.get_atom(id)
    def has_atom(self, id: str): return self.matrix.has_atom(id)

    def list_atoms(self, layer: str = None, emanation: str = None, visible_only: bool = True):
        atoms = self.matrix.atoms()
        if layer: atoms = [a for a in atoms if a.state == layer]
        if emanation: atoms = [a for a in atoms if a.E == emanation]
        if visible_only: atoms = [a for a in atoms if SystemState.classify(a) != "ghost"]
        return atoms

    def count_atoms(self, layer: str = None): return len(self.list_atoms(layer=layer, visible_only=False))

    def status_summary(self) -> Dict[str, int]:
        return {
            "HOT": self.count_atoms("HOT"),
            "WARM": self.count_atoms("WARM"),
            "COLD": self.count_atoms("COLD"),
            "TOMB": self.count_atoms("TOMB"),
        }

    # ─── PĘTLA TERMODYNAMICZNA ───
    def step(self):
        for atom, event_type in self.matrix.step():
            self.events.emit(event_type, atom)

    def start_loop(self, interval=0.2):
        if self._running: return
        self._running = True
        def loop():
            while self._running:
                self.step()
                time.sleep(interval)
        threading.Thread(target=loop, daemon=True).start()

    def stop_loop(self): self._running = False