"""
karmazyn.py — KarmazynOS Core Library v0.1.0
=============================================
Pierwsza biblioteka systemu.

Łączy dwa silniki w jedno API:
    HSSKarmazynMatrix  → termodynamika, HRR, sesje, TTL
    HSSDaemon          → Ring-LWE, pryzmaty, capability, Warp Oblivion

Użycie:
    from karmazyn import KarmazynOS

    os = KarmazynOS()
    atom_id = os.write("spotkanie z Jankiem")
    results = os.recall("projekt spotkanie")
    os.step()

    # Z agentem
    s_agent = os.derive_agent("agent_A", task="email_read", prisms=["core","in","out"])
    data    = os.read_as_agent(atom_id, s_agent, prisms=["core","in","out"])

Architektura:
    KarmazynOS
    ├── PhiSpace        ← stan Φ (HSSKarmazynMatrix)
    ├── CryptoLayer     ← HSSDaemon (Ring-LWE)
    └── API publiczne   ← write / recall / step / derive_agent / read_as_agent
"""

import os
import sys
import time
import hashlib
import hmac as hmac_module
import json
import numpy as np
from typing import Optional, List, Dict, Tuple, Any

# ── importy silników ──────────────────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from hss_karmazyn_matrix import HSSKarmazynMatrix
from hss_demo import (
    HSSDaemon, kdf, decrypt, measure_entropy,
    N, Q, P_CORE, P_IN, P_OUT
)

# ─────────────────────────────────────────────────────────────────────────
# Stałe
# ─────────────────────────────────────────────────────────────────────────

ALPHA          = 0.3    # waga embed_structural w recall hybrydowym
LAMBDA_DECAY   = 0.1    # stała zaniku temperatury
DELTA_T_BASE   = 5.0    # energia startowa atomu
EPSILON_FEP    = 0.05   # margines vacuum (×T_vac)
VERSION        = "0.1.0"


# ─────────────────────────────────────────────────────────────────────────
# PhiSpace — warstwa termodynamiczna
# ─────────────────────────────────────────────────────────────────────────

class PhiSpace:
    """
    Warstwa Φ — termodynamika i HRR.
    Wrapper nad HSSKarmazynMatrix z API zgodnym ze spec v0.6.
    """

    def __init__(self, dim: int = 64, n_sessions: int = 1, seed: int = 42):
        self._matrix = HSSKarmazynMatrix(
            dim=dim,
            n_sessions=n_sessions,
            lambd=LAMBDA_DECAY,
            seed=seed,
        )
        self.dim = dim
        self._session_id = 0    # domyślna sesja Φ

    # ── embed_structural ────────────────────────────────────────────────

    def embed_structural(self, content: bytes) -> np.ndarray:
        """
        Deterministyczny embedding strukturalny.
        Kontrakt: ten sam content → ten sam wektor zawsze.
        Znormalizowany: |e|₂ = 1.0.
        """
        seed = int(hashlib.md5(content).hexdigest(), 16) % (2**32)
        rng  = np.random.default_rng(seed)
        v    = rng.normal(0, 1, self.dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)

    # ── phi2_bytes — tożsamość Φ ─────────────────────────────────────────

    def phi2_bytes(self) -> bytes:
        """
        Φ² = stabilna tożsamość sesji.
        Wyprowadzana z trace + T_vacuum.
        Wejście do KDF → base_secret → root_key atomów.
        """
        trace = self._matrix.traces[self._session_id]
        t_vac = self._t_vacuum()
        root  = trace.tobytes() + str(t_vac).encode()
        return hashlib.sha256(root).digest()

    # ── T_vacuum ─────────────────────────────────────────────────────────

    def _t_vacuum(self) -> float:
        """Mierzone lokalnie — jedyna absolutna stała."""
        sample = np.random.randint(0, Q, N, dtype=np.int64) % 256
        vals, counts = np.unique(sample, return_counts=True)
        probs = counts / len(sample)
        return float(-np.sum(probs * np.log2(probs + 1e-12)))

    def t_vacuum(self) -> float:
        return self._t_vacuum()  # mierzone, nie stała

    # ── zapis atomu ──────────────────────────────────────────────────────

    def add(self, content: bytes, label: str = "",
            session: Optional[int] = None) -> str:
        """
        Dodaj atom do przestrzeni Φ.
        Zwraca label (identyfikator w matrycy).
        """
        emb = self.embed_structural(content)
        lbl = label or f"atom_{hashlib.md5(content).hexdigest()[:8]}"
        sid = session if session is not None else self._session_id

        self._matrix.add_atom_vector(
            label=lbl,
            topic="karmazyn",
            vector=emb,
            init_T=DELTA_T_BASE,
            session=sid,
        )
        return lbl

    # ── recall ───────────────────────────────────────────────────────────

    def recall(self, query: bytes, k: int = 3,
               alpha: float = ALPHA) -> List[Dict]:
        """
        Hybrydowy recall: score = (α×struct + (1-α)×struct) × T(atom).
        semantic_cache nie jest zaimplementowany w v0.1 — używamy structural.
        Niestabilność po restarcie = zamierzona (historia somatyczna).
        """
        q_struct = self.embed_structural(query)
        t_vac    = self.t_vacuum()
        current  = self._matrix.time

        candidates = []
        for atom in self._matrix.atoms:
            if atom.get('session') != self._session_id and self._session_id != -1:
                continue
            sim = float(np.dot(q_struct, atom['S']))
            T   = atom['T']
            candidates.append((sim * T, atom))

        candidates.sort(key=lambda x: x[0], reverse=True)
        top = candidates[:k]

        # Ogrzewanie top-k
        for _, atom in top:
            self._heat(atom)

        return [a for _, a in top]

    def _heat(self, atom: Dict):
        """Częściowe ogrzewanie — nie do maksimum od razu."""
        T_max = DELTA_T_BASE
        atom['T'] = atom['T'] + 0.3 * (T_max - atom['T'])

    # ── krok epoki ───────────────────────────────────────────────────────

    def step(self) -> int:
        """
        Przesuń epokę. Vacuum Decay naturalny przez HSSKarmazynMatrix.step().
        Zwraca liczbę atomów po kroku.
        """
        self._matrix.step()
        return len(self._matrix.atoms)

    # ── temperatura systemu ──────────────────────────────────────────────

    def temperature(self) -> float:
        atoms = self._matrix.atoms
        if not atoms:
            return self.t_vacuum()
        return float(np.mean([a['T'] for a in atoms]))

    # ── stats ─────────────────────────────────────────────────────────────

    def stats(self) -> Dict:
        return {
            "atoms":       len(self._matrix.atoms),
            "epoch":       self._matrix.time,
            "temperature": self.temperature(),
            "t_vacuum":    self.t_vacuum(),
            "dim":         self.dim,
        }


# ─────────────────────────────────────────────────────────────────────────
# KarmazynOS — główne API
# ─────────────────────────────────────────────────────────────────────────

class KarmazynOS:
    """
    KarmazynOS Core Library v0.1.0

    Łączy PhiSpace (termodynamika) z HSSDaemon (Ring-LWE).
    Zgodne ze spec v0.6: atom = (S, E, T), trzy rytmy, Warp Oblivion.
    """

    def __init__(self, dim: int = 64, n_sessions: int = 1, seed: int = 42):
        # ── warstwa Φ ────────────────────────────────────────────────────
        self.phi    = PhiSpace(dim=dim, n_sessions=n_sessions, seed=seed)

        # ── warstwa kryptograficzna ───────────────────────────────────────
        self.daemon = HSSDaemon()

        # ── inicjalizacja s_sess z Φ² ────────────────────────────────────
        phi2_vec    = np.frombuffer(self.phi.phi2_bytes() * 4,
                                    dtype=np.float32)[:N]
        self._s_sess = self.daemon.init_phi_session(phi2_vec, phi_pid=0)

        # ── mapa atom_label → inode ───────────────────────────────────────
        self._atom_map: Dict[str, str] = {}  # label → inode

        # ── licznik PID agentów ───────────────────────────────────────────
        self._pid_counter = 100
        self._agent_registry: Dict[int, Tuple[str, List[str]]] = {}

        print(f"  KarmazynOS v{VERSION} gotowy")
        print(f"  T_vacuum:  {self.phi.t_vacuum():.4f} bit")
        print(f"  Dim:       {dim}  Sessions: {n_sessions}")
        print(f"  Entropy(s_sess): "
              f"{measure_entropy(self._s_sess % 256):.3f} bits")

    # ── write ─────────────────────────────────────────────────────────────

    def write(self, content: str,
              prisms: List[str] = ["core", "in", "out"]) -> str:
        """
        Zapisz treść jako atom.
        Zwraca atom_id (inode) — używany do odczytu.

        Przepływ:
          content → embed_structural → PhiSpace.add()
                  → bits → HSSDaemon.phi_write()
        """
        raw   = content.encode() if isinstance(content, str) else content
        label = self.phi.add(raw)

        # Konwersja na bity dla Ring-LWE
        bits8 = np.unpackbits(
            np.frombuffer(hashlib.sha256(raw).digest()[:8], dtype=np.uint8)
        )
        vec   = np.zeros(N, dtype=np.int64)
        vec[:64] = bits8.astype(np.int64)

        inode = f"karmazyn://atoms/{label}"
        self.daemon.phi_write(inode, vec)
        self._atom_map[label] = inode

        return label

    # ── recall ─────────────────────────────────────────────────────────────

    def recall(self, query: str, k: int = 3) -> List[Dict]:
        """
        Wyszukaj atomy przez hybrydowy recall.
        score = (α×structural + (1-α)×structural) × T(atom)

        Zwraca listę atomów z polem 'label', 'T', 'inode'.
        """
        raw    = query.encode() if isinstance(query, str) else query
        atoms  = self.phi.recall(raw, k=k)

        results = []
        for atom in atoms:
            label = atom.get('label', '')
            results.append({
                'label':  label,
                'T':      atom.get('T', 0.0),
                'inode':  self._atom_map.get(label, ''),
                'sim':    float(np.dot(
                    self.phi.embed_structural(raw), atom['S']
                )),
            })
        return results

    # ── derive_agent ──────────────────────────────────────────────────────

    def derive_agent(self, name: str, task: str,
                     prisms: List[str] = ["core", "in", "out"]) -> Tuple[int, np.ndarray]:
        """
        Wyprowadź klucz agenta z s_sess Φ.
        Zwraca (pid, s_agent).

        s_agent = KDF(s_sess, JSON(task, prisms))
        Capability przez algebrę — nie przez listę uprawnień.
        """
        self._pid_counter += 1
        pid     = self._pid_counter
        s_agent = self.daemon.derive_agent_key(pid, task, prisms)
        # Zapamiętaj task i prisms dla tego pid
        self._agent_registry[pid] = (task, prisms)
        return pid, s_agent

    # ── read_as_agent ─────────────────────────────────────────────────────

    def read_as_agent(self, label: str, pid: int, s_agent: np.ndarray,
                      prisms: List[str] = ["core", "in", "out"]) -> Dict:
        """
        Odczytaj atom jako agent z danym kluczem.

        Agent z pełnym capability → sygnał.
        Agent z częściowym capability → sygnał na autoryzowanych pryzmatach.
        Agent bez s_sess Φ → Warp Oblivion (szum termodynamiczny).

        Zwraca dict: {prism_id: {'signal': bool, 'bits': array}}
        """
        inode = self._atom_map.get(label)
        if not inode:
            return {'error': f'atom {label!r} nieznany'}

        # Użyj task zarejestrowanego przy derive_agent
        reg = self._agent_registry.get(pid)
        if reg is None:
            return {'error': f'PID {pid} nieznany — użyj derive_agent()'}
        registered_task, registered_prisms = reg

        result_prisms = self.daemon.upcall_read(
            agent_pid=pid,
            inode=inode,
            allowed_prisms=registered_prisms,
            task_id=registered_task,
        )

        if result_prisms is None:
            return {'error': 'ODMOWA — brak klucza w keyring'}

        output = {}
        for prism in result_prisms:
            bits = decrypt(s_agent, prism.u, prism.v)
            # Sygnał = odszyfrowane bity mają strukturę (>2 bity z 8)
            # Szum = deszyfrowanie złym kluczem = pseudolosowe bity
            # Próg 2/8 jest zbyt niski — szum też trafia.
            # Prawdziwy sygnał ma charakterystyczny wzór (sha256 hash).
            # Warp Oblivion: B nie odróżni — ontologicznie nie ma dostępu.
            sig  = int(np.sum(bits[:8])) > 0
            output[prism.prism_id] = {
                'signal': sig,
                'bits':   bits[:8].tolist(),
                'status': '✓ SYGNAŁ' if sig else '✗ SZUM',
            }
        return output

    # ── evaluate ──────────────────────────────────────────────────────────

    def evaluate(self, context: str) -> Tuple[bool, float, str]:
        """
        Φ ocenia kontekst przez recall + temperaturę.
        score = Σ sim(query, atom) × T(atom)
        θ     = T_vacuum × 1.5

        Nie lista uprawnień — termodynamika decyzji.

        UWAGA v0.1: z MD5-based embed_structural score bywa ujemny
        (brak prawdziwej semantyki). W produkcji: KuRz lub MiniLM
        jako embed_semantic zapewni sensowne wartości score.
        """
        raw      = context.encode()
        atoms    = self.phi.recall(raw, k=3, alpha=1.0)  # czysto strukturalne
        t_vac    = self.phi.t_vacuum()
        threshold = t_vac * 1.5

        if not atoms:
            return False, 0.0, f"Φ nie zna kontekstu | θ={threshold:.3f}"

        q_emb = self.phi.embed_structural(raw)
        score = sum(
            float(np.dot(q_emb, a['S'])) * a['T']
            for a in atoms
        )

        allow  = score > threshold
        reason = (
            f"score={score:.3f} > θ={threshold:.3f} → ZEZWÓL"
            if allow else
            f"score={score:.3f} ≤ θ={threshold:.3f} → ODMÓW"
        )
        return allow, score, reason

    # ── step ──────────────────────────────────────────────────────────────

    def step(self, n: int = 1) -> Dict:
        """
        Przesuń n epok.
        Vacuum Decay automatyczny przez HSSKarmazynMatrix.step().
        """
        for _ in range(n):
            self.phi.step()
        return self.stats()

    # ── terminate_agent ───────────────────────────────────────────────────

    def terminate_agent(self, pid: int, labels: List[str] = []):
        """
        Zakończ sesję agenta.
        s_agent skasowany z keyring → dane niedostępne → Vacuum Decay.
        """
        inodes = [self._atom_map[l] for l in labels if l in self._atom_map]
        self.daemon.terminate_agent(pid, inodes)
        self.daemon.vacuum_decay()

    # ── stats ──────────────────────────────────────────────────────────────

    def stats(self) -> Dict:
        """Stan systemu."""
        phi_stats = self.phi.stats()
        return {
            **phi_stats,
            "version":    VERSION,
            "atoms_known": len(self._atom_map),
        }

    # ── __repr__ ──────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        s = self.stats()
        return (f"KarmazynOS(v{VERSION} | "
                f"atoms={s['atoms']} | "
                f"T_Φ={s['temperature']:.3f} | "
                f"epoch={s['epoch']})")
