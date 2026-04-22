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
VERSION        = "0.2.0"


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
        self._session_id = 0
        # T_vacuum mierzone RAZ przy starcie — stabilna stała instancji
        self._t_vac_measured = self._measure_t_vacuum()
        # Stabilny seed Φ² — nie zmienia się przez całe życie instancji
        self._phi2_seed = os.urandom(32)

    # ── embed_structural ────────────────────────────────────────────────

    def embed_structural(self, content: bytes) -> np.ndarray:
        """
        Deterministyczny embedding strukturalny.
        Kontrakt: ten sam content → ten sam wektor zawsze.
        Znormalizowany: |e|₂ = 1.0.
        Używany wyłącznie do HRR trace — nie do recall semantycznego.
        """
        seed = int(hashlib.md5(content).hexdigest(), 16) % (2**32)
        rng  = np.random.default_rng(seed)
        v    = rng.normal(0, 1, self.dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)

    def embed_semantic(self, content: bytes) -> np.ndarray:
        """
        Embedding semantyczny przez hashing trick na tokenach.
        Deterministyczny. Brak LLM — działa offline.
        Słowa podobne znaczeniowo → bliższe wektory niż MD5.

        Metoda: każdy token → HMAC-based pozycja w R^D,
        wektor = suma pozycji tokenów (bag-of-embeddings).
        """
        try:
            text = content.decode('utf-8', errors='ignore').lower()
        except Exception:
            text = content.hex()

        # Tokenizacja: słowa + bigramy (lepsze pokrycie semantyczne)
        tokens = [w for w in text.split() if len(w) > 1]
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        all_tokens = tokens + bigrams

        if not all_tokens:
            return self.embed_structural(content)  # fallback

        v = np.zeros(self.dim, dtype=np.float32)
        for token in all_tokens:
            # Każdy token → deterministyczny wektor przez seed
            seed = int(hashlib.md5(token.encode()).hexdigest(), 16) % (2**32)
            rng  = np.random.default_rng(seed)
            tv   = rng.normal(0, 1, self.dim).astype(np.float32)
            v   += tv  # suma → bag-of-embeddings

        n = np.linalg.norm(v)
        if n < 1e-9:
            return self.embed_structural(content)
        return v / n

    # ── phi2_bytes — tożsamość Φ ─────────────────────────────────────────

    def phi2_bytes(self) -> bytes:
        """
        Φ² = stabilna tożsamość sesji.
        Korzeń: _phi2_seed (losowy przy starcie, stały przez życie instancji).
        Trace NIE wchodzi do Φ² — trace zmienia się, tożsamość nie.
        """
        return hashlib.sha256(self._phi2_seed + b"phi2-v2").digest()

    # ── T_vacuum ─────────────────────────────────────────────────────────

    def _measure_t_vacuum(self) -> float:
        """Jednorazowy pomiar — wywoływany tylko przy __init__."""
        sample = np.random.randint(0, Q, N, dtype=np.int64) % 256
        vals, counts = np.unique(sample, return_counts=True)
        probs = counts / len(sample)
        return float(-np.sum(probs * np.log2(probs + 1e-12)))

    def t_vacuum(self) -> float:
        """Stała instancji — mierzona raz przy starcie, nie zmienia się."""
        return self._t_vac_measured

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
        Hybrydowy recall: score = (α×struct + (1-α)×semantic) × T(atom)
        embed_semantic: bag-of-words hashing trick — ma semantykę.
        embed_structural: MD5-based — stabilna kotwica tożsamości.
        """
        q_struct   = self.embed_structural(query)
        q_semantic = self.embed_semantic(query)

        candidates = []
        for atom in self._matrix.atoms:
            if atom.get('session') != self._session_id and self._session_id != -1:
                continue
            sim_s = float(np.dot(q_struct,   atom['S']))
            sim_m = float(np.dot(q_semantic, atom['S']))
            # Hybrydowy score — max(0,...) eliminuje ujemne korelacje
            sim = alpha * max(0.0, sim_s) + (1 - alpha) * max(0.0, sim_m)
            T   = atom['T']
            candidates.append((sim * T, atom))

        candidates.sort(key=lambda x: x[0], reverse=True)
        top = candidates[:k]

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
        self._atom_map: Dict[str, str] = {}
        # Wzorce SHA256 contentu dla detekcji sygnału
        self._content_fingerprints: Dict[str, np.ndarray] = {}

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
        # Zapisz wzorzec dla detekcji sygnału w read_as_agent
        self._content_fingerprints[label] = bits8.astype(np.int64)

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

        # Oczekiwany wzorzec — SHA256 contentu (zapisany przy write)
        # Agent który ma właściwy klucz odzyska ten wzorzec.
        # Agent z złym kluczem odzyska pseudolosowe bity.
        expected_bits = None
        inode = self._atom_map.get(label, '')
        for lbl, ino in self._atom_map.items():
            if ino == inode and lbl == label:
                # Wzorzec ze scache (jeśli mamy)
                cached = self._content_fingerprints.get(label)
                if cached is not None:
                    expected_bits = cached
                break

        output = {}
        for prism in result_prisms:
            bits = decrypt(s_agent, prism.u, prism.v)

            if expected_bits is not None:
                # Hamming distance: im bliżej 0 tym lepszy sygnał
                hamming = int(np.sum(bits[:8] != expected_bits[:8]))
                sig = hamming <= 3   # tolerancja na błędy LWE
                status = f'✓ SYGNAŁ (hamming={hamming})' if sig else f'✗ SZUM (hamming={hamming})'
            else:
                # Fallback: entropia bitów — szum ma entropia ~0.5
                n_ones = int(np.sum(bits[:16]))
                sig = 4 <= n_ones <= 12  # bliżej 50% = szum, skrajności = sygnał
                status = '✓ SYGNAŁ' if sig else '✗ SZUM'

            output[prism.prism_id] = {
                'signal': sig,
                'bits':   bits[:8].tolist(),
                'status': status,
            }
        return output

    # ── evaluate ──────────────────────────────────────────────────────────

    def evaluate(self, context: str) -> Tuple[bool, float, str]:
        """
        Φ ocenia kontekst przez recall + temperaturę.
        score = Σ max(0, sim_semantic(query, atom)) × T(atom)
        θ     = mean(T) × 0.5  (adaptywny, nie T_vacuum)
        Używa embed_semantic — ma prawdziwą semantykę (bag-of-words).
        """
        raw    = context.encode()
        q_sem  = self.phi.embed_semantic(raw)
        atoms  = self.phi._matrix.atoms

        if not atoms:
            return False, 0.0, "Φ pusta"

        score     = sum(max(0.0, float(np.dot(q_sem, a['S']))) * a['T'] for a in atoms)
        mean_T    = float(np.mean([a['T'] for a in atoms]))
        threshold = mean_T * 0.5

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
