"""Recovery controls and authenticated delivery on owned sockets."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from benchmark.bench_resilience import trial
from protocol.data_v2 import DataChannel, RecordError
from protocol.handshake_v2 import HandshakeError
from protocol.resilience import Inbox, Policy, RecoveryClient, TimedStream, serve_session


class RecoveryTests(unittest.TestCase):
    def test_loss_of_receipt_fresh_session_and_delivery(self):
        with TemporaryDirectory() as temp:
            result = trial(Path(temp), "ml-kem-768", True)
        self.assertEqual(result["inbox_rows"], 3)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["receipts_during_outage"], 0)
        self.assertEqual(result["receipts_after_outage"], 2)
        self.assertTrue(0 < result["tcp_recovery_ns"] <= result["secure_recovery_ns"]
                        <= result["delivery_recovery_ns"])
        self.assertEqual(sum(r["event"] == "pong" for r in result["events"]), 3)

    def test_inbox_survives_restart_rejects_conflicts(self):
        msg = secrets.token_bytes(16)
        with TemporaryDirectory() as temp:
            path = Path(temp) / "peer.sqlite"
            with closing(Inbox(path)) as inbox:
                self.assertTrue(inbox.accept(msg, b"test"))
            with closing(Inbox(path)) as inbox:
                self.assertFalse(inbox.accept(msg, b"test"))
                with self.assertRaises(RecordError):
                    inbox.accept(msg, b"other")
                self.assertEqual(inbox.db.execute("SELECT payload FROM inbox").fetchall(), [(b"test",)])

    def test_exhaustion_and_capped_backoff(self):
        events = []
        client = RecoveryClient(("127.0.0.1", 1), secrets.token_bytes(32),
                                policy=Policy(1, 4, .25, .5), event=events.append)
        with patch("protocol.resilience.socket.create_connection", side_effect=ConnectionRefusedError) as connect:
            with patch("protocol.resilience.time.sleep") as wait, self.assertRaises(ConnectionRefusedError):
                client.send(b"data")
        self.assertEqual(connect.call_count, 5)
        self.assertEqual([c.args[0] for c in wait.call_args_list], [.25, .5, .5, .5])
        self.assertEqual(events[-1]["event"], "exhausted")
        self.assertEqual(len({r["id"] for r in events}), 1)

    def test_real_heartbeat_timeout_and_auth_failure(self):
        psk = secrets.token_bytes(32)
        for bad_auth in (False, True):
            with self.subTest(bad_auth=bad_auth), socket.socket() as listener, ThreadPoolExecutor(1) as pool:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(2)
                events = []
                def peer():
                    sock, _ = listener.accept()
                    with sock, closing(Inbox(":memory:")) as inbox:
                        # A confirmed peer stays silent after it has consumed the ping.
                        if bad_auth:
                            with self.assertRaises(HandshakeError):
                                serve_session(sock, psk, "ml-kem-768", inbox, 1, 1, lambda row: None)
                        else:
                            with DataChannel(sock, role="server", psk=psk) as channel:
                                channel.receive()
                                time.sleep(.6)
                task = pool.submit(peer)
                with closing(RecoveryClient(listener.getsockname(), secrets.token_bytes(32) if bad_auth else psk,
                                            policy=Policy(.4, 2 if bad_auth else 0),
                                            event=events.append)) as client:
                    with self.assertRaises(HandshakeError if bad_auth else socket.timeout):
                        client.heartbeat()
                task.result()
                self.assertEqual(events[-1]["event"], "rejected" if bad_auth else "exhausted")
                self.assertEqual(sum(r["event"] == "attempt_started" for r in events), 1)

    def test_cli_reconnect_same_id_and_scheduled_heartbeat(self):
        with TemporaryDirectory() as temp:
            psk = Path(temp) / "lab.psk"
            psk.write_bytes(secrets.token_bytes(32))
            path = Path(temp) / "inbox.sqlite"
            cli = [sys.executable, "-B", "-m", "protocol.resilience_cli"]
            common = ["--psk-file", str(psk), "--suite", "ml-kem-512", "--timeout", "2"]
            with subprocess.Popen(cli + ["server", "--port", "0", "--inbox", str(path)] + common,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as server:
                try:
                    with ThreadPoolExecutor(1) as pool:
                        line = pool.submit(server.stdout.readline)
                        try:
                            port = str(json.loads(line.result(timeout=8))["port"])
                        except BaseException:
                            server.kill()
                            raise
                    client = cli + ["client", "--port", port, "--text", "test"] + common
                    first = subprocess.run(client + ["--count", "2", "--interval", ".15", "--heartbeat", ".03"],
                                           capture_output=True, text=True, timeout=8, check=True)
                    events = [json.loads(line) for line in first.stdout.splitlines()]
                    self.assertIn("pong", [row["event"] for row in events])
                    first_id, second_id = [row["id"] for row in events if row["event"] == "delivered"]
                    self.assertNotEqual(first_id, second_id)
                    resumed = subprocess.run(client + ["--message-id", first_id], capture_output=True,
                                             text=True, timeout=8, check=True)
                    self.assertEqual(json.loads(resumed.stdout.splitlines()[-1])["id"], first_id)
                    with closing(sqlite3.connect(path)) as db:
                        self.assertEqual(db.execute("SELECT count(*) FROM inbox").fetchone()[0], 2)
                finally:
                    server.terminate()
                    server.communicate(timeout=5)

    def test_deadline_and_policy_validation(self):
        for policy in ((0, 1, .1, 2), (.1, -1, .1, 2), (.1, 1, 2, 1), (float("nan"), 1, 1, 1)):
            with self.assertRaises(ValueError):
                Policy(*policy)
        with socket.socket() as sock:
            stream = TimedStream(sock)
            with patch("protocol.resilience.time.monotonic", side_effect=[1.0, 2.1]):
                stream.begin(1)
                with self.assertRaises(socket.timeout):
                    stream.recv(1)
