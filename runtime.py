"""
KarmazynOS — SanctuaryRuntime v1.0
Jedyny punkt dostępu do macierzy atomów, egzekwuje cykl życia i emituje zdarzenia.
"""
import threading
import time
from typing import Optional, List, Tuple
from karmazyn import Atom
from hss_karmazyn_matrix import HSSMatrix
from karmazyn_ui import audio, gfx

# ═══════════════════════════════════════════
# MAPOWANIE STANÓW (zgodne z STC-Φ-001)
# ═══════════════════════════════════════════
STATE_MAP = {
    "active":  {"color": "phi_stable", "sound": "tick",         "dot": "active"},
    "thermal": {"color": "phi_thermal","sound": "tick",         "dot": "thermal"},
    "decay":   {"color": "phi_decay",  "sound": "vacuum_decay", "dot": "decay"},
    "corrupt": {"color": "phi_bright", "sound": "corruption",   "dot": "thermal"},
    "ghost":   {"color": "phi_ghost",  "sound": None,           "dot": "ghost"},
}

class SystemState:
    """Klasyfikuje atom i zwraca tokeny percepcji."""
    @staticmethod
    def classify(atom: Atom) -> str:
        if atom.state == "TOMB" or atom.T <= 0:
            return "ghost"
        if hasattr(atom, 'splamiony') and atom.splamiony:
            return "corrupt"
        if atom.T > 70:
            return "active"
        if atom.T > 30:
            return "thermal"
        return "decay"

    @staticmethod
    def color_for(atom: Atom) -> str:
        return STATE_MAP[SystemState.classify(atom)]["color"]

    @staticmethod
    def sound_for(atom: Atom) -> Optional[str]:
        return STATE_MAP[SystemState.classify(atom)]["sound"]

    @staticmethod
    def dot_for(atom: Atom) -> str:
        return STATE_MAP[SystemState.classify(atom)]["dot"]


class EventBus:
    def __init__(self):
        self._handlers = {}

    def on(self, event: str, handler):
        self._handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, *args):
        for h in self._handlers.get(event, []):
            h(*args)


class SanctuaryRuntime:
    def __init__(self):
        self.matrix = HSSMatrix()
        self.events = EventBus()
        self.audio = audio.AudioEngine()
        self._running = False
        self._thread = None

        # Podłączamy audio do zdarzeń
        self.events.on("tick", lambda a: self.audio.tick(a.T))
        self.events.on("vacuum_decay", lambda a: self.audio.vacuum_decay())
        self.events.on("atom_stabilized", lambda a: self.audio.mandala_harmony())
        self.events.on("atom_corrupted", lambda a: self.audio.corruption())

    # ═══════════════════════════════════════
    # API PUBLICZNE
    # ═══════════════════════════════════════
    def create_atom(self, id: str, S: str, E: str, T: float) -> Atom:
        if self.matrix.has_atom(id):
            raise ValueError(f"Atom {id} już istnieje")
        atom = self.matrix.create_atom(id, S, E, T)
        self.events.emit("atom_created", atom)
        return atom

    def delete_atom(self, id: str) -> Atom:
        atom = self.matrix.get_atom(id)
        if atom is None:
            raise ValueError(f"Atom {id} nie istnieje")
        if atom.state not in ("HOT", "WARM"):
            raise ValueError("Atom mus nie być HOT lub WARM")
        atom.state = "TOMB"
        self.events.emit("atom_deleted", atom)
        return atom

    def stabilize_atom(self, id: str) -> Atom:
        atom = self.matrix.get_atom(id)
        if atom is None:
            raise ValueError(f"Atom {id} nie istnieje")
        atom.T = atom.T_max
        atom.state = "HOT"
        self.events.emit("atom_stabilized", atom)
        return atom

    def update_atom(self, id: str, **kwargs) -> Atom:
        atom = self.matrix.get_atom(id)
        if atom is None:
            raise ValueError(f"Atom {id} nie istnieje")
        for key, value in kwargs.items():
            if hasattr(atom, key):
                setattr(atom, key, value)
        self.events.emit("atom_updated", atom)
        return atom

    def clone_atom(self, src_id: str, dst_id: str) -> Atom:
        src = self.matrix.get_atom(src_id)
        if src is None:
            raise ValueError(f"Źródłowy atom {src_id} nie istnieje")
        if self.matrix.has_atom(dst_id):
            raise ValueError(f"Docelowy atom {dst_id} już istnieje")
        return self.create_atom(dst_id, src.S, src.E, src.T)

    def get_atom(self, id: str) -> Optional[Atom]:
        return self.matrix.get_atom(id)

    def has_atom(self, id: str) -> bool:
        return self.matrix.has_atom(id)

    def list_atoms(self, layer: str = None, prism: str = None, emanation: str = None) -> List[Atom]:
        atoms = self.matrix.atoms()
        if layer:
            atoms = [a for a in atoms if a.state == layer]
        if emanation:
            atoms = [a for a in atoms if a.E == emanation]
        # Filtrowanie Warp Oblivion
        if prism is None:
            atoms = [a for a in atoms if SystemState.classify(a) != "ghost"]
        return atoms

    def count_atoms(self, layer: str = None) -> int:
        return len(self.list_atoms(layer=layer))

    # ═══════════════════════════════════════
    # PĘTLA TERMODYNAMICZNA
    # ═══════════════════════════════════════
    def step(self):
        changes = self.matrix.step()
        for atom, event_type in changes:
            if event_type == "decay":
                self.events.emit("vacuum_decay", atom)
            elif event_type == "tick":
                self.events.emit("tick", atom)
            elif event_type == "warm":
                self.events.emit("warm_threshold", atom)

    def start_loop(self, interval: float = 0.2):
        if self._running:
            return
        self._running = True
        def loop():
            while self._running:
                self.step()
                time.sleep(interval)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop_loop(self):
        self._running = False
