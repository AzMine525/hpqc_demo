"""Authenticated DATA and ACK records on a fresh Stage 04 connection."""

from dataclasses import dataclass
import secrets
import socket
import struct
from threading import Lock
from typing import Optional, Union

from cryptography.exceptions import InvalidTag

from crypto_engine.v2.aead import DirectionCipher, DirectionContext
from crypto_engine.v2.suites import DEFAULT_SUITE
from protocol.handshake_v2 import DEFAULT_TIMEOUT, VERSION, establish
from protocol.transport import recv_exact

DATA = 0x10
ACK = 0x11
HEADER = struct.Struct("!BBB16sBQ12sI")
TAG_SIZE = 16
ID_SIZE = 16
MAX_DATA = 1 << 20
MAX_BODY = 2 << 20


class RecordError(ValueError):
    """The peer sent an invalid record. The channel has been closed."""


@dataclass(frozen=True, repr=False)
class ReceivedData:
    message_id: bytes
    payload: bytes


@dataclass(frozen=True)
class Acknowledgement:
    message_id: bytes


class DataChannel:
    """Own a connected socket, its handshake, and one cipher per direction."""

    def __init__(self, sock: socket.socket, *, role: str, psk: bytes,
                 timeout: float = DEFAULT_TIMEOUT, suite: str = DEFAULT_SUITE) -> None:
        self._sock = sock
        self._session = establish(sock, role=role, psk=psk, timeout=timeout, suite=suite)
        try:
            session = self._session
            self._out = DirectionContext(VERSION, session.suite_id, session.session_id, session.role)
            self._in = DirectionContext(VERSION, session.suite_id, session.session_id, 1 - session.role)
            self._tx: Optional[DirectionCipher] = DirectionCipher(session.traffic_keys.send, self._out)
            self._rx: Optional[DirectionCipher] = DirectionCipher(session.traffic_keys.receive, self._in)
            self._send_sequence = 0
            self._receive_sequence = 0
            self._sent_ids: set[bytes] = set()
            self._received_ids: set[bytes] = set()
            self._pending: Optional[bytes] = None
            self._send_lock = Lock()
            self._receive_lock = Lock()
            self._close_lock = Lock()
        except BaseException:
            self._session.close()
            raise

    def _write(self, kind: int, plaintext: bytes) -> None:
        """Called with the send lock held, also when replying from receive()."""
        cipher = self._tx
        if cipher is None:
            raise ConnectionError("Channel closed")
        seq = self._send_sequence
        nonce, sealed = cipher.encrypt(plaintext, message_type=kind, sequence=seq)
        header = self._out.build_aad(kind, seq, nonce, len(plaintext))
        self._sock.sendall(struct.pack("!I", len(header) + len(sealed)) + header + sealed)
        self._send_sequence += 1

    def send_data(self, payload: bytes) -> bytes:
        """Send binary DATA and return its ID. receive() verifies the corresponding ACK."""
        if type(payload) is not bytes or len(payload) > MAX_DATA:
            raise ValueError("Expected a payload of at most 1 MiB")
        with self._send_lock:
            if self._tx is None:
                raise ConnectionError("Channel closed")
            if self._pending is not None:
                raise RuntimeError("Previous DATA still awaits its ACK")
            try:
                message_id = secrets.token_bytes(ID_SIZE)
                if message_id in self._sent_ids:
                    raise RuntimeError("Message ID collision; fresh session required")
                self._write(DATA, message_id + payload)
                self._sent_ids.add(message_id)
                self._pending = message_id
                return message_id
            except BaseException:
                self.close()
                raise

    def _read(self) -> tuple[int, bytes]:
        cipher = self._rx
        if cipher is None:
            raise ConnectionError("Channel closed")
        body_size, = struct.unpack("!I", recv_exact(self._sock, 4))
        if not HEADER.size + ID_SIZE + TAG_SIZE <= body_size <= MAX_BODY:
            raise RecordError("Invalid record size")
        header = recv_exact(self._sock, HEADER.size)
        version, kind, suite, session_id, direction, seq, nonce, size = HEADER.unpack(header)
        if (version, suite, session_id, direction, seq) != (
            VERSION, self._in.suite, self._in.session_id, self._in.direction, self._receive_sequence
        ):
            raise RecordError("Unexpected record context or sequence")
        if size + HEADER.size + TAG_SIZE != body_size:
            raise RecordError("Inconsistent ciphertext length")
        if kind == DATA:
            if not ID_SIZE <= size <= ID_SIZE + MAX_DATA:
                raise RecordError("Invalid DATA size")
        elif kind != ACK or size != ID_SIZE:
            raise RecordError("Invalid record type or ACK size")
        sealed = recv_exact(self._sock, size + TAG_SIZE)
        try:
            plaintext = cipher.decrypt(nonce, sealed, message_type=kind, sequence=seq)
        except InvalidTag:
            raise RecordError("Record authentication failed") from None
        return kind, plaintext

    def receive(self) -> Union[ReceivedData, Acknowledgement]:
        """Read one authenticated record. Send an ACK only for accepted DATA."""
        with self._receive_lock:
            try:
                kind, plaintext = self._read()
                message_id = plaintext[:ID_SIZE]
                if kind == DATA:
                    if message_id in self._received_ids:
                        raise RecordError("Duplicate DATA ID")
                    record = ReceivedData(message_id, plaintext[ID_SIZE:])
                    self._received_ids.add(message_id)
                    self._receive_sequence += 1
                    with self._send_lock:
                        self._write(ACK, message_id)
                    return record
                with self._send_lock:
                    if self._pending != message_id:
                        raise RecordError("Unexpected ACK ID")
                    self._pending = None
                self._receive_sequence += 1
                return Acknowledgement(message_id)
            except BaseException:
                self.close()
                raise

    def close(self) -> None:
        """Interrupt blocked socket I/O and discard the directional ciphers."""
        with self._close_lock:
            if self._tx is None:
                return
            self._tx = self._rx = None
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                self._session.close()

    def __enter__(self) -> "DataChannel":
        if self._tx is None:
            raise ConnectionError("Channel closed")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
