"""
karmazyn.py — KarmazynOS Core Library v0.4.0
=============================================

Zmiany względem v0.3:

  [1] Payload w bąblach — encrypted_content = XOR(content, bubble_key)
      Bubble teraz wie CO przechowuje, nie tylko ZE istnieje.
      k.read_bubble(label) → odszyfrowana treść

  [2] Bubble-aware crypto — revoke() kryptograficznie blokuje dostęp
      s_bubble = KDF(s_sess, bubble_key_hex)
      Po revoke: bubble_key="" → inny klucz → Warp Oblivion

  [3] IDF w embed_semantic — rzadkie słowa ważniejsze
      Globalny IDFCounter per instancja.

  [4] BUBBLE_BIAS = 1.5 — bąble mają przewagę w recall
      Trwała pamięć > gorące ale efemeryczne Φ.

  [5] consolidate() używa _raw content — nie traci oryginalnej repr.

  [6] Auto-konsolidacja — k.write(..., auto_consolidate=N)
      Po N recall → automatyczny consolidate()

  [7] evaluate() z adaptywnym progiem (percentyl 60%)
"""

import os
import sys
import hashlib
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
# Payload crypto
# ─────────────────────────────────────────────────────────────────────────

def _xor_crypt(data: bytes, key: bytes, nonce: bytes) -> bytes:
    """XOR stream z SHA256-DRBG + nonce. Symetryczne."""
    out, offset, counter = bytearray(len(data)), 0, 0
    while offset < len(data):
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, 'big')).digest()
        for b in block:
            if offset >= len(data):
                break
            out[offset] = data[offset] ^ b
            offset += 1
        counter += 1
    return bytes(out)

def _make_hmac(key: bytes, data: bytes) -> bytes:
    """HMAC-SHA256 dla integralności payloadu."""
    import hmac as _hmac
    return _hmac.new(key, data, hashlib.sha256).digest()

def _payload_seal(content: bytes, key: bytes) -> Tuple[bytes, bytes, bytes]:
    """
    Zapieczętuj payload: (ciphertext, nonce, tag).
    nonce = losowe 16 bajtów — unikalne per bąbel.
    tag   = HMAC(key, nonce || ciphertext) — integralność.
    """
    nonce  = os.urandom(16)
    ct     = _xor_crypt(content, key, nonce)
    tag    = _make_hmac(key, nonce + ct)
    return ct, nonce, tag

def _payload_open(ct: bytes, nonce: bytes, tag: bytes,
                  key: bytes) -> Tuple[Optional[bytes], bool]:
    """
    Otwórz payload. Zwraca (plaintext, ok).
    ok=False: tag niezgodny → dane skompromitowane lub klucz zły.
    """
    expected = _make_hmac(key, nonce + ct)
    import hmac as _hmac
    if not _hmac.compare_digest(expected, tag):
        return None, False
    return _xor_crypt(ct, key, nonce), True


# ─────────────────────────────────────────────────────────────────────────
# Bubble
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class Bubble:
    """Bąbel Mazura — pamięć trwała z payloadem. T=∞."""
    id:                str
    label:             str
    S_struct:          np.ndarray
    S_sem:             np.ndarray
    fingerprint:       np.ndarray
    bubble_key:        bytes
    encrypted_content: bytes
    payload_nonce:     bytes        # losowy nonce — unikalne per bąbel
    payload_tag:       bytes        # HMAC(key, nonce||ct) — integralność
    inode:             str
    epoch_born:        int
    recall_count:      int  = 0
    consolidated_from: str  = ""
    metadata:          Dict = field(default_factory=dict)

    def is_alive(self) -> bool:
        return bool(self.bubble_key)

    def decrypt_content(self) -> Tuple[Optional[bytes], bool]:
        """
        Odszyfruj i zweryfikuj.
        Zwraca (plaintext, ok).
        Po revoke: klucz inny → tag niezgodny → (None, False).
        """
        key = self.bubble_key if self.bubble_key else b"revoked_warp_oblivion"
        return _payload_open(self.encrypted_content,
                             self.payload_nonce, self.payload_tag, key)


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
        """s_bubble = KDF(s_sess, bubble_key_hex). Zmienia się po revoke."""
        hex_key = bubble.bubble_key.hex() if bubble.bubble_key else "revoked"
        return kdf(self._s.tobytes(), f"bubble:{hex_key}")

    def store(self, label: str, S_struct: np.ndarray, S_sem: np.ndarray,
              fingerprint: np.ndarray, content_raw: bytes,
              inode: str, epoch: int,
              consolidated_from: str = "", metadata: Dict = None) -> Bubble:
        bid = "bubble_" + hashlib.md5((label + str(epoch)).encode()).hexdigest()[:12]
        key = self._make_key(bid)
        ct, nonce, tag = _payload_seal(content_raw, key)
        b   = Bubble(
            id=bid, label=label,
            S_struct=S_struct.copy(), S_sem=S_sem.copy(),
            fingerprint=fingerprint.copy(),
            bubble_key=key,
            encrypted_content=ct,
            payload_nonce=nonce,
            payload_tag=tag,
            inode=inode, epoch_born=epoch,
            consolidated_from=consolidated_from,
            metadata=metadata or {},
        )
        self._b[bid]   = b
        self._idx[label] = bid
        return b

    def recall(self, q_sem: np.ndarray, k: int = 3) -> List[Tuple[float, Bubble]]:
        res = [(float(np.dot(q_sem, b.S_sem)), b)
               for bid, b in self._b.items() if bid not in self._rev]
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

    @property
    def count(self) -> int:
        return len(self._b) - len(self._rev)

    @property
    def all_active(self) -> List[Bubble]:
        return [b for bid, b in self._b.items() if bid not in self._rev]


# ─────────────────────────────────────────────────────────────────────────
# IDF
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
        # Standardowy IDF + 1 (unika 0), z górnym ograniczeniem
        freq = self._freq.get(token, 0)
        raw  = np.log((self._ndocs + 1) / (freq + 1)) + 1.0
        return float(min(raw, 5.0))   # MAX_IDF = 5.0


# ─────────────────────────────────────────────────────────────────────────
# PhiSpace
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
        self._rc:   Dict[str, int]        = {}   # recall counts
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
        return hashlib.sha256(self._p2s + b"phi2-v4").digest()

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
        self._sem[lbl] = s_sem
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
# KarmazynOS v0.4
# ─────────────────────────────────────────────────────────────────────────

class KarmazynOS:
    """KarmazynOS v0.4.0 — dual memory z payloadem i bubble-aware crypto."""

    def __init__(self, dim: int = 64, n_sessions: int = 1, seed: int = 42):
        self.phi    = PhiSpace(dim=dim, n_sessions=n_sessions, seed=seed)
        self.daemon = HSSDaemon()
        phi2_vec    = np.frombuffer(self.phi.phi2_bytes() * 4,
                                     dtype=np.float32)[:N]
        self._s_sess = self.daemon.init_phi_session(phi2_vec, phi_pid=0)
        self.bubbles = BubbleStore(self.phi.phi2_bytes(), self._s_sess)
        self._amap:  Dict[str, str]             = {}
        self._fp:    Dict[str, np.ndarray]      = {}
        self._raw:   Dict[str, bytes]           = {}
        self._ac:    Dict[str, int]             = {}   # auto_consolidate thresh
        self._pid    = 100
        self._reg:   Dict[int, Tuple[str, List[str]]] = {}
        print(f"  KarmazynOS v{VERSION}")
        print(f"  Φ (stygnie) + Bąble (T=∞, payload, crypto-liveness)")
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
        self._fp[label]   = bits8.astype(np.int64)
        self._raw[label]  = raw
        self._ac[label]   = auto_consolidate
        return label

    # ── consolidate ───────────────────────────────────────────────────────

    def consolidate(self, label: str, metadata: Dict = None) -> Optional[str]:
        """Φ → Bąbel z zaszyfrowaną treścią."""
        if label not in self._amap:
            return None
        raw     = self._raw.get(label, label.encode())
        phi_a   = next((a for a in self.phi._mx.atoms
                        if a.get('label') == label), None)
        s_str   = phi_a['S'].copy() if phi_a else self.phi.embed_structural(raw)
        s_sem   = self.phi._sem.get(label, self.phi.embed_semantic(raw))
        fp      = self._fp.get(label, np.zeros(8, dtype=np.int64))
        b_inode = f"karmazyn://bubbles/{label}"
        vec     = np.zeros(N, dtype=np.int64)
        vec[:len(fp)] = fp
        self.daemon.phi_write(b_inode, vec)
        bubble = self.bubbles.store(
            label=label, S_struct=s_str, S_sem=s_sem,
            fingerprint=fp, content_raw=raw,
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
        """Recall z Φ + Bąble. Bąble mają BUBBLE_BIAS={BUBBLE_BIAS}."""
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
        for sim, b in self.bubbles.recall(q_sem, k=k_bub):
            bub_res.append({'label': b.label, 'layer': 'bubble',
                             'T': float('inf'), 'sim': sim,
                             'score': sim * BUBBLE_BIAS,
                             'inode': b.inode, 'bubble_id': b.id})

        all_res = phi_res + bub_res
        all_res.sort(key=lambda x: x['score'], reverse=True)
        return all_res[:k]

    # ── read_bubble ───────────────────────────────────────────────────────

    def read_bubble(self, label: str) -> Optional[str]:
        """
        Odszyfruj i zweryfikuj treść bąbla.
        Po revoke(): tag niezgodny → zwraca None (nie bełkot).
        Warp Oblivion: nie wiesz czy dane są poprawne bez klucza.
        """
        b = self.bubbles.get_by_label(label)
        if b is None:
            return None
        plaintext, ok = b.decrypt_content()
        if not ok:
            return None   # Warp Oblivion — klucz zły lub dane skompromitowane
        try:
            return plaintext.decode('utf-8', errors='replace')
        except Exception:
            return plaintext.hex()

    # ── evaluate ──────────────────────────────────────────────────────────

    def evaluate(self, context: str) -> Tuple[bool, float, str]:
        """Decyzja z obu warstw. Próg adaptywny (percentyl 60%)."""
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
        """Ring-LWE read. from_bubble=True → bubble-aware crypto."""
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
            hamming = int(np.sum(bits[:8] != fp[:8])) if fp is not None else 4
            sig     = hamming <= 3
            out[p.prism_id] = {
                'signal': sig, 'bits': bits[:8].tolist(),
                'status': f'{"✓ SYGNAŁ" if sig else "✗ SZUM"} (h={hamming})'}
        return out

    # ── lifecycle ─────────────────────────────────────────────────────────

    def step(self, n: int = 1) -> Dict:
        for _ in range(n):
            self.phi.step()
        # Memory hygiene: usuń _raw/_fp/_amap dla martwych atomów
        # Zachowaj jeśli atom ma bąbel (potrzebny dla consolidate)
        alive_phi     = {a['label'] for a in self.phi._mx.atoms}
        alive_bubbles = {b.consolidated_from for b in self.bubbles.all_active}
        alive         = alive_phi | alive_bubbles
        self._raw  = {k: v for k, v in self._raw.items()  if k in alive}
        self._fp   = {k: v for k, v in self._fp.items()   if k in alive}
        self._amap = {k: v for k, v in self._amap.items() if k in alive}
        return self.stats()

    def terminate_agent(self, pid: int, labels: List[str] = []):
        inodes = [self._amap[l] for l in labels if l in self._amap]
        self.daemon.terminate_agent(pid, inodes)
        self.daemon.vacuum_decay()

    def revoke_bubble(self, label: str) -> bool:
        """Jedyna droga śmierci bąbla. Po revoke: Warp Oblivion."""
        ok = self.bubbles.revoke_by_label(label)
        if ok:
            print(f"  [REVOKE] '{label}' → bubble_key='' | Warp Oblivion")
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
