"""Derivation of the two directional keys in the prototype."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def keys_from_secret(secret: bytes) -> tuple[bytes, bytes]:
    """Return the client-to-server and server-to-client AES keys in order."""
    data = HKDF(
        algorithm=hashes.SHA512(),
        length=64,
        salt=None,
        info=b"HPQC-LAB-v1 ML-KEM-768 AES-256-GCM",
    ).derive(secret)
    return data[:32], data[32:]
