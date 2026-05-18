"""
hss_demo.py — Holographic Secure Storage (deamon)
================================================
Minimalna implementacja Ring-LWE + HSS na potrzeby KarmazynOS.

Zawiera:
  - N, Q – parametry kraty
  - kdf() – deterministyczna funkcja wyprowadzania klucza sesyjnego
  - decrypt() – odszyfrowanie próbki Ring-LWE do bitów
  - HSSDaemon – zarządza sesjami, inodami i agentami

To jest symulacja – nie używa prawdziwej kryptografii, tylko
deterministycznego szumu i iloczynów skalarnych.
"""

import hashlib
import numpy as np

# Parametry – dopasowane do wymiaru z KarmazynOS (domyślnie dim=64)
N = 15          # wymiar wektora
Q = 256         # moduł (mały, dla demonstracji)

def kdf(seed_bytes: bytes, salt: str) -> np.ndarray:
    """
    Deterministyczna funkcja wyprowadzania klucza sesyjnego.
    Zwraca wektor liczb całkowitych modulo Q o długości N.
    """
    h = hashlib.sha256(seed_bytes + salt.encode()).digest()
    # Rozszerzamy hash do N bajtów (cyklicznie)
    extended = (h * ((N // len(h)) + 1))[:N]
    return np.frombuffer(extended, dtype=np.uint8).astype(np.int64) % Q

def measure_entropy(data: np.ndarray) -> float:
    """Pomocnicza funkcja entropii (używana w PhiSpace)."""
    _, counts = np.unique(data, return_counts=True)
    probs = counts / len(data)
    return -np.sum(probs * np.log2(probs + 1e-12))

def decrypt(s_agent: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """
    Deszyfrowanie Ring-LWE:
      bity = round( (v - <s_agent, u>) / (Q/2) ) mod 2
    Zwraca wektor bitów (int64, wartości 0 lub 1) o długości len(v).
    """
    # u i v są listami/tablicami próbek
    bits = []
    for ui, vi in zip(u, v):
        # iloczyn skalarny w Z_q
        dot = np.dot(s_agent, ui) % Q
        # różnica, skalowanie, zaokrąglenie do bitu
        diff = (vi - dot) % Q
        # Jeśli diff jest blisko 0 -> bit 0, blisko Q/2 -> bit 1
        if diff < Q//4 or diff > 3*Q//4:
            bit = 1 if diff > Q//2 else 0
        else:
            bit = 0  # szum
        bits.append(bit)
    return np.array(bits, dtype=np.int64)


class HSSDaemon:
    """
    Demon zarządzający:
      - sesjami Phi (phi_pid)
      - agentami (pid)
      - inodami (kluczami)
      - historią zapisów (do upcall_read)
    """

    def __init__(self):
        # Sesje Phi: phi_pid -> s_sess (klucz sesyjny)
        self._phi_sessions = {}
        # Agenci: pid -> (s_agent, prisms, task)
        self._agents = {}
        # Inody: nazwa -> historia (lista wektorów vec)
        self._inodes = {}
        # Śledzenie zakończonych agentów dla vacuum_decay
        self._terminated_agents = set()

    def init_phi_session(self, phi2_vec: np.ndarray, phi_pid: int) -> np.ndarray:
        """
        Inicjalizuje sesję Phi.
        Zwraca s_sess (klucz sesji) wyprowadzony z phi2_vec.
        """
        seed = phi2_vec.tobytes()
        s_sess = kdf(seed, f"phi_sess_{phi_pid}")
        self._phi_sessions[phi_pid] = s_sess
        return s_sess

    def derive_agent_key(self, pid: int, task: str,
                         prisms: list = None) -> np.ndarray:
        """
        Tworzy nowego agenta.
        s_agent = KDF(master_seed, pid, task)
        """
        # Używamy stałego master_seed z braku lepszego (w demo)
        master = b"HSS_MASTER_SEED_v1"
        s_agent = kdf(master, f"{pid}_{task}")
        self._agents[pid] = (s_agent, prisms or ["core"], task)
        return s_agent

    def phi_write(self, inode: str, vec: np.ndarray):
        """
        Zapisuje wektor pod danym inodem.
        W prawdziwym HSS byłoby to rozproszone; tutaj po prostu dodajemy do listy.
        """
        if inode not in self._inodes:
            self._inodes[inode] = []
        self._inodes[inode].append(vec.copy())

    def upcall_read(self, pid: int, inode: str, prisms: list, task: str):
        """
        Symulacja odczytu Ring-LWE.
        Zwraca listę obiektów z polami: prism_id, u, v
        lub None, jeśli agent nie ma uprawnień.
        """
        if pid not in self._agents:
            return None
        s_agent, agent_prisms, agent_task = self._agents[pid]
        # Sprawdzenie uprawnień (proste)
        if not any(p in agent_prisms for p in prisms):
            return None
        # Pobieramy historię zapisów dla inode
        history = self._inodes.get(inode, [])
        if not history:
            # Brak danych -> zwracamy puste
            return []

        # Generujemy próbki Ring-LWE dla każdego wpisu
        results = []
        for i, stored_vec in enumerate(history):
            # u – losowy wektor (tajny)
            np.random.seed(hash(f"{inode}_{i}_u") % 2**32)
            u = np.random.randint(0, Q, size=(N,), dtype=np.int64)
            # v = <s_agent, u> + szum + stored_vec_bit * (Q/2)
            dot = np.dot(s_agent, u) % Q
            # stored_vec_bit: używamy pierwszego bitu wektora jako "wiadomości"
            msg_bit = stored_vec[0] & 1
            noise = np.random.randint(-2, 3)  # mały szum
            v = (dot + msg_bit * (Q//2) + noise) % Q
            # Tworzymy obiekt (może być zwykła klasa lub namedtuple)
            class RLWEResult:
                def __init__(self, prism_id, u, v):
                    self.prism_id = prism_id
                    self.u = u
                    self.v = v
            results.append(RLWEResult(prisms[0], u, v))
        return results

    def terminate_agent(self, pid: int, inodes: list):
        """
        Usuwa agenta i czyści jego ślady (opcjonalnie).
        """
        if pid in self._agents:
            del self._agents[pid]
            self._terminated_agents.add(pid)

    def vacuum_decay(self):
        """
        Okresowe czyszczenie – w demo nie robi nic poza
        ewentualnym zmniejszeniem historii (można dodać).
        """
        pass