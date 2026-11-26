"""Stage 04 tests on local connected sockets using the actual Stage 03 engine."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import hmac
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from crypto_engine.v2.kdf import derive_keys
from protocol import handshake_v2 as hs


class HandshakeTests(unittest.TestCase):
    def setUp(self):
        self.psk = secrets.token_bytes(32)

    def exchange(self, client_psk=None):
        client, server = socket.socketpair()
        self.addCleanup(client.close)
        self.addCleanup(server.close)
        client.settimeout(3)
        server.settimeout(None)
        with ThreadPoolExecutor(2) as pool:
            ends = [
                pool.submit(hs.establish, client, role="client",
                            psk=self.psk if client_psk is None else client_psk, timeout=2),
                pool.submit(hs.establish, server, role="server", psk=self.psk, timeout=2),
            ]
        results = []
        for future, sock, original_timeout in zip(ends, (client, server), (3, None)):
            try:
                session = future.result()
            except hs.HandshakeError as exc:
                self.assertEqual(sock.fileno(), -1)
                results.append(exc)
            else:
                self.addCleanup(session.close)
                self.assertEqual(sock.gettimeout(), original_timeout)
                results.append(session)
        return results

    def rejected(self, results):
        for result in results:
            self.assertIsInstance(result, hs.HandshakeError)
            self.assertNotIsInstance(result, hs.HandshakeTimeout)

    def test_five_frames_proofs_and_key_schedule_against_wire_spec(self):
        frames = []
        secrets_for_check = []
        original_write = hs._Exchange._write
        original_encapsulate = hs.kem.encapsulate

        def record(exchange, kind, payload):
            frames.append((kind, payload))
            return original_write(exchange, kind, payload)

        def encapsulate(public):
            ciphertext, secret = original_encapsulate(public)
            secrets_for_check.append(secret)
            return ciphertext, secret

        with patch.object(hs._Exchange, "_write", record), patch.object(hs.kem, "encapsulate", encapsulate):
            client, server = self.exchange()
        self.assertEqual([int(kind) for kind, _ in frames], [1, 2, 3, 4, 5])
        self.assertEqual([len(p) for _, p in frames], [32, 1264, 1120, 32, 32])
        client_random, server_hello = frames[0][1], frames[1][1]
        transcript = b"HPQC/v2/handshake\x00"
        for kind, payload in frames:
            role = 0 if kind in (1, 3, 4) else 1
            header = bytes([2, kind, 1, role])
            if kind > 1:
                unsigned = header + payload[:-32]
                digest = hashlib.sha256(transcript + struct.pack("!I", len(unsigned)) + unsigned).digest()
                if kind in (2, 3):
                    proof_key = self.psk
                else:
                    proof_key = keys.confirm_client if kind == 4 else keys.confirm_server
                expected = hmac.digest(proof_key, b"HPQC/v2/proof\x00" + digest, "sha256")
                self.assertTrue(hmac.compare_digest(payload[-32:], expected))
            transcript += struct.pack("!I", len(header) + len(payload)) + header + payload
            if kind == 3:
                keys = derive_keys(secrets_for_check[0], client_random=client_random,
                                   server_random=server_hello[:32], version=2, suite=1,
                                   transcript_hash=hashlib.sha256(transcript).digest())
        self.assertEqual((client.role, server.role), (0, 1))
        for session in (client, server):
            self.assertEqual(session.session_id, server_hello[32:48])
            self.assertEqual(session.transcript_hash, hashlib.sha256(transcript).digest())
        self.assertTrue(client.traffic_keys.send == server.traffic_keys.receive == keys.aes_c2s)
        self.assertTrue(server.traffic_keys.send == client.traffic_keys.receive == keys.aes_s2c)

    def test_fresh_sessions_and_close(self):
        client, _ = self.exchange()
        other, _ = self.exchange()
        self.assertNotEqual(client.session_id, other.session_id)
        self.assertTrue(client.traffic_keys != other.traffic_keys)
        with client:
            self.assertEqual(len(client.traffic_keys.send), 32)
        client.close()
        with self.assertRaises(RuntimeError):
            _ = client.traffic_keys
        with self.assertRaises(RuntimeError):
            with client:
                self.fail("Closed session reopened")

    def test_wrong_psk(self):
        self.rejected(self.exchange(client_psk=secrets.token_bytes(32)))

    def test_implicit_rejection_detected_at_client_finished(self):
        original_decapsulate = hs.kem.decapsulate

        def different_secret(private, ciphertext):
            # Keep wire bytes and both PSK proofs valid. Feed ML-KEM a different
            # full-length ciphertext locally to exercise real implicit rejection.
            changed = bytes([ciphertext[0] ^ 1]) + ciphertext[1:]
            return original_decapsulate(private, changed)

        with patch.object(hs.kem, "decapsulate", side_effect=different_secret) as decap:
            client, server = self.exchange()
        self.assertEqual(decap.call_count, 1)
        self.rejected((client, server))
        self.assertEqual(str(server), "Handshake proof rejected")

    def test_transcript_and_proof_tampering(self):
        original_receive = hs._Exchange._receive
        # Change one field in the local decoder fixture after framing.
        for kind, offset in ((1, 0), (2, 0), (2, 32), (2, 48), (2, -1),
                             (3, 0), (3, -1), (4, -1), (5, -1)):
            def modified(exchange, expected):
                payload = bytearray(original_receive(exchange, expected))
                if expected == kind:
                    payload[offset] ^= 1
                return bytes(payload)

            with self.subTest(kind=kind, offset=offset), patch.object(hs._Exchange, "_receive", modified):
                client, server = self.exchange()
                if kind == 5:
                    self.assertIsInstance(client, hs.HandshakeError)
                    self.assertIsInstance(server, hs.ConfirmedSession)
                else:
                    self.rejected((client, server))

    def test_replayed_server_hello_rejected_with_fresh_challenge(self):
        previous = []
        original_receive = hs._Exchange._receive

        def reuse_hello(exchange, kind):
            payload = original_receive(exchange, kind)
            if kind == hs.Message.SERVER_HELLO:
                previous.append(payload)
                return previous[0]
            return payload

        with patch.object(hs._Exchange, "_receive", reuse_hello):
            self.assertIsInstance(self.exchange()[0], hs.ConfirmedSession)
            self.rejected(self.exchange())

    def test_client_rejects_unsupported_server_suite_before_encapsulation(self):
        # Supply a buffered fixture for the client's expected second frame.
        sock = Mock(spec=socket.socket)
        sock.recv.side_effect = [struct.pack("!I", 1268), bytes([2, 2, 7, 1])]
        with patch.object(hs.kem, "encapsulate") as encapsulate:
            with self.assertRaisesRegex(hs.HandshakeError, "header"):
                hs.establish(sock, role="client", psk=self.psk)
        self.assertEqual(encapsulate.call_count, 0)
        sock.close.assert_called_once()

    def test_server_checks_client_authentication_before_decapsulation(self):
        original_write = hs._Exchange._write

        def wrong_client_proof(exchange, kind, payload):
            if kind == hs.Message.CLIENT_KEM:
                payload = payload[:-1] + bytes([payload[-1] ^ 1])
            original_write(exchange, kind, payload)

        with patch.object(hs._Exchange, "_write", wrong_client_proof), \
                patch.object(hs.kem, "decapsulate") as decapsulate:
            self.rejected(self.exchange())
        self.assertEqual(decapsulate.call_count, 0)

    def test_bad_version_suite_role_order_size_and_eof(self):
        for kind, prefix, header in (
            ("version", 36, bytes([1, 1, 1, 0])), ("suite", 36, bytes([2, 1, 7, 0])),
            ("role", 36, bytes([2, 1, 1, 1])), ("order", 36, bytes([2, 4, 1, 0])),
            ("oversize", 2**32 - 1, b""), ("undersize", 1, b""),
            ("truncated", 36, bytes([2, 1, 1, 0]) + b"x"),
        ):
            with self.subTest(kind=kind), ExitStack() as stack:
                left, right = socket.socketpair()
                stack.enter_context(left)
                stack.enter_context(right)
                left.sendall(struct.pack("!I", prefix) + header)
                if kind == "truncated":
                    left.shutdown(socket.SHUT_WR)
                with self.assertRaises(hs.HandshakeError) as caught:
                    hs.establish(right, role="server", psk=self.psk, timeout=0.5)
                self.assertNotIsInstance(caught.exception, hs.HandshakeTimeout)
                self.assertEqual(right.fileno(), -1)

    def test_idle_handshake_times_out_for_each_role(self):
        for role in ("client", "server"):
            with self.subTest(role=role), ExitStack() as stack:
                left, right = socket.socketpair()
                stack.enter_context(left)
                stack.enter_context(right)
                with self.assertRaises(hs.HandshakeTimeout):
                    hs.establish(right, role=role, psk=self.psk, timeout=0.05)
                self.assertEqual(right.fileno(), -1)

    def test_partial_reads_share_one_deadline(self):
        sock = Mock(spec=socket.socket)
        sock.recv.return_value = b"\x00"
        with patch.object(hs.time, "monotonic", side_effect=[0.0, 0.1, 0.8, 1.1]):
            with self.assertRaises(hs.HandshakeTimeout):
                hs.establish(sock, role="server", psk=self.psk, timeout=1)
        self.assertEqual(sock.recv.call_count, 2)
        self.assertAlmostEqual(sock.settimeout.call_args_list[1].args[0], 0.2)
        sock.close.assert_called_once()

    def test_invalid_local_parameters_close_socket(self):
        for overrides in (dict(psk=b"short"), dict(psk=bytearray(32)), dict(timeout=0),
                          dict(timeout=float("nan")), dict(timeout=float("inf")), dict(role="other")):
            sock = Mock(spec=socket.socket)
            with self.assertRaises(ValueError):
                hs.establish(sock, **{**dict(role="client", psk=self.psk), **overrides})
            sock.close.assert_called_once()

    def test_cli_loopback_and_psk_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lab.psk"
            path.write_bytes(self.psk)
            cli = [sys.executable, "-B", "-m", "protocol.handshake_cli"]
            options = ["--psk-file", str(path), "--host", "127.0.0.1", "--timeout", "3"]
            with ThreadPoolExecutor(1) as pool, subprocess.Popen(
                cli + ["server", "--port", "0"] + options, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            ) as server:
                try:
                    ready = pool.submit(server.stdout.readline).result(timeout=5)
                    port = int(ready.rpartition(":")[2])
                    client = subprocess.run(cli + ["client", "--port", str(port)] + options,
                                            capture_output=True, text=True, timeout=5)
                    output, errors = server.communicate(timeout=5)
                    self.assertEqual((client.returncode, server.returncode), (0, 0))
                    self.assertTrue(re.fullmatch(r"Handshake terkonfirmasi\. Session ID [0-9a-f]{32}\s*",
                                                 client.stdout) is not None)
                    self.assertTrue(output == client.stdout and not client.stderr and not errors)
                finally:
                    if server.poll() is None:
                        server.kill()
                        server.communicate()
            path.write_bytes(self.psk + b"x")
            bad = subprocess.run(cli + ["client"] + options, capture_output=True, timeout=5)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn(b"exactly 32 raw bytes", bad.stderr)
