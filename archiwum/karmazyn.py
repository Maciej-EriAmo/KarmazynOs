"""
karmazyn.py — Thermodynamic Memory Kernel v1.4
================================================
Jądro KarmazynOS. Korzysta z zewnętrznych modułów:
  - phi_space.py    (wspólna przestrzeń semantyczna)
  - hss_demo.py     (wielobitowy demon HSS)
  - hss_karmazyn_matrix.py (macierz termodynamiczna, importowana przez phi_space)
  - phi_store.py    (opcjonalnie, podłączany w runtime/shell)

Nie duplikuje klas ani stałych – importuje je z jednego źródła.
"""

import os, sys, hashlib, hmac, math, time
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from collections import Counter
from Crypto.Cipher import AES

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

# Współdzielone moduły
from phi_space import PhiSpace, ALPHA, LAMBDA_DECAY, DELTA_T_BASE, STOPWORDS
from hss_demo import HSSDaemon, kdf, decrypt_multibit, N, Q, RLWEResult, HistoryEntry

VERSION = "1.4"

# =====================================================================
# Funkcje pomocnicze (pozostają w jądrze)
# =====================================================================
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
    return hmac.HMAC(key, label.encode() + content, hashlib.sha256).digest()

def _hamming_distance(a: bytes, b: bytes) -> int:
    xor = bytes(x ^ y for x, y in zip(a, b))
    return sum(bin(byte).count('1') for byte in xor)

# =====================================================================
# Bubble
# =====================================================================
@dataclass
class Bubble:
    id: str; label: str; S_struct: np.ndarray; S_sem: np.ndarray; fingerprint: bytes
    bubble_key: bytes; encrypted_content: bytes; inode: str; epoch_born: int
    recall_count: int = 0; consolidated_from: str = ""; metadata: Dict = field(default_factory=dict)
    decay_start_epoch: Optional[int] = None; decay_rate: float = 0.0
    immortal: bool = False

    def is_alive(self): return bool(self.bubble_key)

    def liveliness(self, current_epoch: int) -> float:
        if self.decay_start_epoch is None or self.decay_rate <= 0: return 1.0
        elapsed = max(0, current_epoch - self.decay_start_epoch)
        return math.exp(-self.decay_rate * elapsed)

    def decrypt_content(self):
        key = self.bubble_key if self.bubble_key else b"revoked_warp_oblivion"
        return _xor_crypt(self.encrypted_content, key)

# =====================================================================
# BubbleStore
# =====================================================================
class BubbleStore:
    def __init__(self, phi2_bytes: bytes, s_sess: np.ndarray):
        self._b: Dict[str, Bubble] = {}; self._idx: Dict[str, str] = {}
        self._phi2 = phi2_bytes; self._s = s_sess; self._rev: set = set()

    def _make_key(self, bid: str):
        return hashlib.sha256(self._phi2 + b"bubble:" + bid.encode()).digest()

    def bubble_s_agent(self, bubble: Bubble):
        hex_key = bubble.bubble_key.hex() if bubble.bubble_key else "revoked"
        return kdf(self._s.tobytes(), f"bubble:{hex_key}")

    def store(self, label, S_struct, S_sem, content_raw, inode, epoch,
              consolidated_from="", metadata=None, immortal=False, bid_override=None):
        if bid_override:
            bid = bid_override
        else:
            bid = "bubble_" + hashlib.md5((label+str(epoch)).encode()).hexdigest()[:12]
        key = self._make_key(bid)
        fp = _compute_fingerprint(content_raw, key, label)
        b = Bubble(
            id=bid, label=label, S_struct=S_struct.copy(), S_sem=S_sem.copy(),
            fingerprint=fp, bubble_key=key,
            encrypted_content=_xor_crypt(content_raw, key),
            inode=inode, epoch_born=epoch,
            consolidated_from=consolidated_from,
            metadata=metadata or {},
            immortal=immortal,
        )
        self._b[bid] = b; self._idx[label] = bid
        return b

    def recall(self, q_sem, current_epoch, k=3, bias=1.5):
        res = []
        for bid, b in self._b.items():
            if bid in self._rev or not b.is_alive(): continue
            liv = b.liveliness(current_epoch)
            if liv <= 1e-9: continue
            sim = float(np.dot(q_sem, b.S_sem)); score = sim * bias * liv
            res.append((score, b))
        res.sort(key=lambda x: x[0], reverse=True)
        for _, b in res[:k]:
            b.recall_count += 1
            if b.decay_start_epoch is not None:
                elapsed = current_epoch - b.decay_start_epoch
                b.decay_start_epoch = current_epoch - elapsed * 0.7
        return res[:k]

    def get_by_label(self, label): return self._b.get(self._idx.get(label))
    def revoke_by_label(self, label):
        bid = self._idx.get(label)
        if bid in self._b:
            if self._b[bid].immortal:
                print(f"  [!] Bąbel '{label}' jest nieśmiertelny – odmowa revoke")
                return False
            self._b[bid].bubble_key = b""
            self._rev.add(bid)
            return True
        return False
    def cleanup_revoked(self):
        removed = 0
        for bid in list(self._rev):
            b = self._b.pop(bid, None)
            if b:
                if self._idx.get(b.label) == bid: del self._idx[b.label]
                removed += 1
        self._rev.clear()
        return removed
    def mark_for_decay(self, label, start_epoch, rate):
        b = self.get_by_label(label)
        if b:
            if b.immortal:
                print(f"  [!] Bąbel '{label}' jest nieśmiertelny – odmowa decay")
                return False
            b.decay_start_epoch = start_epoch
            b.decay_rate = rate
            return True
        return False
    def refresh_bubble(self, label):
        b = self.get_by_label(label)
        if b:
            b.decay_start_epoch = None; b.decay_rate = 0.0
            return True
        return False
    def remove_bubble(self, label):
        bid = self._idx.get(label)
        if bid and bid in self._b:
            if self._b[bid].immortal:
                print(f"  [!] Bąbel '{label}' jest nieśmiertelny – odmowa remove")
                return False
            del self._b[bid]; del self._idx[label]
            if bid in self._rev: self._rev.remove(bid)
            return True
        return False
    def remove_bubbles(self, labels):
        """
        Zbiorcze usuwanie bąbli — jedna operacja zamiast N pojedynczych
        wywołań remove_bubble w pętli (batch API z jednym podsumowaniem
        zamiast N komunikatów; jedno set-difference na _rev zamiast N remove).
        Nieśmiertelne pomijane. Zwraca (usuniete: list, odmowa: list).
        """
        removed, refused = [], []
        removed_bids = set()
        for label in labels:
            bid = self._idx.get(label)
            if not bid or bid not in self._b:
                continue
            if self._b[bid].immortal:
                refused.append(label)
                continue
            del self._b[bid]
            del self._idx[label]
            removed_bids.add(bid)
            removed.append(label)
        if removed_bids:
            self._rev.difference_update(removed_bids)   # _rev to set → różnica zbiorów
        return removed, refused
    @property
    def count(self): return len(self._b) - len(self._rev)
    @property
    def count_decaying(self):
        return sum(1 for b in self._b.values()
                   if b.decay_start_epoch is not None and b.id not in self._rev)
    @property
    def all_active(self):
        return [b for bid, b in self._b.items() if bid not in self._rev]

# =====================================================================
# Hologram
# =====================================================================
@dataclass
class Hologram:
    id: str; topic: str; proto: np.ndarray; generators: List[np.ndarray]
    weights: List[float]; bubble_labels: List[str]; epoch_created: int
    decay_rate: float = 0.001; metadata: Dict = field(default_factory=dict)
    def liveliness(self, current_epoch):
        elapsed = max(0, current_epoch - self.epoch_created)
        return math.exp(-self.decay_rate * elapsed)

# =====================================================================
# KarmazynOS – jądro systemu
# =====================================================================
class KarmazynOS:
    _P2S_BUBBLE_LABEL = "__phi_identity_p2s__"
    _P2S_BID = "phi_identity_p2s"

    def __init__(self, dim=15, n_sessions=1, seed=42, auto_cleanup_interval=50):
        self.phi = PhiSpace(dim, n_sessions, seed)
        self.daemon = HSSDaemon(bits_per_element=2)
        phi2_vec = np.frombuffer(self.phi.phi2_bytes() * 4, dtype=np.float32)[:N]
        self._s_sess = self.daemon.init_phi_session(phi2_vec, phi_pid=0)
        self.bubbles = BubbleStore(self.phi.phi2_bytes(), self._s_sess)
        self._amap: Dict[str, str] = {}; self._fp: Dict[str, bytes] = {}
        self._raw: Dict[str, bytes] = {}; self._ac: Dict[str, int] = {}
        self._agents: Dict[str, Dict] = {}
        self._auto_cleanup_interval = auto_cleanup_interval
        self._steps_since_cleanup = 0
        self.holograms: Dict[str, Hologram] = {}
        self.crimson_key: Optional[bytes] = None
        self._peer_phi2_bytes: Optional[bytes] = None
        self._pid = 0   # licznik kompatybilności dla soul_store
        self._init_p2s_bubble()
        print(f"  KarmazynOS v{VERSION} — Thermodynamic Memory Kernel")
        print(f"  Φ + Bąble + Hologramy | T_vacuum = {self.phi.t_vacuum:.4f} bit")

    # ── Tożsamość ────────────────────────────────────────────────────
    def _init_p2s_bubble(self):
        if self.bubbles.get_by_label(self._P2S_BUBBLE_LABEL) is None:
            self.write_p2s_bubble()
            print(f"  [Φ-ID] Utworzono bąbel tożsamości: {self.get_phi_id()}")
        else:
            print(f"  [Φ-ID] Węzeł: {self.get_phi_id()}")

    def write_p2s_bubble(self):
        label = self._P2S_BUBBLE_LABEL
        old = self.bubbles.get_by_label(label)
        if old:
            self.bubbles.remove_bubble(label)
        content_raw = self.phi._p2s
        s_str = self.phi.embed_structural(content_raw)
        s_sem = self.phi.embed_semantic(content_raw)
        inode = f"karmazyn://identity/{label}"
        vec = np.frombuffer(content_raw[:N], dtype=np.uint8).astype(np.int64)
        self.daemon.phi_write(inode, vec)
        self.bubbles.store(
            label=label, S_struct=s_str, S_sem=s_sem,
            content_raw=content_raw, inode=inode, epoch=self.phi.epoch,
            consolidated_from="__system__",
            metadata={"type": "phi_identity", "phi_id": self.get_phi_id()},
            immortal=True,
            bid_override=self._P2S_BID
        )

    def read_p2s_bubble(self) -> Optional[bytes]:
        b = self.bubbles.get_by_label(self._P2S_BUBBLE_LABEL)
        if not b: return None
        try:
            raw = b.decrypt_content()
            if len(raw) == 32: return raw
            return None
        except Exception as e:
            print(f"  [!] Błąd odczytu bąbla _p2s: {e}")
            return None

    def get_phi_id(self) -> str:
        return hashlib.sha256(self.phi._p2s + b"phi-identity-v1").hexdigest()[:32]

    def get_p2s_commitment(self, nonce: bytes, peer_phi_id: str) -> bytes:
        b = self.bubbles.get_by_label(self._P2S_BUBBLE_LABEL)
        if not b: raise RuntimeError("Brak bąbla tożsamości")
        phi_id_bytes = bytes.fromhex(self.get_phi_id())
        peer_bytes = bytes.fromhex(peer_phi_id) if peer_phi_id else b""
        return hmac.HMAC(b.bubble_key, phi_id_bytes + nonce + peer_bytes, hashlib.sha256).digest()

    def verify_peer_commitment(self, peer_phi_id: str, peer_nonce: bytes,
                               peer_commitment: bytes, peer_phi2_bytes_hex: str) -> bool:
        peer_phi2_bytes = bytes.fromhex(peer_phi2_bytes_hex)
        peer_bubble_key = hashlib.sha256(
            peer_phi2_bytes + b"bubble:" + self._P2S_BID.encode()
        ).digest()
        my_phi_id_bytes = bytes.fromhex(self.get_phi_id())
        peer_phi_id_bytes = bytes.fromhex(peer_phi_id)
        expected = hmac.HMAC(peer_bubble_key,
                             peer_phi_id_bytes + peer_nonce + my_phi_id_bytes,
                             hashlib.sha256).digest()
        return hmac.compare_digest(expected, peer_commitment)

    # ── Karmazynowy Uścisk Dłoni ────────────────────────────────────
    def get_phi2_vector(self, dim=128) -> np.ndarray:
        seed_bytes = self.phi.phi2_bytes()
        seed_int = int.from_bytes(seed_bytes[:4], 'big')
        rng = np.random.default_rng(seed_int)
        vec = rng.standard_normal(dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 1e-9: vec = vec / norm
        return vec

    def _get_blinding(self, K: bytes, tag: str, length: int) -> np.ndarray:
        seed = hashlib.sha256(K + tag.encode()).digest()
        rng = np.random.default_rng(int.from_bytes(seed[:4], 'big'))
        return rng.standard_normal(length).astype(np.float32)

    def crimson_handshake(self, peer_blinded_bytes: bytes, is_initiator: bool,
                          K: bytes, peer_phi2_bytes_hex: str) -> Tuple[bool, Optional[bytes]]:
        dim = len(peer_blinded_bytes) // 4
        peer_blinded = np.frombuffer(peer_blinded_bytes, dtype=np.float32)
        peer_tag = "blind-B" if is_initiator else "blind-A"
        blind = self._get_blinding(K, peer_tag, dim)
        peer_phi2 = peer_blinded - blind
        my_phi2 = self.get_phi2_vector(dim)
        norm_self = np.linalg.norm(my_phi2)
        norm_peer = np.linalg.norm(peer_phi2)
        if norm_self < 1e-9 or norm_peer < 1e-9:
            return False, None
        rez = float(np.dot(my_phi2, peer_phi2) / (norm_self * norm_peer))
        if rez >= 0.8:
            my_phi2_bytes = self.phi.phi2_bytes()
            peer_phi2_bytes = bytes.fromhex(peer_phi2_bytes_hex)
            self._peer_phi2_bytes = peer_phi2_bytes
            phi_a, phi_b = sorted([my_phi2_bytes, peer_phi2_bytes])
            self.crimson_key = hashlib.sha256(
                K + phi_a + phi_b + b"crimson-channel"
            ).digest()
            confirm = self._get_blinding(K, "confirm", dim)
            return True, confirm.tobytes()
        else:
            self.crimson_key = None
            return False, None

    def crimson_encrypt(self, plaintext: str) -> bytes:
        if self.crimson_key is None:
            raise RuntimeError("Brak karmazynowego klucza sesji")
        from Crypto.Cipher import AES
        cipher = AES.new(self.crimson_key[:32], AES.MODE_GCM)
        ct, tag = cipher.encrypt_and_digest(plaintext.encode('utf-8'))
        return cipher.nonce + ct + tag

    def crimson_decrypt(self, ciphertext: bytes) -> str:
        if self.crimson_key is None:
            raise RuntimeError("Brak karmazynowego klucza sesji")
        from Crypto.Cipher import AES
        nonce = ciphertext[:16]; ct = ciphertext[16:-16]; tag = ciphertext[-16:]
        cipher = AES.new(self.crimson_key[:32], AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ct, tag).decode('utf-8')

    # ── Zapis / Odczyt ──────────────────────────────────────────────
    def _content_to_hss_vec(self, content: bytes) -> np.ndarray:
        h = hashlib.sha256(content).digest()
        extended = (h * ((N // len(h)) + 1))[:N]
        vals = []
        for byte in extended:
            vals.append((byte >> 6) & 0x3)
            vals.append((byte >> 4) & 0x3)
            vals.append((byte >> 2) & 0x3)
            vals.append(byte & 0x3)
        return np.array(vals[:N], dtype=np.int64)

    def _hss_vec_to_bytes(self, vec: np.ndarray) -> bytes:
        if len(vec) % 4 != 0:
            pad = 4 - (len(vec) % 4)
            vec = np.concatenate([vec, np.zeros(pad, dtype=vec.dtype)])
        out = bytearray()
        for i in range(0, len(vec), 4):
            byte_val = (int(vec[i]) << 6) | (int(vec[i+1]) << 4) | \
                       (int(vec[i+2]) << 2) | int(vec[i+3])
            out.append(byte_val)
        return bytes(out)

    def write(self, content: str, auto_consolidate=0):
        raw = content.encode()
        label = self.phi.add(raw)
        vec = self._content_to_hss_vec(raw)
        inode = f"karmazyn://phi/{label}"
        self.daemon.phi_write(inode, vec)
        self._amap[label] = inode
        self._fp[label] = hashlib.sha256(raw).digest()
        self._raw[label] = raw
        self._ac[label] = auto_consolidate
        return label

    def consolidate(self, label, metadata=None):
        if label not in self._amap: return None
        raw = self._raw.get(label, label.encode())
        phi_a = next((a for a in self.phi._mx.atoms if a.get('label') == label), None)
        s_str = phi_a['S'].copy() if phi_a else self.phi.embed_structural(raw)
        s_sem = self.phi._sem.get(label, self.phi.embed_semantic(raw)).copy()
        b_inode = f"karmazyn://bubbles/{label}"
        vec = self._content_to_hss_vec(raw)
        self.daemon.phi_write(b_inode, vec)
        bubble = self.bubbles.store(
            label=label, S_struct=s_str, S_sem=s_sem,
            content_raw=raw, inode=b_inode, epoch=self.phi.epoch,
            consolidated_from=label, metadata=metadata or {}
        )
        print(f"  [KONSOLIDACJA] '{label[:30]}' → {bubble.id}")
        return bubble.id

    def _auto_check(self, label):
        thresh = self._ac.get(label, 0)
        if thresh > 0 and self.phi.recall_count(label) >= thresh:
            if self.bubbles.get_by_label(label) is None:
                print(f"  [AUTO] '{label[:25]}' recall≥{thresh} → consolidate")
                self.consolidate(label)

    def recall(self, query: str, k=5):
        raw = query.encode(); q_sem = self.phi.embed_semantic(raw)
        k_phi = max(1, int(k * 0.6)); k_bub = max(1, k - k_phi)
        phi_res = []
        for atom, sim in self.phi.recall(raw, k=k_phi):
            lbl = atom.get('label', ''); s_sem = self.phi._sem.get(lbl, atom['S'])
            sim_f = max(0.0, float(np.dot(q_sem, s_sem)))
            phi_res.append({'label': lbl, 'layer': 'phi', 'T': atom['T'], 'sim': sim_f,
                            'score': sim_f * atom['T'], 'inode': self._amap.get(lbl, ''),
                            'bubble_id': None})
            self._auto_check(lbl)
        bias = self._bubble_bias(); bub_res = []
        current_epoch = self.phi.epoch
        for score, b in self.bubbles.recall(q_sem, current_epoch, k=k_bub, bias=bias):
            liv = b.liveliness(current_epoch)
            bub_res.append({'label': b.label, 'layer': 'bubble', 'T': float('inf'),
                            'sim': score / (bias * liv) if liv > 0 else 0.0,
                            'score': score, 'inode': b.inode, 'bubble_id': b.id,
                            'liveliness': liv})
        all_res = phi_res + bub_res
        all_res.sort(key=lambda x: x['score'], reverse=True)
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
        T_init = DELTA_T_BASE * (0.3 + 0.7 * liv) + 0.1 * math.log1p(b.recall_count)
        T_init = min(T_init, DELTA_T_BASE * 2.0)
        content = b.decrypt_content()
        new_label = self.phi.add(content, label=f"react_{label}", init_T=T_init)
        print(f"  [REAKTYWACJA] '{label[:30]}' → {new_label} (T={T_init:.2f})")
        return new_label

    def evaluate(self, context):
        raw = context.encode(); q_sem = self.phi.embed_semantic(raw)
        phi_a = self.phi._mx.atoms; bubs = self.bubbles.all_active; all_s = []
        s_phi = 0.0
        if phi_a:
            sims = [max(0.0, float(np.dot(q_sem, self.phi._sem.get(a['label'], a['S']))))
                    for a in phi_a]
            all_s.extend(sims)
            s_phi = sum(s * a['T'] for s, a in zip(sims, phi_a)) / len(phi_a)
        s_bub = 0.0
        if bubs:
            simsb = [max(0.0, float(np.dot(q_sem, b.S_sem))) for b in bubs]
            all_s.extend(simsb); s_bub = sum(simsb) / len(bubs)
        score = 0.6 * s_phi + 0.4 * s_bub
        theta = max(float(np.percentile(all_s, 60)), 0.1) if all_s else 0.3
        allow = score > theta
        reason = (f"score={score:.3f} [φ={s_phi:.3f} b={s_bub:.3f}] "
                  f"{'>' if allow else '≤'} θ={theta:.3f}")
        return allow, score, reason

    # ── Agenci ──────────────────────────────────────────────────────
    def derive_agent(self, name: str, task: str, prisms: List[str] = None) -> Tuple[str, np.ndarray]:
        self._pid += 1
        agent_uuid = hashlib.sha256(f"{name}:{task}:{time.time()}".encode()).hexdigest()[:16]
        s_agent = self.daemon.derive_agent_key(agent_uuid, task, prisms)
        self._agents[agent_uuid] = {"task": task, "prisms": prisms or ["core"], "s_agent": s_agent}
        return agent_uuid, s_agent

    def read_as_agent(self, label: str, agent_uuid: str, from_bubble: bool = False):
        if agent_uuid not in self._agents:
            return {'error': f'Agent {agent_uuid} nieznany'}
        agent_info = self._agents[agent_uuid]
        task = agent_info['task']; prisms = agent_info['prisms']; s_agent = agent_info['s_agent']

        if from_bubble:
            b = self.bubbles.get_by_label(label)
            if not b: return {'error': f'bąbel {label} nieznany'}
            inode = b.inode; s_eff = self.bubbles.bubble_s_agent(b); fp = b.fingerprint
        else:
            inode = self._amap.get(label)
            if not inode: return {'error': f'atom {label} nieznany'}
            s_eff = s_agent; fp = self._fp.get(label)

        entries = self.daemon.upcall_read(agent_uuid, inode, prisms, task)
        if entries is None:
            return {'error': 'ODMOWA – brak wspólnego prisma'}
        if not entries:
            return {'error': 'pusta projekcja – brak danych'}

        out = {}
        for entry in entries:
            bits = decrypt_multibit(s_eff, entry.results, entry.bits_per_element)
            recovered_bytes = self._hss_vec_to_bytes(bits)
            if fp and len(recovered_bytes) >= len(fp):
                hamming = _hamming_distance(fp, recovered_bytes[:len(fp)])
                n_bits = len(fp) * 8
                mean = n_bits * 0.5
                std = math.sqrt(n_bits * 0.5 * 0.5)
                threshold = int(mean + 2 * std)
                sig = hamming <= threshold
                out[entry.results[0].projection_id] = {
                    'signal': sig, 'hamming': hamming,
                    'status': f'{"✓ SYGNAŁ" if sig else "✗ SZUM"} (h={hamming})'
                }
            else:
                out[entry.results[0].projection_id] = {
                    'signal': False, 'status': '✗ SZUM (brak fp)'
                }
        return out

    # ── Bąble / Hologramy / Krok ────────────────────────────────────
    def mark_bubble_for_decay(self, label, rate=0.01):
        return self.bubbles.mark_for_decay(label, self.phi.epoch, rate)
    def refresh_bubble(self, label):
        return self.bubbles.refresh_bubble(label)
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
        data = np.array(vectors); proto = np.mean(data, axis=0)
        proto /= np.linalg.norm(proto) + 1e-9
        centered = data - proto; cov = centered.T @ centered / len(data)
        eigvals, eigvecs = np.linalg.eigh(cov)
        k = min(n_components, len(eigvals)); top_idx = np.argsort(eigvals)[-k:]
        generators = [eigvecs[:, i] for i in top_idx]
        weights = [float(eigvals[i]) for i in top_idx]
        max_w = max(weights) if weights else 1.0
        weights = [w / max_w for w in weights]
        hid = f"idea_{topic}_{self.phi.epoch}_{hashlib.md5(topic.encode()).hexdigest()[:6]}"
        self.holograms[hid] = Hologram(
            id=hid, topic=topic, proto=proto, generators=generators,
            weights=weights, bubble_labels=labels, epoch_created=self.phi.epoch
        )
        print(f"  [IDEA] Utworzono '{hid}' z {len(labels)} bąbli")
        if remove_originals:
            removed, refused = self.bubbles.remove_bubbles(labels)
            msg = f"  [IDEA] Usunięto {len(removed)} oryginalnych bąbli"
            if refused:
                msg += f" (pominięto nieśmiertelne: {len(refused)})"
            print(msg)
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
        return [{'label': b.label, 'sim': sim} for sim, b in scores[:k]]
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
        iso = np.random.normal(0, 0.05 * temperature, size=base.shape)
        synthetic = base + noise + iso
        synthetic /= np.linalg.norm(synthetic) + 1e-9
        synthetic *= liv
        return synthetic
    def rehydrate_hologram(self, hologram_id):
        h = self.holograms.get(hologram_id)
        if not h: return []
        restored = []
        for i in range(len(h.generators)):
            vec = h.proto.copy(); label = f"rehyd_{h.id}_{i}"
            self.phi.add_semantic_vector(vec, label=label)
            restored.append(label)
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
    def _bubble_bias(self):
        n_eff_b = sum(b.liveliness(self.phi.epoch) for b in self.bubbles.all_active)
        n_eff_h = sum(h.liveliness(self.phi.epoch) * 0.5 for h in self.holograms.values())
        return 1.0 + 0.5 * math.log1p(n_eff_b + n_eff_h)
    def stats(self):
        s = self.phi.stats()
        return {**s, "version": VERSION, "atoms_phi": s["atoms"],
                "bubbles": self.bubbles.count,
                "bubbles_decaying": self.bubbles.count_decaying,
                "bubbles_revoked": len(self.bubbles._rev),
                "holograms": len(self.holograms),
                "bubble_bias": self._bubble_bias(),
                "phi_id": self.get_phi_id()}
    def save(self, path="./karmazyn_data"):
        try:
            from soul_store import save_soul
            return save_soul(self, path)
        except ImportError:
            print("  [!] soul_store.py nieodnaleziony.")
            return False
    def load(self, path="./karmazyn_data"):
        try:
            from soul_store import load_soul
            return load_soul(self, path)
        except ImportError:
            print("  [!] soul_store.py nieodnaleziony.")
            return False
    def __repr__(self):
        s = self.stats()
        return (f"KarmazynOS(v{VERSION} | φ={s['atoms_phi']} T={s['temperature']:.2f} | "
                f"bąble={s['bubbles']} bias={s['bubble_bias']:.2f} | "
                f"idee={s['holograms']} | Φ-ID={s['phi_id'][:12]}…)")

# ========================================================================
#  TESTY
# ========================================================================
if __name__ == "__main__":
    print("=== Testy KarmazynOS v1.4 ===")
    kernel = KarmazynOS(dim=15, n_sessions=1, seed=123)

    print("\n[Test 1] Zapis i odczyt percepcyjny")
    label = kernel.write("Sekret Karmazyna: Φ² rezonuje w próżni.")
    alice_uuid, _ = kernel.derive_agent("Alicja", "analiza", ["science", "medical"])
    res = kernel.read_as_agent(label, alice_uuid)
    assert 'error' not in res, f"Błąd odczytu: {res}"
    print(f"  Wynik odczytu: {res}")

    print("\n[Test 2] Odmowa dostępu")
    eve_uuid, _ = kernel.derive_agent("Eve", "szpieg", ["covert"])
    res_eve = kernel.read_as_agent(label, eve_uuid)
    assert 'error' in res_eve and 'ODMOWA' in res_eve['error']
    print(f"  Eve: {res_eve}")

    print("\n[Test 3] Degradacja przy niezgodnym tasku")
    bob_uuid, s_bob = kernel.derive_agent("Bob", "zapis", ["science", "kernel"])
    inode = kernel._amap[label]
    entries = kernel.daemon.upcall_read(bob_uuid, inode, ["science"], "analiza")
    assert entries is not None
    rec = decrypt_multibit(s_bob, entries[0].results, entries[0].bits_per_element)
    orig_vec = kernel._content_to_hss_vec("Sekret Karmazyna: Φ² rezonuje w próżni.".encode())
    match = np.mean(rec[:len(orig_vec)] == orig_vec)
    print(f"  Zgodność z oryginałem: {match*100:.1f}%")
    assert match < 1.0, "Szum powinien powodować błędy"
    print("  OK – degradacja działa.")

    print("\n[Test 4] Crimson Handshake")
    kernel2 = KarmazynOS(dim=15, n_sessions=1, seed=999)
    kernel2.phi._p2s = kernel.phi._p2s
    kernel2._init_p2s_bubble()
    K = os.urandom(32)
    dim = 128
    my_phi2 = kernel.get_phi2_vector(dim)
    peer_phi2 = kernel2.get_phi2_vector(dim)
    blind_a = kernel._get_blinding(K, "blind-A", dim)
    blind_b = kernel2._get_blinding(K, "blind-B", dim)
    peer_blinded = (my_phi2 + blind_a).tobytes()
    initiator_blinded = (peer_phi2 + blind_b).tobytes()
    peer_hex = kernel2.phi.phi2_bytes().hex()
    ok, _ = kernel.crimson_handshake(initiator_blinded, True, K, peer_hex)
    assert ok
    my_hex = kernel.phi.phi2_bytes().hex()
    ok2, _ = kernel2.crimson_handshake(peer_blinded, False, K, my_hex)
    assert ok2
    assert kernel.crimson_key == kernel2.crimson_key
    print("  Klucz karmazynowy OK.")
    ct = kernel.crimson_encrypt("Witaj, Karmazynie!")
    pt = kernel2.crimson_decrypt(ct)
    assert pt == "Witaj, Karmazynie!"
    print("  Szyfrowanie OK.")

    print("\n=== Wszystkie testy przeszły pomyślnie ===")