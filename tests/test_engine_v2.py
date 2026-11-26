"""Local Stage 03 tests with real primitives and forced nonce collisions."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from crypto_engine.v2 import kem, kdf
from crypto_engine.v2.aead import DirectionCipher, DirectionContext, MAX_PAYLOAD, SessionExhausted


class KEMTests(unittest.TestCase):
    def setUp(self):
        self.pk, self.sk = kem.generate_keypair()
        self.ct, self.secret = kem.encapsulate(self.pk)

    def test_agreement_sizes_and_ephemeral_generation(self):
        self.assertEqual(tuple(map(len, (self.pk, self.sk, self.ct, self.secret))),
                         (1184, 2400, 1088, 32))
        self.assertTrue(kem.decapsulate(self.sk, self.ct) == self.secret)
        self.assertTrue(kem.generate_keypair()[0] != self.pk)

    def test_malformed_input(self):
        for value in (self.pk[:-1], self.pk + b"x", bytearray(self.pk), bytes([255]) * 1184):
            with self.assertRaises(ValueError):
                kem.encapsulate(value)
        for key, ct in ((self.sk[:-1], self.ct), (self.sk, self.ct[:-1]),
                        (self.sk, bytearray(self.ct)), (self.sk, self.ct + b"x"),
                        (self.sk[:-64] + bytes(64), self.ct)):
            with self.assertRaises(ValueError):
                kem.decapsulate(key, ct)

    def test_changed_ciphertext_implicit_rejection(self):
        altered = self.ct[:-1] + bytes([self.ct[-1] ^ 1])
        other = kem.decapsulate(self.sk, altered)
        self.assertEqual(len(other), 32)
        self.assertTrue(other != self.secret)

    def test_backend_output_dimensions(self):
        for function, args, name, output in (
            (kem.generate_keypair, (), "keygen", (b"", self.sk)),
            (kem.generate_keypair, (), "keygen", (self.pk, b"")),
            (kem.encapsulate, (self.pk,), "encaps", (b"", self.secret)),
            (kem.encapsulate, (self.pk,), "encaps", (self.ct, b"")),
            (kem.decapsulate, (self.sk, self.ct), "decaps", b""),
        ):
            with patch.object(kem.ml_kem_768, name, return_value=output), self.assertRaises(ValueError):
                function(*args)


def key_inputs():
    return dict(shared_secret=bytes(range(32)), client_random=b"C" * 32,
                server_random=b"S" * 32, version=2, suite=1,
                transcript_hash=sha256(b"synthetic transcript").digest())


class KDFTests(unittest.TestCase):
    def test_rfc5869_appendix_a1(self):
        result = kdf._hkdf(b"\x0b" * 22, bytes(range(13)), bytes(range(0xf0, 0xfa)), 42)
        self.assertTrue(result == bytes.fromhex(
            "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
            "34007208d5b887185865"))

    def test_derivation_and_context_binding(self):
        inputs = key_inputs()
        keys = kdf.derive_keys(**inputs)
        self.assertTrue(keys == kdf.derive_keys(**inputs))
        fields = vars(keys)
        self.assertEqual(len(set(fields.values())), 4)
        self.assertTrue(all(len(key) == 32 for key in fields.values()))
        for name, value in inputs.items():
            changed = dict(inputs)
            changed[name] = value + 1 if type(value) is int else bytes([value[0] ^ 1]) + value[1:]
            other = vars(kdf.derive_keys(**changed))
            self.assertTrue(all(other[field] != key for field, key in fields.items()), name)

    def test_bad_kdf_input(self):
        inputs = key_inputs()
        for name, value in inputs.items():
            invalid = (True, -1, 256) if type(value) is int else (bytearray(value), b"", bytes(33))
            for bad in invalid:
                with self.assertRaises(ValueError):
                    kdf.derive_keys(**{**inputs, name: bad})


class AEADTests(unittest.TestCase):
    def setUp(self):
        self.context = DirectionContext(2, 1, bytes(range(16)), 0)
        self.key = bytes(range(32))
        self.sender = DirectionCipher(self.key, self.context)
        self.receiver = DirectionCipher(self.key, self.context)
        self.fields = dict(message_type=3, sequence=258)

    def test_header_encoding(self):
        expected = bytes.fromhex("020301 000102030405060708090a0b0c0d0e0f 00 "
                                 "0000000000000102 000102030405060708090a0b 00010000")
        self.assertEqual(self.context.build_aad(3, 258, bytes(range(12)), 65536), expected)
        self.assertEqual(len(expected), 44)

    def test_invalid_header_fields(self):
        for name, bad in (("version", -1), ("suite", 256), ("direction", 2),
                          ("direction", True), ("session_id", bytes(15))):
            with self.assertRaises(ValueError):
                replace(self.context, **{name: bad})
        for args in ((256, 0, bytes(12), 0), (1, 1 << 64, bytes(12), 0),
                     (1, -1, bytes(12), 0), (1, 0, bytes(11), 0),
                     (1, 0, bytes(12), 1 << 32)):
            with self.assertRaises(ValueError):
                self.context.build_aad(*args)

    def test_bad_cipher_configuration(self):
        for key, ctx, limit in ((bytes(16), self.context, 1), (bytes(24), self.context, 1),
                                (self.key, None, 1), (self.key, self.context, 0),
                                (self.key, self.context, 65537), (self.key, self.context, True)):
            with self.assertRaises(ValueError):
                DirectionCipher(key, ctx, limit=limit)

    def test_round_trip_and_library_format(self):
        for plaintext in (b"", bytes(range(256)), bytes(MAX_PAYLOAD)):
            nonce, sealed = self.sender.encrypt(plaintext, **self.fields)
            self.assertEqual(len(nonce), 12)
            self.assertEqual(len(sealed), len(plaintext) + 16)
            aad = self.context.build_aad(3, 258, nonce, len(plaintext))
            self.assertTrue(AESGCM(self.key).decrypt(nonce, sealed, aad) == plaintext)
            self.assertTrue(self.receiver.decrypt(nonce, sealed, **self.fields) == plaintext)

    def test_invalid_payloads_and_nonce(self):
        for value in ("abc", bytes(MAX_PAYLOAD + 1)):
            with self.assertRaises(ValueError):
                self.sender.encrypt(value, **self.fields)
        for nonce, value in ((bytes(12), bytes(15)), (bytes(11), bytes(16)),
                             (bytes(12), bytes(MAX_PAYLOAD + 17)), (bytes(12), "abc")):
            with self.assertRaises(ValueError):
                self.receiver.decrypt(nonce, value, **self.fields)

    def test_tampering_and_nonce_commit_after_authentication(self):
        nonce, sealed = self.sender.encrypt(b"A", **self.fields)
        for index in (0, -1):
            changed = bytearray(sealed)
            changed[index] ^= 1
            with self.assertRaises(InvalidTag):
                self.receiver.decrypt(nonce, bytes(changed), **self.fields)
        for ctx in (replace(self.context, version=3), replace(self.context, suite=2),
                    replace(self.context, direction=1), replace(self.context, session_id=bytes(16))):
            with self.assertRaises(InvalidTag):
                DirectionCipher(self.key, ctx).decrypt(nonce, sealed, **self.fields)
        for kwargs in (dict(message_type=4, sequence=258), dict(message_type=3, sequence=259)):
            with self.assertRaises(InvalidTag):
                self.receiver.decrypt(nonce, sealed, **kwargs)
        with self.assertRaises(InvalidTag):
            DirectionCipher(bytes(32), self.context).decrypt(nonce, sealed, **self.fields)
        with self.assertRaises(InvalidTag):
            self.receiver.decrypt(nonce, sealed + b"x", **self.fields)
        with self.assertRaises(InvalidTag):
            self.receiver.decrypt(bytes([nonce[0] ^ 1]) + nonce[1:], sealed, **self.fields)
        self.assertEqual(self.receiver.decrypt(nonce, sealed, **self.fields), b"A")
        with self.assertRaises(InvalidTag):
            self.receiver.decrypt(nonce, sealed, **self.fields)

    def test_forced_collision_retry_and_exhaustion(self):
        first, second = bytes(12), b"N" * 12
        path = "crypto_engine.v2.aead.secrets.token_bytes"
        with patch(path, side_effect=[first, first, second]) as rng:
            self.assertEqual(self.sender.encrypt(b"", **self.fields)[0], first)
            self.assertEqual(self.sender.encrypt(b"", **self.fields)[0], second)
            self.assertEqual([call.args for call in rng.call_args_list], [(12,)] * 3)
        with patch(path, return_value=second) as rng, self.assertRaises(SessionExhausted):
            self.sender.encrypt(b"", **self.fields)
        self.assertEqual(rng.call_count, 8)
        with self.assertRaises(SessionExhausted):
            self.sender.encrypt(b"", **self.fields)

    def test_per_key_limit_on_both_peers(self):
        sender = DirectionCipher(self.key, self.context, limit=1)
        receiver = DirectionCipher(self.key, self.context, limit=1)
        record = sender.encrypt(b"x", **self.fields)
        self.assertEqual(receiver.decrypt(*record, **self.fields), b"x")
        with self.assertRaises(SessionExhausted):
            sender.encrypt(b"x", **self.fields)
        with self.assertRaises(SessionExhausted):
            receiver.decrypt(*record, **self.fields)

    def test_atomic_last_slot(self):
        sender = DirectionCipher(self.key, self.context, limit=1)
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(sender.encrypt, b"x", **self.fields) for _ in range(2)]
        self.assertEqual(sum(f.exception() is None for f in futures), 1)
        self.assertEqual(sum(isinstance(f.exception(), SessionExhausted) for f in futures), 1)

    def test_encryption_error_burns_reserved_nonce(self):
        first, second = bytes(12), b"N" * 12
        with patch("crypto_engine.v2.aead.secrets.token_bytes", side_effect=[first, first, second]):
            with patch.object(self.sender, "_cipher") as backend:
                backend.encrypt.side_effect = RuntimeError("test backend failure")
                with self.assertRaises(RuntimeError):
                    self.sender.encrypt(b"x", **self.fields)
            self.assertEqual(self.sender.encrypt(b"x", **self.fields)[0], second)


class LocalEngineTests(unittest.TestCase):
    def test_real_kem_through_key_schedule_and_both_directions(self):
        public, private = kem.generate_keypair()
        ciphertext, client_secret = kem.encapsulate(public)
        context = key_inputs()
        del context["shared_secret"]
        client_keys = kdf.derive_keys(client_secret, **context)
        server_keys = kdf.derive_keys(kem.decapsulate(private, ciphertext), **context)
        self.assertTrue(client_keys == server_keys)
        for direction, send_key, recv_key in (
            (0, client_keys.aes_c2s, server_keys.aes_c2s),
            (1, server_keys.aes_s2c, client_keys.aes_s2c),
        ):
            ctx = DirectionContext(2, 1, b"S" * 16, direction)
            send, receive = DirectionCipher(send_key, ctx), DirectionCipher(recv_key, ctx)
            record = send.encrypt(b"HPQC", message_type=1, sequence=0)
            self.assertEqual(receive.decrypt(*record, message_type=1, sequence=0), b"HPQC")
