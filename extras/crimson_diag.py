#!/usr/bin/env python3
"""
crimson_diag.py — Diagnostyk Łączności Crimson (v1.0.0)
========================================================
Narzędzie diagnostyczne protokołu Crimson Handshake.
Sprawdza każdy krok połączenia między dwoma węzłami KarmazynOS
i raportuje dokładnie gdzie i dlaczego coś nie działa.

Użycie:
  # Węzeł nasłuchujący (uruchom pierwszy):
  python3 crimson_diag.py --listen 9000

  # Węzeł łączący się (uruchom drugi):
  python3 crimson_diag.py --connect 127.0.0.1 9000

  # Opcjonalnie – własny katalog danych:
  python3 crimson_diag.py --listen 9000 --data ./moj_wezel
  python3 crimson_diag.py --connect host 9000 --data ./moj_wezel2
"""

import argparse
import hashlib
import hmac
import json
import os
import queue
import socket
import sys
import threading
import time
import numpy as np
from typing import Optional

# ── Kolory terminala ─────────────────────────────────────────────────────────
_NO_COLOR = not sys.stdout.isatty()

def _c(code, text):
    if _NO_COLOR: return text
    return f"\033[{code}m{text}\033[0m"

def GREEN(t):  return _c("32", t)
def RED(t):    return _c("31", t)
def YELLOW(t): return _c("33", t)
def CYAN(t):   return _c("36", t)
def BOLD(t):   return _c("1",  t)
def DIM(t):    return _c("2",  t)

# ── Krok diagnostyczny ───────────────────────────────────────────────────────

class DiagStep:
    """Reprezentuje jeden krok diagnostyki z wynikiem i czasem."""

    def __init__(self, number: int, label: str):
        self.number  = number
        self.label   = label
        self.status  = None   # 'ok' | 'fail' | 'warn' | 'skip'
        self.detail  = ""
        self.elapsed = 0.0
        self._start  = time.time()

    def ok(self, detail=""):
        self.status  = "ok"
        self.detail  = detail
        self.elapsed = time.time() - self._start
        _print_step(self)

    def fail(self, detail=""):
        self.status  = "fail"
        self.detail  = detail
        self.elapsed = time.time() - self._start
        _print_step(self)

    def warn(self, detail=""):
        self.status  = "warn"
        self.detail  = detail
        self.elapsed = time.time() - self._start
        _print_step(self)

    def skip(self, detail=""):
        self.status  = "skip"
        self.detail  = detail
        self.elapsed = time.time() - self._start
        _print_step(self)


def _print_step(s: DiagStep):
    icons = {"ok": GREEN("✓"), "fail": RED("✗"), "warn": YELLOW("!"), "skip": DIM("–")}
    icon  = icons.get(s.status, "?")
    num   = DIM(f"[{s.number:02d}]")
    label = BOLD(f"{s.label:<42s}")
    t     = DIM(f"{s.elapsed*1000:6.1f}ms")
    detail = f"  {DIM(s.detail)}" if s.detail else ""
    print(f"  {num} {icon} {label} {t}{detail}")


# ── Główna klasa diagnostyczna ───────────────────────────────────────────────

class CrimsonDiag:
    """
    Przeprowadza pełną diagnostykę łączności Crimson Handshake.
    Działa jako serwer (--listen) lub klient (--connect).
    """

    def __init__(self, data_path: str = "./karmazyn_diag_data"):
        self.data_path   = data_path
        self.steps       = []
        self.karmazyn    = None
        self.peer_info   = {}
        self._step_count = 0
        self._results_q  = queue.Queue()

    def _step(self, label: str) -> DiagStep:
        self._step_count += 1
        s = DiagStep(self._step_count, label)
        self.steps.append(s)
        return s

    # ── Inicjalizacja ────────────────────────────────────────────────────────

    def init_karmazyn(self) -> bool:
        s = self._step("Inicjalizacja KarmazynOS")
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from karmazyn import KarmazynOS
            self._KarmazynOS = KarmazynOS

            # Przekieruj print z KarmazynOS żeby nie zaśmiecać wyjścia
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.karmazyn = KarmazynOS()

            s.ok(f"v{self.karmazyn.stats()['version']}")
            return True
        except Exception as e:
            s.fail(str(e))
            return False

    def init_identity(self) -> bool:
        s = self._step("Bąbel tożsamości (_p2s)")
        try:
            import io, contextlib
            buf = io.StringIO()

            # Próbuj wczytać istniejący stan
            if os.path.isdir(self.data_path):
                with contextlib.redirect_stdout(buf):
                    self.karmazyn.load(self.data_path)
                s.ok(f"wczytano z {self.data_path}")
            else:
                with contextlib.redirect_stdout(buf):
                    self.karmazyn._init_p2s_bubble()
                s.ok("nowa sesja")

            return True
        except Exception as e:
            s.fail(str(e))
            return False

    def check_phi_id(self) -> bool:
        s = self._step("Φ-ID węzła")
        try:
            phi_id   = self.karmazyn.get_phi_id()
            phi2_hex = self.karmazyn.phi.phi2_bytes().hex()
            b = self.karmazyn.bubbles.get_by_label(
                self.karmazyn._P2S_BUBBLE_LABEL
            )
            immortal = b.immortal if b else False
            s.ok(f"{phi_id[:20]}…  immortal={immortal}")
            print(f"       {DIM('Φ-ID pełny:  ')}{CYAN(phi_id)}")
            print(f"       {DIM('phi2_hex:    ')}{DIM(phi2_hex[:40]+'…')}")
            return True
        except Exception as e:
            s.fail(str(e))
            return False

    def check_p2s_readable(self) -> bool:
        s = self._step("Odczyt _p2s z bąbla")
        try:
            p2s = self.karmazyn.read_p2s_bubble()
            if p2s is None:
                s.fail("read_p2s_bubble() zwróciło None")
                return False
            if len(p2s) != 32:
                s.fail(f"zła długość: {len(p2s)} (oczekiwano 32)")
                return False
            if p2s != self.karmazyn.phi._p2s:
                s.fail("p2s z bąbla != p2s w pamięci (niezgodność!)")
                return False
            s.ok("32 bajty, zgodny z pamięcią")
            return True
        except Exception as e:
            s.fail(str(e))
            return False

    def check_immortal_protection(self) -> bool:
        s = self._step("Ochrona immortal bąbla")
        label = self.karmazyn._P2S_BUBBLE_LABEL
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r1 = self.karmazyn.bubbles.mark_for_decay(label, 0, 0.1)
            r2 = self.karmazyn.bubbles.revoke_by_label(label)
            r3 = self.karmazyn.bubbles.remove_bubble(label)
        if r1 or r2 or r3:
            s.fail(f"blokada nieskuteczna: decay={r1} revoke={r2} remove={r3}")
            return False
        s.ok("decay/revoke/remove zablokowane")
        return True

    def check_phi2_vector(self) -> bool:
        s = self._step("Wektor Φ² (get_phi2_vector)")
        try:
            v = self.karmazyn.get_phi2_vector(128)
            if v.shape != (128,):
                s.fail(f"zły kształt: {v.shape}")
                return False
            if not np.all(np.isfinite(v)):
                s.fail("wektor zawiera NaN/Inf")
                return False
            norm = float(np.linalg.norm(v))
            if abs(norm - 1.0) > 1e-5:
                s.fail(f"wektor nie jest znormalizowany (norm={norm:.6f})")
                return False
            # Deterministyczność
            v2 = self.karmazyn.get_phi2_vector(128)
            if not np.array_equal(v, v2):
                s.fail("nie jest deterministyczny")
                return False
            s.ok(f"dim=128 norm={norm:.6f} deterministyczny")
            return True
        except Exception as e:
            s.fail(str(e))
            return False

    def check_commitment(self) -> bool:
        s = self._step("Generacja commitment")
        try:
            nonce      = os.urandom(16)
            my_phi_id  = self.karmazyn.get_phi_id()
            commitment = self.karmazyn.get_p2s_commitment(nonce, my_phi_id)
            if len(commitment) != 32:
                s.fail(f"zła długość: {len(commitment)}")
                return False
            # Deterministyczność
            c2 = self.karmazyn.get_p2s_commitment(nonce, my_phi_id)
            if commitment != c2:
                s.fail("commitment nie jest deterministyczny")
                return False
            s.ok("32 bajty, deterministyczny")
            return True
        except Exception as e:
            s.fail(str(e))
            return False

    # ── Diagnostyka sieciowa ─────────────────────────────────────────────────

    def run_server(self, port: int):
        """Tryb serwera – nasłuchuje i przeprowadza diagnostykę połączenia."""
        print()
        print(BOLD("═" * 60))
        print(BOLD(f"  CRIMSON DIAG – SERWER  port={port}"))
        print(BOLD("═" * 60))

        # Faza 1: diagnostyka lokalna
        if not self._run_local_checks():
            self._print_summary()
            return

        # Faza 2: nasłuchiwanie
        s_tcp = self._step(f"TCP listen :{port}")
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", port))
            srv.listen(1)
            srv.settimeout(60)
            s_tcp.ok(f"nasłuchuję – czekam na połączenie (timeout 60s)…")
            print(f"\n  {YELLOW('Czekam na klienta…')}")
        except Exception as e:
            s_tcp.fail(str(e))
            self._print_summary()
            return

        try:
            conn, addr = srv.accept()
            print(f"  {GREEN('Połączenie od')} {addr[0]}:{addr[1]}")
            srv.close()
        except socket.timeout:
            self._step("Oczekiwanie na klienta").fail("timeout 60s – brak połączenia")
            self._print_summary()
            return

        # Faza 3: handshake diagnostyczny
        self._run_handshake_diag(conn, is_initiator=False,
                                  peer_address=f"{addr[0]}:{addr[1]}")
        self._print_summary()

    def run_client(self, host: str, port: int):
        """Tryb klienta – łączy się i przeprowadza diagnostykę połączenia."""
        print()
        print(BOLD("═" * 60))
        print(BOLD(f"  CRIMSON DIAG – KLIENT  {host}:{port}"))
        print(BOLD("═" * 60))

        # Faza 1: diagnostyka lokalna
        if not self._run_local_checks():
            self._print_summary()
            return

        # Faza 2: TCP connect
        s_tcp = self._step(f"TCP connect → {host}:{port}")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((host, port))
            sock.settimeout(None)
            s_tcp.ok()
        except socket.timeout:
            s_tcp.fail(f"timeout – {host}:{port} nie odpowiada")
            self._print_summary()
            return
        except ConnectionRefusedError:
            s_tcp.fail(f"odmowa połączenia – serwer nie nasłuchuje na {port}?")
            self._print_summary()
            return
        except Exception as e:
            s_tcp.fail(str(e))
            self._print_summary()
            return

        # Faza 3: handshake diagnostyczny
        self._run_handshake_diag(sock, is_initiator=True,
                                  peer_address=f"{host}:{port}")
        self._print_summary()

    # ── Lokalne sprawdzenia ──────────────────────────────────────────────────

    def _run_local_checks(self) -> bool:
        print()
        print(BOLD("  ── Diagnostyka lokalna ──────────────────────────────"))
        ok = True
        ok &= self.init_karmazyn()
        if not self.karmazyn:
            return False
        ok &= self.init_identity()
        ok &= self.check_phi_id()
        ok &= self.check_p2s_readable()
        ok &= self.check_immortal_protection()
        ok &= self.check_phi2_vector()
        ok &= self.check_commitment()
        print()
        return ok

    # ── Handshake diagnostyczny ──────────────────────────────────────────────

    def _recv_all(self, sock, n):
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _send_frame(self, sock, payload: bytes):
        sock.sendall(len(payload).to_bytes(4, 'big') + payload)

    def _recv_frame(self, sock) -> Optional[bytes]:
        raw = self._recv_all(sock, 4)
        if not raw: return None
        return self._recv_all(sock, int.from_bytes(raw, 'big'))

    def _diag_kem(self, sock, is_initiator):
        """
        Własna implementacja KEM dla diagnostyki.
        Obsługuje Kyber (przez oqs) i ECDH z pełną wymianą kluczy publicznych.
        W ECDH obie strony wymieniają klucze publiczne – nie używa KeyExchange
        z crimson_network który ma ograniczenie ECDH decapsulate.
        """
        # Próbuj Kyber
        try:
            import oqs
            if is_initiator:
                kem_obj = oqs.KeyEncapsulation("Kyber768")
                pk = kem_obj.generate_keypair()
                self._send_frame(sock, pk)
                ct = self._recv_frame(sock)
                if not ct: return None, "kyber"
                K = kem_obj.decap_secret(ct)
            else:
                pk = self._recv_frame(sock)
                if not pk: return None, "kyber"
                kem_obj = oqs.KeyEncapsulation("Kyber768")
                ct, K = kem_obj.encap_secret(pk)
                self._send_frame(sock, ct)
            return K, "kyber"
        except (ImportError, RuntimeError):
            pass

        # Fallback: pełne ECDH (obie strony wymieniają pub klucze)
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization

        priv = ec.generate_private_key(ec.SECP256R1())
        my_pub = priv.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint
        )

        if is_initiator:
            self._send_frame(sock, my_pub)
            peer_pub_bytes = self._recv_frame(sock)
            if not peer_pub_bytes: return None, "ecdh"
        else:
            peer_pub_bytes = self._recv_frame(sock)
            if not peer_pub_bytes: return None, "ecdh"
            self._send_frame(sock, my_pub)

        peer_pub = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), peer_pub_bytes
        )
        K = priv.exchange(ec.ECDH(), peer_pub)
        return K, "ecdh"

    def _run_handshake_diag(self, sock: socket.socket,
                             is_initiator: bool, peer_address: str):
        print(BOLD("  ── Diagnostyka handshake ────────────────────────────"))

        # Import KeyExchange z crimson_network
        try:
            from crimson_network import KeyExchange, NodeRegistry
        except ImportError as e:
            self._step("Import crimson_network").fail(str(e))
            return

        K = None
        peer_frame = None
        my_nonce = os.urandom(16)
        my_phi_id = self.karmazyn.get_phi_id()

        # ── KROK 0: WYMIANA Φ-ID ─────────────────────────────────────────
        s0 = self._step("Krok 0: wymiana Φ-ID")
        try:
            def build_frame(peer_phi_id_hex):
                phi2_hex   = self.karmazyn.phi.phi2_bytes().hex()
                commitment = self.karmazyn.get_p2s_commitment(
                    my_nonce, peer_phi_id_hex
                )
                b_obj = self.karmazyn.bubbles.get_by_label(
                    self.karmazyn._P2S_BUBBLE_LABEL
                )
                return json.dumps({
                    "phi_id":     my_phi_id,
                    "nonce":      my_nonce.hex(),
                    "commitment": commitment.hex(),
                    "phi2_hex":   phi2_hex,
                    "bubble_id":  b_obj.id if b_obj else "",
                    "version":    "crimson-1.3",
                }, separators=(',', ':')).encode()

            def parse_frame(data):
                f = json.loads(data.decode())
                f["nonce_bytes"]      = bytes.fromhex(f["nonce"])
                f["commitment_bytes"] = bytes.fromhex(f["commitment"])
                f["phi2_bytes"]       = bytes.fromhex(f["phi2_hex"])
                f.setdefault("bubble_id", "")
                return f

            if is_initiator:
                self._send_frame(sock, build_frame(""))
                raw = self._recv_frame(sock)
                if not raw: raise ConnectionError("brak ramki od serwera")
                peer_frame = parse_frame(raw)
                self._send_frame(sock, build_frame(peer_frame["phi_id"]))
            else:
                raw = self._recv_frame(sock)
                if not raw: raise ConnectionError("brak ramki od klienta")
                peer_frame = parse_frame(raw)
                self._send_frame(sock, build_frame(peer_frame["phi_id"]))
                raw = self._recv_frame(sock)
                if not raw: raise ConnectionError("brak ramki commitment")
                peer_frame = parse_frame(raw)

            self.peer_info = {
                "phi_id":   peer_frame["phi_id"],
                "phi2_hex": peer_frame["phi2_hex"],
                "address":  peer_address,
            }
            s0.ok(f"peer Φ-ID={peer_frame['phi_id'][:16]}…")
            print(f"       {DIM('Peer Φ-ID:   ')}{CYAN(peer_frame['phi_id'])}")
            print(f"       {DIM('Peer phi2:   ')}{DIM(peer_frame['phi2_hex'][:40]+'…')}")
        except Exception as e:
            s0.fail(str(e))
            sock.close(); return

        # ── KROK 0b: REJESTR TOFU ────────────────────────────────────────
        s0b = self._step("Krok 0b: rejestr TOFU")
        try:
            registry = NodeRegistry(
                os.path.join(self.data_path, "known_nodes.json")
            )
            peer_phi_id = peer_frame["phi_id"]
            if registry.is_known(peer_phi_id):
                ok_phi2 = registry.verify_phi2(peer_phi_id, peer_frame["phi2_hex"])
                if ok_phi2:
                    node = registry.get(peer_phi_id)
                    s0b.ok(f"znany węzeł: '{node.get('name', '?')}' phi2 OK")
                else:
                    s0b.fail("ALARM: phi2_hex niezgodny z rejestrem!")
                    sock.close(); return
            else:
                registry.register(peer_phi_id, peer_frame["phi2_hex"],
                                  address=peer_address)
                s0b.ok("nowy węzeł – dodano do rejestru (TOFU)")
        except Exception as e:
            s0b.warn(f"rejestr niedostępny: {e}")

        # ── KROK 1: KEM ──────────────────────────────────────────────────
        s1 = self._step("Krok 1: wymiana kluczy KEM")
        try:
            K, kem_mode = self._diag_kem(sock, is_initiator)
            if K is None:
                s1.fail("wymiana kluczy nieudana")
                sock.close(); return
            s1.ok(f"tryb={kem_mode}  K={K.hex()[:16]}…")
        except Exception as e:
            s1.fail(str(e))
            sock.close(); return

        # ── KROK 2: ZAŚLEPIONE Φ² ────────────────────────────────────────
        s2 = self._step("Krok 2: wymiana zaślepionych Φ²")
        try:
            dim    = 128
            my_tag = "blind-A" if is_initiator else "blind-B"
            blind  = self.karmazyn._get_blinding(K, my_tag, dim)
            phi2v  = self.karmazyn.get_phi2_vector(dim)
            my_blinded = (phi2v + blind).tobytes()
            self._send_frame(sock, my_blinded)
            peer_blinded = self._recv_frame(sock)
            if not peer_blinded: raise ConnectionError("brak zaślepionego Φ²")
            s2.ok(f"wysłano {len(my_blinded)}B  odebrano {len(peer_blinded)}B")
        except Exception as e:
            s2.fail(str(e))
            sock.close(); return

        # ── KROK 3: REZONANS ─────────────────────────────────────────────
        s3 = self._step("Krok 3: rezonans Φ²")
        try:
            peer_tag   = "blind-B" if is_initiator else "blind-A"
            peer_blind = self.karmazyn._get_blinding(K, peer_tag, dim)
            peer_phi2v = np.frombuffer(peer_blinded, dtype=np.float32) - peer_blind

            norm_my   = float(np.linalg.norm(phi2v))
            norm_peer = float(np.linalg.norm(peer_phi2v))
            rez = float(np.dot(phi2v, peer_phi2v) / (norm_my * norm_peer + 1e-9))

            if rez >= 0.8:
                s3.ok(f"cosinus={rez:.6f} ≥ 0.8  REZONANS")
            elif rez >= 0.5:
                s3.warn(f"cosinus={rez:.6f} < 0.8  SŁABY REZONANS")
            else:
                s3.fail(f"cosinus={rez:.6f} < 0.8  BRAK REZONANSU")
                print(f"       {RED('Węzły mają różne _p2s lub uszkodzony bąbel tożsamości.')}")
                self._send_result(sock, False)
                self._recv_result(sock)
                sock.close(); return
        except Exception as e:
            s3.fail(str(e))
            sock.close(); return

        # ── KROK 4: COMMITMENT ───────────────────────────────────────────
        s4 = self._step("Krok 4: weryfikacja commitment")
        try:
            peer_phi2_bytes_from_frame = peer_frame["phi2_bytes"]
            # bubble_id z ramki tożsamości (jawny identyfikator bąbla peera)
            peer_bubble_id = peer_frame.get("bubble_id", "").encode()
            peer_bkey = hashlib.sha256(
                peer_phi2_bytes_from_frame + b"bubble:" + peer_bubble_id
            ).digest()
            peer_phi_id_bytes = bytes.fromhex(peer_frame["phi_id"])
            my_phi_id_bytes   = bytes.fromhex(my_phi_id)
            expected = hmac.HMAC(
                peer_bkey,
                peer_phi_id_bytes + peer_frame["nonce_bytes"] + my_phi_id_bytes,
                hashlib.sha256
            ).digest()
            ok_commit = hmac.compare_digest(expected, peer_frame["commitment_bytes"])
            if ok_commit:
                s4.ok("HMAC OK – Φ-ID peera jest autentyczny")
            else:
                s4.fail("HMAC MISMATCH – możliwy MITM lub uszkodzony bąbel")
                self._send_result(sock, False)
                self._recv_result(sock)
                sock.close(); return
        except Exception as e:
            s4.fail(str(e))
            sock.close(); return

        # ── KROK 5: CRIMSON KEY ──────────────────────────────────────────
        s5 = self._step("Krok 5: wyprowadzenie crimson_key")
        try:
            self.karmazyn._peer_phi2_bytes = peer_frame["phi2_bytes"]
            ok_rez, confirm = self.karmazyn.crimson_handshake(
                peer_blinded, is_initiator, K
            )
            if not ok_rez or self.karmazyn.crimson_key is None:
                s5.fail("crimson_handshake() zwróciło False")
                sock.close(); return
            s5.ok(f"key={self.karmazyn.crimson_key.hex()[:16]}…")
        except Exception as e:
            s5.fail(str(e))
            sock.close(); return

        # ── KROK 6: PING-PONG (test szyfrowania) ─────────────────────────
        s6 = self._step("Krok 6: ping-pong (AES-256-GCM)")
        try:
            MAGIC = "CRIMSON_PING_v1"
            if is_initiator:
                # Wyślij zaszyfrowany ping
                ct_ping = self.karmazyn.crimson_encrypt(MAGIC)
                self._send_frame(sock, ct_ping)
                # Odbierz pong
                ct_pong = self._recv_frame(sock)
                if not ct_pong: raise ConnectionError("brak pong")
                pong = self.karmazyn.crimson_decrypt(ct_pong)
                if pong != f"PONG:{MAGIC}":
                    raise ValueError(f"zły pong: '{pong}'")
                s6.ok(f"ping→pong OK  ct={len(ct_ping)}B")
            else:
                # Odbierz ping
                ct_ping = self._recv_frame(sock)
                if not ct_ping: raise ConnectionError("brak ping")
                ping = self.karmazyn.crimson_decrypt(ct_ping)
                # Wyślij pong
                ct_pong = self.karmazyn.crimson_encrypt(f"PONG:{ping}")
                self._send_frame(sock, ct_pong)
                s6.ok(f"ping odebrano pong wysłano  '{ping}'")
        except Exception as e:
            s6.fail(str(e))
            sock.close(); return

        # ── KROK 7: CONFIRM (protokołowy) ────────────────────────────────
        s7 = self._step("Krok 7: potwierdzenie protokołu")
        try:
            if is_initiator:
                self._send_frame(sock, confirm)
                s7.ok("confirm wysłany")
            else:
                peer_confirm = self._recv_frame(sock)
                if peer_confirm:
                    s7.ok("confirm odebrany")
                else:
                    s7.warn("brak confirm od inicjatora (nie krytyczne)")
        except Exception as e:
            s7.warn(str(e))

        sock.close()
        print()

    def _send_result(self, sock, ok: bool):
        """Wysyła wynik diagnostyki do peera (synchronizacja przy błędzie)."""
        try:
            self._send_frame(sock, b"\x01" if ok else b"\x00")
        except Exception:
            pass

    def _recv_result(self, sock) -> bool:
        """Odbiera wynik diagnostyki od peera."""
        try:
            data = self._recv_frame(sock)
            return data == b"\x01"
        except Exception:
            return False

    # ── Podsumowanie ─────────────────────────────────────────────────────────

    def _print_summary(self):
        ok_steps   = [s for s in self.steps if s.status == "ok"]
        fail_steps = [s for s in self.steps if s.status == "fail"]
        warn_steps = [s for s in self.steps if s.status == "warn"]
        skip_steps = [s for s in self.steps if s.status == "skip"]
        total_ms   = sum(s.elapsed for s in self.steps) * 1000

        print(BOLD("═" * 60))
        print(BOLD("  PODSUMOWANIE"))
        print(BOLD("═" * 60))
        print(f"  {GREEN('✓')} OK:       {len(ok_steps)}")
        if warn_steps:
            print(f"  {YELLOW('!')} Ostrzeżenia: {len(warn_steps)}")
        if fail_steps:
            print(f"  {RED('✗')} Błędy:    {len(fail_steps)}")
        if skip_steps:
            print(f"  {DIM('–')} Pominięte: {len(skip_steps)}")
        print(f"  {DIM('⏱')} Czas:     {total_ms:.1f}ms")

        if self.peer_info:
            print()
            print(f"  Peer Φ-ID: {CYAN(self.peer_info.get('phi_id', '?'))}")

        if fail_steps:
            print()
            print(RED("  PROBLEMY:"))
            for s in fail_steps:
                print(f"    [{s.number:02d}] {s.label}: {s.detail}")
            print()
            self._print_diagnosis(fail_steps)

        print()
        if not fail_steps:
            print(GREEN(BOLD("  ✓ POŁĄCZENIE CRIMSON SPRAWNE")))
        else:
            print(RED(BOLD("  ✗ POŁĄCZENIE CRIMSON NIEUDANE")))
        print()

    def _print_diagnosis(self, fail_steps):
        """Wyświetla wskazówki diagnostyczne na podstawie kroków które nie przeszły."""
        labels = {s.label for s in fail_steps}
        print(YELLOW("  WSKAZÓWKI:"))

        if any("tożsamości" in l or "_p2s" in l for l in labels):
            print("    • Bąbel tożsamości uszkodzony lub brak karmazyn_data/")
            print("      Usuń katalog danych i uruchom ponownie.")

        if any("Φ²" in l or "wektor" in l.lower() for l in labels):
            print("    • Wektor Φ² zawiera NaN/Inf – błąd inicjalizacji _p2s.")

        if any("rezonans" in l.lower() for l in labels):
            print("    • Brak rezonansu – dwa węzły mają różne _p2s.")
            print("      To normalne jeśli łączysz dwa różne węzły.")
            print("      Rezonans = 1.0 tylko gdy oba węzły mają ten sam _p2s.")

        if any("commitment" in l.lower() for l in labels):
            print("    • Commitment MISMATCH – możliwy atak MITM lub")
            print("      uszkodzony/podmieniony bąbel tożsamości.")

        if any("TCP" in l or "connect" in l.lower() for l in labels):
            print("    • Problem sieciowy – sprawdź:")
            print("      - czy serwer (--listen) jest uruchomiony")
            print("      - czy port nie jest zablokowany przez firewall")
            print("      - czy adres IP jest poprawny")

        if any("ping" in l.lower() or "GCM" in l for l in labels):
            print("    • Błąd szyfrowania – crimson_key asymetryczny.")
            print("      Sprawdź czy oba węzły mają tę samą wersję karmazyn.py.")

        if any("KEM" in l for l in labels):
            print("    • Błąd wymiany kluczy KEM.")
            print("      Sprawdź połączenie sieciowe i wersję bibliotek.")


# ── Punkt wejścia ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Diagnostyk łączności Crimson Handshake",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--listen",  type=int, metavar="PORT",
                      help="tryb serwera – nasłuchuj na podanym porcie")
    mode.add_argument("--connect", nargs=2, metavar=("HOST", "PORT"),
                      help="tryb klienta – połącz z HOST:PORT")
    parser.add_argument("--data", default="./karmazyn_diag_data",
                        metavar="ŚCIEŻKA",
                        help="katalog danych KarmazynOS (domyślnie: ./karmazyn_diag_data)")

    args = parser.parse_args()
    diag = CrimsonDiag(data_path=args.data)

    if args.listen:
        diag.run_server(port=args.listen)
    else:
        host, port = args.connect[0], int(args.connect[1])
        diag.run_client(host=host, port=port)


if __name__ == "__main__":
    main()
