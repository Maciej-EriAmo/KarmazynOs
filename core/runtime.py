"""
karmazyn/core/runtime.py
Ujednolicony runtime dla KarmazynOS – fasada nad KarmazynOS (kernel) i HSSKarmazynMatrix.
"""

import threading
import time
from typing import Dict, List, Optional, Any

from .bubble import Atom, Bubble
from ..hss_karmazyn_matrix import HSSKarmazynMatrix   # ścieżka względna – dostosuj
from karmazyn_ui import AudioEngine


class Runtime:
    """
    Główny runtime systemu. Używa HSSKarmazynMatrix do termodynamiki atomów
    oraz własnego słownika bąbli. Emituje zdarzenia przez EventBus.
    """
    
    def __init__(self):
        self.matrix = HSSKarmazynMatrix(dim=64)
        self.bubbles: Dict[str, Bubble] = {}
        self.events = EventBus()
        self.audio = AudioEngine()
        self._running = False
        self._loop_thread: Optional[threading.Thread] = None
        self.current_mission: Optional[dict] = None
        self.resources: Dict[str, int] = {"żywica": 10}
        
        # Podłącz audio do eventów
        self.events.on("tick", lambda a: self.audio.tick(a.T / 100.0))
        self.events.on("vacuum_decay", lambda a: self.audio.vacuum_decay())
        self.events.on("atom_stabilized", lambda a: self.audio.mandala_harmony())
        self.events.on("atom_corrupted", lambda a: self.audio.corruption())
    
    # --- API atomów (delegacja do matrix) ---
    def create_atom(self, id: str, S: str, E: str, T: float) -> Any:
        return self.matrix.create_atom(id, S, E, T)
    
    def get_atom(self, id: str) -> Optional[Any]:
        return self.matrix.get_atom(id)
    
    def has_atom(self, id: str) -> bool:
        return self.matrix.has_atom(id)
    
    def delete_atom(self, id: str):
        atom = self.matrix.get_atom(id)
        if atom:
            atom.T = 0.0
            atom.state = "TOMB"
            self.events.emit("atom_deleted", atom)
    
    def stabilize_atom(self, id: str):
        atom = self.matrix.get_atom(id)
        if atom:
            atom.T = atom.T_max
            atom.state = "HOT"
            self.events.emit("atom_stabilized", atom)
    
    def corrupt_atom(self, id: str, amount: float = 25):
        atom = self.matrix.get_atom(id)
        if atom:
            amount_norm = amount / 100.0 if amount <= 1.0 else amount
            atom.T = max(0.0, atom.T - amount_norm)
            self.events.emit("atom_corrupted", atom)
            if atom.T <= 0:
                atom.state = "TOMB"
                self.events.emit("vacuum_decay", atom)
    
    def clone_atom(self, src_id: str, dst_id: str):
        src = self.get_atom(src_id)
        if src and not self.has_atom(dst_id):
            return self.create_atom(dst_id, src.S, src.E, src.T)
        raise ValueError("Nie można sklonować")
    
    def list_atoms(self, layer: str = None, visible_only: bool = True) -> list:
        atoms = self.matrix.atoms()
        if layer:
            atoms = [a for a in atoms if a.state == layer]
        if visible_only:
            atoms = [a for a in atoms if a.state != "TOMB"]
        return atoms
    
    def status_summary(self) -> dict:
        atoms = self.matrix.atoms()
        return {
            "HOT": sum(1 for a in atoms if a.state == "HOT"),
            "WARM": sum(1 for a in atoms if a.state == "WARM"),
            "COLD": sum(1 for a in atoms if a.state == "COLD"),
            "TOMB": sum(1 for a in atoms if a.state == "TOMB"),
        }
    
    # --- API bąbli ---
    def create_bubble(self, name: str, bubble_type: str = "document") -> Bubble:
        bid = f"bubble_{int(time.time())}_{hashlib.md5(name.encode()).hexdigest()[:8]}"
        bubble = Bubble(id=bid, name=name)
        bubble.manifest["type"] = bubble_type
        self.bubbles[bid] = bubble
        return bubble
    
    def get_bubble(self, bubble_id: str) -> Optional[Bubble]:
        return self.bubbles.get(bubble_id)
    
    def add_atom_to_bubble(self, bubble_id: str, content: str, energy: float = 1.0) -> Optional[str]:
        bubble = self.bubbles.get(bubble_id)
        if not bubble:
            return None
        atom_id = f"atom_{uuid.uuid4().hex[:8]}"
        atom = Atom(id=atom_id, content=content, energy=energy)
        bubble.add_atom(atom)
        return atom_id
    
    def get_bubble_content(self, bubble_id: str, prism: str = "CORE") -> str:
        bubble = self.bubbles.get(bubble_id)
        return bubble.assemble_content(prism) if bubble else ""
    
    def refresh_bubble(self, bubble_id: str) -> int:
        bubble = self.bubbles.get(bubble_id)
        if not bubble:
            return 0
        count = 0
        for atom in bubble.atoms:
            atom.refresh()
            count += 1
        return count
    
    def list_bubbles(self) -> List[dict]:
        return [
            {
                "id": b.id,
                "name": b.name,
                "active_atoms": len(b.get_active_atoms()),
                "created_at": b.created_at,
                "type": b.manifest["type"],
                "media_stats": b.manifest["media_stats"],
            }
            for b in self.bubbles.values()
        ]
    
    def find_bubble_by_name(self, name: str) -> Optional[str]:
        for bid, b in self.bubbles.items():
            if b.name.lower() == name.lower():
                return bid
        return None
    
    # --- Termodynamika (krok) ---
    def step(self, n: int = 1) -> dict:
        for _ in range(n):
            for atom, event_type in self.matrix.step():
                self.events.emit(event_type, atom)
        return self.status_summary()
    
    # --- Pętla zdarzeń ---
    def start_loop(self, interval: float = 0.2):
        if self._running:
            return
        self._running = True
        self._loop_thread = threading.Thread(target=self._loop_worker, args=(interval,), daemon=True)
        self._loop_thread.start()
    
    def _loop_worker(self, interval: float):
        while self._running:
            self.step()
            time.sleep(interval)
    
    def stop_loop(self):
        self._running = False
        if self._loop_thread:
            self._loop_thread.join(timeout=1.0)
            self._loop_thread = None
    
    # --- Persystencja (uproszczona) ---
    def save_all(self, path: str = ".bubbles"):
        import os
        os.makedirs(path, exist_ok=True)
        for bubble in self.bubbles.values():
            filepath = os.path.join(path, f"{bubble.name}.bubble")
            filepath_atom = filepath + ".atom"
            with open(filepath_atom, "w", encoding="utf-8") as f:
                json.dump({
                    "id": bubble.id,
                    "name": bubble.name,
                    "atoms": [{"id": a.id, "content": a.content, "energy": a.energy, "metadata": a.metadata} for a in bubble.atoms],
                    "manifest": bubble.manifest,
                    "created_at": bubble.created_at
                }, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Operacja zamiany bezpieczna dla Windows
            for attempt in range(5):
                try:
                    os.replace(filepath_atom, filepath)
                    break
                except PermissionError:
                    time.sleep(0.1)
    
    def load_all(self, path: str = ".bubbles"):
        self.bubbles.clear()
        for file in os.listdir(path):
            if file.endswith(".bubble"):
                with open(os.path.join(path, file), "r", encoding="utf-8") as f:
                    data = json.load(f)
                bubble = Bubble(id=data["id"], name=data["name"])
                bubble.created_at = data["created_at"]
                bubble.manifest = data["manifest"]
                for a in data["atoms"]:
                    atom = Atom(id=a["id"], content=a["content"], energy=a["energy"], metadata=a["metadata"])
                    bubble.atoms.append(atom)
                self.bubbles[bubble.id] = bubble


class EventBus:
    def __init__(self):
        self._handlers: Dict[str, list] = {}
    
    def on(self, event: str, handler):
        self._handlers.setdefault(event, []).append(handler)
    
    def emit(self, event: str, *args):
        for h in self._handlers.get(event, []):
            h(*args)
