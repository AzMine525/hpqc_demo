"""Regression checks for the original framing and cryptographic parameters."""

import hashlib
import hmac
import importlib
import socket
import struct
import unittest
from unittest.mock import Mock

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from crypto_engine.aead import MessageCipher
from crypto_engine.kdf import keys_from_secret
from protocol.transport import recv_exact, recv_frame, send_frame


class ImportTests(unittest.TestCase):
    def test_application_modules_import(self):
        modules = (
            "chat", "client", "server", "config",
            "crypto_engine.kem", "crypto_engine.kdf", "crypto_engine.aead",
            "protocol.transport", "protocol.handshake", "protocol.session",
        )
        for name in modules:
            with self.subTest(name=name):
                importlib.import_module(name)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.sock = Mock(spec=socket.socket)

    def test_exact_read_handles_partial_reads(self):
        self.sock.recv.side_effect = [b"a", b"bc"]
        self.assertEqual(recv_exact(self.sock, 3), b"abc")
        self.assertEqual([call.args for call in self.sock.recv.call_args_list], [(3,), (2,)])

    def test_frame_uses_unsigned_big_endian_length(self):
        send_frame(self.sock, b"abc")
        self.sock.sendall.assert_called_once_with(b"\x00\x00\x00\x03abc")

    def test_receive_fragmented_prefix_and_body(self):
        self.sock.recv.side_effect = [b"\x00", b"\x00\x00\x03", b"ab", b"c"]
        self.assertEqual(recv_frame(self.sock), b"abc")

    def test_empty_frame(self):
        send_frame(self.sock, b"")
        self.sock.sendall.assert_called_once_with(b"\x00" * 4)
        self.sock.recv.return_value = b"\x00" * 4
        self.assertEqual(recv_frame(self.sock), b"")
        self.sock.recv.assert_called_once_with(4)

    def test_max_frame_body_allowed_for_send_and_receive(self):
        body = b"x" * 1_048_576
        prefix = b"\x00\x10\x00\x00"
        send_frame(self.sock, body)
        self.sock.sendall.assert_called_once_with(prefix + body)
        self.sock.recv.side_effect = [prefix, body]
        self.assertEqual(recv_frame(self.sock), body)

    def test_oversize_rejected_before_send_or_body_read(self):
        with self.assertRaisesRegex(ValueError, "Frame terlalu panjang"):
            send_frame(self.sock, b"x" * 1_048_577)
        self.sock.sendall.assert_not_called()
        self.sock.recv.return_value = struct.pack("!I", 1_048_577)
        with self.assertRaisesRegex(ValueError, "Frame terlalu panjang"):
            recv_frame(self.sock)
        self.sock.recv.assert_called_once_with(4)

    def test_eof_in_prefix_or_body(self):
        for chunks in ([b"\x00", b""], [struct.pack("!I", 3), b"ab", b""]):
            with self.subTest(chunks=chunks):
                self.sock.recv.side_effect = chunks
                with self.assertRaisesRegex(EOFError, "Koneksi ditutup"):
                    recv_frame(self.sock)


class CryptoTests(unittest.TestCase):
    def test_hkdf_sha512_uses_original_info_and_key_split(self):
        secret = bytes(range(32))
        prk = hmac.digest(bytes(hashlib.sha512().digest_size), secret, "sha512")
        expected = hmac.digest(prk, b"HPQC-LAB-v1 ML-KEM-768 AES-256-GCM\x01", "sha512")
        self.assertEqual(keys_from_secret(secret), (expected[:32], expected[32:]))

    def test_ciphertext_matches_original_nonce_aad_and_utf8(self):
        key = bytes(range(32))
        sequence = 258
        message = "Uji é"
        for direction in (b"c2s", b"s2c"):
            with self.subTest(direction=direction):
                cipher = MessageCipher(key, direction)
                payload, _ = cipher.encrypt(message, sequence)
                plaintext = message.encode("utf-8")
                nonce = bytes.fromhex("000000000000000000000102")
                aad = b"HPQC-LAB-v1:" + direction + bytes.fromhex("0000000000000102")
                self.assertEqual(payload, AESGCM(key).encrypt(nonce, plaintext, aad))
                self.assertEqual(len(payload), len(plaintext) + 16)
                self.assertEqual(cipher.decrypt(payload, sequence), plaintext)

    def test_message_rejected_at_wrong_sequence_or_direction(self):
        key = bytes(32)
        cipher = MessageCipher(key, b"c2s")
        payload, _ = cipher.encrypt("Uji", 0)
        with self.assertRaises(InvalidTag):
            cipher.decrypt(payload, 1)
        with self.assertRaises(InvalidTag):
            MessageCipher(key, b"s2c").decrypt(payload, 0)
