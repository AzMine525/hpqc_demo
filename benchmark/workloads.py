"""Measure the production crypto engine and two HPQC endpoints on IPv4 loopback."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
import secrets
import socket
import struct
import sys
from time import perf_counter_ns, process_time_ns
from typing import Callable, Optional, TypeVar, Union

import psutil

from crypto_engine.v2.aead import DirectionCipher, DirectionContext
from crypto_engine.v2.kdf import derive_keys
from crypto_engine.v2.suites import SUITES
from protocol.data_v2 import Acknowledgement, DATA, DataChannel, ReceivedData
from protocol.handshake_v2 import VERSION

LOOPBACK = "127.0.0.1"
SIZES = (1024, 100 * 1024, 1024 * 1024)
DIRECTIONS = ("client_to_server", "server_to_client")
T = TypeVar("T")


class BenchmarkError(Exception):
    """The measured workload failed its application-level checks."""


@dataclass(frozen=True)
class Sample:
    metric: str
    unit: str
    value: Optional[Union[int, float]] = None
    payload_bytes: int = 0
    direction: str = ""
    status: str = "ok"
    error: str = ""


def measure(samples: list[Sample], process: psutil.Process, name: str,
            operation: Callable[[], T], size: int = 0) -> T:
    """Measure wall/CPU time and take two process RSS snapshots per operation."""
    rss_before = process.memory_info().rss
    cpu_start = process_time_ns()
    start = perf_counter_ns()
    result = operation()
    elapsed = perf_counter_ns() - start
    cpu = process_time_ns() - cpu_start
    rss_after = process.memory_info().rss
    for suffix, unit, value in (
        ("wall", "ns", elapsed), ("cpu", "ns", cpu),
        ("rss_before", "bytes", rss_before), ("rss_after", "bytes", rss_after),
    ):
        samples.append(Sample(f"{name}_{suffix}", unit, value, size))
    return result


def crypto_trial(samples: list[Sample], process: psutil.Process, suite: str) -> None:
    """Exercise one key exchange and key schedule, then AEAD at each payload size."""
    choice = SUITES[suite]
    engine = choice.engine
    public, private = measure(samples, process, "keygen", engine.generate_keypair)
    ciphertext, secret = measure(samples, process, "encapsulate", lambda: engine.encapsulate(public))
    peer_secret = measure(samples, process, "decapsulate", lambda: engine.decapsulate(private, ciphertext))
    if peer_secret != secret:
        raise BenchmarkError("Secret mismatch")

    client_random, server_random, digest = (secrets.token_bytes(32) for _ in range(3))
    keys = measure(samples, process, "hkdf", lambda: derive_keys(
        secret, client_random=client_random, server_random=server_random,
        version=VERSION, suite=choice.wire_id, transcript_hash=digest,
    ))
    context = DirectionContext(VERSION, choice.wire_id, secrets.token_bytes(16), 0)
    sender = DirectionCipher(keys.aes_c2s, context)
    receiver = DirectionCipher(keys.aes_c2s, context)
    for seq, size in enumerate(SIZES):
        payload = secrets.token_bytes(size)
        nonce, sealed = measure(samples, process, "aes_encrypt", lambda: sender.encrypt(
            payload, message_type=DATA, sequence=seq), size)
        decoded = measure(samples, process, "aes_decrypt", lambda: receiver.decrypt(
            nonce, sealed, message_type=DATA, sequence=seq), size)
        if decoded != payload:
            raise BenchmarkError("Plaintext mismatch")


class CountedSocket:
    """Count bytes successfully written to TCP without retaining frame contents."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.bytes_sent = 0

    def __getattr__(self, name: str):
        return getattr(self.sock, name)

    def sendall(self, data: bytes) -> None:
        self.sock.sendall(data)
        self.bytes_sent += len(data)


def tcp_retransmissions(sock: socket.socket) -> Optional[int]:
    """Read Linux per-socket tcpi_total_retrans when exposed by the kernel."""
    if not sys.platform.startswith("linux") or not hasattr(socket, "TCP_INFO"):
        return None
    # Linux UAPI struct tcp_info: eight bytes and 23 u32 fields precede this u32.
    offset = 100
    try:
        info = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, offset + 4)
    except OSError:
        return None
    return struct.unpack_from("=I", info, offset)[0] if len(info) >= offset + 4 else None


def confirmed_rtt(pool: ThreadPoolExecutor, sender: DataChannel,
                  receiver: DataChannel, payload: bytes) -> int:
    """Time one DATA-to-ACK exchange, with delivery verified at both endpoints."""
    received = pool.submit(receiver.receive)
    start = perf_counter_ns()
    sent_id = sender.send_data(payload)
    ack = sender.receive()
    elapsed = perf_counter_ns() - start
    if ack != Acknowledgement(sent_id) or received.result() != ReceivedData(sent_id, payload):
        raise BenchmarkError("Delivery verification failed")
    if elapsed <= 0:
        raise BenchmarkError("Clock did not advance")
    return elapsed


def network_trial(samples: list[Sample], process: psutil.Process,
                  suite: str, size: int, timeout: float) -> None:
    """Start a fresh connection and verify one DATA/ACK transfer in each direction."""
    payloads = (secrets.token_bytes(size), secrets.token_bytes(size))
    psk = secrets.token_bytes(32)
    confirmed = set()

    def exchange() -> None:
        with ExitStack() as stack:
            listener = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            listener.settimeout(timeout)
            listener.bind((LOOPBACK, 0))
            listener.listen(1)
            client_sock = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            client_sock.settimeout(timeout)
            address = listener.getsockname()
            start = perf_counter_ns()
            client_sock.connect(address)
            samples.append(Sample("tcp_connect", "ns", perf_counter_ns() - start, size))
            server_sock, _ = listener.accept()
            stack.enter_context(server_sock)
            server_sock.settimeout(timeout)
            left, right = CountedSocket(client_sock), CountedSocket(server_sock)
            pool = stack.enter_context(ThreadPoolExecutor(1))
            server_ready = pool.submit(DataChannel, right, role="server", psk=psk,
                                       suite=suite, timeout=timeout)
            start = perf_counter_ns()
            client = stack.enter_context(DataChannel(left, role="client", psk=psk,
                                                     suite=suite, timeout=timeout))
            server = stack.enter_context(server_ready.result())
            samples.append(Sample("handshake", "ns", perf_counter_ns() - start, size))
            samples.append(Sample("handshake_wire", "bytes", left.bytes_sent + right.bytes_sent, size))
            for direction, sender, receiver, payload in zip(
                DIRECTIONS, (client, server), (server, client), payloads,
            ):
                elapsed = confirmed_rtt(pool, sender, receiver, payload)
                confirmed.add(direction)
                samples.append(Sample("application_rtt", "ns", elapsed, size, direction))
                samples.append(Sample("goodput", "bytes/s", size * 1e9 / elapsed, size, direction))
            for sock, direction in zip((client_sock, server_sock), DIRECTIONS):
                total = tcp_retransmissions(sock)
                samples.append(Sample("tcp_retransmissions", "segments", total, size, direction,
                                      "unavailable" if total is None else "ok"))

    try:
        measure(samples, process, "network_session", exchange, size)
    finally:
        for direction in DIRECTIONS:
            samples.append(Sample("delivery_success", "ratio", int(direction in confirmed), size, direction))
