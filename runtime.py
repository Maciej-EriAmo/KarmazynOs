"""
runtime.py — SanctuaryRuntime v1.4 (Kontrakt Systemowy)
========================================================
KarmazynOS — Maciej Mazur, Warsaw 2026

Jedyne źródło prawdy. Każda operacja przechodzi przez runtime i emituje zdarzenie.

Zmiany v1.4:
  - HSSDaemon przeniesiony z bedit.py do runtime jako usługa mikrojądra.
    self.hss       — instancja HSSDaemon lub None
    self._hss_available — bool

Wymaga HSSKarmazynMatrix v2.0 (hss_karmazyn_matrix.py).
"""

import hashlib
import math
import re
import threading
import time
from typing import Dict, List, Optional, Tuple, Any

import numpy as np

from hss_karmazyn_matrix import HSSKarmazynMatrix
from karmazyn_ui import audio, gfx
from core.phi_math import PhiPhysics

# =====================================================================
# ADAPTER ATOMÓW
# =====================================================================
class Atom:
    def __init__(self, id_str, S_raw, E, T, decay_rate=0.0):
        self.id    = id_str
        self._S_raw = S_raw
        self.S      = PhiPhysics.normalize_to_phi_space(S_raw)
        self.E      = E
        self.T      = T
        self.decay  = decay_rate

# =====================================================================
# MAPOWANIE STANÓW
# =====================================================================

STATE_MAP = {
    "HOT":  {"color": "phi_stable",  "sound": "tick",         "dot": "active"},
    "WARM": {"color": "phi_thermal", "sound": "tick",         "dot": "thermal"},
    "COLD": {"color": "phi_decay",   "sound": "vacuum_decay", "dot": "decay"},
    "TOMB": {"color": "phi_ghost",   "sound": None,           "dot": "ghost"},
}


class SystemState:
    @classmethod
    def classify(cls, atom) -> str:
        if atom.state == "TOMB" or atom.T <= 0:
            return "ghost"
        if getattr(atom, "splamiony", False):
            return "corrupt"
        if atom.T > 70:
            return "active"
        if atom.T > 30:
            return "thermal"
        return "decay"

    @classmethod
    def color_for(cls, atom):
        state = atom.state if atom.state in STATE_MAP else "COLD"
        return STATE_MAP[state]["color"]

    @classmethod
    def sound_for(cls, atom):
        state = atom.state if atom.state in STATE_MAP else "COLD"
        return STATE_MAP[state]["sound"]


class EventBus:
    def __init__(self):
        self._handlers: Dict[str, list] = {}

    def on(self, event: str, handler):
        self._handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, *args):
        for h in self._handlers.get(event, []):
            h(*args)


# =====================================================================
# PHI SPACE
# =====================================================================

_PHI_DIM = 15


class PhiSpace:
    def __init__(self, dim: int = _PHI_DIM):
        self.dim   = dim
        self.epoch = 0
        self._sem: Dict[str, np.ndarray] = {}
        self._rc:  Dict[str, int]        = {}
        from core.phi_math import PhiPhysics
        self.space = PhiPhysics.get_space()

    def embed(self, text: str) -> np.ndarray:
        tokens = [w for w in re.split(r"\W+", text.lower()) if len(w) > 1]
        if not tokens:
            tokens = [text[:8] if text else "empty"]
        vec = np.zeros(self.space.n, dtype=np.float32)
        for tok in set(tokens):
            seed = int(hashlib.md5(tok.encode()).hexdigest(), 16) % (2 ** 32)
            v    = np.random.default_rng(seed).standard_normal(self.space.n).astype(np.float32)
            vec += v
        return self.space.normalize(vec)

    def register(self, label: str, text: str):
        self._sem[label] = self.embed(text)
        self._rc[label]  = 0

    def add_vector(self, label: str, vec: np.ndarray):
        self._sem[label] = self.space.normalize(vec)
        self._rc[label]  = 0

    def search(self, query: str, candidates: List[str],
               k: int = 5) -> List[Tuple[str, float]]:
        q      = self.embed(query)
        scores = []
        for lbl in candidates:
            v = self._sem.get(lbl)
            if v is None:
                continue
            sim = 1.0 - (self.space.metric(q, v) / 2.0)
            scores.append((lbl, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        for lbl, _ in scores[:k]:
            self._rc[lbl] = self._rc.get(lbl, 0) + 1
        return scores[:k]

    def get(self, label: str) -> Optional[np.ndarray]:
        return self._sem.get(label)

    def remove(self, label: str):
        self._sem.pop(label, None)
        self._rc.pop(label, None)


# =====================================================================
# BUBBLE / HOLOGRAM / AGENT
# =====================================================================

from karmazyn_core import Hologram as CoreHologram, Bubble as CoreBubble, BubbleMode


class Bubble(CoreBubble):
    def __init__(self, label: str, content: str, immortal: bool = False):
        from core.phi_math import PhiPhysics
        self.label    = label
        self.content  = content
        self.immortal = immortal
        self.density  = 1.0

        space    = PhiPhysics.get_space()
        vecs     = [PhiPhysics.normalize_to_phi_space(content)]
        phi1     = CoreHologram(space, vecs)
        phi2_vec = PhiPhysics.normalize_to_phi_space(label)

        super().__init__(space=space, phi1=phi1, phi2_vector=phi2_vec,
                         theta=3.0, mode=BubbleMode.WORKSPACE)

    def get_core_vector(self):
        from core.phi_math import PhiPhysics
        return PhiPhysics.normalize_to_phi_space(self.content)

    def absorb(self, atom):
        self.content = (
            f"{self.content} "
            f"{atom._S_raw if hasattr(atom, '_S_raw') else atom.S} "
            f"{atom.E}"
        ).strip()

    def liveliness(self, runtime) -> float:
        atom = runtime.get_atom(self.label)
        if atom is None:
            return 0.0
        return max(0.0, min(1.0, atom.T / atom.T_max))


class Hologram(CoreHologram):
    def __init__(self, hid: str, topic: str, proto: np.ndarray,
                 generators: List[np.ndarray], weights: List[float],
                 atom_labels: List[str], epoch: int):
        self.id           = hid
        self.topic        = topic
        self.proto        = proto
        self.generators   = generators
        self.weights      = weights
        self.atom_labels  = atom_labels
        self.epoch_created = epoch

        from core.phi_math import PhiPhysics
        space = PhiPhysics.get_space()
        vecs  = [proto] + generators if generators else [proto]
        super().__init__(space, vecs)

    def liveliness(self, current_epoch: int) -> float:
        return math.exp(-0.001 * max(0, current_epoch - self.epoch_created))


class Agent:
    _counter = 100

    def __init__(self, name: str, task: str, prisms: List[str]):
        Agent._counter += 1
        self.pid    = Agent._counter
        self.name   = name
        self.task   = task
        self.prisms = prisms


# =====================================================================
# SANCTUARY RUNTIME v1.4
# =====================================================================

class SanctuaryRuntime:
    """
    Termodynamiczny runtime KarmazynOS — jedyne źródło prawdy.

    v1.4: HSSDaemon podniesiony z bedit.py do mikrojądra runtime.
          Dostępny jako self.hss (lub None jeśli brak hss_demo.py).
    """

    def __init__(self):
        self.matrix       = HSSKarmazynMatrix(dim=_PHI_DIM)
        self.events       = EventBus()
        self.audio_engine = audio.AudioEngine()
        self._running     = False
        self._loop_thread: Optional[threading.Thread] = None
        self.current_mission: Optional[dict] = None
        self.resources: Dict[str, int] = {"żywica": 10}

        # ── HSS mikrojądro ────────────────────────────────────────────
        # HSSDaemon jest usługą jądra, nie aplikacji.
        # bedit.py i shell.py pobierają referencję przez RUNTIME.hss.
        try:
            from hss_demo import HSSDaemon
            self.hss = HSSDaemon()
            self._hss_available = True
        except ImportError:
            self.hss = None
            self._hss_available = False

        # ── Audio events ──────────────────────────────────────────────
        self.events.on("tick",           lambda a: self.audio_engine.tick(a.T))
        self.events.on("vacuum_decay",   lambda a: self.audio_engine.vacuum_decay())
        self.events.on("atom_stabilized",lambda a: self.audio_engine.mandala_harmony())
        self.events.on("atom_corrupted", lambda a: self.audio_engine.corruption())

        # Hard Save Broadcast
        self.events.on("vacuum_decay",   lambda a: self.events.emit("trigger_hard_save"))

        # Semantyczne warstwy (.karm)
        self.phi         = PhiSpace(dim=_PHI_DIM)
        self._bubbles:   Dict[str, Bubble]   = {}
        self._holograms: Dict[str, Hologram] = {}
        self._agents:    Dict[int, Agent]    = {}
        self._name_to_id: Dict[str, str]     = {}

    # ================================================================
    # API v1.1 — kompatybilność z shell.py i grą
    # ================================================================

    def create_atom(self, id: str, S: str, E: str, T: float,
                    decay_rate: float = 0.0):
        if self.matrix.has_atom(id):
            raise ValueError(f"Atom '{id}' już istnieje")
        atom = self.matrix.create_atom(id, S, E, T, decay_rate=decay_rate)
        self.phi.register(id, f"{S} {E}")
        self.events.emit("atom_created", atom)
        return atom

    def delete_atom(self, id: str):
        atom = self.matrix.get_atom(id)
        if not atom:
            raise ValueError(f"Atom '{id}' nie istnieje")
        atom.state = "TOMB"
        atom.T     = 0.0
        self.events.emit("atom_deleted", atom)
        return atom

    def stabilize_atom(self, id: str):
        atom = self.matrix.get_atom(id)
        if not atom:
            raise ValueError(f"Atom '{id}' nie istnieje")
        atom.T     = atom.T_max
        atom.state = "HOT"
        self.events.emit("atom_stabilized", atom)
        return atom

    def corrupt_atom(self, id: str, amount: float = 25):
        atom = self.matrix.get_atom(id)
        if not atom:
            raise ValueError(f"Atom '{id}' nie istnieje")
        amount_norm = amount / 100.0 if amount <= 1.0 else amount
        atom.T = max(0.0, atom.T - amount_norm)
        self.events.emit("atom_corrupted", atom)
        if atom.T <= 0:
            atom.state = "TOMB"
            self.events.emit("vacuum_decay", atom)
        return atom

    def update_atom(self, id: str, **kwargs):
        atom = self.matrix.get_atom(id)
        if not atom:
            raise ValueError(f"Atom '{id}' nie istnieje")
        for k, v in kwargs.items():
            if hasattr(atom, k):
                setattr(atom, k, v)
        self.events.emit("atom_updated", atom)
        return atom

    def clone_atom(self, src_id: str, dst_id: str):
        src = self.matrix.get_atom(src_id)
        if not src:
            raise ValueError(f"Źródło '{src_id}' nie istnieje")
        if self.matrix.has_atom(dst_id):
            raise ValueError(f"Cel '{dst_id}' już istnieje")
        return self.create_atom(dst_id, src.S, src.E, src.T)

    def get_atom(self, id: str):
        return self.matrix.get_atom(id)

    def has_atom(self, id: str) -> bool:
        return self.matrix.has_atom(id)

    def list_atoms(self, layer: str = None, emanation: str = None,
                   visible_only: bool = True) -> list:
        atoms = self.matrix.atoms()
        if layer:
            atoms = [a for a in atoms if a.state == layer]
        if emanation:
            atoms = [a for a in atoms if a.E == emanation]
        if visible_only:
            atoms = [a for a in atoms if a.state != "TOMB"]
        return atoms

    def count_atoms(self, layer: str = None) -> int:
        return len(self.list_atoms(layer=layer, visible_only=False))

    def status_summary(self) -> Dict[str, int]:
        return {
            "HOT":  self.count_atoms("HOT"),
            "WARM": self.count_atoms("WARM"),
            "COLD": self.count_atoms("COLD"),
            "TOMB": self.count_atoms("TOMB"),
        }

    # ── termodynamika ─────────────────────────────────────────────────

    def step(self, n: int = 1) -> dict:
        for _ in range(n):
            for atom, event_type in self.matrix.step():
                self.events.emit(event_type, atom)
                if event_type == "vacuum_decay":
                    self.phi.remove(atom.id)
                    self._bubbles.pop(atom.id, None)
            self.phi.epoch += 1
        return {**self.status_summary(), "epoch": self.phi.epoch}

    def start_loop(self, interval: float = 0.2):
        if self._running:
            return
        self._running     = True
        self._loop_thread = threading.Thread(
            target=self._loop_worker, args=(interval,), daemon=True
        )
        self._loop_thread.start()

    def _loop_worker(self, interval: float):
        while self._running:
            self.step()
            time.sleep(interval)

    def stop_loop(self):
        self._running = False
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=1.0)
        self._loop_thread = None

    def is_alive(self) -> bool:
        return self._loop_thread is not None and self._loop_thread.is_alive()

    def start_system_loop(self, interval: float = 0.2):
        """Alias dla kompatybilności z hss_demo.py / sanktuarium."""
        self.start_loop(interval)

    # ── misja ─────────────────────────────────────────────────────────

    def start_mission(self, mission: dict):
        self.current_mission       = mission
        self.resources["żywica"]   = int(mission.get("startowa_zywica", 10))
        for r in mission.get("relikwie", []):
            try:
                self.create_atom(
                    str(r["id"]),
                    str(r.get("S", "")),
                    str(r.get("E", "")),
                    float(r.get("T_start", r.get("T", 80.0))),
                )
            except ValueError:
                pass
        self.events.emit("mission_started", mission)

    # ================================================================
    # API v1.3 — semantyczne (.karm)
    # ================================================================

    def write(self, name: str, S: str, E: str, T: float,
              decay_rate: float = 0.0) -> str:
        label  = name
        suffix = 0
        while self.matrix.has_atom(label):
            suffix += 1
            label   = f"{name}_{suffix}"
        T_scaled = max(1.0, min(100.0, float(T) * 100.0))
        atom     = self.matrix.create_atom(label, S, E, T_scaled,
                                           decay_rate=decay_rate)
        self.phi.register(label, f"{S} {E}")
        self._name_to_id[name] = label
        self.events.emit("atom_created", atom)
        return label

    def consolidate_to_bubble(self, atom, bubble):
        from core.phi_math import PhiPhysics
        tau = 0.75
        if bubble.resonates_with(atom, tau):
            bubble.absorb(atom)
            bubble.update_psi([atom])
            return {"status": "absorbed", "atom": atom.id}
        return {
            "status":    "reflected",
            "atom":      atom.id,
            "reason":    "phase_mismatch",
            "coherence": float(np.dot(
                PhiPhysics._space.normalize(atom.S),
                PhiPhysics._space.normalize(bubble.get_core_vector())
            )),
        }

    def consolidate(self, label: str, metadata: dict = None) -> str:
        if label in self._bubbles:
            return f"bubble_{label}"
        atom = self.matrix.get_atom(label)
        if atom is None:
            raise ValueError(f"consolidate: atom '{label}' nie istnieje")
        self._bubbles[label] = Bubble(
            label=label,
            content=f"{atom.S} {atom.E}".strip()
        )
        self.events.emit("atom_stabilized", atom)
        return f"bubble_{label}"

    def get_bubble(self, label: str) -> Optional[Bubble]:
        return self._bubbles.get(label)

    def recall(self, query: str, k: int = 5) -> List[dict]:
        candidates = list(self.phi._sem.keys())
        phi_hits   = self.phi.search(query, candidates, k=k)
        results    = []
        for lbl, sim in phi_hits:
            atom = self.matrix.get_atom(lbl)
            T    = atom.T if atom else 0.0
            results.append({
                "label": lbl, "layer": "phi",
                "T": T, "sim": sim,
                "score": sim * (T / 100.0),
                "inode": f"sanctuary://{lbl}",
            })
        q_vec = self.phi.embed(query)
        for lbl, bubble in self._bubbles.items():
            v = self.phi.get(lbl)
            if v is None:
                continue
            liv = bubble.liveliness(self)
            if liv < 0.01:
                continue
            sim = float(np.dot(q_vec, v) /
                        (np.linalg.norm(q_vec) * np.linalg.norm(v) + 1e-9))
            results.append({
                "label": lbl, "layer": "bubble",
                "T": liv * 100.0, "sim": sim,
                "score": sim * liv,
                "inode": f"sanctuary://bubbles/{lbl}",
                "bubble_id": f"bubble_{lbl}",
                "liveliness": liv,
            })
        results.sort(key=lambda x: x["score"], reverse=True)
        self.events.emit("recall_fired", query)
        return results[:k]

    def archive_to_hologram(self, topic: str, atom_ids: List[str],
                            remove_originals: bool = False,
                            n_components: int = 5) -> str:
        vectors  = []
        valid_ids = []
        for lbl in atom_ids:
            v = self.phi.get(lbl)
            if v is not None:
                vectors.append(v)
                valid_ids.append(lbl)
        if not vectors:
            raise ValueError(f"archive_to_hologram '{topic}': brak wektorów")
        data    = np.array(vectors, dtype=np.float32)
        proto   = np.mean(data, axis=0)
        norm    = np.linalg.norm(proto)
        proto   = proto / norm if norm > 1e-9 else proto
        centered = data - proto
        cov      = centered.T @ centered / max(1, len(data))
        eigvals, eigvecs = np.linalg.eigh(cov)
        k       = min(n_components, len(eigvals))
        top_idx = np.argsort(eigvals)[-k:]
        generators = [eigvecs[:, i].astype(np.float32) for i in top_idx]
        raw_w      = [float(eigvals[i]) for i in top_idx]
        max_w      = max(raw_w) if raw_w else 1.0
        weights    = [w / max_w for w in raw_w]
        hid        = (f"idea_{topic}_{self.phi.epoch}_"
                      f"{hashlib.md5(topic.encode()).hexdigest()[:6]}")
        self._holograms[hid] = Hologram(
            hid=hid, topic=topic, proto=proto,
            generators=generators, weights=weights,
            atom_labels=valid_ids, epoch=self.phi.epoch,
        )
        if remove_originals:
            for lbl in valid_ids:
                self._bubbles.pop(lbl, None)
        self.events.emit("hologram_created", hid)
        return hid

    def generate_from_idea(self, hologram_id: str, prompt: str,
                           temperature: float = 0.3) -> Optional[np.ndarray]:
        h = self._holograms.get(hologram_id)
        if h is None:
            return None
        liv = h.liveliness(self.phi.epoch)
        if liv <= 1e-9:
            return None
        q         = self.phi.embed(prompt)
        synthetic = h.proto * float(np.dot(q, h.proto))
        for g, w in zip(h.generators, h.weights):
            synthetic += g * float(np.dot(q, g)) * w * temperature
        seed      = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16)
        noise     = np.random.default_rng(seed).standard_normal(_PHI_DIM).astype(np.float32)
        synthetic += noise * 0.05 * temperature
        synthetic *= liv
        norm       = np.linalg.norm(synthetic)
        return synthetic / norm if norm > 1e-9 else synthetic

    def refresh_bubble(self, label: str) -> bool:
        if not self.matrix.has_atom(label):
            return False
        self.stabilize_atom(label)
        return True

    def revoke_bubble(self, label: str) -> bool:
        bubble = self._bubbles.get(label)
        if bubble and bubble.immortal:
            return False
        atom = self.matrix.get_atom(label)
        if atom is None:
            return False
        self.corrupt_atom(label, atom.T_max + 1.0)
        self._bubbles.pop(label, None)
        return True

    def mark_bubble_for_decay(self, label: str, rate: float = 0.01) -> bool:
        atom = self.matrix.get_atom(label)
        if atom is None:
            return False
        amount = max(1.0, rate * atom.T_max)
        self.corrupt_atom(label, amount)
        return True

    def derive_agent(self, name: str, task: str,
                     prisms: List[str]) -> Tuple[int, bytes]:
        agent  = Agent(name, task, prisms)
        self._agents[agent.pid] = agent
        s_agent = hashlib.sha256(
            f"{name}:{task}:{prisms}".encode()
        ).digest()
        bubble_label = f"transient_bubble_{agent.pid}"
        self.write(bubble_label, "BUBBLE",
                   f"Transient Bubble dla agenta {name} ({agent.pid})",
                   1.0, decay_rate=0.05)
        return agent.pid, s_agent

    def read_as_agent(self, atom_id: str, pid: int,
                      s_agent: bytes) -> dict:
        agent = self._agents.get(pid)
        if agent is None:
            return {"error": f"PID {pid} nieznany"}
        atom = self.matrix.get_atom(atom_id)
        if atom is None:
            return {"sanctuary": {"signal": False,
                                  "status": "✗ SZUM (atom nieznany)"}}
        if atom.state == "TOMB" or atom.T <= 0:
            return {"sanctuary": {"signal": False,
                                  "status": "✗ SZUM (Warp Oblivion)"}}
        if "core" not in agent.prisms and "in" not in agent.prisms:
            return {"sanctuary": {"signal": False,
                                  "status": "✗ SZUM (brak dostępu CORE/IN)"}}
        return {"sanctuary": {
            "signal": True,
            "status": f"✓ SYGNAŁ (T={atom.T:.1f} state={atom.state})",
            "S": atom.S, "E": atom.E, "T": atom.T,
        }}

    def atom_id_for(self, name: str) -> Optional[str]:
        if name in self._name_to_id:
            return self._name_to_id[name]
        if self.matrix.has_atom(name):
            return name
        return None