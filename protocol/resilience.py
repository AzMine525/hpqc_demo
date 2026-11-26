"""Stop-and-wait application delivery over independently authenticated v2 sessions."""

from dataclasses import dataclass
import math
from pathlib import Path
import secrets
import socket
import sqlite3
import time
from typing import Callable, Optional

from crypto_engine.v2.suites import DEFAULT_SUITE, SUITES
from protocol.data_v2 import Acknowledgement, DataChannel, MAX_DATA, ReceivedData, RecordError
from protocol.handshake_v2 import HandshakeError, HandshakeTimeout, HandshakeTransportError

PROFILE = b"HPQ9"
MESSAGE, RECEIPT, PING, PONG = (bytes([n]) for n in range(1, 5))
TRANSIENT = (EOFError, OSError, HandshakeTimeout, HandshakeTransportError)


@dataclass(frozen=True)
class Policy:
    timeout: float = 5.0
    retries: int = 3
    backoff: float = 0.2
    cap: float = 2.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) and v > 0 for v in (self.timeout, self.backoff, self.cap)):
            raise ValueError("Timeout and backoff must be finite and positive")
        if type(self.retries) is not int or self.retries < 0 or self.cap < self.backoff:
            raise ValueError("Invalid retry policy")


class TimedStream:
    """Apply one monotonic deadline across all partial reads/writes of an exchange."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.deadline: Optional[float] = None

    def __getattr__(self, name: str):
        return getattr(self.sock, name)

    def begin(self, seconds: float) -> None:
        self.deadline = time.monotonic() + seconds

    def _arm(self) -> None:
        if self.deadline is not None:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("Exchange deadline exceeded")
            self.sock.settimeout(remaining)

    def recv(self, n: int) -> bytes:
        self._arm()
        return self.sock.recv(n)

    def sendall(self, data: bytes) -> None:
        self._arm()
        self.sock.sendall(data)


class Inbox:
    """One SQLite inbox per provisioned peer. The committed row is the delivery."""

    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, timeout=1.0)
        self.db.execute("CREATE TABLE IF NOT EXISTS inbox "
                        "(message_id BLOB PRIMARY KEY, payload BLOB NOT NULL)")

    def accept(self, message_id: bytes, payload: bytes) -> bool:
        """Atomically commit new content, or verify an identical previous delivery."""
        with self.db:
            inserted = self.db.execute("INSERT INTO inbox VALUES (?, ?) ON CONFLICT(message_id) "
                                       "DO NOTHING", (message_id, payload)).rowcount
            if not inserted:
                stored, = self.db.execute("SELECT payload FROM inbox WHERE message_id=?",
                                          (message_id,)).fetchone()
                if stored != payload:
                    raise RecordError("Conflicting logical message ID")
            return bool(inserted)

    def close(self) -> None:
        self.db.close()


def _send(channel: DataChannel, payload: bytes) -> None:
    record_id = channel.send_data(payload)
    if channel.receive() != Acknowledgement(record_id):
        raise RecordError("Expected authenticated record ACK")


def _read(channel: DataChannel) -> bytes:
    record = channel.receive()
    if not isinstance(record, ReceivedData):
        raise RecordError("Expected authenticated DATA")
    return record.payload


def serve_session(sock: socket.socket, psk: bytes, suite: str, inbox: Inbox,
                  timeout: float, idle: float, event: Callable[[dict], None]) -> None:
    """Serve one pinned peer until disconnect, deadline, or protocol rejection."""
    stream = TimedStream(sock)
    with DataChannel(stream, role="server", psk=psk, suite=suite, timeout=timeout) as channel:
        while True:
            stream.begin(idle)
            control = _read(channel)
            if len(control) != 21 or not control.startswith(PROFILE):
                raise RecordError("Invalid recovery envelope")
            kind, logical_id = control[4:5], control[5:]
            stream.begin(timeout)
            if kind == PING:
                reply = PONG
            elif kind == MESSAGE:
                payload = _read(channel)
                new = inbox.accept(logical_id, payload)
                event(dict(event="committed" if new else "duplicate", id=logical_id.hex()))
                reply = RECEIPT
            else:
                raise RecordError("Unexpected recovery command")
            _send(channel, PROFILE + reply + logical_id)


class RecoveryClient:
    """Single-owner client. A logical operation has one ID and a bounded retry budget."""

    def __init__(self, address: tuple[str, int], psk: bytes, *, suite: str = DEFAULT_SUITE,
                 policy: Policy = Policy(), event: Callable[[dict], None] = lambda row: None):
        if suite not in SUITES or type(psk) is not bytes or len(psk) != 32:
            raise ValueError("Invalid suite or PSK")
        self.address, self.psk, self.suite = address, psk, suite
        self.policy, self.event = policy, event
        self.channel: Optional[DataChannel] = None
        self.stream: Optional[TimedStream] = None
        self.failure_ns: Optional[int] = None

    def close(self) -> None:
        if self.channel is not None:
            self.channel.close()
        self.channel = self.stream = None

    def _log(self, name: str, attempt: int, logical_id: bytes, **fields) -> None:
        now = time.perf_counter_ns()
        elapsed = None if self.failure_ns is None else now - self.failure_ns
        self.event(dict(event=name, attempt=attempt, id=logical_id.hex(), at_ns=now,
                        since_detection_ns=elapsed, **fields))

    def _connect(self, attempt: int, logical_id: bytes) -> None:
        sock = socket.create_connection(self.address, timeout=self.policy.timeout)
        try:
            self._log("tcp_connected", attempt, logical_id)
            stream = TimedStream(sock)
            channel = DataChannel(stream, role="client", psk=self.psk, suite=self.suite,
                                  timeout=self.policy.timeout)
        except BaseException:
            sock.close()
            raise
        self.stream, self.channel = stream, channel
        self._log("secure_ready", attempt, logical_id, session=channel.session_id.hex())

    def _exchange(self, logical_id: bytes, payload: Optional[bytes]) -> bytes:
        delay = self.policy.backoff
        kind, expected = (PING, PONG) if payload is None else (MESSAGE, RECEIPT)
        for attempt in range(1, self.policy.retries + 2):
            try:
                self._log("attempt_started", attempt, logical_id,
                          operation="heartbeat" if payload is None else "message")
                if self.channel is None:
                    self._connect(attempt, logical_id)
                self.stream.begin(self.policy.timeout)
                _send(self.channel, PROFILE + kind + logical_id)
                if payload is not None:
                    _send(self.channel, payload)
                if _read(self.channel) != PROFILE + expected + logical_id:
                    raise RecordError("Unexpected recovery response")
                self._log("pong" if payload is None else "delivered", attempt, logical_id)
                self.failure_ns = None
                return logical_id
            except TRANSIENT as exc:
                if self.failure_ns is None:
                    self.failure_ns = time.perf_counter_ns()
                self.close()
                self._log("interrupted", attempt, logical_id, error=type(exc).__name__)
                if attempt > self.policy.retries:
                    self._log("exhausted", attempt, logical_id)
                    raise
                self._log("backoff", attempt, logical_id, seconds=delay)
                time.sleep(delay)
                delay = min(delay * 2, self.policy.cap)
            except (HandshakeError, RecordError, RuntimeError, ValueError):
                self.close()
                self._log("rejected", attempt, logical_id)
                raise

    def send(self, payload: bytes, message_id: Optional[bytes] = None) -> bytes:
        """Return the stable ID after a receipt confirming peer inbox commit."""
        if type(payload) is not bytes or len(payload) > MAX_DATA:
            raise ValueError("Expected a payload of at most 1 MiB")
        if message_id is None:
            message_id = secrets.token_bytes(16)
        if type(message_id) is not bytes or len(message_id) != 16:
            raise ValueError("Expected a 16-byte message ID")
        return self._exchange(message_id, payload)

    def heartbeat(self) -> None:
        """Require a fresh authenticated challenge response, recovering if necessary."""
        self._exchange(secrets.token_bytes(16), None)

    def wait(self, duration: float, interval: float) -> None:
        """During an idle period, probe at each interval until the next send is due."""
        if not math.isfinite(duration) or duration < 0 or not math.isfinite(interval) or interval <= 0:
            raise ValueError("Invalid idle or heartbeat interval")
        end = time.monotonic() + duration
        while True:
            remaining = end - time.monotonic()
            if remaining <= interval:
                time.sleep(max(0, remaining))
                return
            time.sleep(interval)
            self.heartbeat()
