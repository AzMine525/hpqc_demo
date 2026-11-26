"""Measure normal service and a temporary application outage on owned loopback sockets."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import secrets
import socket
import sqlite3
from tempfile import TemporaryDirectory
from threading import Event, Lock
import time

from crypto_engine.v2.suites import DEFAULT_SUITE, SUITES
from protocol.handshake_v2 import HandshakeError
from protocol.resilience import Inbox, Policy, RecoveryClient, serve_session


def trial(folder: Path, suite: str, outage: bool) -> dict:
    """Exercise an ambiguous delivery, then verify inbox contents and recovery clocks."""
    psk = secrets.token_bytes(32)
    ledger = folder / ("outage.db" if outage else "normal.db")
    messages = [(secrets.token_bytes(16), secrets.token_bytes(1024)) for _ in range(3)]
    stop = Event()
    lock = Lock()
    events = []
    until = 0
    policy = Policy(timeout=1, retries=6, backoff=0.04, cap=0.12)

    def log(side: str, row: dict) -> None:
        with lock:
            events.append(dict({"side": side, "at_ns": time.perf_counter_ns()}, **row))

    def serve(listener: socket.socket) -> None:
        nonlocal until
        with closing(Inbox(ledger)) as inbox:
            while not stop.is_set():
                try:
                    sock, _ = listener.accept()
                except socket.timeout:
                    continue
                with sock:
                    if time.perf_counter_ns() < until:
                        log("server", {"event": "service_unavailable"})
                        continue

                    def committed(row: dict) -> None:
                        nonlocal until
                        log("server", row)
                        if outage and not until and row["id"] == messages[1][0].hex():
                            until = time.perf_counter_ns() + 200_000_000
                            log("server", {"event": "outage_started", "available_from_ns": until})
                            sock.shutdown(socket.SHUT_RDWR)
                            raise ConnectionAbortedError("Controlled loss of receipt")

                    try:
                        serve_session(sock, psk, suite, inbox, 1, 2, committed)
                    except (EOFError, OSError, HandshakeError) as exc:
                        log("server", {"event": "closed", "error": type(exc).__name__})

    with socket.socket() as listener, ThreadPoolExecutor(1) as pool:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.1)
        server = pool.submit(serve, listener)
        try:
            with closing(RecoveryClient(listener.getsockname(), psk, suite=suite, policy=policy,
                                        event=lambda row: log("client", row))) as client:
                for logical_id, payload in messages:
                    client.send(payload, logical_id)
                    client.heartbeat()
        finally:
            stop.set()
            server.result()
    with closing(sqlite3.connect(ledger)) as db:
        actual = dict(db.execute("SELECT message_id,payload FROM inbox"))
    if actual != dict(messages):
        raise RuntimeError("Inbox verification failed")
    ready = [row for row in events if row["event"] == "secure_ready"]
    receipts = [row for row in events if row["event"] == "delivered"]
    duplicate_count = sum(row["event"] == "duplicate" for row in events)
    if len(receipts) != 3 or duplicate_count != int(outage):
        raise RuntimeError("Delivery accounting failed")
    tcp_ns = confirmed_tcp_ns = secure_ns = delivery_ns = None
    during = None
    if outage:
        if len({row["session"] for row in ready}) < 2:
            raise RuntimeError("Missing fresh session")
        recovered = next(row for row in ready if row["since_detection_ns"] is not None)
        connections = [row for row in events if row["event"] == "tcp_connected"
                       and row["since_detection_ns"] is not None]
        tcp_ns = connections[0]["since_detection_ns"]
        confirmed_tcp_ns = next(row["since_detection_ns"] for row in connections
                                if (row["id"], row["attempt"]) == (recovered["id"], recovered["attempt"]))
        secure_ns = recovered["since_detection_ns"]
        delivery_ns = receipts[1]["since_detection_ns"]
        started = next(row["at_ns"] for row in events if row["event"] == "outage_started")
        during = sum(started <= row["at_ns"] < until for row in receipts)
    attempts = sum(row["event"] == "attempt_started" for row in events)
    timeouts = sum(row.get("error") in ("TimeoutError", "HandshakeTimeout", "timeout")
                   for row in events if row["event"] == "interrupted")
    return dict(scenario="temporary_service_outage" if outage else "normal", events=events,
                acknowledged=len(receipts), inbox_rows=len(actual), duplicates=duplicate_count,
                planned_messages=len(messages), delivery_ratio=len(receipts) / len(messages),
                tcp_recovery_ns=tcp_ns, secure_recovery_ns=secure_ns, delivery_recovery_ns=delivery_ns,
                confirmed_connection_tcp_ns=confirmed_tcp_ns,
                receipts_during_outage=during,
                receipts_after_outage=sum(row["at_ns"] >= until for row in receipts) if outage else None,
                attempts=attempts, timeouts=timeouts, timeout_rate=timeouts / attempts,
                interruptions=sum(row["event"] == "interrupted" for row in events))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New evidence file")
    parser.add_argument("--suite", choices=tuple(SUITES), default=DEFAULT_SUITE)
    args = parser.parse_args()
    source_files = ("protocol/data_v2.py", "protocol/handshake_v2.py", "protocol/resilience.py",
                    "protocol/resilience_cli.py", "benchmark/bench_resilience.py")
    root = Path(__file__).resolve().parents[1]
    with args.output.open("x", encoding="utf-8") as dest, TemporaryDirectory(dir=args.output.parent) as temp:
        report = dict(started=datetime.now(timezone.utc).isoformat(), host=platform.node(),
                      os=platform.platform(), python=platform.python_version(), suite=args.suite,
                      versions={n: version(n) for n in ("pqcrypto", "cryptography")},
                      source_sha256={n: sha256((root/n).read_bytes()).hexdigest() for n in source_files},
                      trials=[trial(Path(temp), args.suite, outage) for outage in (False, True)])
        json.dump(report, dest, indent=2)
        dest.write("\n")
    print("Verified both scenarios:", args.output)


if __name__ == "__main__":
    main()
