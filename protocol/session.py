"""Run a single interactive session with independent send and receive counters."""

import socket
import threading
import time

from crypto_engine.aead import MessageCipher
from protocol.handshake import client_handshake, server_handshake
from protocol.transport import recv_frame, send_frame


def handle(sock: socket.socket, server: bool) -> None:
    """Complete the handshake, exchange chat messages, and close the socket."""
    start = time.perf_counter()
    if server:
        key_c2s, key_s2c = server_handshake(sock)
        send_key, recv_key = key_s2c, key_c2s
        label_send, label_recv = b"s2c", b"c2s"
    else:
        key_c2s, key_s2c = client_handshake(sock)
        send_key, recv_key = key_c2s, key_s2c
        label_send, label_recv = b"c2s", b"s2c"
    print(f"ML-KEM handshake awal selesai ({(time.perf_counter()-start)*1000:.2f} ms; bukan RTT tersinkron).")
    tx = MessageCipher(send_key, label_send)
    rx = MessageCipher(recv_key, label_recv)
    stop = threading.Event()

    def receiver() -> None:
        receive_sequence = 0
        try:
            while not stop.is_set():
                payload = recv_frame(sock)
                plaintext = rx.decrypt(payload, receive_sequence)
                print("\n[Pesan diterima]:", plaintext.decode("utf-8"))
                print("Pesan kamu> ", end="", flush=True)
                receive_sequence += 1
        except (EOFError, ConnectionError, OSError):
            print("\nPeer menutup koneksi.")
        except Exception as exc:
            print("\nPesan ditolak / gagal diproses:", type(exc).__name__, str(exc))
        finally:
            stop.set()

    thread = threading.Thread(target=receiver, daemon=True)
    thread.start()
    send_sequence = 0
    print("Ketik pesan lalu Enter. Ketik /quit untuk keluar.")
    try:
        while not stop.is_set():
            message = input("Pesan kamu> ")
            if message.strip() == "/quit":
                break
            payload, elapsed_ms = tx.encrypt(message, send_sequence)
            send_frame(sock, payload)
            print(f"[Terkirim] ciphertext={len(payload)} bytes; AES encryption={elapsed_ms:.3f} ms")
            send_sequence += 1
    except (EOFError, KeyboardInterrupt, BrokenPipeError, ConnectionError, OSError):
        pass
    finally:
        stop.set()
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()
