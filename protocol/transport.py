"""Length-prefixed binary frames over a TCP byte stream."""

import socket
import struct

from config import MAX_FRAME


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read n bytes or raise EOFError when the peer closes early."""
    parts = []
    while n:
        chunk = sock.recv(n)
        if not chunk:
            raise EOFError("Koneksi ditutup")
        parts.append(chunk)
        n -= len(chunk)
    return b"".join(parts)


def send_frame(sock: socket.socket, data: bytes) -> None:
    """Send a four-byte big-endian length and the frame body."""
    if len(data) > MAX_FRAME:
        raise ValueError("Frame terlalu panjang")
    sock.sendall(struct.pack("!I", len(data)) + data)


def recv_frame(sock: socket.socket) -> bytes:
    """Read a frame after checking its declared size."""
    size = struct.unpack("!I", recv_exact(sock, 4))[0]
    if size > MAX_FRAME:
        raise ValueError("Frame terlalu panjang")
    return recv_exact(sock, size)
