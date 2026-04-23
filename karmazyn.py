"""
karmazyn.py — KarmazynOS Core Library v0.5.0
=============================================

Zmiany względem v0.4:

  [1] Wzmocniony fingerprint – 256 bitów (HMAC-SHA256 z bubble_key)
      Próg Hamminga adaptacyjny (domyślnie ≤ 10 błędów na 256 bitów).

  [2] Markery rozpadu (decay markers) dla bąbli:
      - decay_start_epoch, decay_rate
      - liveliness() wpływa na score w recall
      - mark_for_decay(label, rate), refresh_bubble(label)

  [3] Garbage collection dla revoked bąbli:
      - cleanup_revoked() – fizyczne usunięcie z BubbleStore

  [4] Ulepszone statystyki: bubbles_active, bubbles_decaying, bubbles_revoked

  [5] Poprawki w consolidate() – jawna kopia wektorów semantycznych
"""

import os
import sys
import hashlib
import hmac
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from collections import Counter

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from hss_karmazyn_matrix import HSSKarmazynMatrix
from hss_demo import HSSDaemon, kdf, decrypt, measure_entropy, N, Q

VERSION      = "0.5.0"
ALPHA        = 0.3
LAMBDA_DECAY = 0.1
DELTA_T_BASE = 5.0
BUBBLE_BIAS  = 1.5
STOPWORDS = {
    'i','w','z','na','do','ze','to','sie','nie','jest','jak','ale','po',
    'the','a','an','and','or','in','on','at','to','of','is','it','for',
    'ze','co','byc','tak','ten','ta','te','ich','jej','jego','tym','przez',
}


# ─────────────────────────────────────────────────────────────────────────
# Payload crypto (XOR stream z SHA256-DRBG)
# ─────────────────────────────────────────────────────────────────────────

def _xor_crypt(data: bytes, key: bytes) -> bytes:
    out, offset, counter = bytearray(len(data)), 0, 0
    while offset < len(data):
        block = hashlib.sha256(key + counter.to_bytes(4, 'big')).digest()
        for b in block:
            if offset >= len(data):
                break
            out[offset] = data[offset] ^ b
            offset += 1
        counter += 1
    return bytes(out)


def _compute_fingerprint(content: bytes, key: bytes, label: str) -> bytes:
    """HMAC-SHA256(key, label.encode() + content) -> 32 bajty."""
    return hmac.new(key, label.encode() + content, hashlib.sha256).digest()


def _hamming_distance(a: bytes, b: bytes) -> int:
    """Odległość Hamminga między dwoma ciągami bajtów."""
    xor = bytes(x ^ y for x, y in zip(a, b))
    return sum(bin(byte).count('1') for byte in xor)


# ─────────────────────────────────────────────────────────────────────────
# Bubble (pamięć trwała z markerami rozpadu)
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class Bubble:
    id:                str
    label:             str
    S_struct:          np.ndarray
    S_sem:             np.ndarray
    fingerprint:       bytes                     # teraz 32 bajty
    bubble_key:        bytes
    encrypted_content: bytes
    inode:             str
    epoch_born:        int
    recall_count:      int  = 0
    consolidated_from: str  = ""
    metadata:          Dict = field(default_factory=dict)

    # Nowe pola – markery rozpadu
    decay_start_epoch: Optional[int] = None
    decay_rate:        float = 0.0   # np. 0.01 → 1% utraty żywotności na epokę

    def is_alive(self) -> bool:
        return bool(self.bubble_key)

    def liveliness(self, current_epoch: int) -> float:
        """Zwraca współczynnik żywotności ∈ [0,1]."""
        if self.decay_start_epoch is None or self.decay_rate <= 0:
            return 1.0
        elapsed = max(0, current_epoch - self.decay_start_epoch)
        return max(0.0, 1.0 - elapsed * self.decay_rate)

    def decrypt_content(self) -> bytes:
        key = self.bubble_key if self.bubble_key else b"revoked_warp_oblivion"
        return _xor_crypt(self.encrypted_content, key)


# ─────────────────────────────────────────────────────────────────────────
# BubbleStore
# ─────────────────────────────────────────────────────────────────────────

class BubbleStore:
    def __init__(self, phi2_bytes: bytes, s_sess: np.ndarray):
        self._b:    Dict[str, Bubble] = {}
        self._idx:  Dict[str, str]    = {}   # label → id
        self._phi2  = phi2_bytes
        self._s     = s_sess
        self._rev:  set = set()

    def _make_key(self, bid: str) -> bytes:
        return hashlib.sha256(self._phi2 + b"bubble:" + bid.encode()).digest()

    def bubble_s_agent(self, bubble: Bubble) -> np.ndarray:
        hex_key = bubble.bubble_key.hex() if bubble.bubble_key else "revoked"
        return kdf(self._s.tobytes(), f"bubble:{hex_key}")

    def store(self, label: str, S_struct: np.ndarray, S_sem: np.ndarray,
              content_raw: bytes,
              inode: str, epoch: int,
              consolidated_from: str = "", metadata: Dict = None) -> Bubble:
        bid = "bubble_" + hashlib.md5((label + str(epoch)).encode()).hexdigest()[:12]
        key = self._make_key(bid)

        # Nowy fingerprint: HMAC-SHA256(key, label+content)
        fp = _compute_fingerprint(content_raw, key, label)

        b = Bubble(
            id=bid, label=label,
            S_struct=S_struct.copy(), S_sem=S_sem.copy(),
            fingerprint=fp,
            bubble_key=key,
            encrypted_content=_xor_crypt(content_raw, key),
            inode=inode, epoch_born=epoch,
            consolidated_from=consolidated_from,
            metadata=metadata or {},
        )
        self._b[bid]   = b
        self._idx[label] = bid
        return b

    def recall(self, q_sem: np.ndarray, current_epoch: int,
               k: int = 3) -> List[Tuple[float, Bubble]]:
        res = []
        for bid, b in self._b.items():
            if bid in self._rev:
                continue
            if not b.is_alive():
                continue
            sim = float(np.dot(q_sem, b.S_sem))
            liv = b.liveliness(current_epoch)
            if liv <= 0.0:
                continue
            score = sim * BUBBLE_BIAS * liv
            res.append((score, b))
        res.sort(key=lambda x: x[0], reverse=True)
        for _, b in res[:k]:
            b.recall_count += 1
        return res[:k]

    def get_by_label(self, label: str) -> Optional[Bubble]:
        bid = self._idx.get(label)
        return self._b.get(bid) if bid else None

    def revoke(self, bid: str) -> bool:
        if bid in self._b:
            self._b[bid].bubble_key = b""
            self._rev.add(bid)
            return True
        return False

    def revoke_by_label(self, label: str) -> bool:
        bid = self._idx.get(label)
        return self.revoke(bid) if bid else False

    def cleanup_revoked(self) -> int:
        """Fizycznie usuwa wszystkie revoked bąble z pamięci."""
        removed = 0
        for bid in list(self._rev):
            b = self._b.pop(bid, None)
            if b:
                # Usuń też z indeksu label→id, jeśli wciąż wskazuje na ten sam bid
                if self._idx.get(b.label) == bid:
                    del self._idx[b.label]
                removed += 1
        self._rev.clear()
        return removed

    def mark_for_decay(self, label: str, start_epoch: int, rate: float) -> bool:
        b = self.get_by_label(label)
        if b is None:
            return False
        b.decay_start_epoch = start_epoch
        b.decay_rate = rate
        return True

    def refresh_bubble(self, label: str) -> bool:
        """Resetuje marker rozpadu – bąbel odzyskuje pełną żywotność."""
        b = self.get_by_label(label)
        if b is None:
            return False
        b.decay_start_epoch = None
        b.decay_rate = 0.0
        return True

    @property
    def count(self) -> int:
        return len(self._b) - len(self._rev)

    @property
    def count_decaying(self) -> int:
        return sum(1 for b in self._b.values()
                   if b.decay_start_epoch is not None and b.id not in self._rev)

    @property
    def all_active(self) -> List[Bubble]:
        return [b for bid, b in self._b.items() if bid not in self._rev]


# ─────────────────────────────────────────────────────────────────────────
# IDF (bez zmian)
# ─────────────────────────────────────────────────────────────────────────

class IDFCounter:
    def __init__(self):
        self._freq:  Counter = Counter()
        self._ndocs: int     = 0

    def add_doc(self, tokens: List[str]):
        self._ndocs += 1
        for t in set(tokens):
            self._freq[t] += 1

    def idf(self, token: str) -> float:
        return float(np.log1p(self._ndocs / (1 + self._freq.get(token, 0))))


# ─────────────────────────────────────────────────────────────────────────
# PhiSpace (bez większych zmian)
# ─────────────────────────────────────────────────────────────────────────

class PhiSpace:
    def __init__(self, dim: int = 64, n_sessions: int = 1, seed: int = 42):
        self._mx  = HSSKarmazynMatrix(dim=dim, n_sessions=n_sessions,
                                       lambd=LAMBDA_DECAY, seed=seed)
        self.dim  = dim
        self._sid = 0
        self._tvac = self._measure_tvac()
        self._p2s  = os.urandom(32)
        self._sem:  Dict[str, np.ndarray] = {}
        self._rc:   Dict[str, int]        = {}
        self._idf   = IDFCounter()

    def embed_structural(self, c: bytes) -> np.ndarray:
        s = int(hashlib.md5(c).hexdigest(), 16) % (2**32)
        v = np.random.default_rng(s).normal(0, 1, self.dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)

    def embed_semantic(self, c: bytes, update: bool = False) -> np.ndarray:
        try:
            text = c.decode('utf-8', errors='ignore').lower()
        except Exception:
            return self.embed_structural(c)
        tokens  = [w for w in text.split() if len(w) > 1 and w not in STOPWORDS]
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        all_t   = tokens + bigrams
        if not all_t:
            return self.embed_structural(c)
        if update:
            self._idf.add_doc(tokens)
        v = np.zeros(self.dim, dtype=np.float32)
        for t in all_t:
            w = self._idf.idf(t) * min(1.0, len(t) / 5.0)
            s = int(hashlib.md5(t.encode()).hexdigest(), 16) % (2**32)
            v += w * np.random.default_rng(s).normal(0, 1, self.dim).astype(np.float32)
        n = np.linalg.norm(v)
        return v / n if n > 1e-9 else self.embed_structural(c)

    def phi2_bytes(self) -> bytes:
        return hashlib.sha256(self._p2s + b"phi2-v5").digest()

    def _measure_tvac(self) -> float:
        s = np.random.randint(0, Q, N, dtype=np.int64) % 256
        _, c = np.unique(s, return_counts=True)
        p = c / len(s)
        return float(-np.sum(p * np.log2(p + 1e-12)))

    def t_vacuum(self) -> float:
        return self._tvac

    def add(self, content: bytes, label: str = "") -> str:
        s_str = self.embed_structural(content)
        s_sem = self.embed_semantic(content, update=True)
        lbl   = label or f"atom_{hashlib.md5(content).hexdigest()[:8]}"
        self._mx.add_atom_vector(label=lbl, topic="karmazyn",
                                  vector=s_str, init_T=DELTA_T_BASE,
                                  session=self._sid)
        self._sem[lbl] = s_sem.copy()
        self._rc[lbl]  = 0
        return lbl

    def recall(self, query: bytes, k: int = 3) -> List[Tuple[Dict, float]]:
        q_str = self.embed_structural(query)
        q_sem = self.embed_semantic(query)
        cands = []
        for a in self._mx.atoms:
            if a.get('session') != self._sid:
                continue
            lbl   = a.get('label', '')
            s_sem = self._sem.get(lbl, a['S'])
            sim_s = max(0.0, float(np.dot(q_str, a['S'])))
            sim_m = max(0.0, float(np.dot(q_sem, s_sem)))
            sim   = ALPHA * sim_s + (1 - ALPHA) * sim_m
            cands.append((sim * a['T'], a, sim))
        cands.sort(key=lambda x: x[0], reverse=True)
        result = []
        for _, a, sim in cands[:k]:
            a['T'] = a['T'] + 0.3 * (DELTA_T_BASE - a['T'])
            lbl = a.get('label', '')
            self._rc[lbl] = self._rc.get(lbl, 0) + 1
            result.append((a, sim))
        return result

    def recall_count(self, label: str) -> int:
        return self._rc.get(label, 0)

    def step(self) -> int:
        self._mx.step()
        alive      = {a['label'] for a in self._mx.atoms}
        self._sem  = {k: v for k, v in self._sem.items() if k in alive}
        self._rc   = {k: v for k, v in self._rc.items() if k in alive}
        return len(self._mx.atoms)

    def temperature(self) -> float:
        a = self._mx.atoms
        return float(np.mean([x['T'] for x in a])) if a else self._tvac

    def stats(self) -> Dict:
        return {"atoms": len(self._mx.atoms), "epoch": self._mx.time,
                "temperature": self.temperature(), "t_vacuum": self._tvac,
                "dim": self.dim}


# ─────────────────────────────────────────────────────────────────────────
# KarmazynOS v0.5.0
# ─────────────────────────────────────────────────────────────────────────

class KarmazynOS:
    """KarmazynOS v0.5.0 – trwała pamięć z markerami rozpadu."""

    def __init__(self, dim: int = 64, n_sessions: int = 1, seed: int = 42):
        self.phi    = PhiSpace(dim=dim, n_sessions=n_sessions, seed=seed)
        self.daemon = HSSDaemon()
        phi2_vec    = np.frombuffer(self.phi.phi2_bytes() * 4,
                                     dtype=np.float32)[:N]
        self._s_sess = self.daemon.init_phi_session(phi2_vec, phi_pid=0)
        self.bubbles = BubbleStore(self.phi.phi2_bytes(), self._s_sess)
        self._amap:  Dict[str, str]             = {}
        self._fp:    Dict[str, bytes]           = {}   # teraz bytes (32 bajty)
        self._raw:   Dict[str, bytes]           = {}
        self._ac:    Dict[str, int]             = {}
        self._pid    = 100
        self._reg:   Dict[int, Tuple[str, List[str]]] = {}
        print(f"  KarmazynOS v{VERSION}")
        print(f"  Φ (stygnie) + Bąble (T=∞, payload, crypto-liveness, decay markers)")
        print(f"  T_vacuum = {self.phi.t_vacuum():.4f} bit")

    # ── write ─────────────────────────────────────────────────────────────

    def write(self, content: str, auto_consolidate: int = 0) -> str:
        raw   = content.encode() if isinstance(content, str) else content
        label = self.phi.add(raw)
        bits8 = np.unpackbits(np.frombuffer(
            hashlib.sha256(raw).digest()[:8], dtype=np.uint8))
        vec   = np.zeros(N, dtype=np.int64)
        vec[:64] = bits8.astype(np.int64)
        inode = f"karmazyn://phi/{label}"
        self.daemon.phi_write(inode, vec)
        self._amap[label] = inode
        # przechowujemy pełny 32-bajtowy fingerprint (na wszelki wypadek)
        self._fp[label]   = hashlib.sha256(raw).digest()
        self._raw[label]  = raw
        self._ac[label]   = auto_consolidate
        return label

    # ── consolidate ───────────────────────────────────────────────────────

    def consolidate(self, label: str, metadata: Dict = None) -> Optional[str]:
        if label not in self._amap:
            return None
        raw     = self._raw.get(label, label.encode())
        phi_a   = next((a for a in self.phi._mx.atoms
                        if a.get('label') == label), None)
        s_str   = phi_a['S'].copy() if phi_a else self.phi.embed_structural(raw)
        s_sem   = self.phi._sem.get(label, self.phi.embed_semantic(raw)).copy()
        b_inode = f"karmazyn://bubbles/{label}"
        vec     = np.zeros(N, dtype=np.int64)
        # wektor dla daemona – tylko do zachowania kompatybilności
        self.daemon.phi_write(b_inode, vec)
        bubble = self.bubbles.store(
            label=label, S_struct=s_str, S_sem=s_sem,
            content_raw=raw,
            inode=b_inode, epoch=self.phi._mx.time,
            consolidated_from=label, metadata=metadata or {})
        print(f"  [KONSOLIDACJA] '{label[:30]}' → {bubble.id} | T=∞")
        return bubble.id

    def _auto_check(self, label: str):
        thresh = self._ac.get(label, 0)
        if thresh > 0 and self.phi.recall_count(label) >= thresh:
            if self.bubbles.get_by_label(label) is None:
                print(f"  [AUTO] '{label[:25]}' recall≥{thresh} → consolidate")
                self.consolidate(label)

    # ── recall ─────────────────────────────────────────────────────────────

    def recall(self, query: str, k: int = 5) -> List[Dict]:
        raw   = query.encode() if isinstance(query, str) else query
        q_sem = self.phi.embed_semantic(raw)
        k_phi = max(1, int(k * 0.6))
        k_bub = max(1, k - k_phi)

        phi_res = []
        for atom, sim in self.phi.recall(raw, k=k_phi):
            lbl   = atom.get('label', '')
            s_sem = self.phi._sem.get(lbl, atom['S'])
            sim_f = max(0.0, float(np.dot(q_sem, s_sem)))
            phi_res.append({'label': lbl, 'layer': 'phi',
                             'T': atom['T'], 'sim': sim_f,
                             'score': sim_f * atom['T'],
                             'inode': self._amap.get(lbl, ''),
                             'bubble_id': None})
            self._auto_check(lbl)

        bub_res = []
        current_epoch = self.phi._mx.time
        for score, b in self.bubbles.recall(q_sem, current_epoch, k=k_bub):
            bub_res.append({'label': b.label, 'layer': 'bubble',
                             'T': float('inf'), 'sim': score / (BUBBLE_BIAS * b.liveliness(current_epoch)),
                             'score': score,
                             'inode': b.inode, 'bubble_id': b.id,
                             'liveliness': b.liveliness(current_epoch)})

        all_res = phi_res + bub_res
        all_res.sort(key=lambda x: x['score'], reverse=True)
        return all_res[:k]

    # ── read_bubble ───────────────────────────────────────────────────────

    def read_bubble(self, label: str) -> Optional[str]:
        b = self.bubbles.get_by_label(label)
        if b is None:
            return None
        raw = b.decrypt_content()
        try:
            return raw.decode('utf-8', errors='replace')
        except Exception:
            return raw.hex()

    # ── evaluate ──────────────────────────────────────────────────────────

    def evaluate(self, context: str) -> Tuple[bool, float, str]:
        raw   = context.encode()
        q_sem = self.phi.embed_semantic(raw)
        phi_a = self.phi._mx.atoms
        bubs  = self.bubbles.all_active
        all_s = []

        s_phi = 0.0
        if phi_a:
            sims  = [max(0.0, float(np.dot(q_sem,
                         self.phi._sem.get(a['label'], a['S']))))
                     for a in phi_a]
            all_s.extend(sims)
            s_phi = sum(s * a['T'] for s, a in zip(sims, phi_a)) / len(phi_a)

        s_bub = 0.0
        if bubs:
            simsb = [max(0.0, float(np.dot(q_sem, b.S_sem))) for b in bubs]
            all_s.extend(simsb)
            s_bub = sum(simsb) / len(bubs)

        score = 0.6 * s_phi + 0.4 * s_bub
        theta = max(float(np.percentile(all_s, 60)), 0.1) if all_s else 0.3
        allow = score > theta
        reason = (f"score={score:.3f} [φ={s_phi:.3f} b={s_bub:.3f}]"
                  f" {'>' if allow else '≤'} θ={theta:.3f}(p60)"
                  f" → {'ZEZWÓL' if allow else 'ODMÓW'}")
        return allow, score, reason

    # ── agenty ────────────────────────────────────────────────────────────

    def derive_agent(self, name: str, task: str,
                     prisms: List[str] = ["core","in","out"]) -> Tuple[int, np.ndarray]:
        self._pid += 1
        s = self.daemon.derive_agent_key(self._pid, task, prisms)
        self._reg[self._pid] = (task, prisms)
        return self._pid, s

    def read_as_agent(self, label: str, pid: int, s_agent: np.ndarray,
                      from_bubble: bool = False) -> Dict:
        if from_bubble:
            b = self.bubbles.get_by_label(label)
            if b is None:
                return {'error': f'bąbel {label!r} nieznany'}
            inode, fp = b.inode, b.fingerprint
            s_eff     = self.bubbles.bubble_s_agent(b)
        else:
            inode = self._amap.get(label)
            if not inode:
                return {'error': f'atom {label!r} nieznany'}
            fp, s_eff = self._fp.get(label), s_agent

        reg = self._reg.get(pid)
        if reg is None:
            return {'error': f'PID {pid} nieznany'}
        task, prisms = reg

        res = self.daemon.upcall_read(pid, inode, prisms, task)
        if res is None:
            return {'error': 'ODMOWA'}

        out = {}
        for p in res:
            bits    = decrypt(s_eff, p.u, p.v)
            if fp is not None and len(bits) >= len(fp)*8:
                # konwersja bitów do bajtów
                read_bytes = np.packbits(bits[:len(fp)*8]).tobytes()
                hamming = _hamming_distance(fp, read_bytes)
                sig = hamming <= 10  # próg dla 256 bitów
                out[p.prism_id] = {
                    'signal': sig, 'bits': bits[:8].tolist(),
                    'status': f'{"✓ SYGNAŁ" if sig else "✗ SZUM"} (h={hamming})'}
            else:
                out[p.prism_id] = {
                    'signal': False, 'bits': bits[:8].tolist(),
                    'status': '✗ SZUM (brak fingerprintu)'}
        return out

    # ── zarządzanie rozpadami ─────────────────────────────────────────────

    def mark_bubble_for_decay(self, label: str, rate: float = 0.01) -> bool:
        """Rozpoczyna proces rozpadu bąbla od bieżącej epoki."""
        return self.bubbles.mark_for_decay(label, self.phi._mx.time, rate)

    def refresh_bubble(self, label: str) -> bool:
        """Resetuje marker rozpadu – bąbel odzyskuje pełną żywotność."""
        return self.bubbles.refresh_bubble(label)

    def cleanup_revoked(self) -> int:
        """Usuwa fizycznie wszystkie unieważnione bąble."""
        return self.bubbles.cleanup_revoked()

    # ── lifecycle ─────────────────────────────────────────────────────────

    def step(self, n: int = 1) -> Dict:
        for _ in range(n):
            self.phi.step()
        return self.stats()

    def terminate_agent(self, pid: int, labels: List[str] = []):
        inodes = [self._amap[l] for l in labels if l in self._amap]
        self.daemon.terminate_agent(pid, inodes)
        self.daemon.vacuum_decay()

    def revoke_bubble(self, label: str) -> bool:
        ok = self.bubbles.revoke_by_label(label)
        if ok:
            print(f"  [REVOKE] '{label}' → bubble_key='' | Warp Oblivion")
        return ok

    def stats(self) -> Dict:
        s = self.phi.stats()
        return {**s, "version": VERSION,
                "atoms_phi": s["atoms"],
                "bubbles": self.bubbles.count,
                "bubbles_decaying": self.bubbles.count_decaying,
                "bubbles_revoked": len(self.bubbles._rev)}

    def __repr__(self) -> str:
        s = self.stats()
        return (f"KarmazynOS(v{VERSION} | "
                f"φ={s['atoms_phi']} T={s['temperature']:.2f} | "
                f"bubbles={s['bubbles']} (decay={s['bubbles_decaying']}) T=∞ | epoch={s['epoch']})")