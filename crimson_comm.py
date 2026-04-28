#!/usr/bin/env python3
import socket
import threading
import sys
import numpy as np
from crimson_daemon import CrimsonNode  # klasa z poprzedniego fragmentu

# ===== Konfiguracja =====
MY_PORT = int(sys.argv[1])          # port, na którym nasłuchujemy
PEER_HOST = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
PEER_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else None

# Dwa przykładowe, silnie rezonujące wektory Φ² (w praktyce każdy ma swój)
np.random.seed(42)  # dla demonstracji, aby oba były podobne
PHI_BASE = np.random.randn(128).astype(np.float32)
MY_PHI = PHI_BASE + 0.05 * np.random.randn(128).astype(np.float32)

# Próg rezonansu – ustawiony na 0.9 (kosinus)
THETA = 0.9

node = CrimsonNode(MY_PHI, THETA)
peer_socket = None      # gniazdo do drugiej strony
s_crimson_ready = threading.Event()

def handle_incoming(client_sock, addr):
    """Wątek obsługi połączenia przychodzącego (serwer)."""
    global peer_socket
    peer_socket = client_sock
    print(f"[+] Połączono z {addr}")
    
    try:
        # Odbierz zaślepione Φ² od inicjatora
        data = recv_all(client_sock, 128 * 4)  # 128 float32
        if not data:
            return
        
        # Jesteśmy odpowiadającym (B)
        # W rzeczywistym protokole Kyber wymaga wcześniejszej wymiany,
        # tutaj dla uproszczenia pomijamy fazę enkapsulacji
        # i od razu używamy zaślepienia (symulacja).
        # W pełnej wersji należy zintegrować Kyber handshake.
        ok, confirm = node.complete_handshake(data, is_initiator=False)
        
        if ok:
            client_sock.sendall(confirm)   # potwierdzenie rezonansu
            s_crimson_ready.set()
            print("[+] Rezonans osiągnięty! Kanał karmazynowy otwarty.")
            receiver_loop(client_sock)
        else:
            # Cisza termodynamiczna – zamykamy połączenie bez słowa
            client_sock.close()
            print("[-] Brak rezonansu – cisza termodynamiczna.")
    except Exception as e:
        print(f"[!] Błąd: {e}")
    finally:
        if peer_socket:
            peer_socket.close()

def initiate_connection(host, port):
    """Wątek klienta inicjującego połączenie."""
    global peer_socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        peer_socket = sock
        print(f"[+] Połączono z {host}:{port}")
        
        # Wysyłamy zaślepione Φ² (jako inicjator A)
        blind = node._get_blinding("blind-A") + node.phi2
        sock.sendall(blind.tobytes())
        
        # Odbieramy potwierdzenie od B
        confirm = recv_all(sock, 128 * 4)
        if not confirm:
            return
        
        ok, _ = node.complete_handshake(confirm, is_initiator=True)
        if ok:
            s_crimson_ready.set()
            print("[+] Rezonans osiągnięty! Kanał karmazynowy otwarty.")
            receiver_loop(sock)
        else:
            sock.close()
            print("[-] Brak rezonansu – cisza termodynamiczna.")
    except Exception as e:
        print(f"[!] Nie można połączyć: {e}")

def recv_all(sock, n):
    """Odbiera dokładnie n bajtów."""
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data

def receiver_loop(sock):
    """Pętla odbierania wiadomości."""
    while True:
        try:
            # Każda wiadomość to: długość(4B) + nonce(16B) + ct + tag(16B)
            raw_len = recv_all(sock, 4)
            if not raw_len:
                break
            msg_len = int.from_bytes(raw_len, 'big')
            data = recv_all(sock, msg_len)
            if not data:
                break
            plain = node.decrypt_message(data)
            print(f"<Odebrano> {plain}")
        except Exception as e:
            print(f"[!] Rozłączono: {e}")
            break

def sender_loop():
    """Wątek wysyłania wiadomości z konsoli."""
    while True:
        try:
            msg = input()
            if msg.lower() == "/quit":
                if peer_socket:
                    peer_socket.close()
                break
            if not s_crimson_ready.is_set():
                print("[!] Kanał jeszcze nie gotowy.")
                continue
            ciphertext = node.encrypt_message(msg)
            # Ramka: długość + szyfrogram
            frame = len(ciphertext).to_bytes(4, 'big') + ciphertext
            peer_socket.sendall(frame)
        except (BrokenPipeError, OSError):
            break

# ===== Uruchomienie =====
if __name__ == "__main__":
    threading.Thread(target=sender_loop, daemon=True).start()
    
    # Serwer nasłuchujący
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", MY_PORT))
    server.listen(1)
    print(f"[*] Nasłuchiwanie na porcie {MY_PORT}")
    
    if PEER_PORT:
        # Jeśli podano port partnera, inicjujemy połączenie
        threading.Thread(target=initiate_connection, args=(PEER_HOST, PEER_PORT), daemon=True).start()
    
    # Akceptujemy jedno połączenie przychodzące
    client, addr = server.accept()
    threading.Thread(target=handle_incoming, args=(client, addr), daemon=True).start()
    
    # Czekamy na zakończenie
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("\n[*] Zamykanie komunikatora.")
