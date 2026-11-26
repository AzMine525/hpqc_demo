"""Stage 06 synthetic control and HPQC v2 traffic, restricted to IPv4 loopback."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import secrets
import socket
import struct
import subprocess

from protocol.data_v2 import Acknowledgement, DataChannel, ReceivedData
from protocol.transport import recv_frame, send_frame

LOOPBACK = "127.0.0.1"
MARKERS = (b"HPQC-STAGE06-CLIENT-MARKER", b"HPQC-STAGE06-SERVER-MARKER")
PAYLOADS = tuple(marker.ljust(1024, b".") for marker in MARKERS)


class ObservedSocket:
    """Keep only bytes passed successfully to the TCP transport."""

    def __init__(self, sock):
        self.sock = sock
        self.frames = []

    def __getattr__(self, name):
        return getattr(self.sock, name)

    def sendall(self, data):
        self.sock.sendall(data)
        self.frames.append(data)


def exchange(sock, role, secure, psk):
    outgoing, incoming = PAYLOADS if role == "client" else PAYLOADS[::-1]
    if secure:
        with DataChannel(sock, role=role, psk=psk) as channel:
            if role == "server":
                received = channel.receive()
            message_id = channel.send_data(outgoing)
            if channel.receive() != Acknowledgement(message_id):
                raise ValueError("ACK mismatch")
            if role == "client":
                received = channel.receive()
            if not isinstance(received, ReceivedData) or received.payload != incoming:
                raise ValueError("Authenticated delivery mismatch")
    else:
        if role == "server":
            received = recv_frame(sock)
        send_frame(sock, outgoing)
        if role == "client":
            received = recv_frame(sock)
        if received != incoming:
            raise ValueError("Control delivery mismatch")


def check_wire(frames, secure, client):
    """Validate message order and wire lengths independently of the record parser."""
    bodies = []
    for frame in frames:
        if int.from_bytes(frame[:4], "big") != len(frame) - 4:
            raise ValueError("Incorrect length prefix")
        bodies.append(frame[4:])
    wire = b"".join(frames)
    marker_counts = [wire.count(m) for m in MARKERS]
    if secure:
        types = [1, 3, 4, 16, 17] if client else [2, 5, 17, 16]
        lengths = [36, 1124, 36, 1100, 76] if client else [1268, 36, 76, 1100]
        if [b[1] for b in bodies] != types or [len(b) for b in bodies] != lengths:
            raise ValueError("Unexpected v2 frame layout")
        for seq, record in enumerate(bodies[-2:]):
            v, _, suite, _, direction, sequence, _, size = struct.unpack("!BBB16sBQ12sI", record[:44])
            if (v, suite, direction, sequence, size) != (2, 1, int(not client), seq, len(record)-60):
                raise ValueError("Unexpected v2 record header")
        expected_counts = [0, 0]
    else:
        if bodies != [PAYLOADS[0 if client else 1]]:
            raise ValueError("Unexpected plaintext frame")
        types = []
        expected_counts = [1, 0] if client else [0, 1]
    if marker_counts != expected_counts:
        raise ValueError("Marker control failed")
    return dict(bytes=len(wire), sha256=sha256(wire).hexdigest(), marker_counts=marker_counts,
                body_lengths=[len(b) for b in bodies], types=types)


def experiment(secure, port, capture_path=None):
    with ExitStack() as stack:
        listener = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        listener.bind((LOOPBACK, port))
        listener.listen(1)
        client = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        client.bind((LOOPBACK, 0))
        ports = client.getsockname()[1], listener.getsockname()[1]
        if capture_path is not None:
            from experiments.loopback_pcap import PacketCapture
            capture = stack.enter_context(PacketCapture(ports, capture_path))
        client.settimeout(5)
        client.connect(listener.getsockname())
        server, _ = listener.accept()
        stack.enter_context(server)
        server.settimeout(5)
        left, right = ObservedSocket(client), ObservedSocket(server)
        psk = secrets.token_bytes(32) if secure else None
        with ThreadPoolExecutor(1) as pool:
            peer = pool.submit(exchange, right, "server", secure, psk)
            exchange(left, "client", secure, psk)
            peer.result()
        result = dict(ports=ports, client=check_wire(left.frames, secure, True),
                      server=check_wire(right.frames, secure, False), delivery="PASS")
    if capture_path is not None:
        result["capture"] = capture.verify(left.frames, right.frames)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
    parser.add_argument("--windows-capture", action="store_true", help="Capture actual IPv4 packets")
    parser.add_argument("--port", type=int, default=0, help="First of two ports, or 0 for ephemeral")
    args = parser.parse_args()
    if not 0 <= args.port < 65535:
        parser.error("Invalid first TCP port")
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(time_utc=datetime.now(timezone.utc).isoformat(), python=platform.python_version(),
                  pqcrypto=version("pqcrypto"), cryptography=version("cryptography"),
                  commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                  runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    for index, name in enumerate(("plaintext", "secure")):
        path = args.output / (name + ".pcap") if args.windows_capture else None
        report[name] = experiment(bool(index), args.port + index if args.port else 0, path)
    (args.output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Verified both transfers. Evidence:", args.output)


if __name__ == "__main__":
    main()
