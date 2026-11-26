"""Two-frame ML-KEM-768 key exchange used by the prototype."""

import hashlib
import socket

from crypto_engine.kdf import keys_from_secret
from crypto_engine.kem import decaps, encaps, keygen
from protocol.transport import recv_frame, send_frame


def server_handshake(sock: socket.socket) -> tuple[bytes, bytes]:
    """Send a fresh public key and derive keys from the received ciphertext."""
    public, private = keygen()
    print("SHA256 fingerprint public key server:", hashlib.sha256(public).hexdigest())
    send_frame(sock, public)
    kem_ct = recv_frame(sock)
    return keys_from_secret(decaps(private, kem_ct))


def client_handshake(sock: socket.socket) -> tuple[bytes, bytes]:
    """Encapsulate to the received key and send the KEM ciphertext."""
    public = recv_frame(sock)
    print("SHA256 fingerprint public key diterima:", hashlib.sha256(public).hexdigest())
    print("PERINGATAN: Verifikasi fingerprint ini melalui jalur tepercaya sebelum menganggap peer terautentikasi.")
    kem_ct, secret = encaps(public)
    send_frame(sock, kem_ct)
    return keys_from_secret(secret)
