"""
karmazyn.py — Thermodynamic Memory Kernel (KarmazynOS) v1.1.1
===============================================================

Zmiany v1.1.1:
  [fix] Zapis i odczyt phi._p2s w save()/load()
        (bez tego klucze bąbli nie przechodziły restartu)
"""

import os
import sys
import hashlib
import hmac
import math
import json
import pickle
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from collections import Counter

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

from hss_karmazyn_matrix import HSSKarmazynMatrix
from hss_demo import HSSDaemon, kdf, decrypt, N, Q

VERSION      = "1.1.1"
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
            if offset >= len(data): break
            out[offset] = data[offset] ^ b
            offset += 1
        counter += 1
    return bytes(out)

def _compute_fingerprint(content: bytes, key: bytes, label: str) -> bytes:
    return hmac.new(key, label.encode() + content, hashlib.sha256).digest()

def _hamming_distance(a: bytes, b: bytes) -> int:
    xor = bytes(x ^ y for x, y in zip(a, b))
    return sum(bin(byte).count('1') for byte in xor)

@dataclass
class Bubble:
    id: str; label: str; S_struct: np.ndarray; S_sem: np.ndarray; fingerprint: bytes
    bubble_key: bytes; encrypted_content: bytes; inode: str; epoch_born: int
    recall_count: int = 0; consolidated_from: str = ""; metadata: Dict = field(default_factory=dict)
    decay_start_epoch: Optional[int] = None; decay_rate: float = 0.0
    def is_alive(self): return bool(self.bubble_key)
    def liveliness(self, current_epoch: int) -> float:
        if self.decay_start_epoch is None or self.decay_rate <= 0: return 1.0
        elapsed = max(0, current_epoch - self.decay_start_epoch)
        return math.exp(-self.decay_rate * elapsed)
    def decrypt_content(self):
        key = self.bubble_key if self.bubble_key else b"revoked_warp_oblivion"
        return _xor_crypt(self.encrypted_content, key)

class BubbleStore:
    def __init__(self, phi2_bytes: bytes, s_sess: np.ndarray):
        self._b: Dict[str, Bubble] = {}; self._idx: Dict[str, str] = {}
        self._phi2 = phi2_bytes; self._s = s_sess; self._rev: set = set()
    def _make_key(self, bid: str): return hashlib.sha256(self._phi2 + b"bubble:" + bid.encode()).digest()
    def bubble_s_agent(self, bubble: Bubble):
        hex_key = bubble.bubble_key.hex() if bubble.bubble_key else "revoked"
        return kdf(self._s.tobytes(), f"bubble:{hex_key}")
    def store(self, label, S_struct, S_sem, content_raw, inode, epoch, consolidated_from="", metadata=None):
        bid = "bubble_" + hashlib.md5((label+str(epoch)).encode()).hexdigest()[:12]
        key = self._make_key(bid); fp = _compute_fingerprint(content_raw, key, label)
        b = Bubble(id=bid, label=label, S_struct=S_struct.copy(), S_sem=S_sem.copy(),
                   fingerprint=fp, bubble_key=key, encrypted_content=_xor_crypt(content_raw, key),
                   inode=inode, epoch_born=epoch, consolidated_from=consolidated_from, metadata=metadata or {})
        self._b[bid]=b; self._idx[label]=bid; return b
    def recall(self, q_sem, current_epoch, k=3, bias=1.5):
        res = []
        for bid, b in self._b.items():
            if bid in self._rev or not b.is_alive(): continue
            liv = b.liveliness(current_epoch)
            if liv <= 1e-9: continue
            sim = float(np.dot(q_sem, b.S_sem)); score = sim * bias * liv
            res.append((score,b))
        res.sort(key=lambda x: x[0], reverse=True)
        for _,b in res[:k]:
            b.recall_count += 1
            if b.decay_start_epoch is not None:
                elapsed = current_epoch - b.decay_start_epoch
                b.decay_start_epoch = current_epoch - elapsed*0.7
        return res[:k]
    def get_by_label(self, label): return self._b.get(self._idx.get(label))
    def revoke_by_label(self, label):
        bid = self._idx.get(label)
        if bid in self._b: self._b[bid].bubble_key = b""; self._rev.add(bid); return True
        return False
    def cleanup_revoked(self):
        removed = 0
        for bid in list(self._rev):
            b = self._b.pop(bid,None)
            if b:
                if self._idx.get(b.label)==bid: del self._idx[b.label]
                removed += 1
        self._rev.clear(); return removed
    def mark_for_decay(self, label, start_epoch, rate):
        b = self.get_by_label(label)
        if b: b.decay_start_epoch = start_epoch; b.decay_rate = rate; return True
        return False
    def refresh_bubble(self, label):
        b = self.get_by_label(label)
        if b: b.decay_start_epoch = None; b.decay_rate = 0.0; return True
        return False
    def remove_bubble(self, label):
        bid = self._idx.get(label)
        if bid and bid in self._b:
            del self._b[bid]; del self._idx[label]
            if bid in self._rev: self._rev.remove(bid)
            return True
        return False
    @property
    def count(self): return len(self._b)-len(self._rev)
    @property
    def count_decaying(self):
        return sum(1 for b in self._b.values() if b.decay_start_epoch is not None and b.id not in self._rev)
    @property
    def all_active(self): return [b for bid,b in self._b.items() if bid not in self._rev]

class IDFCounter:
    def __init__(self): self._freq=Counter(); self._ndocs=0
    def add_doc(self, tokens):
        self._ndocs+=1
        for t in set(tokens): self._freq[t]+=1
    def idf(self, token): return float(np.log1p(self._ndocs/(1+self._freq.get(token,0))))

class PhiSpace:
    def __init__(self, dim=64, n_sessions=1, seed=42):
        self._mx = HSSKarmazynMatrix(dim=dim, n_sessions=n_sessions, lambd=LAMBDA_DECAY, seed=seed)
        self.dim = dim; self._sid = 0; self._tvac = self._measure_tvac()
        self._p2s = os.urandom(32)  # ← TEN ATRYBUT MUSI BYĆ ZAPISYWANY
        self._sem: Dict[str,np.ndarray] = {}; self._rc: Dict[str,int] = {}; self._idf = IDFCounter()
    def embed_structural(self, c: bytes):
        s = int(hashlib.md5(c).hexdigest(),16)%(2**32)
        v = np.random.default_rng(s).normal(0,1,self.dim).astype(np.float32)
        return v/(np.linalg.norm(v)+1e-9)
    def embed_semantic(self, c: bytes, update=False):
        try: text = c.decode('utf-8', errors='ignore').lower()
        except: return self.embed_structural(c)
        tokens = [w for w in text.split() if len(w)>1 and w not in STOPWORDS]
        bigrams = [f"{a}_{b}" for a,b in zip(tokens,tokens[1:])]
        all_t = tokens+bigrams
        if not all_t: return self.embed_structural(c)
        if update: self._idf.add_doc(tokens)
        v = np.zeros(self.dim, dtype=np.float32)
        for t in all_t:
            w = self._idf.idf(t)*min(1.0, len(t)/5.0)
            s = int(hashlib.md5(t.encode()).hexdigest(),16)%(2**32)
            v += w * np.random.default_rng(s).normal(0,1,self.dim).astype(np.float32)
        n = np.linalg.norm(v); return v/n if n>1e-9 else self.embed_structural(c)
    def phi2_bytes(self): return hashlib.sha256(self._p2s + b"phi2-v1").digest()
    def _measure_tvac(self):
        s = np.random.randint(0,Q,N,dtype=np.int64)%256
        _,c = np.unique(s, return_counts=True); p = c/len(s)
        return float(-np.sum(p*np.log2(p+1e-12)))
    def t_vacuum(self): return self._tvac
    def add(self, content: bytes, label="", init_T=DELTA_T_BASE):
        s_str = self.embed_structural(content); s_sem = self.embed_semantic(content, update=True)
        lbl = label or f"atom_{hashlib.md5(content).hexdigest()[:8]}"
        self._mx.add_atom_vector(label=lbl, topic="karmazyn", vector=s_str, init_T=init_T, session=self._sid)
        self._sem[lbl] = s_sem.copy(); self._rc[lbl] = 0; return lbl
    def add_semantic_vector(self, vector: np.ndarray, label="", init_T=DELTA_T_BASE):
        lbl = label or f"atom_{hashlib.md5(vector.tobytes()).hexdigest()[:8]}"
        seed = int(hashlib.md5(vector.tobytes()).hexdigest(),16)%(2**32)
        s_str = np.random.default_rng(seed).normal(0,1,self.dim).astype(np.float32)
        s_str /= np.linalg.norm(s_str)+1e-9
        self._mx.add_atom_vector(label=lbl, topic="karmazyn", vector=s_str, init_T=init_T, session=self._sid)
        self._sem[lbl] = vector.copy(); self._rc[lbl] = 0; return lbl
    def recall(self, query: bytes, k=3):
        q_str = self.embed_structural(query); q_sem = self.embed_semantic(query)
        cands = []
        for a in self._mx.atoms:
            if a.get('session')!=self._sid: continue
            lbl = a.get('label',''); s_sem = self._sem.get(lbl, a['S'])
            sim_s = max(0.0, float(np.dot(q_str, a['S'])))
            sim_m = max(0.0, float(np.dot(q_sem, s_sem)))
            sim = ALPHA*sim_s + (1-ALPHA)*sim_m
            cands.append((sim*a['T'], a, sim))
        cands.sort(key=lambda x:x[0], reverse=True)
        result = []
        for _,a,sim in cands[:k]:
            a['T'] = a['T'] + 0.3*(DELTA_T_BASE - a['T'])
            lbl = a.get('label',''); self._rc[lbl] = self._rc.get(lbl,0)+1
            result.append((a,sim))
        return result
    def recall_count(self, label): return self._rc.get(label,0)
    def step(self):
        self._mx.step()
        alive = {a['label'] for a in self._mx.atoms}
        self._sem = {k:v for k,v in self._sem.items() if k in alive}
        self._rc  = {k:v for k,v in self._rc.items() if k in alive}
        return len(self._mx.atoms)
    def temperature(self):
        a = self._mx.atoms
        return float(np.mean([x['T'] for x in a])) if a else self._tvac
    @property
    def epoch(self): return self._mx.time
    def stats(self):
        return {"atoms": len(self._mx.atoms), "epoch": self.epoch,
                "temperature": self.temperature(), "t_vacuum": self._tvac, "dim": self.dim}

@dataclass
class Hologram:
    id: str; topic: str; proto: np.ndarray; generators: List[np.ndarray]; weights: List[float]
    bubble_labels: List[str]; epoch_created: int; decay_rate: float = 0.001
    metadata: Dict = field(default_factory=dict)
    def liveliness(self, current_epoch):
        elapsed = max(0, current_epoch - self.epoch_created)
        return math.exp(-self.decay_rate * elapsed)

class KarmazynOS:
    def __init__(self, dim=64, n_sessions=1, seed=42, auto_cleanup_interval=50):
        self.phi = PhiSpace(dim, n_sessions, seed)
        self.daemon = HSSDaemon()
        phi2_vec = np.frombuffer(self.phi.phi2_bytes()*4, dtype=np.float32)[:N]
        self._s_sess = self.daemon.init_phi_session(phi2_vec, phi_pid=0)
        self.bubbles = BubbleStore(self.phi.phi2_bytes(), self._s_sess)
        self._amap: Dict[str,str] = {}; self._fp: Dict[str,bytes] = {}; self._raw: Dict[str,bytes] = {}
        self._ac: Dict[str,int] = {}; self._pid = 100; self._reg: Dict[int,Tuple] = {}
        self._auto_cleanup_interval = auto_cleanup_interval; self._steps_since_cleanup = 0
        self.holograms: Dict[str,Hologram] = {}
        print(f"  KarmazynOS v{VERSION} — Thermodynamic Memory Kernel")
        print(f"  Φ + Bąble + Hologramy | T_vacuum = {self.phi.t_vacuum():.4f} bit")

    def _bubble_bias(self):
        n_eff_b = sum(b.liveliness(self.phi.epoch) for b in self.bubbles.all_active)
        n_eff_h = sum(h.liveliness(self.phi.epoch)*0.5 for h in self.holograms.values())
        return 1.0 + 0.5*math.log1p(n_eff_b + n_eff_h)

    def write(self, content: str, auto_consolidate=0):
        raw = content.encode(); label = self.phi.add(raw)
        bits8 = np.unpackbits(np.frombuffer(hashlib.sha256(raw).digest()[:8], dtype=np.uint8))
        vec = np.zeros(N, dtype=np.int64); vec[:64] = bits8.astype(np.int64)
        inode = f"karmazyn://phi/{label}"; self.daemon.phi_write(inode, vec)
        self._amap[label] = inode; self._fp[label] = hashlib.sha256(raw).digest()
        self._raw[label] = raw; self._ac[label] = auto_consolidate; return label

    def consolidate(self, label, metadata=None):
        if label not in self._amap: return None
        raw = self._raw.get(label, label.encode())
        phi_a = next((a for a in self.phi._mx.atoms if a.get('label')==label), None)
        s_str = phi_a['S'].copy() if phi_a else self.phi.embed_structural(raw)
        s_sem = self.phi._sem.get(label, self.phi.embed_semantic(raw)).copy()
        b_inode = f"karmazyn://bubbles/{label}"; self.daemon.phi_write(b_inode, np.zeros(N, dtype=np.int64))
        bubble = self.bubbles.store(label=label, S_struct=s_str, S_sem=s_sem,
                                    content_raw=raw, inode=b_inode, epoch=self.phi.epoch,
                                    consolidated_from=label, metadata=metadata or {})
        print(f"  [KONSOLIDACJA] '{label[:30]}' → {bubble.id}"); return bubble.id

    def _auto_check(self, label):
        thresh = self._ac.get(label,0)
        if thresh>0 and self.phi.recall_count(label)>=thresh:
            if self.bubbles.get_by_label(label) is None:
                print(f"  [AUTO] '{label[:25]}' recall≥{thresh} → consolidate")
                self.consolidate(label)

    def recall(self, query: str, k=5):
        raw = query.encode(); q_sem = self.phi.embed_semantic(raw)
        k_phi = max(1, int(k*0.6)); k_bub = max(1, k-k_phi)
        phi_res = []
        for atom, sim in self.phi.recall(raw, k=k_phi):
            lbl = atom.get('label',''); s_sem = self.phi._sem.get(lbl, atom['S'])
            sim_f = max(0.0, float(np.dot(q_sem, s_sem)))
            phi_res.append({'label': lbl, 'layer': 'phi', 'T': atom['T'], 'sim': sim_f,
                            'score': sim_f*atom['T'], 'inode': self._amap.get(lbl,''), 'bubble_id': None})
            self._auto_check(lbl)
        bias = self._bubble_bias(); bub_res = []
        current_epoch = self.phi.epoch
        for score, b in self.bubbles.recall(q_sem, current_epoch, k=k_bub, bias=bias):
            liv = b.liveliness(current_epoch)
            bub_res.append({'label': b.label, 'layer': 'bubble', 'T': float('inf'),
                            'sim': score/(bias*liv) if liv>0 else 0.0, 'score': score,
                            'inode': b.inode, 'bubble_id': b.id, 'liveliness': liv})
        all_res = phi_res + bub_res
        all_res.sort(key=lambda x:x['score'], reverse=True)
        return all_res[:k]

    def read_bubble(self, label):
        b = self.bubbles.get_by_label(label)
        if not b: return None
        raw = b.decrypt_content()
        try: return raw.decode('utf-8', errors='replace')
        except: return raw.hex()

    def reactivate_bubble(self, label):
        b = self.bubbles.get_by_label(label)
        if not b: return None
        liv = b.liveliness(self.phi.epoch)
        T_init = DELTA_T_BASE*(0.3+0.7*liv) + 0.1*math.log1p(b.recall_count)
        T_init = min(T_init, DELTA_T_BASE*2.0)
        content = b.decrypt_content()
        new_label = self.phi.add(content, label=f"react_{label}", init_T=T_init)
        print(f"  [REAKTYWACJA] '{label[:30]}' → {new_label} (T={T_init:.2f})")
        return new_label

    def evaluate(self, context):
        raw = context.encode(); q_sem = self.phi.embed_semantic(raw)
        phi_a = self.phi._mx.atoms; bubs = self.bubbles.all_active; all_s = []
        s_phi = 0.0
        if phi_a:
            sims = [max(0.0, float(np.dot(q_sem, self.phi._sem.get(a['label'], a['S'])))) for a in phi_a]
            all_s.extend(sims); s_phi = sum(s*a['T'] for s,a in zip(sims,phi_a))/len(phi_a)
        s_bub = 0.0
        if bubs:
            simsb = [max(0.0, float(np.dot(q_sem, b.S_sem))) for b in bubs]
            all_s.extend(simsb); s_bub = sum(simsb)/len(bubs)
        score = 0.6*s_phi + 0.4*s_bub
        theta = max(float(np.percentile(all_s,60)), 0.1) if all_s else 0.3
        allow = score > theta
        reason = f"score={score:.3f} [φ={s_phi:.3f} b={s_bub:.3f}] {'>' if allow else '≤'} θ={theta:.3f}"
        return allow, score, reason

    def derive_agent(self, name, task, prisms=["core","in","out"]):
        self._pid+=1; s = self.daemon.derive_agent_key(self._pid, task, prisms)
        self._reg[self._pid] = (task, prisms); return self._pid, s

    def read_as_agent(self, label, pid, s_agent, from_bubble=False):
        if from_bubble:
            b = self.bubbles.get_by_label(label)
            if not b: return {'error': f'bąbel {label} nieznany'}
            inode, fp = b.inode, b.fingerprint; s_eff = self.bubbles.bubble_s_agent(b)
        else:
            inode = self._amap.get(label)
            if not inode: return {'error': f'atom {label} nieznany'}
            fp, s_eff = self._fp.get(label), s_agent
        reg = self._reg.get(pid)
        if not reg: return {'error': f'PID {pid} nieznany'}
        task, prisms = reg
        res = self.daemon.upcall_read(pid, inode, prisms, task)
        if res is None: return {'error': 'ODMOWA'}
        out = {}
        for p in res:
            bits = decrypt(s_eff, p.u, p.v)
            if fp and len(bits)>=len(fp)*8:
                read_bytes = np.packbits(bits[:len(fp)*8]).tobytes()
                hamming = _hamming_distance(fp, read_bytes)
                n_bits = len(fp)*8; mean = n_bits*0.5; std = math.sqrt(n_bits*0.5*0.5)
                threshold = int(mean+2*std); sig = hamming <= threshold
                out[p.prism_id] = {'signal': sig, 'hamming': hamming,
                    'status': f'{"✓ SYGNAŁ" if sig else "✗ SZUM"} (h={hamming})'}
            else: out[p.prism_id] = {'signal': False, 'status': '✗ SZUM (brak fp)'}
        return out

    def mark_bubble_for_decay(self, label, rate=0.01): return self.bubbles.mark_for_decay(label, self.phi.epoch, rate)
    def refresh_bubble(self, label): return self.bubbles.refresh_bubble(label)

    def revoke_bubble(self, label):
        ok = self.bubbles.revoke_by_label(label)
        if ok: print(f"  [REVOKE] '{label}' → Warp Oblivion")
        return ok

    def archive_bubbles_to_hologram(self, topic, bubble_labels, remove_originals=False, n_components=5):
        vectors = []; labels = []
        for lbl in bubble_labels:
            b = self.bubbles.get_by_label(lbl)
            if b: vectors.append(b.S_sem); labels.append(lbl)
        if not vectors: return None
        data = np.array(vectors); proto = np.mean(data, axis=0); proto /= np.linalg.norm(proto)+1e-9
        centered = data - proto; cov = centered.T @ centered / len(data)
        eigvals, eigvecs = np.linalg.eigh(cov)
        k = min(n_components, len(eigvals)); top_idx = np.argsort(eigvals)[-k:]
        generators = [eigvecs[:,i] for i in top_idx]
        weights = [float(eigvals[i]) for i in top_idx]
        max_w = max(weights) if weights else 1.0; weights = [w/max_w for w in weights]
        hid = f"idea_{topic}_{self.phi.epoch}_{hashlib.md5(topic.encode()).hexdigest()[:6]}"
        self.holograms[hid] = Hologram(id=hid, topic=topic, proto=proto,
            generators=generators, weights=weights, bubble_labels=labels, epoch_created=self.phi.epoch)
        print(f"  [IDEA] Utworzono '{hid}' z {len(labels)} bąbli")
        if remove_originals:
            for lbl in labels: self.bubbles.remove_bubble(lbl)
            print("  [IDEA] Usunięto oryginalne bąble")
        return hid

    def recall_from_hologram(self, hologram_id, cue, k=3):
        h = self.holograms.get(hologram_id)
        if not h: return []
        q_sem = self.phi.embed_semantic(cue.encode())
        scores = []
        for lbl in h.bubble_labels:
            b = self.bubbles.get_by_label(lbl)
            if b: scores.append((float(np.dot(q_sem, b.S_sem)), b))
        scores.sort(reverse=True)
        return [{'label': b.label, 'sim': sim} for sim,b in scores[:k]]

    def generate_from_idea(self, hologram_id, prompt, temperature=0.3):
        h = self.holograms.get(hologram_id)
        if not h: return None
        liv = h.liveliness(self.phi.epoch)
        if liv <= 1e-9: return None
        q_sem = self.phi.embed_semantic(prompt.encode())
        proj = float(np.dot(q_sem, h.proto)); base = h.proto * proj
        noise = np.zeros_like(base)
        for g, w in zip(h.generators, h.weights):
            coeff = np.dot(q_sem, g) * w * temperature
            noise += g * coeff
        iso = np.random.normal(0, 0.05*temperature, size=base.shape)
        synthetic = base + noise + iso
        synthetic /= np.linalg.norm(synthetic)+1e-9
        synthetic *= liv
        return synthetic

    def rehydrate_hologram(self, hologram_id):
        h = self.holograms.get(hologram_id)
        if not h: return []
        restored = []
        for i in range(len(h.generators)):
            vec = h.proto.copy(); label = f"rehyd_{h.id}_{i}"
            self.phi.add_semantic_vector(vec, label=label); restored.append(label)
        return restored

    def step(self, n=1):
        for _ in range(n):
            self.phi.step()
            self._steps_since_cleanup += 1
            if self._steps_since_cleanup >= self._auto_cleanup_interval:
                removed = self.bubbles.cleanup_revoked()
                if removed: print(f"  [GC] Usunięto {removed} revoked bąbli")
                self._steps_since_cleanup = 0
        return self.stats()

    def cleanup_revoked(self): return self.bubbles.cleanup_revoked()

    def stats(self):
        s = self.phi.stats()
        return {**s, "version": VERSION, "atoms_phi": s["atoms"], "bubbles": self.bubbles.count,
                "bubbles_decaying": self.bubbles.count_decaying, "bubbles_revoked": len(self.bubbles._rev),
                "holograms": len(self.holograms), "bubble_bias": self._bubble_bias()}

    # ──────────────────────────── PERSISTENCE ────────────────────────────
    def save(self, path="./karmazyn_data"):
        os.makedirs(path, exist_ok=True)
        # Φ
        self.phi._mx.save(os.path.join(path, "hss_matrix.npz"))
        np.savez(os.path.join(path, "phi_sem.npz"), **self.phi._sem)
        with open(os.path.join(path, "phi_rc.json"), "w") as f:
            json.dump(self.phi._rc, f)
        # Bąble
        with open(os.path.join(path, "bubbles.pkl"), "wb") as f:
            pickle.dump({
                "_b": self.bubbles._b, "_idx": self.bubbles._idx,
                "_rev": self.bubbles._rev, "_phi2": self.bubbles._phi2.hex()
            }, f)
        # Hologramy
        holo_dict = {}
        for hid, h in self.holograms.items():
            holo_dict[hid] = {
                "topic": h.topic, "proto": h.proto.tolist(),
                "generators": [g.tolist() for g in h.generators],
                "weights": h.weights, "bubble_labels": h.bubble_labels,
                "epoch_created": h.epoch_created, "decay_rate": h.decay_rate,
                "metadata": h.metadata
            }
        with open(os.path.join(path, "holograms.json"), "w") as f:
            json.dump(holo_dict, f, indent=2)
        # Meta – zawiera teraz p2s
        meta = {
            "epoch":       self.phi.epoch,
            "temperature": self.phi.temperature(),
            "pid":         self._pid,
            "version":     VERSION,
            "p2s":         self.phi._p2s.hex(),   # ← ZAPISANE
        }
        with open(os.path.join(path, "meta.json"), "w") as f:
            json.dump(meta, f)
        print(f"Stan zapisany w {path}")

    def load(self, path="./karmazyn_data"):
        if not os.path.isdir(path):
            print(f"Nie znaleziono katalogu {path}")
            return False
        # Φ
        self.phi._mx.load(os.path.join(path, "hss_matrix.npz"))
        sem_data = np.load(os.path.join(path, "phi_sem.npz"), allow_pickle=True)
        self.phi._sem = {k: sem_data[k] for k in sem_data.files}
        with open(os.path.join(path, "phi_rc.json"), "r") as f:
            self.phi._rc = json.load(f)
        # Bąble
        with open(os.path.join(path, "bubbles.pkl"), "rb") as f:
            bdata = pickle.load(f)
        self.bubbles._b = bdata["_b"]
        self.bubbles._idx = bdata["_idx"]
        self.bubbles._rev = set(bdata["_rev"])
        self.bubbles._phi2 = bytes.fromhex(bdata["_phi2"])
        # Hologramy
        with open(os.path.join(path, "holograms.json"), "r") as f:
            holo_dict = json.load(f)
        self.holograms.clear()
        for hid, hd in holo_dict.items():
            self.holograms[hid] = Hologram(
                id=hid, topic=hd["topic"], proto=np.array(hd["proto"], dtype=np.float32),
                generators=[np.array(g, dtype=np.float32) for g in hd["generators"]],
                weights=hd["weights"], bubble_labels=hd["bubble_labels"],
                epoch_created=hd["epoch_created"], decay_rate=hd["decay_rate"],
                metadata=hd["metadata"]
            )
        # Meta
        with open(os.path.join(path, "meta.json"), "r") as f:
            meta = json.load(f)
        self._pid = meta.get("pid", 100)
        if "p2s" in meta:                          # ← ODTWORZONE
            self.phi._p2s = bytes.fromhex(meta["p2s"])
        print(f"Stan wczytany z {path} (epoka: {meta['epoch']})")
        return True

    def __repr__(self):
        s = self.stats()
        return (f"KarmazynOS(v{VERSION} | φ={s['atoms_phi']} T={s['temperature']:.2f} | "
                f"bąble={s['bubbles']} bias={s['bubble_bias']:.2f} | idee={s['holograms']})")