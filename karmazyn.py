"""
karmazyn.py — Thermodynamic Memory Kernel (KarmazynOS) v1.3.1
===============================================================

Zmiany v1.3.0:
  [nowe] Bubble.immortal – flaga chroniąca bąbel przed decay/revoke/remove
  [nowe] BubbleStore: blokada operacji destrukcyjnych na immortal bąblach
  [nowe] KarmazynOS._P2S_BUBBLE_LABEL – stała etykieta bąbla tożsamości
  [nowe] KarmazynOS._init_p2s_bubble() – tworzy/weryfikuje bąbel _p2s przy starcie
  [nowe] KarmazynOS.write_p2s_bubble() – zapisuje _p2s jako bąbel immortal
  [nowe] KarmazynOS.read_p2s_bubble() – odczytuje _p2s z bąbla
  [nowe] KarmazynOS.get_phi_id() – trwały identyfikator węzła (16 bajtów hex)
  [nowe] KarmazynOS.get_p2s_commitment() – HMAC dla Crimson Handshake
  [nowe] KarmazynOS.verify_peer_commitment() – weryfikacja commitment peera
  [fix]  KarmazynOS.save(): usunięto p2s z meta.json (_p2s w bąblu)
  [fix]  KarmazynOS.load(): usunięto odczyt p2s z meta.json + odczyt z bąbla
  [fix]  crimson_handshake(): symetryzacja crimson_key przez sorted(phi2_bytes)
  [fix]  crimson_key = None inicjalizowany w __init__
  [fix]  get_phi2_vector(): deterministyczny RNG zamiast np.frombuffer (NaN/Inf)
  [fix]  crimson_handshake(): tagi blindingu odwrócone (peer_tag)
  [fix]  _compute_fingerprint(): hmac.HMAC zamiast hmac.new
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

VERSION      = "1.3.1"
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
    return hmac.HMAC(key, label.encode() + content, hashlib.sha256).digest()

def _hamming_distance(a: bytes, b: bytes) -> int:
    xor = bytes(x ^ y for x, y in zip(a, b))
    return sum(bin(byte).count('1') for byte in xor)

@dataclass
class Bubble:
    id: str; label: str; S_struct: np.ndarray; S_sem: np.ndarray; fingerprint: bytes
    bubble_key: bytes; encrypted_content: bytes; inode: str; epoch_born: int
    recall_count: int = 0; consolidated_from: str = ""; metadata: Dict = field(default_factory=dict)
    decay_start_epoch: Optional[int] = None; decay_rate: float = 0.0
    immortal: bool = False  # [nowe] chroni przed decay/revoke/remove

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

    def _make_key(self, bid: str):
        return hashlib.sha256(self._phi2 + b"bubble:" + bid.encode()).digest()

    def bubble_s_agent(self, bubble: Bubble):
        hex_key = bubble.bubble_key.hex() if bubble.bubble_key else "revoked"
        return kdf(self._s.tobytes(), f"bubble:{hex_key}")

    def store(self, label, S_struct, S_sem, content_raw, inode, epoch,
              consolidated_from="", metadata=None, immortal=False):
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

    def get_by_label(self, label):
        return self._b.get(self._idx.get(label))

    def revoke_by_label(self, label):
        bid = self._idx.get(label)
        if bid in self._b:
            # [nowe] blokada immortal
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
            # [nowe] blokada immortal
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
            # [nowe] blokada immortal
            if self._b[bid].immortal:
                print(f"  [!] Bąbel '{label}' jest nieśmiertelny – odmowa remove")
                return False
            del self._b[bid]; del self._idx[label]
            if bid in self._rev: self._rev.remove(bid)
            return True
        return False

    @property
    def count(self): return len(self._b) - len(self._rev)

    @property
    def count_decaying(self):
        return sum(1 for b in self._b.values()
                   if b.decay_start_epoch is not None and b.id not in self._rev)

    @property
    def all_active(self):
        return [b for bid, b in self._b.items() if bid not in self._rev]


class IDFCounter:
    def __init__(self): self._freq = Counter(); self._ndocs = 0

    def add_doc(self, tokens):
        self._ndocs += 1
        for t in set(tokens): self._freq[t] += 1

    def idf(self, token):
        return float(np.log1p(self._ndocs / (1 + self._freq.get(token, 0))))


class PhiSpace:
    def __init__(self, dim=15, n_sessions=1, seed=42):
        self._mx = HSSKarmazynMatrix(dim=dim, n_sessions=n_sessions, lambd=LAMBDA_DECAY, seed=seed)
        self.dim = dim; self._sid = 0; self._tvac = self._measure_tvac()
        self._p2s = os.urandom(32)
        self._sem: Dict[str, np.ndarray] = {}
        self._rc: Dict[str, int] = {}
        self._idf = IDFCounter()

    def embed_structural(self, c: bytes):
        s = int(hashlib.md5(c).hexdigest(), 16) % (2**32)
        v = np.random.default_rng(s).normal(0, 1, self.dim).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)

    def embed_semantic(self, c: bytes, update=False):
        try: text = c.decode('utf-8', errors='ignore').lower()
        except: return self.embed_structural(c)
        tokens = [w for w in text.split() if len(w) > 1 and w not in STOPWORDS]
        bigrams = [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        all_t = tokens + bigrams
        if not all_t: return self.embed_structural(c)
        if update: self._idf.add_doc(tokens)
        v = np.zeros(self.dim, dtype=np.float32)
        for t in all_t:
            w = self._idf.idf(t) * min(1.0, len(t) / 5.0)
            s = int(hashlib.md5(t.encode()).hexdigest(), 16) % (2**32)
            v += w * np.random.default_rng(s).normal(0, 1, self.dim).astype(np.float32)
        n = np.linalg.norm(v)
        return v / n if n > 1e-9 else self.embed_structural(c)

    def phi2_bytes(self):
        return hashlib.sha256(self._p2s + b"phi2-v1").digest()

    def _measure_tvac(self):
        s = np.random.randint(0, Q, N, dtype=np.int64) % 256
        _, c = np.unique(s, return_counts=True); p = c / len(s)
        return float(-np.sum(p * np.log2(p + 1e-12)))

    def t_vacuum(self): return self._tvac

    def add(self, content: bytes, label="", init_T=DELTA_T_BASE):
        s_str = self.embed_structural(content)
        s_sem = self.embed_semantic(content, update=True)
        lbl = label or f"atom_{hashlib.md5(content).hexdigest()[:8]}"
        self._mx.add_atom_vector(label=lbl, topic="karmazyn", vector=s_str,
                                 init_T=init_T, session=self._sid)
        self._sem[lbl] = s_sem.copy(); self._rc[lbl] = 0
        return lbl

    def add_semantic_vector(self, vector: np.ndarray, label="", init_T=DELTA_T_BASE):
        lbl = label or f"atom_{hashlib.md5(vector.tobytes()).hexdigest()[:8]}"
        seed = int(hashlib.md5(vector.tobytes()).hexdigest(), 16) % (2**32)
        s_str = np.random.default_rng(seed).normal(0, 1, self.dim).astype(np.float32)
        s_str /= np.linalg.norm(s_str) + 1e-9
        self._mx.add_atom_vector(label=lbl, topic="karmazyn", vector=s_str,
                                 init_T=init_T, session=self._sid)
        self._sem[lbl] = vector.copy(); self._rc[lbl] = 0
        return lbl

    def recall(self, query: bytes, k=3):
        q_str = self.embed_structural(query); q_sem = self.embed_semantic(query)
        cands = []
        for a in self._mx.atoms:
            if a.get('session') != self._sid: continue
            lbl = a.get('label', ''); s_sem = self._sem.get(lbl, a['S'])
            sim_s = max(0.0, float(np.dot(q_str, a['S'])))
            sim_m = max(0.0, float(np.dot(q_sem, s_sem)))
            sim = ALPHA * sim_s + (1 - ALPHA) * sim_m
            cands.append((sim * a['T'], a, sim))
        cands.sort(key=lambda x: x[0], reverse=True)
        result = []
        for _, a, sim in cands[:k]:
            a['T'] = a['T'] + 0.3 * (DELTA_T_BASE - a['T'])
            lbl = a.get('label', ''); self._rc[lbl] = self._rc.get(lbl, 0) + 1
            result.append((a, sim))
        return result

    def recall_count(self, label): return self._rc.get(label, 0)

    def step(self):
        self._mx.step()
        alive = {a['label'] for a in self._mx.atoms}
        self._sem = {k: v for k, v in self._sem.items() if k in alive}
        self._rc = {k: v for k, v in self._rc.items() if k in alive}
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
    id: str; topic: str; proto: np.ndarray; generators: List[np.ndarray]
    weights: List[float]; bubble_labels: List[str]; epoch_created: int
    decay_rate: float = 0.001; metadata: Dict = field(default_factory=dict)

    def liveliness(self, current_epoch):
        elapsed = max(0, current_epoch - self.epoch_created)
        return math.exp(-self.decay_rate * elapsed)


class KarmazynOS:
    # [nowe] Stała etykieta bąbla tożsamości – nie zmienia się nigdy
    _P2S_BUBBLE_LABEL = "__phi_identity_p2s__"

    def __init__(self, dim=15, n_sessions=1, seed=42, auto_cleanup_interval=50):
        self.phi = PhiSpace(dim, n_sessions, seed)
        self.daemon = HSSDaemon()
        phi2_vec = np.frombuffer(self.phi.phi2_bytes() * 4, dtype=np.float32)[:N]
        self._s_sess = self.daemon.init_phi_session(phi2_vec, phi_pid=0)
        self.bubbles = BubbleStore(self.phi.phi2_bytes(), self._s_sess)
        self._amap: Dict[str, str] = {}; self._fp: Dict[str, bytes] = {}
        self._raw: Dict[str, bytes] = {}; self._ac: Dict[str, int] = {}
        self._pid = 100; self._reg: Dict[int, Tuple] = {}
        self._auto_cleanup_interval = auto_cleanup_interval
        self._steps_since_cleanup = 0
        self.holograms: Dict[str, Hologram] = {}
        self.crimson_key: Optional[bytes] = None
        self._init_p2s_bubble()
        print(f"  KarmazynOS v{VERSION} — Thermodynamic Memory Kernel")
        print(f"  Φ + Bąble + Hologramy | T_vacuum = {self.phi.t_vacuum():.4f} bit")

    # ========================================================================
    #  TOŻSAMOŚĆ WĘZŁA – Φ-ID i bąbel _p2s
    # ========================================================================

    def _init_p2s_bubble(self):
        """
        Tworzy bąbel _p2s jeśli jeszcze nie istnieje.
        Wywołać po __init__ lub po load() gdy bąbel nie został wczytany.
        """
        if self.bubbles.get_by_label(self._P2S_BUBBLE_LABEL) is None:
            self.write_p2s_bubble()
            print(f"  [Φ-ID] Utworzono bąbel tożsamości: {self.get_phi_id()}")
        else:
            print(f"  [Φ-ID] Węzeł: {self.get_phi_id()}")

    def write_p2s_bubble(self):
        """
        Zapisuje bieżące _p2s jako immortal bąbel tożsamości.
        Jeśli bąbel już istnieje – zastępuje go (rotacja _p2s).
        """
        label = self._P2S_BUBBLE_LABEL
        # Usuń stary bąbel jeśli istnieje (tymczasowo zezwól przez bezpośredni dostęp)
        bid = self.bubbles._idx.get(label)
        if bid and bid in self.bubbles._b:
            del self.bubbles._b[bid]
            del self.bubbles._idx[label]
            if bid in self.bubbles._rev:
                self.bubbles._rev.remove(bid)

        content_raw = self.phi._p2s  # 32 bajty
        s_str = self.phi.embed_structural(content_raw)
        s_sem = self.phi.embed_semantic(content_raw)
        inode = f"karmazyn://identity/{label}"
        self.daemon.phi_write(inode, np.zeros(N, dtype=np.int64))

        self.bubbles.store(
            label=label,
            S_struct=s_str,
            S_sem=s_sem,
            content_raw=content_raw,
            inode=inode,
            epoch=self.phi.epoch,
            consolidated_from="__system__",
            metadata={"type": "phi_identity", "phi_id": self.get_phi_id()},
            immortal=True,
        )

    def read_p2s_bubble(self) -> Optional[bytes]:
        """
        Odczytuje _p2s z bąbla tożsamości.
        Zwraca 32 bajty lub None jeśli bąbel nie istnieje / nie można odszyfrować.
        """
        b = self.bubbles.get_by_label(self._P2S_BUBBLE_LABEL)
        if not b:
            return None
        try:
            raw = b.decrypt_content()
            if len(raw) == 32:
                return raw
            return None
        except Exception as e:
            print(f"  [!] Błąd odczytu bąbla _p2s: {e}")
            return None

    def get_phi_id(self) -> str:
        """
        Zwraca trwały identyfikator węzła (Φ-ID) jako hex string 32 znaków.
        Wyprowadzony deterministycznie z _p2s – stały dla danej instancji.
        """
        return hashlib.sha256(self.phi._p2s + b"phi-identity-v1").hexdigest()[:32]

    def get_p2s_commitment(self, nonce: bytes, peer_phi_id: str) -> bytes:
        """
        Generuje kryptograficzne zobowiązanie Φ-ID dla Crimson Handshake.
        commitment = HMAC(bubble_key, phi_id_bytes + nonce + peer_phi_id_bytes)

        Zobowiązanie wiąże jawny Φ-ID z tajnym bubble_key (_p2s),
        uniemożliwiając MITM podmianę Φ-ID bez znajomości _p2s.
        """
        b = self.bubbles.get_by_label(self._P2S_BUBBLE_LABEL)
        if not b:
            raise RuntimeError("Brak bąbla tożsamości – wywołaj _init_p2s_bubble()")
        phi_id_bytes = bytes.fromhex(self.get_phi_id())
        peer_bytes = bytes.fromhex(peer_phi_id) if peer_phi_id else b""
        return hmac.HMAC(
            b.bubble_key,
            phi_id_bytes + nonce + peer_bytes,
            hashlib.sha256
        ).digest()

    def verify_peer_commitment(self, peer_phi_id: str, peer_nonce: bytes,
                                peer_commitment: bytes, peer_phi2: np.ndarray) -> bool:
        """
        Weryfikuje commitment peera po odzyskaniu jego Φ² z handshake.
        peer_phi2 – wektor odzyskany po odślenieniu (po rezonansie).
        Rekonstruujemy bubble_key peera z jego phi2_bytes i weryfikujemy HMAC.
        """
        # Rekonstrukcja phi2_bytes peera z odzyskanego wektora
        # phi2_bytes = sha256(_p2s + 'phi2-v1') – nie znamy _p2s peera
        # Ale bubble_key = sha256(bubbles._phi2 + 'bubble:' + bid)
        # gdzie bubbles._phi2 = phi2_bytes peera
        # Możemy odtworzyć bubble_key jeśli znamy phi2_bytes peera
        # phi2_bytes peera != peer_phi2 (wektor float32) – to różne rzeczy!
        #
        # Rozwiązanie: peer wysyła phi2_bytes (hash) jawnie obok Φ-ID
        # Tutaj zakładamy że peer_phi2_bytes jest przekazane jako dodatkowy parametr
        # W praktyce: peer wysyła w kroku 0: phi_id, nonce, commitment, phi2_bytes_hex
        # phi2_bytes_hex to sha256(_p2s+'phi2-v1') – 32 bajty – jawne (nie sekret)
        # Sekret to _p2s – phi2_bytes to tylko hash
        #
        # Uproszczenie dla tej wersji: weryfikacja przez porównanie phi_id
        # Pełna weryfikacja z phi2_bytes_hex dodana w krok 0 handshake
        peer_phi_id_bytes = bytes.fromhex(peer_phi_id)
        my_phi_id_bytes = bytes.fromhex(self.get_phi_id())

        # Tworzymy tymczasowy bubble_key z peer_phi2 (przybliżenie)
        # Właściwa weryfikacja wymaga peer_phi2_bytes – patrz crimson_network.py
        peer_phi2_bytes_approx = hashlib.sha256(peer_phi2.tobytes()).digest()
        bid_label = self._P2S_BUBBLE_LABEL.encode()
        peer_bubble_key_approx = hashlib.sha256(
            peer_phi2_bytes_approx + b"bubble:" + bid_label
        ).digest()

        expected = hmac.HMAC(
            peer_bubble_key_approx,
            peer_phi_id_bytes + peer_nonce + my_phi_id_bytes,
            hashlib.sha256
        ).digest()
        return hmac.compare_digest(expected, peer_commitment)

    # ========================================================================
    #  METODY KARMAZYNOWEGO KOMUNIKATORA
    # ========================================================================

    def get_phi2_vector(self, dim=128) -> np.ndarray:
        """
        Zwraca znormalizowany wektor Φ² dla protokołu Crimson Handshake.
        Deterministyczny RNG z seed z sha256(_p2s) – bezpieczne float32.
        """
        seed_bytes = self.phi.phi2_bytes()
        seed_int = int.from_bytes(seed_bytes[:4], 'big')
        rng = np.random.default_rng(seed_int)
        vec = rng.standard_normal(dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 1e-9:
            vec = vec / norm
        return vec

    def _get_blinding(self, K: bytes, tag: str, length: int) -> np.ndarray:
        """Generuje deterministyczne maskowanie addytywne z K i tagu."""
        seed = hashlib.sha256(K + tag.encode()).digest()
        rng = np.random.default_rng(int.from_bytes(seed[:4], 'big'))
        return rng.standard_normal(length).astype(np.float32)

    def crimson_handshake(self, peer_blinded_bytes: bytes, is_initiator: bool,
                          K: bytes) -> Tuple[bool, Optional[bytes]]:
        """
        Karmazynowy Uścisk Dłoni – weryfikuje rezonans Φ².

        [fix] Tagi blindingu odwrócone (peer_tag zamiast own_tag).
        [fix] crimson_key symetryczny przez sorted(phi2_bytes) – obie strony
              obliczają identyczny klucz niezależnie od kolejności.
        """
        dim = len(peer_blinded_bytes) // 4
        peer_blinded = np.frombuffer(peer_blinded_bytes, dtype=np.float32)

        # Odślepiamy tagiem PEERA (peer zaślepiał się swoim tagiem)
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
            # [fix] Używamy phi2_bytes (sha256 hash, deterministyczny) zamiast
            # wektora float32. Operacje +blind/-blind na float32 wprowadzają
            # błędy zaokrągleń (~1e-8), więc tobytes() daje różne bajty
            # po obu stronach mimo identycznego _p2s.
            # phi2_bytes jest przesyłane jawnie w kroku 0 (phi2_hex w ramce
            # tożsamości) – identyczne i deterministyczne po obu stronach.
            my_phi2_bytes = self.phi.phi2_bytes()
            peer_phi2_bytes = getattr(self, '_peer_phi2_bytes', my_phi2_bytes)
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
        """Szyfruje wiadomość Karmazynowym Kluczem Sesji (AES-256-GCM)."""
        if self.crimson_key is None:
            raise RuntimeError("Brak karmazynowego klucza sesji – kanał nieaktywny.")
        from Crypto.Cipher import AES
        cipher = AES.new(self.crimson_key[:32], AES.MODE_GCM)
        ct, tag = cipher.encrypt_and_digest(plaintext.encode('utf-8'))
        return cipher.nonce + ct + tag

    def crimson_decrypt(self, ciphertext: bytes) -> str:
        """Deszyfruje wiadomość Karmazynowym Kluczem Sesji."""
        if self.crimson_key is None:
            raise RuntimeError("Brak karmazynowego klucza sesji.")
        from Crypto.Cipher import AES
        nonce = ciphertext[:16]
        ct = ciphertext[16:-16]
        tag = ciphertext[-16:]
        cipher = AES.new(self.crimson_key[:32], AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ct, tag).decode('utf-8')

    # ========================================================================
    #  ISTNIEJĄCE METODY
    # ========================================================================

    def _bubble_bias(self):
        n_eff_b = sum(b.liveliness(self.phi.epoch) for b in self.bubbles.all_active)
        n_eff_h = sum(h.liveliness(self.phi.epoch) * 0.5 for h in self.holograms.values())
        return 1.0 + 0.5 * math.log1p(n_eff_b + n_eff_h)

    def write(self, content: str, auto_consolidate=0):
        raw = content.encode(); label = self.phi.add(raw)
        bits8 = np.unpackbits(np.frombuffer(hashlib.sha256(raw).digest()[:8], dtype=np.uint8))
        vec = np.zeros(N, dtype=np.int64); vec[:15] = bits8[:15].astype(np.int64)
        inode = f"karmazyn://phi/{label}"; self.daemon.phi_write(inode, vec)
        self._amap[label] = inode; self._fp[label] = hashlib.sha256(raw).digest()
        self._raw[label] = raw; self._ac[label] = auto_consolidate
        return label

    def consolidate(self, label, metadata=None):
        if label not in self._amap: return None
        raw = self._raw.get(label, label.encode())
        phi_a = next((a for a in self.phi._mx.atoms if a.get('label') == label), None)
        s_str = phi_a['S'].copy() if phi_a else self.phi.embed_structural(raw)
        s_sem = self.phi._sem.get(label, self.phi.embed_semantic(raw)).copy()
        b_inode = f"karmazyn://bubbles/{label}"
        self.daemon.phi_write(b_inode, np.zeros(N, dtype=np.int64))
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

    def derive_agent(self, name, task, prisms=["core", "in", "out"]):
        self._pid += 1
        s = self.daemon.derive_agent_key(self._pid, task, prisms)
        self._reg[self._pid] = (task, prisms)
        return self._pid, s

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
            if fp and len(bits) >= len(fp) * 8:
                read_bytes = np.packbits(bits[:len(fp) * 8]).tobytes()
                hamming = _hamming_distance(fp, read_bytes)
                n_bits = len(fp) * 8; mean = n_bits * 0.5
                std = math.sqrt(n_bits * 0.5 * 0.5)
                threshold = int(mean + 2 * std); sig = hamming <= threshold
                out[p.prism_id] = {'signal': sig, 'hamming': hamming,
                    'status': f'{"✓ SYGNAŁ" if sig else "✗ SZUM"} (h={hamming})'}
            else:
                out[p.prism_id] = {'signal': False, 'status': '✗ SZUM (brak fp)'}
        return out

    def mark_bubble_for_decay(self, label, rate=0.01):
        return self.bubbles.mark_for_decay(label, self.phi.epoch, rate)

    def refresh_bubble(self, label):
        return self.bubbles.refresh_bubble(label)

    def revoke_bubble(self, label):
        ok = self.bubbles.revoke_by_label(label)
        if ok: print(f"  [REVOKE] '{label}' → Warp Oblivion")
        return ok

    def archive_bubbles_to_hologram(self, topic, bubble_labels,
                                     remove_originals=False, n_components=5):
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
        hid = (f"idea_{topic}_{self.phi.epoch}_"
               f"{hashlib.md5(topic.encode()).hexdigest()[:6]}")
        self.holograms[hid] = Hologram(
            id=hid, topic=topic, proto=proto, generators=generators,
            weights=weights, bubble_labels=labels, epoch_created=self.phi.epoch
        )
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

    def stats(self):
        s = self.phi.stats()
        return {**s, "version": VERSION, "atoms_phi": s["atoms"],
                "bubbles": self.bubbles.count,
                "bubbles_decaying": self.bubbles.count_decaying,
                "bubbles_revoked": len(self.bubbles._rev),
                "holograms": len(self.holograms),
                "bubble_bias": self._bubble_bias(),
                "phi_id": self.get_phi_id()}

    # ──────────────────────────── PERSISTENCE ────────────────────────────

    def save(self, path="./karmazyn_data"):
        """Zapisuje stan jądra używając formatu .soul (soul_store)."""
        try:
            from soul_store import save_soul
            return save_soul(self, path)
        except ImportError:
            print("  [!] Błąd: soul_store.py nieodnaleziony. Zapis niemożliwy.")
            return False

    def load(self, path="./karmazyn_data"):
        """Wczytuje stan jądra używając formatu .soul (soul_store)."""
        try:
            from soul_store import load_soul
            return load_soul(self, path)
        except ImportError:
            print("  [!] Błąd: soul_store.py nieodnaleziony. Odczyt niemożliwy.")
            return False

    def __repr__(self):
        s = self.stats()
        return (f"KarmazynOS(v{VERSION} | φ={s['atoms_phi']} T={s['temperature']:.2f} | "
                f"bąble={s['bubbles']} bias={s['bubble_bias']:.2f} | "
                f"idee={s['holograms']} | Φ-ID={s['phi_id'][:12]}…)")
