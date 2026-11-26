"""Authenticated Stage 04 key establishment on an already-connected stream."""

import hashlib
import hmac
import math
import secrets
import socket
import struct
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from crypto_engine.v2.kdf import SessionKeys, derive_keys
from crypto_engine.v2.suites import DEFAULT_SUITE, SUITES, Suite

VERSION = 2
SUITE = SUITES[DEFAULT_SUITE].wire_id
CLIENT, SERVER = 0, 1
DEFAULT_TIMEOUT = 10.0


class HandshakeError(Exception):
    """The peer or transport failed the handshake. The socket is closed."""


class HandshakeTimeout(HandshakeError):
    """The deadline for completing the whole handshake expired."""


class HandshakeTransportError(HandshakeError):
    """The stream closed or failed before the handshake completed."""


class Message(IntEnum):
    CLIENT_HELLO = 1
    SERVER_HELLO = 2
    CLIENT_KEM = 3
    CLIENT_FINISHED = 4
    SERVER_FINISHED = 5


class _Exchange:
    """Ordered wire transcript and a single monotonic deadline."""

    def __init__(self, sock: socket.socket, timeout: float, suite: Suite):
        self.sock = sock
        self.suite = suite
        self.layout = {
            Message.CLIENT_HELLO: (CLIENT, 32),
            Message.SERVER_HELLO: (SERVER, 32 + 16 + suite.engine.public_size + 32),
            Message.CLIENT_KEM: (CLIENT, suite.engine.ciphertext_size + 32),
            Message.CLIENT_FINISHED: (CLIENT, 32),
            Message.SERVER_FINISHED: (SERVER, 32),
        }
        self.deadline = time.monotonic() + timeout
        self.transcript = hashlib.sha256(b"HPQC/v2/handshake\x00")

    def _header(self, kind: Message) -> bytes:
        return bytes((VERSION, kind, self.suite.wire_id, self.layout[kind][0]))

    def _frame(self, kind: Message, payload: bytes) -> bytes:
        body = self._header(kind) + payload
        return struct.pack("!I", len(body)) + body

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise HandshakeTimeout("Handshake timed out")
        return remaining

    def _read(self, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            self.sock.settimeout(self.remaining())
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise HandshakeTransportError("Incomplete handshake")
            data.extend(chunk)
        return bytes(data)

    def _write(self, kind: Message, payload: bytes) -> None:
        frame = self._frame(kind, payload)
        self.sock.settimeout(self.remaining())
        self.sock.sendall(frame)
        self.transcript.update(frame)

    def _receive(self, kind: Message) -> bytes:
        length, = struct.unpack("!I", self._read(4))
        if length != 4 + self.layout[kind][1]:
            raise HandshakeError("Unexpected handshake length")
        if self._read(4) != self._header(kind):
            raise HandshakeError("Unexpected handshake header")
        return self._read(length - 4)

    def send_hello(self, random: bytes) -> None:
        self._write(Message.CLIENT_HELLO, random)

    def receive_hello(self) -> bytes:
        random = self._receive(Message.CLIENT_HELLO)
        self.transcript.update(self._frame(Message.CLIENT_HELLO, random))
        return random

    def _proof(self, kind: Message, content: bytes, key: bytes) -> bytes:
        # The virtual frame omits the proof being calculated. Its typed header
        # separates sender, message purpose, version and suite.
        digest = self.transcript.copy()
        digest.update(self._frame(kind, content))
        return hmac.digest(key, b"HPQC/v2/proof\x00" + digest.digest(), "sha256")

    def send_proven(self, kind: Message, content: bytes, key: bytes) -> None:
        self._write(kind, content + self._proof(kind, content, key))

    def receive_proven(self, kind: Message, key: bytes) -> bytes:
        payload = self._receive(kind)
        content, proof = payload[:-32], payload[-32:]
        if not hmac.compare_digest(self._proof(kind, content, key), proof):
            raise HandshakeError("Handshake proof rejected")
        self.transcript.update(self._frame(kind, payload))
        return content


@dataclass(frozen=True, repr=False)
class TrafficKeys:
    send: bytes
    receive: bytes


class ConfirmedSession:
    """Own the connected socket and traffic keys until close or context exit."""

    def __init__(self, sock: socket.socket, role: int, session_id: bytes,
                 transcript_hash: bytes, traffic_keys: TrafficKeys, suite_id: int = SUITE):
        self._sock = sock
        self.role = role
        self.suite_id = suite_id
        self.session_id = session_id
        self.transcript_hash = transcript_hash
        self._keys: Optional[TrafficKeys] = traffic_keys

    @property
    def traffic_keys(self) -> TrafficKeys:
        if self._keys is None:
            raise RuntimeError("Session closed")
        return self._keys

    def close(self) -> None:
        self._keys = None
        self._sock.close()

    def __enter__(self) -> "ConfirmedSession":
        if self._keys is None:
            raise RuntimeError("Session closed")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _keys(exchange: _Exchange, secret: bytes, client_random: bytes,
          server_random: bytes) -> SessionKeys:
    return derive_keys(secret, client_random=client_random, server_random=server_random,
                       version=VERSION, suite=exchange.suite.wire_id, transcript_hash=exchange.transcript.digest())


def _client(exchange: _Exchange, psk: bytes) -> tuple[bytes, TrafficKeys]:
    client_random = secrets.token_bytes(32)
    exchange.send_hello(client_random)
    hello = exchange.receive_proven(Message.SERVER_HELLO, psk)
    server_random, session_id, public = hello[:32], hello[32:48], hello[48:]
    ciphertext, secret = exchange.suite.engine.encapsulate(public)
    exchange.send_proven(Message.CLIENT_KEM, ciphertext, psk)
    keys = _keys(exchange, secret, client_random, server_random)
    exchange.send_proven(Message.CLIENT_FINISHED, b"", keys.confirm_client)
    exchange.receive_proven(Message.SERVER_FINISHED, keys.confirm_server)
    return session_id, TrafficKeys(keys.aes_c2s, keys.aes_s2c)


def _server(exchange: _Exchange, psk: bytes) -> tuple[bytes, TrafficKeys]:
    client_random = exchange.receive_hello()
    server_random, session_id = secrets.token_bytes(32), secrets.token_bytes(16)
    public, private = exchange.suite.engine.generate_keypair()
    exchange.send_proven(Message.SERVER_HELLO, server_random + session_id + public, psk)
    ciphertext = exchange.receive_proven(Message.CLIENT_KEM, psk)
    secret = exchange.suite.engine.decapsulate(private, ciphertext)
    keys = _keys(exchange, secret, client_random, server_random)
    exchange.receive_proven(Message.CLIENT_FINISHED, keys.confirm_client)
    exchange.send_proven(Message.SERVER_FINISHED, b"", keys.confirm_server)
    return session_id, TrafficKeys(keys.aes_s2c, keys.aes_c2s)


def establish(sock: socket.socket, *, role: str, psk: bytes,
              timeout: float = DEFAULT_TIMEOUT, suite: str = DEFAULT_SUITE) -> ConfirmedSession:
    """Take ownership of a connected socket. Return a confirmed session or close it."""
    success = False
    try:
        if type(psk) is not bytes or len(psk) != 32:
            raise ValueError("PSK must be exactly 32 bytes")
        if role not in ("client", "server"):
            raise ValueError("Unknown handshake role")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Handshake timeout must be finite and positive")
        if not isinstance(suite, str) or suite not in SUITES:
            raise ValueError("Unknown key establishment suite")
        previous_timeout = sock.gettimeout()
        exchange = _Exchange(sock, timeout, SUITES[suite])
        try:
            if role == "client":
                session_id, keys = _client(exchange, psk)
                role_id = CLIENT
            else:
                session_id, keys = _server(exchange, psk)
                role_id = SERVER
            exchange.remaining()
            sock.settimeout(previous_timeout)
        except socket.timeout:
            raise HandshakeTimeout("Handshake timed out") from None
        except OSError:
            raise HandshakeTransportError("Handshake transport failed") from None
        except ValueError:
            raise HandshakeError("Handshake failed") from None
        session = ConfirmedSession(sock, role_id, session_id, exchange.transcript.digest(), keys,
                                   exchange.suite.wire_id)
        success = True
        return session
    finally:
        if not success:
            sock.close()
