"""AES-256-GCM for a single direction of the prototype chat."""

import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class MessageCipher:
    """Use the directional key and label with the caller's sequence counter."""

    def __init__(self, key: bytes, direction: bytes) -> None:
        self._cipher = AESGCM(key)
        self._direction = direction

    def _parameters(self, sequence: int) -> tuple[bytes, bytes]:
        nonce = sequence.to_bytes(12, "big")
        aad = b"HPQC-LAB-v1:" + self._direction + sequence.to_bytes(8, "big")
        return nonce, aad

    def encrypt(self, message: str, sequence: int) -> tuple[bytes, float]:
        """Return ciphertext with tag and the existing local timing in ms."""
        nonce, aad = self._parameters(sequence)
        start = time.perf_counter_ns()
        payload = self._cipher.encrypt(nonce, message.encode("utf-8"), aad)
        elapsed_ms = (time.perf_counter_ns() - start) / 1e6
        return payload, elapsed_ms

    def decrypt(self, payload: bytes, sequence: int) -> bytes:
        """Authenticate a ciphertext with its tag and return plaintext bytes."""
        nonce, aad = self._parameters(sequence)
        return self._cipher.decrypt(nonce, payload, aad)
