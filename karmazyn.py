"""
karmazyn.py — KarmazynOS Core Library v0.3.0
=============================================

Dual memory architecture:

    PhiSpace (Φ)        — pamięć robocza, termodynamiczna
    ├── atomy z temperaturą, stygną, umierają przez Vacuum Decay
    ├── kontekst sesji, rzeczy które mają prawo zniknąć
    └── HSSKarmazynMatrix (HRR, TTL, Ring-LWE)

    BubbleStore (Bąble)  — pamięć długotrwała, bez terminu śmierci
    ├── bąbel = zamknięta przestrzeń kryptograficzna
    ├── dane istnieją dopóki istnieje klucz (jawny revoke)
    └── brak decay — trwa przez całe życie sesji Φ

    Konsolidacja         — świadomy transfer Φ → Bąbel
    └── k.consolidate(label) — to co warte zapamiętania na zawsze

Dwa kanały jak w mózgu:
    hippokamp  → PhiSpace   (krótkoterminowa, zapomina)
    kora       → BubbleStore (długoterminowa, pamięta)

Użycie:
    from karmazyn import KarmazynOS

    k = KarmazynOS()
    label     = k.write("spotkanie z Jankiem")
    k.step(10)                          # stygnie w Φ...
    bubble_id = k.consolidate(label)    # → bąbel, trwa wiecznie
    results   = k.recall("spotkanie")  # szuka w obu warstwach
"""

import os
import sys
import hashlib
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from hss_karmazyn_matrix import HSSKarmazynMatrix
from hss_demo import HSSDaemon, kdf, decrypt, measure_entropy, N, Q

ALPHA        = 0.3
LAMBDA_DECAY = 0.1
DELTA_T_BASE = 5.0
VERSION      = "0.3.0"

STOPWORDS = {
    'i','w','z','na','do','ze','to','sie','nie','jest','jak','ale','po',
    'the','a','an','and','or','in','on','at','to','of','is','it','for',
}


# ─────────────────────────────────────────────────────────────────────────
# Bubble
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class Bubble:
    """
    Bąbel Mazura — pamięć bez terminu śmierci.
    T = inf. Umiera tylko przez jawny revoke().
    """
    id:           str
    label:        str
    S_struct:     np.ndarray
    S_sem:        np.ndarray
    fingerprint:  np.ndarray
    bubble_key:   bytes
    inode:        str
    epoch_born:   int
    consolidated_from: str = ""
    metadata:     Dict = field(default_factory=dict)

    def is_alive(self) -> bool:
        return bool(self.bubble_key)


# ─────────────────────────────────────────────────────────────────────────
# BubbleStore
# ─────────────────────────────────────────────────────────────────────────

class BubbleStore:
    def __init__(self, phi2_bytes: bytes):
        self._bubbles: Dict[str, Bubble] = {}
        self._label_index: Dict[str, str] = {}
        self._phi2    = phi2_bytes
        self._revoked: set = set()

    def _make_key(self, bid: str) -> bytes:
        return hashlib.sha256(self._phi2 + b"bubble:" + bid.encode()).digest()

    def store(self, label: str, S_struct: np.ndarray, S_sem: np.ndarray,
              fingerprint: np.ndarray, inode: str, epoch: int,
              consolidated_from: str = "", metadata: Dict = None) -> Bubble:
        bid = "bubble_" + hashlib.md5((label + str(epoch)).encode()).hexdigest()[:12]
        b   = Bubble(
            id=bid, label=label,
            S_struct=S_struct.copy(), S_sem=S_sem.copy(),
            fingerprint=fingerprint.copy(),
            bubble_key=self._make_key(bid),
            inode=inode, epoch_born=epoch,
            consolidated_from=consolidated_from,
            metadata=metadata or {},
        )
        self._bubbles[bid]       = b
        self._label_index[label] = bid
        return b

    def recall(self, q_sem: np.ndarray, k: int = 3) -> List[Tuple[float, Bubble]]:
        results = [
            (float(np.dot(q_sem, b.S_sem)), b)
            for bid, b in self._bubbles.items()
            if bid not in self._revoked
        ]
        results.sort(key=lambda x: x[0], reverse=True)
        return results[:k]

    def get_by_label(self, label: str) -> Optional[Bubble]:
        bid = self._label_index.get(label)
        return self._bubbles.get(bid) if bid else None

    def revoke(self, bid: str) -> bool:
        if bid in self._bubbles:
            self._bubbles[bid].bubble_key = b""
            self._revoked.add(bid)
            return True
        return False

    def revoke_by_label(self, label: str) -> bool:
        bid = self._label_index.get(label)
        return self.revoke(bid) if bid else False

    @property
    def count(self) -> int:
        return len(self._bubbles) - len(self._revoked)

    @property
    def all_active(self) -> List[Bubble]:
        return [b for bid, b in self._bubbles.items() if bid not in self._revoked]


# ─────────────────────────────────────────────────────────────────────────
# PhiSpace
# ─────────────────────────────────────────────────────────────────────────

class PhiSpace:
    def __init__(self, dim: int = 64, n_sessions: int = 1, seed: int = 42):
        self._matrix   = HSSKarmazynMatrix(dim=dim, n_sessions=n_sessions,
                                            lambd=LAMBDA_DECAY, seed=seed)
        self.dim       = dim
        self._sid      = 0
        self._t_vac    = self._measure_t_vac()
        self._phi2seed = os.urandom(32)
        self._sem:     Dict[str, np.ndarray] = {}  # label → S_sem

    def embed_structural(self, c: bytes) -> np.ndarray:
        s = int(hashlib.md5(c).hexdigest(), 16) % (2**32)
        v = np.random.default_rng(s).normal(0, 1, self.dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)

    def embed_semantic(self, c: bytes) -> np.ndarray:
        try:
            text = c.decode('utf-8', errors='ignore').lower()
        except Exception:
            return self.embed_structural(c)
        tokens  = [w for w in text.split() if len(w) > 1 and w not in STOPWORDS]
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        toks    = tokens + bigrams
        if not toks:
            return self.embed_structural(c)
        v = np.zeros(self.dim, dtype=np.float32)
        for t in toks:
            w  = min(1.0, len(t) / 6.0)
            s  = int(hashlib.md5(t.encode()).hexdigest(), 16) % (2**32)
            v += w * np.random.default_rng(s).normal(0, 1, self.dim).astype(np.float32)
        n = np.linalg.norm(v)
        return v / n if n > 1e-9 else self.embed_structural(c)

    def phi2_bytes(self) -> bytes:
        return hashlib.sha256(self._phi2seed + b"phi2-v3").digest()

    def _measure_t_vac(self) -> float:
        s = np.random.randint(0, Q, N, dtype=np.int64) % 256
        _, c = np.unique(s, return_counts=True)
        p = c / len(s)
        return float(-np.sum(p * np.log2(p + 1e-12)))

    def t_vacuum(self) -> float:
        return self._t_vac

    def add(self, content: bytes, label: str = "") -> str:
        s_str = self.embed_structural(content)
        s_sem = self.embed_semantic(content)
        lbl   = label or f"atom_{hashlib.md5(content).hexdigest()[:8]}"
        self._matrix.add_atom_vector(label=lbl, topic="karmazyn",
                                      vector=s_str, init_T=DELTA_T_BASE,
                                      session=self._sid)
        self._sem[lbl] = s_sem
        return lbl

    def recall(self, query: bytes, k: int = 3) -> List[Dict]:
        q_str = self.embed_structural(query)
        q_sem = self.embed_semantic(query)
        cands = []
        for a in self._matrix.atoms:
            if a.get('session') != self._sid:
                continue
            lbl   = a.get('label', '')
            s_sem = self._sem.get(lbl, a['S'])
            sim_s = max(0.0, float(np.dot(q_str, a['S'])))
            sim_m = max(0.0, float(np.dot(q_sem, s_sem)))
            sim   = ALPHA * sim_s + (1 - ALPHA) * sim_m
            cands.append((sim * a['T'], a))
        cands.sort(key=lambda x: x[0], reverse=True)
        top = cands[:k]
        for _, a in top:
            a['T'] = a['T'] + 0.3 * (DELTA_T_BASE - a['T'])
        return [a for _, a in top]

    def step(self) -> int:
        self._matrix.step()
        alive = {a['label'] for a in self._matrix.atoms}
        self._sem = {k: v for k, v in self._sem.items() if k in alive}
        return len(self._matrix.atoms)

    def temperature(self) -> float:
        a = self._matrix.atoms
        return float(np.mean([x['T'] for x in a])) if a else self._t_vac

    def stats(self) -> Dict:
        return {"atoms": len(self._matrix.atoms), "epoch": self._matrix.time,
                "temperature": self.temperature(), "t_vacuum": self._t_vac,
                "dim": self.dim}


# ─────────────────────────────────────────────────────────────────────────
# KarmazynOS v0.3
# ─────────────────────────────────────────────────────────────────────────

class KarmazynOS:
    """KarmazynOS v0.3.0 — dual memory (Φ + Bąble)."""

    def __init__(self, dim: int = 64, n_sessions: int = 1, seed: int = 42):
        self.phi    = PhiSpace(dim=dim, n_sessions=n_sessions, seed=seed)
        self.daemon = HSSDaemon()
        phi2_vec    = np.frombuffer(self.phi.phi2_bytes() * 4, dtype=np.float32)[:N]
        self._s     = self.daemon.init_phi_session(phi2_vec, phi_pid=0)
        self.bubbles= BubbleStore(self.phi.phi2_bytes())
        self._amap: Dict[str, str]         = {}   # label → inode (Φ)
        self._fp:   Dict[str, np.ndarray]  = {}   # label → fingerprint
        self._pid   = 100
        self._reg:  Dict[int, Tuple[str, List[str]]] = {}
        print(f"  KarmazynOS v{VERSION} — dual memory")
        print(f"  Φ (robocza, stygnie) + Bąble (trwałe, T=∞)")
        print(f"  T_vacuum = {self.phi.t_vacuum():.4f} bit")

    # ── write → Φ ────────────────────────────────────────────────────────

    def write(self, content: str) -> str:
        raw   = content.encode() if isinstance(content, str) else content
        label = self.phi.add(raw)
        bits8 = np.unpackbits(np.frombuffer(hashlib.sha256(raw).digest()[:8],
                                             dtype=np.uint8))
        vec   = np.zeros(N, dtype=np.int64)
        vec[:64] = bits8.astype(np.int64)
        inode = f"karmazyn://phi/{label}"
        self.daemon.phi_write(inode, vec)
        self._amap[label] = inode
        self._fp[label]   = bits8.astype(np.int64)
        return label

    # ── consolidate: Φ → Bąbel ───────────────────────────────────────────

    def consolidate(self, label: str, metadata: Dict = None) -> Optional[str]:
        """
        Konsolidacja: atom z Φ → bąbel (pamięć długotrwała).
        Bąbel nie stygnie. Trwa do jawnego revoke().
        Atom Φ nadal istnieje i nadal stygnie — są niezależne.
        """
        if label not in self._amap:
            return None

        phi_atom = next((a for a in self.phi._matrix.atoms
                         if a.get('label') == label), None)
        s_str = phi_atom['S'].copy() if phi_atom else self.phi.embed_structural(label.encode())
        s_sem = self.phi._sem.get(label, self.phi.embed_semantic(label.encode()))
        fp    = self._fp.get(label, np.zeros(8, dtype=np.int64))

        b_inode = f"karmazyn://bubbles/{label}"
        vec = np.zeros(N, dtype=np.int64)
        vec[:len(fp)] = fp
        self.daemon.phi_write(b_inode, vec)

        bubble = self.bubbles.store(
            label=label, S_struct=s_str, S_sem=s_sem,
            fingerprint=fp, inode=b_inode,
            epoch=self.phi._matrix.time,
            consolidated_from=label, metadata=metadata or {},
        )
        print(f"  [KONSOLIDACJA] '{label}' → {bubble.id} | T=∞")
        return bubble.id

    # ── recall: Φ + Bąble ────────────────────────────────────────────────

    def recall(self, query: str, k: int = 5) -> List[Dict]:
        """
        Recall z obu warstw.
        Φ: score = sim × T  (gorące atomy wygrywają)
        Bąble: score = sim  (brak T — równe traktowanie)
        """
        raw   = query.encode() if isinstance(query, str) else query
        q_sem = self.phi.embed_semantic(raw)

        k_phi = max(1, int(k * 0.6))
        k_bub = max(1, k - k_phi)

        phi_atoms = self.phi.recall(raw, k=k_phi)
        phi_res   = []
        for a in phi_atoms:
            lbl   = a.get('label', '')
            s_sem = self.phi._sem.get(lbl, a['S'])
            phi_res.append({
                'label': lbl, 'layer': 'phi',
                'T': a['T'], 'sim': float(np.dot(q_sem, s_sem)),
                'inode': self._amap.get(lbl, ''), 'bubble_id': None,
            })

        bub_hits = self.bubbles.recall(q_sem, k=k_bub)
        bub_res  = [{'label': b.label, 'layer': 'bubble',
                     'T': float('inf'), 'sim': sim,
                     'inode': b.inode, 'bubble_id': b.id}
                    for sim, b in bub_hits]

        all_res = phi_res + bub_res
        all_res.sort(key=lambda x: x['sim'], reverse=True)
        return all_res[:k]

    # ── evaluate ─────────────────────────────────────────────────────────

    def evaluate(self, context: str) -> Tuple[bool, float, str]:
        raw   = context.encode()
        q_sem = self.phi.embed_semantic(raw)

        phi_a = self.phi._matrix.atoms
        s_phi = (sum(max(0.0, float(np.dot(q_sem,
                     self.phi._sem.get(a['label'], a['S'])))) * a['T']
                     for a in phi_a) / len(phi_a)) if phi_a else 0.0

        bubs  = self.bubbles.all_active
        s_bub = (sum(max(0.0, float(np.dot(q_sem, b.S_sem)))
                     for b in bubs) / len(bubs)) if bubs else 0.0

        score = 0.6 * s_phi + 0.4 * s_bub
        theta = 0.3
        allow = score > theta
        reason = (f"score={score:.3f} [φ={s_phi:.3f} b={s_bub:.3f}]"
                  f" {'>' if allow else '≤'} θ={theta:.3f}"
                  f" → {'ZEZWÓL' if allow else 'ODMÓW'}")
        return allow, score, reason

    # ── agenty ───────────────────────────────────────────────────────────

    def derive_agent(self, name: str, task: str,
                     prisms: List[str] = ["core","in","out"]) -> Tuple[int, np.ndarray]:
        self._pid += 1
        pid = self._pid
        s   = self.daemon.derive_agent_key(pid, task, prisms)
        self._reg[pid] = (task, prisms)
        return pid, s

    def read_as_agent(self, label: str, pid: int, s_agent: np.ndarray,
                      from_bubble: bool = False) -> Dict:
        if from_bubble:
            b = self.bubbles.get_by_label(label)
            if b is None:
                return {'error': f'bąbel {label!r} nieznany'}
            inode, fp = b.inode, b.fingerprint
        else:
            inode = self._amap.get(label)
            if not inode:
                return {'error': f'atom {label!r} nieznany'}
            fp = self._fp.get(label)

        reg = self._reg.get(pid)
        if reg is None:
            return {'error': f'PID {pid} nieznany'}
        task, prisms = reg

        res = self.daemon.upcall_read(pid, inode, prisms, task)
        if res is None:
            return {'error': 'ODMOWA — brak klucza'}

        out = {}
        for p in res:
            bits    = decrypt(s_agent, p.u, p.v)
            hamming = int(np.sum(bits[:8] != fp[:8])) if fp is not None else 4
            sig     = hamming <= 3
            out[p.prism_id] = {'signal': sig, 'bits': bits[:8].tolist(),
                                'status': f'{"✓ SYGNAŁ" if sig else "✗ SZUM"} (h={hamming})'}
        return out

    # ── lifecycle ─────────────────────────────────────────────────────────

    def step(self, n: int = 1) -> Dict:
        """Krok Φ. Bąble niezmienione."""
        for _ in range(n):
            self.phi.step()
        return self.stats()

    def terminate_agent(self, pid: int, labels: List[str] = []):
        inodes = [self._amap[l] for l in labels if l in self._amap]
        self.daemon.terminate_agent(pid, inodes)
        self.daemon.vacuum_decay()

    def revoke_bubble(self, label: str) -> bool:
        """Jawne usunięcie bąbla — jedyna droga jego śmierci."""
        ok = self.bubbles.revoke_by_label(label)
        if ok:
            print(f"  [REVOKE] '{label}' → skasowany (jawna decyzja)")
        return ok

    def stats(self) -> Dict:
        s = self.phi.stats()
        return {**s, "version": VERSION,
                "atoms_phi": s["atoms"], "bubbles": self.bubbles.count}

    def __repr__(self) -> str:
        s = self.stats()
        return (f"KarmazynOS(v{VERSION} | "
                f"φ={s['atoms_phi']} T={s['temperature']:.2f} | "
                f"bubbles={s['bubbles']} T=∞ | epoch={s['epoch']})")
