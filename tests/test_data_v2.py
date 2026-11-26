"""Stage 05 loopback tests with real handshake keys and local record fixtures."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from crypto_engine.v2.aead import DirectionCipher, SessionExhausted
from protocol.data_v2 import ACK, DATA, Acknowledgement, DataChannel, ReceivedData, RecordError
from protocol.handshake_v2 import HandshakeError


class Wire:
    """Observe complete writes and optionally fragment reads after the handshake."""

    def __init__(self, sock):
        self.sock = sock
        self.frames = []
        self.chunk_size = None

    def __getattr__(self, name):
        return getattr(self.sock, name)

    def sendall(self, data):
        self.sock.sendall(data)
        self.frames.append(data)

    def recv(self, n):
        return self.sock.recv(min(n, self.chunk_size) if self.chunk_size else n)


class DataTests(unittest.TestCase):
    def channels(self):
        psk = secrets.token_bytes(32)
        left, right = map(Wire, socket.socketpair())
        for wire in (left, right):
            self.addCleanup(wire.close)
            wire.settimeout(4)
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(DataChannel, right, role="server", psk=psk)
            client = DataChannel(left, role="client", psk=psk)
            server = future.result()
        self.addCleanup(client.close)
        self.addCleanup(server.close)
        left.frames.clear()
        right.frames.clear()
        return client, server, left, right

    def test_wire_sizes_full_aad_ack_and_fragmentation(self):
        client, server, left, right = self.channels()
        left.chunk_size = right.chunk_size = 3
        for sequence, payload in enumerate((b"", "Balasan café".encode("utf-8"))):
            message_id = client.send_data(payload)
            self.assertEqual(len(message_id), 16)
            record = server.receive()
            self.assertEqual(record, ReceivedData(message_id, payload))
            self.assertEqual(client.receive(), Acknowledgement(message_id))
            for wire, sender, kind, plaintext, direction in (
                (left, client, 0x10, message_id + payload, 0),
                (right, server, 0x11, message_id, 1),
            ):
                frame = wire.frames[-1]
                self.assertEqual(len(frame), 64 + len(plaintext))
                self.assertEqual(int.from_bytes(frame[:4], "big"), len(frame) - 4)
                header, sealed = frame[4:48], frame[48:]
                fields = struct.unpack("!BBB16sBQ12sI", header)
                self.assertEqual(fields[:6], (2, kind, 1, sender._session.session_id, direction, sequence))
                nonce = fields[6]
                self.assertEqual(fields[7], len(plaintext))
                self.assertEqual(len(sealed), len(plaintext) + 16)
                cipher = AESGCM(sender._session.traffic_keys.send)
                self.assertTrue(cipher.decrypt(nonce, sealed, header) == plaintext)
        for wire in (left, right):
            self.assertNotEqual(wire.frames[0][32:44], wire.frames[1][32:44])
        self.assertEqual(len(left.frames), 2)
        self.assertEqual(len(right.frames), 2)

    def test_simultaneous_bidirectional_binary_sizes(self):
        client, server, left, right = self.channels()

        def read_pair(channel):
            return (channel.receive(), channel.receive())

        with ThreadPoolExecutor(4) as pool:
            for size in (1024, 100 * 1024, 1024 * 1024):
                first, second = secrets.token_bytes(size), secrets.token_bytes(size)
                inbound_client = pool.submit(read_pair, client)
                inbound_server = pool.submit(read_pair, server)
                outgoing_client = pool.submit(client.send_data, first)
                outgoing_server = pool.submit(server.send_data, second)
                client_id, server_id = outgoing_client.result(), outgoing_server.result()
                self.assertCountEqual(inbound_client.result(), (ReceivedData(server_id, second),
                                                               Acknowledgement(client_id)))
                self.assertCountEqual(inbound_server.result(), (ReceivedData(client_id, first),
                                                               Acknowledgement(server_id)))
        for wire in (left, right):
            sequences = [int.from_bytes(frame[24:32], "big") for frame in wire.frames]
            self.assertEqual(sequences, list(range(6)))

    def test_local_input_and_one_pending_per_direction(self):
        client, server, left, _ = self.channels()
        for value in ("teks", bytes(1_048_577)):
            with self.assertRaises(ValueError):
                client.send_data(value)
        self.assertEqual(left.frames, [])
        first = client.send_data(b"text")
        with self.assertRaises(RuntimeError):
            client.send_data(b"berikutnya")
        server.receive()
        self.assertEqual(client.receive(), Acknowledgement(first))
        self.assertNotEqual(client.send_data(b"berikutnya"), first)

    def reject(self, receiver, wire, error=RecordError):
        count = len(wire.frames)
        seq = receiver._receive_sequence
        with self.assertRaises(error):
            receiver.receive()
        self.assertEqual(receiver._receive_sequence, seq)
        self.assertEqual(wire.fileno(), -1)
        self.assertEqual(len(wire.frames), count)

    def test_altered_record_fields_ciphertext_and_tag(self):
        # Replace the next inbound record at the local decoder boundary.
        for field, offset in (("version", 4), ("type", 5), ("suite", 6), ("session", 7),
                              ("direction", 23), ("sequence", 31), ("nonce", 32),
                              ("ciphertext length", 47), ("ciphertext", 48), ("tag", -1)):
            with self.subTest(field=field):
                client, server, left, right = self.channels()
                client.send_data(b"")
                changed = bytearray(left.frames[-1])
                changed[offset] ^= 1
                with patch.object(right, "recv", side_effect=[
                    bytes(changed[:4]), bytes(changed[4:48]), bytes(changed[48:])
                ]):
                    self.reject(server, right)

    def test_replay_and_cross_session(self):
        client, server, left, right = self.channels()
        client.send_data(b"U-01")
        captured = left.frames[-1]
        server.receive()
        client.receive()
        left.sendall(captured)
        self.reject(server, right)
        _, fresh, left2, right2 = self.channels()
        left2.sendall(captured)
        self.reject(fresh, right2)

    def test_authenticated_but_duplicate_message_id_or_nonce(self):
        for duplicate in ("ID", "nonce"):
            with self.subTest(duplicate=duplicate):
                client, server, left, right = self.channels()
                first = client.send_data(b"A")
                server.receive()
                client.receive()
                old_nonce = left.frames[-1][32:44]
                # Independent record fixture, valid tag and next expected sequence.
                nonce = old_nonce if duplicate == "nonce" else secrets.token_bytes(12)
                msg_id = first if duplicate == "ID" else secrets.token_bytes(16)
                header = client._out.build_aad(DATA, 1, nonce, 17)
                sealed = AESGCM(client._session.traffic_keys.send).encrypt(nonce, msg_id + b"B", header)
                left.sendall(struct.pack("!I", len(header) + len(sealed)) + header + sealed)
                self.reject(server, right)

    def test_ack_must_be_authenticated_and_match_one_outstanding_message(self):
        for mode in ("unsolicited", "wrong ID", "bad tag", "duplicate"):
            with self.subTest(mode=mode):
                client, server, left, right = self.channels()
                if mode == "unsolicited":
                    server._write(ACK, secrets.token_bytes(16))
                else:
                    msg_id = client.send_data(b"C")
                    if mode == "wrong ID":
                        server._write(ACK, bytes([msg_id[0] ^ 1]) + msg_id[1:])
                    elif mode == "duplicate":
                        server.receive()
                        self.assertEqual(client.receive(), Acknowledgement(msg_id))
                        server._write(ACK, msg_id)
                    else:
                        server.receive()
                        frame = right.frames[-1]
                        changed = frame[:-1] + bytes([frame[-1] ^ 1])
                        with patch.object(left, "recv", side_effect=[changed[:4], changed[4:48], changed[48:]]):
                            self.reject(client, left)
                        continue
                self.reject(client, left)

    def test_malformed_lengths_and_truncation(self):
        for prefix, rest, eof in (
            (0, b"", False), (2**21 + 1, b"", False), (76, b"x", True),
            (76, None, True), (2**20 + 77, None, False),
        ):
            with self.subTest(prefix=prefix, eof=eof):
                client, server, left, right = self.channels()
                if rest is None:
                    rest = client._out.build_aad(DATA, 0, bytes(12), prefix - 60)
                left.sendall(struct.pack("!I", prefix) + rest)
                if eof:
                    left.shutdown(socket.SHUT_WR)
                self.reject(server, right, EOFError if eof else RecordError)

    def test_future_sequence_with_valid_tag_and_invalid_record_shapes(self):
        for kind, sequence, length in ((DATA, 1, 16), (0xff, 0, 16), (ACK, 0, 17)):
            with self.subTest(kind=kind, sequence=sequence, length=length):
                client, server, left, right = self.channels()
                nonce = secrets.token_bytes(12)
                header = client._out.build_aad(kind, sequence, nonce, length)
                sealed = AESGCM(client._session.traffic_keys.send).encrypt(nonce, bytes(length), header)
                left.sendall(struct.pack("!I", len(header) + len(sealed)) + header + sealed)
                self.reject(server, right)

    def test_key_quota_terminates_session(self):
        def one_record_cipher(key, context):
            return DirectionCipher(key, context, limit=1)

        with patch("protocol.data_v2.DirectionCipher", side_effect=one_record_cipher):
            client, server, left, _ = self.channels()
        msg_id = client.send_data(b"last")
        server.receive()
        self.assertEqual(client.receive(), Acknowledgement(msg_id))
        with self.assertRaises(SessionExhausted):
            client.send_data(b"one too many")
        self.assertEqual(left.fileno(), -1)

    def test_failed_write_aborts_session_and_close_interrupts_read(self):
        client, server, left, _ = self.channels()
        with ThreadPoolExecutor(1) as pool:
            blocked = pool.submit(server.receive)
            with patch.object(left, "sendall", side_effect=OSError):
                with self.assertRaises(OSError):
                    client.send_data(b"partial send")
            with self.assertRaises((EOFError, ConnectionError)):
                blocked.result(timeout=3)
        self.assertEqual(client._send_sequence, 0)
        with self.assertRaises(ConnectionError):
            client.send_data(b"retry")

    def test_handshake_failure_gates_data(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        with ThreadPoolExecutor(1) as pool:
            peer = pool.submit(DataChannel, right, role="server", psk=secrets.token_bytes(32))
            with self.assertRaises(HandshakeError):
                DataChannel(left, role="client", psk=secrets.token_bytes(32))
            with self.assertRaises(HandshakeError):
                peer.result(timeout=3)

    def test_cli_text_and_file_after_real_handshake(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "lab.psk"
            key.write_bytes(secrets.token_bytes(32))
            source = root / "source.bin"
            source.write_bytes(secrets.token_bytes(1 << 20))
            cli = [sys.executable, "-B", "-m", "protocol.transfer_cli"]
            options = ["--psk-file", str(key), "--host", "127.0.0.1"]
            server_args = ["server", "--port", "0", "--text", "Pesan café", "--output", str(root / "in.bin")]
            with ThreadPoolExecutor(1) as pool, subprocess.Popen(
                cli + server_args + options, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            ) as server:
                try:
                    ready = pool.submit(server.stdout.readline).result(timeout=5)
                    port = int(ready.rpartition(":")[2])
                    client = subprocess.run(cli + ["client", "--port", str(port), "--input", str(source),
                                            "--output", str(root / "reply")] + options,
                                            capture_output=True, text=True, timeout=10)
                    output, errors = server.communicate(timeout=5)
                    self.assertEqual((client.returncode, server.returncode), (0, 0))
                    self.assertFalse(errors or client.stderr)
                    self.assertIn("ACK terverifikasi", client.stdout)
                    self.assertIn("ACK terverifikasi", output)
                finally:
                    if server.poll() is None:
                        server.kill()
                        server.communicate()
            self.assertTrue((root / "in.bin").read_bytes() == source.read_bytes())
            self.assertEqual((root / "reply").read_bytes(), "Pesan café".encode("utf-8"))
