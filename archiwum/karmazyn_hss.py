"""
karmazyn_hss.py — HSS Daemon KarmazynOS v1.0
=============================================
Holographic Secure Storage — szyfrowany dostęp do phi-space.

Implementacja Ring-LWE (N=15, Q=256) z wielobitowym kodowaniem (2 bity/element).
Kontrola dostępu przez system pryzmatów (prisms) — ACL na poziomie inodów.

Izomorfizm phi-space:
  inode    ≡ atom.id      (adres w przestrzeni)
  vec      ≡ atom.S       (wektor semantyczny)
  prisms   ≡ kontekst bąbla (izolacja dostępu między domenami)
  task     ≡ intencja agenta (task mismatch → deszyfrowanie niemożliwe)

Kluczowe właściwości:
  - Task mismatch: agent z task A nie może czytać danych task B
    nawet mając poprawny klucz (50% błędów bitu → garbage)
  - ACL inodu: właściciel definiuje wymagane prismy przy pierwszym zapisie
  - Ring-LWE: odporność post-kwantowa
"""

import hashlib
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Parametry kraty – współdzielone z resztą systemu
N = 15
Q = 256
NOISE_BASE = 3           # bazowy zakres szumu (±3)
BITS_PER_ELEMENT = 2     # 2 bity → wartości 0..3

# ── Struktury danych ─────────────────────────────────────────────────
@dataclass
class RLWEResult:
    projection_id: str    # identyfikator projekcji (hash prismów + task)
    u: np.ndarray         # wektor długości N
    v: int                # wartość skalarna

@dataclass
class HistoryEntry:
    shape: Tuple[int, ...]
    bits_per_element: int
    results: List[RLWEResult]   # długość = prod(shape) * bits_per_element

# ── Narzędzia kryptograficzne ────────────────────────────────────────
def kdf(seed_bytes: bytes, salt: str) -> np.ndarray:
    """Deterministyczne wyprowadzenie klucza sesyjnego w Z_q^N."""
    h = hashlib.sha256(seed_bytes + salt.encode()).digest()
    extended = (h * ((N // len(h)) + 1))[:N]
    return np.frombuffer(extended, dtype=np.uint8).astype(np.int64) % Q

def _make_seed(context: str) -> int:
    h = hashlib.sha256(context.encode()).digest()
    return int.from_bytes(h[:4], 'little')

def _make_projection_id(prisms: List[str], task: str) -> str:
    raw = "|".join(sorted(prisms)) + "|" + task
    return hashlib.sha256(raw.encode()).hexdigest()[:12]

def _encode_value(val: int, bits: int) -> List[int]:
    """Rozkłada wartość na listę bitów (LSB first)."""
    return [(val >> i) & 1 for i in range(bits)]

def _decode_bits(bits: List[int]) -> int:
    """Składa listę bitów LSB first w liczbę."""
    return sum(b << i for i, b in enumerate(bits))

# ── Deszyfrowanie wielobitowe ────────────────────────────────────────
def decrypt_multibit(s_agent: np.ndarray,
                     results: List[RLWEResult],
                     bits_per_element: int) -> np.ndarray:
    """
    Dekoduje listę RLWEResult w wektor wartości całkowitych (0..2^bits-1).
    Wynik ma długość len(results) // bits_per_element.
    """
    it = iter(results)
    values = []
    num_elements = len(results) // bits_per_element
    for _ in range(num_elements):
        elem_bits = []
        for _ in range(bits_per_element):
            r = next(it)
            dot = np.dot(s_agent, r.u) % Q
            diff = (r.v - dot) % Q
            if Q//4 < diff < 3*Q//4:
                elem_bits.append(1)
            else:
                elem_bits.append(0)
        values.append(_decode_bits(elem_bits))
    return np.array(values, dtype=np.int64)

# ── Daemon ───────────────────────────────────────────────────────────
class HSSDaemon:
    def __init__(self, bits_per_element: int = BITS_PER_ELEMENT):
        self.bits_per_element = bits_per_element
        self._phi_sessions = {}         # phi_pid -> s_sess
        self._agents = {}               # uuid -> (s_agent, prisms, task)
        self._inodes = {}               # inode -> lista ndarray (plaintext)
        self._inode_prisms = {}         # inode -> set wymaganych prismow (kontrola dostepu)
        self._terminated_agents = set()

    def init_phi_session(self, phi2_vec: np.ndarray, phi_pid: int) -> np.ndarray:
        seed = phi2_vec.tobytes()
        s_sess = kdf(seed, f"phi_sess_{phi_pid}")
        self._phi_sessions[phi_pid] = s_sess
        return s_sess

    def derive_agent_key(self, agent_uuid: str, task: str,
                         prisms: List[str] = None) -> np.ndarray:
        if prisms is None:
            prisms = ["core"]
        master = b"HSS_MASTER_SEED_v1"
        seed = f"{agent_uuid}|{task}|{','.join(sorted(prisms))}"
        s_agent = kdf(master, seed)
        self._agents[agent_uuid] = (s_agent, prisms, task)
        return s_agent

    def phi_write(self, inode: str, vec: np.ndarray,
                  required_prisms: List[str] = None):
        """
        Zapisuje oryginalny wektor (plaintext) do inodu.
        required_prisms – prismy wymagane do odczytu tego inodu.
        Ustawiane tylko przy pierwszym zapisie (wlasciciel definiuje ACL).
        """
        if inode not in self._inodes:
            self._inodes[inode] = []
            # ACL inodu – ustawiany przez wlasciciela przy pierwszym zapisie.
            # Jesli nie podano, domyslnie wymaga prismu 'core'.
            self._inode_prisms[inode] = set(required_prisms) if required_prisms else {'core'}
        mask = (1 << self.bits_per_element) - 1
        clamped = vec.copy() & mask
        self._inodes[inode].append(clamped)

    def upcall_read(self, agent_uuid: str, inode: str,
                    prisms: List[str], task: str) -> Optional[List[HistoryEntry]]:
        if agent_uuid not in self._agents:
            return None
        s_agent, agent_prisms, agent_task = self._agents[agent_uuid]

        # Sprawdz prism agenta vs prism zadania (requestowane przez callera)
        if not any(p in agent_prisms for p in prisms):
            return None

        # Sprawdz ACL inodu – prism agenta musi pokrywac sie z wymaganiami inodu.
        # To zapobiega sytuacji gdy agent z prism 'covert' czyta inod
        # zapisany przez agenta z prism 'science'.
        required = self._inode_prisms.get(inode, {'core'})
        if not required.intersection(set(agent_prisms)):
            return None

        history = self._inodes.get(inode, [])
        if not history:
            return []

        # Klucz efektywny: przy task mismatch uzywamy innego klucza niz agent.
        # Agent probuje deszyfrować swoim s_agent, ale v bylo generowane s_effective ≠ s_agent
        # → diff jest pseudolosowy → deszyfrowanie niepoprawne (~50% bledow bitu).
        s_effective = self._effective_agent_key(s_agent, agent_task, task)

        proj_id = _make_projection_id(prisms, task)
        entries = []
        for i, stored_vec in enumerate(history):
            shape = stored_vec.shape
            seed_int = _make_seed(f"read:{inode}:{i}")
            rng = np.random.default_rng(seed_int)
            results = []
            for idx, val in enumerate(stored_vec.flat):
                val_bits = _encode_value(int(val), self.bits_per_element)
                for bit_idx, bit in enumerate(val_bits):
                    u = rng.integers(0, Q, size=N, dtype=np.int64)
                    dot = np.dot(s_effective, u) % Q   # s_effective, nie s_agent
                    noise_rng = np.random.default_rng(
                        _make_seed(f"noise:{inode}:{i}:{idx}:{bit_idx}"))
                    raw_noise = noise_rng.integers(-NOISE_BASE, NOISE_BASE+1, dtype=np.int64)
                    noise = int(raw_noise)              # skala=1, szum tylko maskujacy
                    v = (dot + bit * (Q//2) + noise) % Q
                    results.append(RLWEResult(projection_id=proj_id, u=u, v=int(v)))
            entries.append(HistoryEntry(shape=shape,
                                        bits_per_element=self.bits_per_element,
                                        results=results))
        return entries

    def _access_noise_scale(self, agent_task, agent_prisms, req_task, req_prisms):
        """Zwraca skale bazowego szumu (maly, sluzy do maskowania wartosci)."""
        return 1.0

    def _effective_agent_key(self, s_agent: np.ndarray,
                              agent_task: str, req_task: str) -> np.ndarray:
        """
        Zwraca klucz uzywany do generowania v w upcall_read.

        Task match:    s_effective = s_agent          → v dekowalny przez agenta
        Task mismatch: s_effective = KDF(s_agent, ...) → v NIE dekowalny przez agenta
                       agent probuje deszyfrować s_agent, ale v bylo generowane innym kluczem
                       → diff jest losowe → ~50% bledow bitu → deszyfrowanie niepoprawne

        Mechanizm: diff = (v - dot_agent) % Q
          Przy match:    diff = (bit * Q//2 + noise) % Q          → poprawny
          Przy mismatch: diff = (dot_eff - dot_agent + bit*Q//2 + noise) % Q → losowy
        """
        if agent_task == req_task:
            return s_agent
        # Wymieszaj klucz agenta z informacja o zadaniu → inny klucz do generowania v
        mixed = kdf(s_agent.tobytes(), f"task_mismatch:{req_task}:{agent_task}")
        return (s_agent + mixed) % Q

    def terminate_agent(self, agent_uuid: str):
        if agent_uuid in self._agents:
            del self._agents[agent_uuid]
            self._terminated_agents.add(agent_uuid)

    def vacuum_decay(self):
        pass