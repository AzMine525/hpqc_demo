"""Domain-separated Stage 03 key schedule."""

from dataclasses import dataclass
from hashlib import sha256

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ._validation import require_bytes, require_uint


@dataclass(frozen=True, repr=False)
class SessionKeys:
    aes_c2s: bytes
    aes_s2c: bytes
    confirm_client: bytes
    confirm_server: bytes


def _hkdf(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def derive_keys(shared_secret: bytes, *, client_random: bytes, server_random: bytes,
                version: int, suite: int, transcript_hash: bytes) -> SessionKeys:
    """Bind four 32-byte keys to the two randoms and canonical transcript digest."""
    require_bytes(shared_secret, "shared secret", 32)
    require_bytes(client_random, "client random", 32)
    require_bytes(server_random, "server random", 32)
    require_bytes(transcript_hash, "SHA-256 transcript hash", 32)
    require_uint(version, "version", 8)
    require_uint(suite, "suite", 8)
    salt = sha256(b"HPQC/v2/salt\x00" + client_random + server_random).digest()
    context = b"HPQC/v2/key\x00" + bytes((version, suite)) + transcript_hash
    labels = (b"aes/c2s", b"aes/s2c", b"confirm/client", b"confirm/server")
    return SessionKeys(*(_hkdf(shared_secret, salt, context + label, 32) for label in labels))
