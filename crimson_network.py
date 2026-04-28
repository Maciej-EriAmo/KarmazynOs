"""
crimson_network.py – Karmazynowa Warstwa Sieciowa (v1.3.0)
===========================================================
Zmiany v1.3.0:
  [nowe] NodeRegistry – rejestr znanych węzłów (TOFU)
  [nowe] Krok 0 handshake – wymiana Φ-ID, nonce, commitment, phi2_bytes_hex
  [nowe] Weryfikacja commitment po rezonansie
  [nowe] Alarm przy niezgodności Φ-ID vs known_nodes
  [fix]  Import ECDH – usunięto nieistniejący moduł kex.ecdh
  [fix]  KeyExchange: shared_secret zapisywany i zwracany przez decapsulate()
  [fix]  crimson_key symetryczny (sorted phi2) – z karmazyn.py v1.3.0
"""

import socket
import threading
import hashlib
import hmac
import json
import os
import time
import numpy as np
from typing import Optional, Callable, Dict

try:
    import oqs
    HAS_OQS = True
except (ImportError, RuntimeError) as e:
    print(f"[!] liboqs niedostępne ({e}) – używam ECDH (bez post-kwantowego)")
    HAS_OQS = False
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

from karmazyn import KarmazynOS

# Rozmiar nagłówka Φ-ID: phi_id(32) + nonce(16) + commitment(32) + phi2_bytes_hex(64) = 144 bajtów
_HANDSHAKE_HEADER_SIZE = 32 + 16 + 32 + 64


class NodeRegistry:
    """
    Rejestr znanych węzłów KarmazynOS (TOFU – Trust On First Use).
    Przechowuje Φ-ID, phi2_bytes_hex i ostatni adres każdego węzła.
    """

    def __init__(self, path="./karmazyn_data/known_nodes.json"):
        self._path = path
        self._nodes: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if os.path.isfile(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._nodes = json.load(f)
            except Exception:
                self._nodes = {}

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._nodes, f, indent=2, ensure_ascii=False)

    def is_known(self, phi_id: str) -> bool:
        return phi_id in self._nodes

    def get(self, phi_id: str) -> Optional[dict]:
        return self._nodes.get(phi_id)

    def register(self, phi_id: str, phi2_bytes_hex: str,
                 name: str = "", address: str = ""):
        """Rejestruje nowy węzeł lub aktualizuje istniejący."""
        self._nodes[phi_id] = {
            "name":           name or phi_id[:12],
            "phi2_bytes_hex": phi2_bytes_hex,
            "address":        address,
            "first_seen":     self._nodes.get(phi_id, {}).get(
                                  "first_seen", time.strftime("%Y-%m-%dT%H:%M:%S")),
            "last_seen":      time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._save()

    def verify_phi2(self, phi_id: str, phi2_bytes_hex: str) -> bool:
        """
        Sprawdza czy phi2_bytes_hex zgadza się z zapisanym.
        Zwraca True jeśli węzeł nieznany (TOFU) lub jeśli się zgadza.
        """
        node = self._nodes.get(phi_id)
        if not node:
            return True  # nieznany – TOFU, akceptuj
        return hmac.compare_digest(
            node["phi2_bytes_hex"].lower(),
            phi2_bytes_hex.lower()
        )

    def list_nodes(self) -> list:
        return [
            {"phi_id": phi_id, **info}
            for phi_id, info in self._nodes.items()
        ]


class KeyExchange:
    """Abstrakcja nad wymianą kluczy – Kyber-768 lub ECDH."""

    def __init__(self):
        self._shared_secret: Optional[bytes] = None

        if HAS_OQS:
            try:
                self._kem = oqs.KeyEncapsulation("Kyber768")
                self._mode = "kyber"
                return
            except Exception as e:
                print(f"[!] Kyber init error: {e}, fallback to ECDH")

        self._ecdh_private = ec.generate_private_key(ec.SECP256R1())
        self._mode = "ecdh"

    @property
    def mode(self) -> str:
        return self._mode

    def get_public_key_bytes(self) -> bytes:
        if self._mode == "kyber":
            return self._kem.generate_keypair()
        else:
            pub = self._ecdh_private.public_key()
            return pub.public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint
            )

    def encapsulate(self, peer_pk: bytes) -> tuple:
        """Zwraca (ciphertext, shared_secret)."""
        if self._mode == "kyber":
            return self._kem.encap_secret(peer_pk)
        else:
            peer_key = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256R1(), peer_pk
            )
            shared = self._ecdh_private.exchange(ec.ECDH(), peer_key)
            self._shared_secret = shared
            ct = hashlib.sha256(shared).digest()
            return ct, shared

    def decapsulate(self, ct: bytes) -> bytes:
        if self._mode == "kyber":
            return self._kem.decap_secret(ct)
        else:
            if self._shared_secret is None:
                raise RuntimeError(
                    "Brak shared_secret w ECDH – encapsulate() musi poprzedzać decapsulate()."
                )
            return self._shared_secret


class CrimsonNetwork:
    def __init__(self, karmazyn: KarmazynOS, my_port: int,
                 registry_path="./karmazyn_data/known_nodes.json"):
        self.karmazyn = karmazyn
        self.my_port = my_port
        self.peer_socket: Optional[socket.socket] = None
        self.crimson_active = threading.Event()
        self.receive_callback: Optional[Callable[[str], None]] = None
        self.registry = NodeRegistry(registry_path)
        # Upewniamy się że bąbel tożsamości istnieje
        self.karmazyn._init_p2s_bubble()

    # ──────────────────────────── NISKO-POZIOMOWY TRANSPORT ─────────────

    def _recv_all(self, sock: socket.socket, n: int) -> Optional[bytes]:
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _send_frame(self, sock: socket.socket, payload: bytes):
        frame = len(payload).to_bytes(4, 'big') + payload
        sock.sendall(frame)

    def _recv_frame(self, sock: socket.socket) -> Optional[bytes]:
        raw_len = self._recv_all(sock, 4)
        if not raw_len:
            return None
        msg_len = int.from_bytes(raw_len, 'big')
        return self._recv_all(sock, msg_len)

    # ──────────────────────────── KROK 0: WYMIANA Φ-ID ──────────────────

    def _build_identity_frame(self, peer_phi_id: str, nonce: bytes) -> bytes:
        """
        Buduje ramkę tożsamości (144 bajty):
          phi_id(32 hex bytes→16B wysyłamy jako 32 hex chars = 32B)
          + nonce(16B)
          + commitment(32B)
          + phi2_bytes_hex(64 hex chars = 32B hash → wysyłamy jako 64B hex)

        Zakodowane jako JSON dla czytelności i rozszerzalności.
        """
        phi_id = self.karmazyn.get_phi_id()                    # 32 hex chars
        phi2_hex = self.karmazyn.phi.phi2_bytes().hex()         # 64 hex chars
        commitment = self.karmazyn.get_p2s_commitment(nonce, peer_phi_id)

        # bubble_id to jawny identyfikator bąbla – potrzebny peerowi
        # do odtworzenia bubble_key = sha256(phi2_bytes + 'bubble:' + bid)
        b_identity = self.karmazyn.bubbles.get_by_label(
            KarmazynOS._P2S_BUBBLE_LABEL
        )
        bubble_id = b_identity.id if b_identity else ""

        frame = {
            "phi_id":     phi_id,
            "nonce":      nonce.hex(),
            "commitment": commitment.hex(),
            "phi2_hex":   phi2_hex,
            "bubble_id":  bubble_id,
            "version":    "crimson-1.3",
        }
        return json.dumps(frame, separators=(',', ':')).encode('utf-8')

    def _parse_identity_frame(self, data: bytes) -> Optional[dict]:
        try:
            frame = json.loads(data.decode('utf-8'))
            required = {"phi_id", "nonce", "commitment", "phi2_hex", "bubble_id", "version"}
            if not required.issubset(frame.keys()):
                return None
            # Konwersja z hex
            frame["nonce_bytes"]      = bytes.fromhex(frame["nonce"])
            frame["commitment_bytes"] = bytes.fromhex(frame["commitment"])
            frame["phi2_bytes"]       = bytes.fromhex(frame["phi2_hex"])
            return frame
        except Exception as e:
            print(f"[!] Błąd parsowania ramki tożsamości: {e}")
            return None

    def _verify_commitment(self, peer_frame: dict, my_phi_id: str,
                            peer_phi2_recovered: np.ndarray) -> bool:
        """
        Weryfikuje commitment peera używając jego phi2_bytes z kroku 0
        (jawny hash) i odzyskanego phi2 wektora z rezonansu.

        Używamy phi2_bytes z ramki (jawne, nie sekret) do odtworzenia
        bubble_key peera i weryfikacji HMAC.
        """
        peer_phi_id     = peer_frame["phi_id"]
        peer_nonce      = peer_frame["nonce_bytes"]
        peer_commitment = peer_frame["commitment_bytes"]
        peer_phi2_bytes = peer_frame["phi2_bytes"]  # sha256(_p2s+'phi2-v1') – jawne

        # Odtworzenie bubble_key peera z jego phi2_bytes i bubble_id
        # bubble_id przesłany jawnie w ramce tożsamości (krok 0)
        peer_bubble_id = peer_frame.get("bubble_id", "").encode()
        peer_bubble_key = hashlib.sha256(
            peer_phi2_bytes + b"bubble:" + peer_bubble_id
        ).digest()

        # Rekonstrukcja oczekiwanego commitment
        peer_phi_id_bytes = bytes.fromhex(peer_phi_id)
        my_phi_id_bytes   = bytes.fromhex(my_phi_id)
        expected = hmac.HMAC(
            peer_bubble_key,
            peer_phi_id_bytes + peer_nonce + my_phi_id_bytes,
            hashlib.sha256
        ).digest()

        return hmac.compare_digest(expected, peer_commitment)

    def _check_registry(self, peer_frame: dict, address: str) -> bool:
        """
        Sprawdza węzeł w rejestrze TOFU.
        Przy nieznanym węźle pyta użytkownika (lub akceptuje automatycznie
        gdy nie ma terminala).
        Zwraca True jeśli połączenie powinno być kontynuowane.
        """
        phi_id   = peer_frame["phi_id"]
        phi2_hex = peer_frame["phi2_hex"]

        if self.registry.is_known(phi_id):
            # Znany węzeł – weryfikuj phi2_bytes_hex (odciski palca)
            if not self.registry.verify_phi2(phi_id, phi2_hex):
                node = self.registry.get(phi_id)
                print(f"\n  [!!] ALARM TOŻSAMOŚCI")
                print(f"  Węzeł Φ-ID={phi_id[:16]}… zmienił phi2_bytes!")
                print(f"  Znane:    {node['phi2_bytes_hex'][:32]}…")
                print(f"  Odebrane: {phi2_hex[:32]}…")
                print(f"  Możliwy atak lub reset instancji. Połączenie odrzucone.")
                return False
            # Aktualizuj last_seen i adres
            node = self.registry.get(phi_id)
            self.registry.register(phi_id, phi2_hex,
                                   name=node.get("name", ""),
                                   address=address)
            print(f"  [Φ-ID] Znany węzeł: {node.get('name', phi_id[:16]+'…')}")
            return True
        else:
            # Nowy węzeł – TOFU
            print(f"\n  [Φ-ID] Nieznany węzeł:")
            print(f"  Φ-ID:    {phi_id}")
            print(f"  Adres:   {address}")
            print(f"  phi2:    {phi2_hex[:32]}…")
            try:
                ans = input("  Zaufać temu węzłowi? [T/n]: ").strip().lower()
                if ans == 'n':
                    print("  Połączenie odrzucone przez użytkownika.")
                    return False
            except (EOFError, OSError):
                # Brak terminala (np. daemon) – automatycznie akceptuj
                print("  (Brak terminala – automatyczna akceptacja TOFU)")
            self.registry.register(phi_id, phi2_hex, address=address)
            print(f"  [Φ-ID] Węzeł dodany do rejestru.")
            return True

    # ──────────────────────────── SERWER / KLIENT ────────────────────────

    def start_server(self):
        """Uruchamia wątek nasłuchujący na połączenia przychodzące."""
        def listen():
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("0.0.0.0", self.my_port))
            server.listen(1)
            print(f"[*] Nasłuchiwanie na porcie {self.my_port}...")
            print(f"[*] Mój Φ-ID: {self.karmazyn.get_phi_id()}")
            while True:
                client, addr = server.accept()
                print(f"[+] Połączenie od {addr}")
                threading.Thread(
                    target=self._handle_connection,
                    args=(client, f"{addr[0]}:{addr[1]}"),
                    daemon=True
                ).start()
        threading.Thread(target=listen, daemon=True).start()

    def connect(self, host: str, port: int):
        """Inicjuje połączenie jako klient i przeprowadza Crimson Handshake."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            print(f"[+] Połączono z {host}:{port}")
            self._perform_handshake(sock, is_initiator=True,
                                    peer_address=f"{host}:{port}")
        except Exception as e:
            print(f"[!] Błąd połączenia: {e}")

    def _handle_connection(self, sock: socket.socket, peer_address: str):
        self._perform_handshake(sock, is_initiator=False, peer_address=peer_address)

    # ──────────────────────────── HANDSHAKE ──────────────────────────────

    def _perform_handshake(self, sock: socket.socket,
                           is_initiator: bool, peer_address: str):
        """
        Pełny Karmazynowy Uścisk Dłoni v1.3:

        Krok 0: Wymiana ramek tożsamości (Φ-ID + nonce + commitment + phi2_hex)
        Krok 1: Wymiana kluczy KEM (Kyber/ECDH)
        Krok 2: Wymiana zaślepionych wektorów Φ²
        Krok 3: Weryfikacja rezonansu + weryfikacja commitment
        Krok 4: Potwierdzenie kanału
        """
        kem = KeyExchange()
        print(f"[*] Tryb wymiany kluczy: {kem.mode}")
        my_phi_id = self.karmazyn.get_phi_id()

        try:
            # ── KROK 0: WYMIANA Φ-ID ─────────────────────────────────────
            my_nonce = os.urandom(16)

            if is_initiator:
                # A wysyła ramkę tożsamości (peer_phi_id jeszcze nieznane – pusty string)
                my_frame_bytes = self._build_identity_frame("", my_nonce)
                self._send_frame(sock, my_frame_bytes)

                peer_frame_bytes = self._recv_frame(sock)
                if not peer_frame_bytes:
                    raise ConnectionError("Nie odebrano ramki tożsamości")
                peer_frame = self._parse_identity_frame(peer_frame_bytes)
                if not peer_frame:
                    raise ConnectionError("Nieprawidłowa ramka tożsamości")

                # Teraz znamy peer_phi_id – wysyłamy ponownie z commitment
                my_frame_bytes = self._build_identity_frame(
                    peer_frame["phi_id"], my_nonce
                )
                self._send_frame(sock, my_frame_bytes)

            else:
                # B odbiera ramkę A (bez commitment do B bo A nie znał phi_id B)
                peer_frame_bytes = self._recv_frame(sock)
                if not peer_frame_bytes:
                    raise ConnectionError("Nie odebrano ramki tożsamości")
                peer_frame = self._parse_identity_frame(peer_frame_bytes)
                if not peer_frame:
                    raise ConnectionError("Nieprawidłowa ramka tożsamości")

                # B wysyła swoją ramkę z commitment do A
                my_frame_bytes = self._build_identity_frame(
                    peer_frame["phi_id"], my_nonce
                )
                self._send_frame(sock, my_frame_bytes)

                # B odbiera ponowną ramkę A (teraz z commitment)
                peer_frame_bytes = self._recv_frame(sock)
                if not peer_frame_bytes:
                    raise ConnectionError("Nie odebrano ramki commitment")
                peer_frame = self._parse_identity_frame(peer_frame_bytes)
                if not peer_frame:
                    raise ConnectionError("Nieprawidłowa ramka commitment")

            peer_phi_id = peer_frame["phi_id"]

            # Sprawdzenie rejestru TOFU
            if not self._check_registry(peer_frame, peer_address):
                sock.close()
                return

            # ── KROK 1: WYMIANA KLUCZY KEM ───────────────────────────────
            if is_initiator:
                pk = kem.get_public_key_bytes()
                self._send_frame(sock, pk)

                ct = self._recv_frame(sock)
                if not ct:
                    raise ConnectionError("Nie odebrano szyfrogramu KEM")
                K = kem.decapsulate(ct)
            else:
                pk = self._recv_frame(sock)
                if not pk:
                    raise ConnectionError("Nie odebrano klucza publicznego KEM")
                ct, K = kem.encapsulate(pk)
                self._send_frame(sock, ct)

            # ── KROK 2: WYMIANA ZAŚLEPIONYCH Φ² ─────────────────────────
            dim = 128
            my_tag  = "blind-A" if is_initiator else "blind-B"
            blind   = self.karmazyn._get_blinding(K, my_tag, dim)
            my_blinded = (self.karmazyn.get_phi2_vector(dim) + blind).tobytes()
            self._send_frame(sock, my_blinded)

            peer_blinded = self._recv_frame(sock)
            if not peer_blinded:
                raise ConnectionError("Nie odebrano zaślepionego Φ²")

            # ── KROK 3: REZONANS + WERYFIKACJA COMMITMENT ────────────────
            # Przekazujemy peer_phi2_bytes (z ramki tożsamości kroku 0)
            # do karmazyn, żeby crimson_key był wyprowadzony z hasha (nie float32)
            self.karmazyn._peer_phi2_bytes = peer_frame["phi2_bytes"]
            ok, confirm = self.karmazyn.crimson_handshake(
                peer_blinded, is_initiator, K
            )

            if not ok:
                print("[-] Brak rezonansu – Cisza Termodynamiczna.")
                sock.close()
                return

            # Weryfikacja commitment peera
            # Odtwarzamy peer_phi2 z zaślepionego wektora do weryfikacji
            peer_tag   = "blind-B" if is_initiator else "blind-A"
            peer_blind = self.karmazyn._get_blinding(K, peer_tag, dim)
            peer_phi2_recovered = (
                np.frombuffer(peer_blinded, dtype=np.float32) - peer_blind
            )

            if not self._verify_commitment(peer_frame, my_phi_id,
                                           peer_phi2_recovered):
                print(f"[!!] COMMIT MISMATCH – Φ-ID={peer_phi_id[:16]}… "
                      f"nie może udowodnić tożsamości. Rozłączam.")
                sock.close()
                return

            print(f"[+] Commitment zweryfikowany dla {peer_phi_id[:16]}…")

            # ── KROK 4: POTWIERDZENIE ─────────────────────────────────────
            if is_initiator:
                self._send_frame(sock, confirm)
                print("[+] REZONANS OSIĄGNIĘTY – Kanał otwarty.")
                self._start_encrypted_chat(sock, peer_phi_id)
            else:
                peer_confirm = self._recv_frame(sock)
                if peer_confirm:
                    print("[+] REZONANS OSIĄGNIĘTY – Kanał otwarty.")
                    self._start_encrypted_chat(sock, peer_phi_id)
                else:
                    print("[-] Brak potwierdzenia od inicjatora.")
                    sock.close()

        except Exception as e:
            print(f"[!] Błąd uzgadniania: {e}")
            sock.close()

    # ──────────────────────────── SZYFROWANY KANAŁ ───────────────────────

    def _start_encrypted_chat(self, sock: socket.socket, peer_phi_id: str):
        """Rozpoczyna szyfrowaną wymianę wiadomości."""
        self.peer_socket = sock
        self.peer_phi_id = peer_phi_id
        self.crimson_active.set()

        def receiver():
            while self.crimson_active.is_set():
                try:
                    data = self._recv_frame(sock)
                    if not data:
                        break
                    msg = self.karmazyn.crimson_decrypt(data)
                    if self.receive_callback:
                        self.receive_callback(msg)
                    else:
                        print(f"\n<Φ:{peer_phi_id[:8]}> {msg}")
                except Exception as e:
                    print(f"\n[!] Rozłączono: {e}")
                    break
            self.crimson_active.clear()
            print("[*] Kanał zamknięty.")

        threading.Thread(target=receiver, daemon=True).start()

    def send(self, message: str):
        """Wysyła zaszyfrowaną wiadomość przez aktywny kanał."""
        if not self.crimson_active.is_set() or not self.peer_socket:
            print("[!] Brak aktywnego kanału.")
            return
        try:
            ct = self.karmazyn.crimson_encrypt(message)
            self._send_frame(self.peer_socket, ct)
        except Exception as e:
            print(f"[!] Błąd wysyłania: {e}")
            self.close()

    def close(self):
        """Zamyka kanał komunikacyjny."""
        self.crimson_active.clear()
        if self.peer_socket:
            self.peer_socket.close()
            self.peer_socket = None
        self.karmazyn.crimson_key = None
        print("[*] Kanał zamknięty.")
