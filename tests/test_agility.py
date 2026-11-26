"""Stage 07 agreement, wire compatibility and local suite pinning."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from hashlib import sha256
from itertools import permutations
import secrets
import socket
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from crypto_engine.v2.kdf import derive_keys
from crypto_engine.v2.suites import DEFAULT_SUITE, SUITES
from protocol.data_v2 import Acknowledgement, DataChannel, ReceivedData, RecordError
from protocol.handshake_v2 import HandshakeError, HandshakeTimeout, establish
from test_data_v2 import Wire


# Protocol expectations independent of the implementation registry.
PARAMETERS = {
    "ml-kem-768": (1, 1184, 1088),
    "ml-kem-512": (2, 800, 768),
    "ml-kem-1024": (3, 1568, 1568),
    "rsa-2048-oaep": (4, 294, 256),
}


class AgilityTests(unittest.TestCase):
    def test_agreement_and_input_lengths(self):
        self.assertEqual(set(SUITES), set(PARAMETERS))
        self.assertEqual(DEFAULT_SUITE, "ml-kem-768")
        for name, (wire_id, public_size, ct_size) in PARAMETERS.items():
            with self.subTest(suite=name):
                suite = SUITES[name]
                self.assertEqual(suite.wire_id, wire_id)
                engine = suite.engine
                public, private = engine.generate_keypair()
                ct, secret = engine.encapsulate(public)
                self.assertEqual((len(public), len(ct), len(secret)), (public_size, ct_size, 32))
                self.assertTrue(secret == engine.decapsulate(private, ct))
                new_ct, new_secret = engine.encapsulate(public)
                self.assertTrue(new_ct != ct and new_secret != secret)
                self.assertTrue(engine.generate_keypair()[0] != public)
                with self.assertRaises(ValueError):
                    engine.encapsulate(public[:-1])
                with self.assertRaises(ValueError):
                    engine.decapsulate(private, ct + b"x")

    def test_rsa_oaep_profile_and_rejection(self):
        engine = SUITES["rsa-2048-oaep"].engine
        public, private = engine.generate_keypair()
        pub = serialization.load_der_public_key(public)
        self.assertEqual((pub.key_size, pub.public_numbers().e), (2048, 65537))
        oaep = padding.OAEP(padding.MGF1(hashes.SHA256()), hashes.SHA256(), None)
        ct, secret = engine.encapsulate(public)
        self.assertTrue(private.decrypt(ct, oaep) == secret)
        other = secrets.token_bytes(32)
        self.assertTrue(engine.decapsulate(private, pub.encrypt(other, oaep)) == other)
        with self.assertRaises(ValueError):
            engine.encapsulate(bytes(len(public)))
        for invalid in (bytes(256), pub.encrypt(other[:-1], oaep),
                        pub.encrypt(other, padding.OAEP(padding.MGF1(hashes.SHA256()),
                                                        hashes.SHA256(), b"other"))):
            with self.subTest(), self.assertRaises(ValueError):
                engine.decapsulate(private, invalid)

    def test_all_suites_bind_handshake_kdf_data_ack_and_replay(self):
        for name, (wire_id, pk_size, ct_size) in PARAMETERS.items():
            with self.subTest(suite=name), ExitStack() as stack:
                left, right = (Wire(stack.enter_context(s)) for s in socket.socketpair())
                left.settimeout(5)
                right.settimeout(5)
                psk = secrets.token_bytes(32)
                engine = SUITES[name].engine
                encapsulate = engine.encapsulate
                secrets_for_check = []

                def observe(public):
                    ciphertext, secret = encapsulate(public)
                    secrets_for_check.append(secret)
                    return ciphertext, secret

                with patch.object(engine, "encapsulate", observe), ThreadPoolExecutor(1) as pool:
                    future = pool.submit(DataChannel, right, role="server", psk=psk, suite=name)
                    client = stack.enter_context(DataChannel(left, role="client", psk=psk, suite=name))
                    server = stack.enter_context(future.result())
                frames = [left.frames[0], right.frames[0], *left.frames[1:], right.frames[1]]
                self.assertEqual([f[4:7] for f in frames],
                                 [bytes((2, kind, wire_id)) for kind in range(1, 6)])
                self.assertEqual([len(f)-4 for f in frames], [36, 84+pk_size, 36+ct_size, 36, 36])
                transcript = b"HPQC/v2/handshake\x00" + b"".join(frames[:3])
                keys = derive_keys(secrets_for_check[0], client_random=frames[0][8:40],
                                   server_random=frames[1][8:40], version=2, suite=wire_id,
                                   transcript_hash=sha256(transcript).digest())
                self.assertTrue(keys.aes_c2s == client._session.traffic_keys.send == server._session.traffic_keys.receive)
                self.assertTrue(keys.aes_s2c == server._session.traffic_keys.send == client._session.traffic_keys.receive)
                for sender, receiver, out, reply in ((client, server, left, right), (server, client, right, left)):
                    payload = secrets.token_bytes(1024)
                    mid = sender.send_data(payload)
                    self.assertTrue(receiver.receive() == ReceivedData(mid, payload))
                    self.assertEqual(sender.receive(), Acknowledgement(mid))
                    self.assertEqual((out.frames[-1][6], reply.frames[-1][6]), (wire_id, wire_id))
                replay = left.frames[3]  # First DATA, after three client handshake frames.
                with patch.object(right, "recv", side_effect=[replay[:4], replay[4:48], replay[48:]]):
                    with self.assertRaises(RecordError):
                        server.receive()
                self.assertEqual(server._receive_sequence, 2)
                self.assertEqual(right.fileno(), -1)

    def test_mismatched_peers_stop_at_first_hello(self):
        for client_suite, server_suite in permutations(PARAMETERS, 2):
            with self.subTest(client=client_suite, server=server_suite), ExitStack() as stack:
                left, right = (Wire(stack.enter_context(s)) for s in socket.socketpair())
                psk = secrets.token_bytes(32)
                with patch.object(SUITES[server_suite].engine, "generate_keypair") as keygen, ThreadPoolExecutor(1) as pool:
                    future = pool.submit(establish, right, role="server", psk=psk, suite=server_suite)
                    with self.assertRaises(HandshakeError) as client_error:
                        establish(left, role="client", psk=psk, suite=client_suite)
                    with self.assertRaises(HandshakeError) as server_error:
                        future.result()
                keygen.assert_not_called()
                self.assertNotIsInstance(client_error.exception, HandshakeTimeout)
                self.assertNotIsInstance(server_error.exception, HandshakeTimeout)
                self.assertEqual((len(left.frames), len(right.frames)), (1, 0))
                self.assertEqual((left.fileno(), right.fileno()), (-1, -1))

    def test_wrong_psk_rejected_on_every_suite(self):
        for name in PARAMETERS:
            with self.subTest(suite=name), ExitStack() as stack:
                left, right = (Wire(stack.enter_context(s)) for s in socket.socketpair())
                with ThreadPoolExecutor(1) as pool:
                    peer = pool.submit(establish, right, role="server", psk=secrets.token_bytes(32), suite=name)
                    with self.assertRaisesRegex(HandshakeError, "proof rejected"):
                        establish(left, role="client", psk=secrets.token_bytes(32), suite=name)
                    with self.assertRaises(HandshakeError):
                        peer.result()
                self.assertEqual((len(left.frames), len(right.frames)), (1, 1))
                self.assertEqual((left.fileno(), right.fileno()), (-1, -1))

    def test_unknown_local_suite_closes_before_transmission(self):
        with ExitStack() as stack:
            left, right = [stack.enter_context(s) for s in socket.socketpair()]
            with self.assertRaisesRegex(ValueError, "Unknown"):
                establish(left, role="client", psk=secrets.token_bytes(32), suite="auto")
            self.assertEqual(right.recv(1), b"")
