"""
karmazyn.py — Thermodynamic Memory Kernel (KarmazynOS) v0.9.0
===============================================================

Trójwarstwowy system pamięci:
  Φ (plazma)      – pamięć robocza, konkurencja, temperatura
  Bąbel (ciało)   – pamięć trwała jednostkowa, wykładniczy decay
  Hologram (pole) – generatywna idea (PCA + stochastyka)

Zmiany v0.9.0:
  [1] Hologramy jako generatory idei (prototyp + kierunki PCA).
  [2] recall_from_hologram() – projekcja + szum kierunkowy.
  [3] Usunięto VSA binding/unbinding.
  [4] Nowa metoda: generate_from_idea() – tworzy nowe atomy Φ.
"""

import os
import sys
import hashlib
import hmac
import math
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from collections import Counter

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from hss_karmazyn_matrix import HSSKarmazynMatrix
from hss_demo import HSSDaemon, kdf, decrypt, measure_entropy, N, Q

VERSION      = "0.9.0"
ALPHA        = 0.3
LAMBDA_DECAY = 0.1
DELTA_T_BASE = 5.0
STOPWORDS = {
    'i','w','z','na','do','ze','to','sie','nie','jest','jak','ale','po',
    'the','a','an','and','or','in','on','at','to','of','is','it','for',
    'ze','co','byc','tak','ten','ta','te','ich','jej','jego','tym','przez',
}

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
    return hmac.new(key, label.encode() + content, hashlib.sha256).digest()

def _hamming_distance(a: bytes, b: bytes) -> int:
    xor = bytes(x ^ y for x, y in zip(a, b))
    return sum(bin(byte).count('1') for byte in xor)

# -------------------------------------------------------------------------
# Bubble
# -------------------------------------------------------------------------
@dataclass
class Bubble:
    id:                str
    label:             str
    S_struct:          np.ndarray
    S_sem:             np.ndarray
    fingerprint:       bytes
    bubble_key:        bytes
    encrypted_content: bytes
    inode:             str
    epoch_born:        int
    recall_count:      int  = 0
    consolidated_from: str  = ""
    metadata:          Dict = field(default_factory=dict)

    decay_start_epoch: Optional[int] = None
    decay_rate:        float = 0.0

    def is_alive(self) -> bool:
        return bool(self.bubble_key)

    def liveliness(self, current_epoch: int) -> float:
        if self.decay_start_epoch is None or self.decay_rate <= 0:
            return 1.0
        elapsed = max(0, current_epoch - self.decay_start_epoch)
        return math.exp(-self.decay_rate * elapsed)

    def decrypt_content(self) -> bytes:
        key = self.bubble_key if self.bubble_key else b"revoked_warp_oblivion"
        return _xor_crypt(self.encrypted_content, key)


class BubbleStore:
    def __init__(self, phi2_bytes: bytes, s_sess: np.ndarray):
        self._b:    Dict[str, Bubble] = {}
        self._idx:  Dict[str, str]    = {}
        self._phi2  = phi2_bytes
        self._s     = s_sess
        self._rev:  set = set()

    def _make_key(self, bid: str) -> bytes:
        return hashlib.sha256(self._phi2 + b"bubble:" + bid.encode()).digest()

    def bubble_s_agent(self, bubble: Bubble) -> np.ndarray:
        hex_key = bubble.bubble_key.hex() if bubble.bubble_key else "revoked"
        return kdf(self._s.tobytes(), f"bubble:{hex_key}")

    def store(self, label: str, S_struct: np.ndarray, S_sem: np.ndarray,
              content_raw: bytes, inode: str, epoch: int,
              consolidated_from: str = "", metadata: Dict = None) -> Bubble:
        bid = "bubble_" + hashlib.md5((label + str(epoch)).encode()).hexdigest()[:12]
        key = self._make_key(bid)
        fp = _compute_fingerprint(content_raw, key, label)
        b = Bubble(id=bid, label=label, S_struct=S_struct.copy(), S_sem=S_sem.copy(),
                   fingerprint=fp, bubble_key=key,
                   encrypted_content=_xor_crypt(content_raw, key),
                   inode=inode, epoch_born=epoch, consolidated_from=consolidated_from,
                   metadata=metadata or {})
        self._b[bid] = b
        self._idx[label] = bid
        return b

    def recall(self, q_sem: np.ndarray, current_epoch: int, k: int = 3, bias: float = 1.5):
        res = []
        for bid, b in self._b.items():
            if bid in self._rev or not b.is_alive(): continue
            liv = b.liveliness(current_epoch)
            if liv <= 1e-9: continue
            sim = float(np.dot(q_sem, b.S_sem))
            score = sim * bias * liv
            res.append((score, b))
        res.sort(key=lambda x: x[0], reverse=True)
        for _, b in res[:k]:
            b.recall_count += 1
            if b.decay_start_epoch is not None:
                elapsed = current_epoch - b.decay_start_epoch
                effective_elapsed = elapsed * 0.7
                b.decay_start_epoch = current_epoch - effective_elapsed
        return res[:k]

    def get_by_label(self, label: str) -> Optional[Bubble]:
        bid = self._idx.get(label)
        return self._b.get(bid) if bid else None

    def revoke_by_label(self, label: str) -> bool:
        bid = self._idx.get(label)
        if bid in self._b:
            self._b[bid].bubble_key = b""
            self._rev.add(bid)
            return True
        return False

    def cleanup_revoked(self) -> int:
        removed = 0
        for bid in list(self._rev):
            b = self._b.pop(bid, None)
            if b:
                if self._idx.get(b.label) == bid: del self._idx[b.label]
                removed += 1
        self._rev.clear()
        return removed

    def mark_for_decay(self, label: str, start_epoch: int, rate: float) -> bool:
        b = self.get_by_label(label)
        if not b: return False
        b.decay_start_epoch = start_epoch
        b.decay_rate = rate
        return True

    def refresh_bubble(self, label: str) -> bool:
        b = self.get_by_label(label)
        if not b: return False
        b.decay_start_epoch = None
        b.decay_rate = 0.0
        return True

    def remove_bubble(self, label: str) -> bool:
        bid = self._idx.get(label)
        if bid and bid in self._b:
            del self._b[bid]
            del self._idx[label]
            if bid in self._rev: self._rev.remove(bid)
            return True
        return False

    @property
    def count(self) -> int: return len(self._b) - len(self._rev)
    @property
    def count_decaying(self) -> int:
        return sum(1 for b in self._b.values()
                   if b.decay_start_epoch is not None and b.id not in self._rev)
    @property
    def all_active(self) -> List[Bubble]:
        return [b for bid, b in self._b.items() if bid not in self._rev]

# -------------------------------------------------------------------------
# IDF
# -------------------------------------------------------------------------
class IDFCounter:
    def __init__(self):
        self._freq = Counter()
        self._ndocs = 0
    def add_doc(self, tokens: List[str]):
        self._ndocs += 1
        for t in set(tokens): self._freq[t] += 1
    def idf(self, token: str) -> float:
        return float(np.log1p(self._ndocs / (1 + self._freq.get(token, 0))))

# -------------------------------------------------------------------------
# PhiSpace
# -------------------------------------------------------------------------
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
        return hashlib.sha256(self._p2s + b"phi2-v9").digest()

    def _measure_tvac(self) -> float:
        s = np.random.randint(0, Q, N, dtype=np.int64) % 256
        _, c = np.unique(s, return_counts=True)
        p = c / len(s)
        return float(-np.sum(p * np.log2(p + 1e-12)))

    def t_vacuum(self) -> float: return self._tvac

    def add(self, content: bytes, label: str = "", init_T: float = DELTA_T_BASE) -> str:
        s_str = self.embed_structural(content)
        s_sem = self.embed_semantic(content, update=True)
        lbl   = label or f"atom_{hashlib.md5(content).hexdigest()[:8]}"
        self._mx.add_atom_vector(label=lbl, topic="karmazyn", vector=s_str, init_T=init_T, session=self._sid)
        self._sem[lbl] = s_sem.copy()
        self._rc[lbl]  = 0
        return lbl

    def recall(self, query: bytes, k: int = 3) -> List[Tuple[Dict, float]]:
        q_str = self.embed_structural(query)
        q_sem = self.embed_semantic(query)
        cands = []
        for a in self._mx.atoms:
            if a.get('session') != self._sid: continue
            lbl = a.get('label', '')
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

    def recall_count(self, label: str) -> int: return self._rc.get(label, 0)

    def step(self) -> int:
        self._mx.step()
        alive = {a['label'] for a in self._mx.atoms}
        self._sem = {k: v for k, v in self._sem.items() if k in alive}
        self._rc  = {k: v for k, v in self._rc.items() if k in alive}
        return len(self._mx.atoms)

    def temperature(self) -> float:
        a = self._mx.atoms
        return float(np.mean([x['T'] for x in a])) if a else self._tvac

    @property
    def epoch(self) -> int: return self._mx.time

    def stats(self) -> Dict:
        return {"atoms": len(self._mx.atoms), "epoch": self.epoch,
                "temperature": self.temperature(), "t_vacuum": self._tvac, "dim": self.dim}

# -------------------------------------------------------------------------
# Hologram (generatywny)
# -------------------------------------------------------------------------
@dataclass
class Hologram:
    id: str
    topic: str
    proto: np.ndarray               # centroid
    generators: List[np.ndarray]    # główne kierunki PCA
    weights: List[float]            # wartości własne (siła kierunku)
    epoch_created: int
    decay_rate: float = 0.001
    metadata: Dict = field(default_factory=dict)

    def liveliness(self, current_epoch: int) -> float:
        elapsed = max(0, current_epoch - self.epoch_created)
        return math.exp(-self.decay_rate * elapsed)

# -------------------------------------------------------------------------
# KarmazynOS v0.9.0
# -------------------------------------------------------------------------
class KarmazynOS:
    def __init__(self, dim: int = 64, n_sessions: int = 1, seed: int = 42,
                 auto_cleanup_interval: int = 50):
        self.phi    = PhiSpace(dim=dim, n_sessions=n_sessions, seed=seed)
        self.daemon = HSSDaemon()
        phi2_vec    = np.frombuffer(self.phi.phi2_bytes() * 4, dtype=np.float32)[:N]
        self._s_sess = self.daemon.init_phi_session(phi2_vec, phi_pid=0)
        self.bubbles = BubbleStore(self.phi.phi2_bytes(), self._s_sess)
        self._amap:  Dict[str, str]             = {}
        self._fp:    Dict[str, bytes]           = {}
        self._raw:   Dict[str, bytes]           = {}
        self._ac:    Dict[str, int]             = {}
        self._pid    = 100
        self._reg:   Dict[int, Tuple[str, List[str]]] = {}
        self._auto_cleanup_interval = auto_cleanup_interval
        self._steps_since_cleanup = 0
        self.holograms: Dict[str, Hologram] = {}

        print(f"  Thermodynamic Memory Kernel v{VERSION}")
        print(f"  Φ + Bąble + Hologramy generatywne (PCA) | T_vacuum = {self.phi.t_vacuum():.4f} bit")

    def _bubble_bias(self) -> float:
        n_eff_b = sum(b.liveliness(self.phi.epoch) for b in self.bubbles.all_active)
        n_eff_h = sum(h.liveliness(self.phi.epoch) * 0.5 for h in self.holograms.values())
        return 1.0 + 0.5 * math.log1p(n_eff_b + n_eff_h)

    def write(self, content: str, auto_consolidate: int = 0) -> str:
        raw   = content.encode()
        label = self.phi.add(raw)
        bits8 = np.unpackbits(np.frombuffer(hashlib.sha256(raw).digest()[:8], dtype=np.uint8))
        vec   = np.zeros(N, dtype=np.int64)
        vec[:64] = bits8.astype(np.int64)
        inode = f"karmazyn://phi/{label}"
        self.daemon.phi_write(inode, vec)
        self._amap[label] = inode
        self._fp[label]   = hashlib.sha256(raw).digest()
        self._raw[label]  = raw
        self._ac[label]   = auto_consolidate
        return label

    def consolidate(self, label: str, metadata: Dict = None) -> Optional[str]:
        if label not in self._amap: return None
        raw   = self._raw.get(label, label.encode())
        phi_a = next((a for a in self.phi._mx.atoms if a.get('label') == label), None)
        s_str = phi_a['S'].copy() if phi_a else self.phi.embed_structural(raw)
        s_sem = self.phi._sem.get(label, self.phi.embed_semantic(raw)).copy()
        b_inode = f"karmazyn://bubbles/{label}"
        self.daemon.phi_write(b_inode, np.zeros(N, dtype=np.int64))
        bubble = self.bubbles.store(label=label, S_struct=s_str, S_sem=s_sem,
                                    content_raw=raw, inode=b_inode, epoch=self.phi.epoch,
                                    consolidated_from=label, metadata=metadata or {})
        print(f"  [KONSOLIDACJA] '{label[:30]}' → {bubble.id}")
        return bubble.id

    def _auto_check(self, label: str):
        thresh = self._ac.get(label, 0)
        if thresh > 0 and self.phi.recall_count(label) >= thresh:
            if self.bubbles.get_by_label(label) is None:
                print(f"  [AUTO] '{label[:25]}' recall≥{thresh} → consolidate")
                self.consolidate(label)

    def recall(self, query: str, k: int = 5) -> List[Dict]:
        raw   = query.encode()
        q_sem = self.phi.embed_semantic(raw)
        k_phi = max(1, int(k * 0.6))
        k_bub = max(1, k - k_phi)

        phi_res = []
        for atom, sim in self.phi.recall(raw, k=k_phi):
            lbl   = atom.get('label', '')
            s_sem = self.phi._sem.get(lbl, atom['S'])
            sim_f = max(0.0, float(np.dot(q_sem, s_sem)))
            phi_res.append({'label': lbl, 'layer': 'phi', 'T': atom['T'], 'sim': sim_f,
                            'score': sim_f * atom['T'], 'inode': self._amap.get(lbl, ''), 'bubble_id': None})
            self._auto_check(lbl)

        bias = self._bubble_bias()
        bub_res = []
        current_epoch = self.phi.epoch
        for score, b in self.bubbles.recall(q_sem, current_epoch, k=k_bub, bias=bias):
            liv = b.liveliness(current_epoch)
            bub_res.append({'label': b.label, 'layer': 'bubble', 'T': float('inf'),
                            'sim': score / (bias * liv) if liv>0 else 0.0, 'score': score,
                            'inode': b.inode, 'bubble_id': b.id, 'liveliness': liv})

        all_res = phi_res + bub_res
        all_res.sort(key=lambda x: x['score'], reverse=True)
        return all_res[:k]

    def read_bubble(self, label: str) -> Optional[str]:
        b = self.bubbles.get_by_label(label)
        if b is None: return None
        raw = b.decrypt_content()
        try: return raw.decode('utf-8', errors='replace')
        except Exception: return raw.hex()

    def reactivate_bubble(self, label: str) -> Optional[str]:
        b = self.bubbles.get_by_label(label)
        if not b: return None
        liv = b.liveliness(self.phi.epoch)
        T_init = DELTA_T_BASE * (0.3 + 0.7 * liv) + 0.1 * math.log1p(b.recall_count)
        T_init = min(T_init, DELTA_T_BASE * 2.0)
        content = b.decrypt_content()
        new_label = self.phi.add(content, label=f"react_{label}", init_T=T_init)
        print(f"  [REAKTYWACJA] '{label[:30]}' → {new_label} (T={T_init:.2f})")
        return new_label

    def evaluate(self, context: str) -> Tuple[bool, float, str]:
        raw = context.encode()
        q_sem = self.phi.embed_semantic(raw)
        phi_a = self.phi._mx.atoms
        bubs  = self.bubbles.all_active
        all_s = []
        s_phi = 0.0
        if phi_a:
            sims = [max(0.0, float(np.dot(q_sem, self.phi._sem.get(a['label'], a['S'])))) for a in phi_a]
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
        reason = (f"score={score:.3f} [φ={s_phi:.3f} b={s_bub:.3f}] {'>' if allow else '≤'} θ={theta:.3f}(p60) → {'ZEZWÓL' if allow else 'ODMÓW'}")
        return allow, score, reason

    def derive_agent(self, name: str, task: str, prisms: List[str] = ["core","in","out"]) -> Tuple[int, np.ndarray]:
        self._pid += 1
        s = self.daemon.derive_agent_key(self._pid, task, prisms)
        self._reg[self._pid] = (task, prisms)
        return self._pid, s

    def read_as_agent(self, label: str, pid: int, s_agent: np.ndarray, from_bubble: bool = False) -> Dict:
        if from_bubble:
            b = self.bubbles.get_by_label(label)
            if not b: return {'error': f'bąbel {label!r} nieznany'}
            inode, fp = b.inode, b.fingerprint
            s_eff = self.bubbles.bubble_s_agent(b)
        else:
            inode = self._amap.get(label)
            if not inode: return {'error': f'atom {label!r} nieznany'}
            fp, s_eff = self._fp.get(label), s_agent
        reg = self._reg.get(pid)
        if not reg: return {'error': f'PID {pid} nieznany'}
        task, prisms = reg
        res = self.daemon.upcall_read(pid, inode, prisms, task)
        if res is None: return {'error': 'ODMOWA'}
        out = {}
        for p in res:
            bits = decrypt(s_eff, p.u, p.v)
            if fp is not None and len(bits) >= len(fp)*8:
                read_bytes = np.packbits(bits[:len(fp)*8]).tobytes()
                hamming = _hamming_distance(fp, read_bytes)
                n_bits = len(fp) * 8
                mean = n_bits * 0.5
                std = math.sqrt(n_bits * 0.5 * 0.5)
                threshold = int(mean + 2 * std)
                sig = hamming <= threshold
                out[p.prism_id] = {'signal': sig, 'hamming': hamming, 'threshold': threshold,
                                   'status': f'{"✓ SYGNAŁ" if sig else "✗ SZUM"} (h={hamming}, thr={threshold})'}
            else:
                out[p.prism_id] = {'signal': False, 'status': '✗ SZUM (brak fingerprintu)'}
        return out

    def mark_bubble_for_decay(self, label: str, rate: float = 0.01) -> bool:
        return self.bubbles.mark_for_decay(label, self.phi.epoch, rate)

    def refresh_bubble(self, label: str) -> bool:
        return self.bubbles.refresh_bubble(label)

    def revoke_bubble(self, label: str) -> bool:
        ok = self.bubbles.revoke_by_label(label)
        if ok: print(f"  [REVOKE] '{label}' → Warp Oblivion")
        return ok

    # --------------------- Hologramy v0.9 (generatywne) --------------------
    def archive_bubbles_to_hologram(self, topic: str, bubble_labels: List[str],
                                    remove_originals: bool = False, n_components: int = 5) -> Optional[str]:
        vectors = []
        labels = []
        for lbl in bubble_labels:
            b = self.bubbles.get_by_label(lbl)
            if b:
                vectors.append(b.S_sem)
                labels.append(lbl)
        if not vectors: return None
        data = np.array(vectors)
        proto = np.mean(data, axis=0)
        proto /= np.linalg.norm(proto) + 1e-9
        # PCA
        centered = data - proto
        cov = centered.T @ centered / len(data)
        eigvals, eigvecs = np.linalg.eigh(cov)
        k = min(n_components, len(eigvals))
        top_idx = np.argsort(eigvals)[-k:]
        generators = [eigvecs[:, i] for i in top_idx]
        weights = [float(eigvals[i]) for i in top_idx]
        max_w = max(weights) if weights else 1.0
        weights = [w/max_w for w in weights]

        hid = f"idea_{topic}_{self.phi.epoch}_{hashlib.md5(topic.encode()).hexdigest()[:6]}"
        self.holograms[hid] = Hologram(id=hid, topic=topic, proto=proto,
                                       generators=generators, weights=weights,
                                       epoch_created=self.phi.epoch)
        print(f"  [IDEA] Utworzono hologram '{hid}' z {len(labels)} bąbli (temat: {topic})")
        if remove_originals:
            for lbl in labels: self.bubbles.remove_bubble(lbl)
            print(f"  [IDEA] Usunięto oryginalne bąble.")
        return hid

    def recall_from_hologram(self, hologram_id: str, cue: str, temperature: float = 0.2,
                             k: int = 1) -> List[np.ndarray]:
        h = self.holograms.get(hologram_id)
        if not h: return []
        q_sem = self.phi.embed_semantic(cue.encode())
        results = []
        for _ in range(k):
            base = h.proto * np.dot(q_sem, h.proto)
            noise = np.zeros_like(base)
            for g, w in zip(h.generators, h.weights):
                coeff = np.dot(q_sem, g) * w * temperature
                noise += g * coeff
            iso = np.random.normal(0, 0.05 * temperature, size=base.shape)
            synthetic = base + noise + iso
            synthetic /= np.linalg.norm(synthetic) + 1e-9
            results.append(synthetic)
        return results

    def generate_from_idea(self, hologram_id: str, prompt: str, temperature: float = 0.3,
                           create_atom: bool = True) -> List[str]:
        vectors = self.recall_from_hologram(hologram_id, prompt, temperature=temperature, k=1)
        if not vectors: return []
        generated = []
        for vec in vectors:
            # wektor semantyczny -> można by zdekodować do tekstu, tu uproszczone
            if create_atom:
                label = f"gen_{hologram_id}_{self.phi.epoch}"
                self.phi._sem[label] = vec
                generated.append(label)
            else:
                generated.append(str(vec[:8]))
        return generated

    def step(self, n: int = 1) -> Dict:
        for _ in range(n):
            self.phi.step()
            self._steps_since_cleanup += 1
            if self._steps_since_cleanup >= self._auto_cleanup_interval:
                removed = self.bubbles.cleanup_revoked()
                if removed > 0: print(f"  [GC] Usunięto {removed} revoked bąbli.")
                self._steps_since_cleanup = 0
        return self.stats()

    def cleanup_revoked(self) -> int: return self.bubbles.cleanup_revoked()

    def stats(self) -> Dict:
        s = self.phi.stats()
        return {**s, "version": VERSION, "atoms_phi": s["atoms"], "bubbles": self.bubbles.count,
                "bubbles_decaying": self.bubbles.count_decaying,
                "bubbles_revoked": len(self.bubbles._rev),
                "holograms": len(self.holograms), "bubble_bias": self._bubble_bias()}

    def __repr__(self) -> str:
        s = self.stats()
        return (f"ThermodynamicMemoryKernel(v{VERSION} | φ={s['atoms_phi']} T={s['temperature']:.2f} | "
                f"bubbles={s['bubbles']} bias={s['bubble_bias']:.2f} | ideas={s['holograms']} | epoch={s['epoch']})")