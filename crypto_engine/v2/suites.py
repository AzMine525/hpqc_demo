"""Locally selectable HPQC v2 key establishment suites."""

from dataclasses import dataclass
import secrets
from typing import Generic, Protocol, TypeVar

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pqcrypto.kem import ml_kem_512, ml_kem_1024

from ._validation import require_bytes
from .kem import MLKEM, ML_KEM_768

Private = TypeVar("Private")


class KeyEstablishment(Protocol[Private]):
    """Exchange public bytes and ciphertext. Keep the private handle on the server."""

    public_size: int
    ciphertext_size: int

    def generate_keypair(self) -> tuple[bytes, Private]: ...
    def encapsulate(self, public: bytes) -> tuple[bytes, bytes]: ...
    def decapsulate(self, private: Private, ciphertext: bytes) -> bytes: ...


class RSAOAEP:
    """RSA-2048 key transport with fixed SPKI encoding and OAEP-SHA256."""

    public_size = 294
    ciphertext_size = 256
    _padding = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)

    @staticmethod
    def _encode(key: rsa.RSAPublicKey) -> bytes:
        return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)

    def generate_keypair(self) -> tuple[bytes, rsa.RSAPrivateKey]:
        """Generate an ephemeral key, keeping its private component in the backend."""
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return self._encode(key.public_key()), key

    def encapsulate(self, public: bytes) -> tuple[bytes, bytes]:
        """Wrap a fresh 32-byte secret using the authenticated server key."""
        require_bytes(public, "RSA public key", self.public_size)
        try:
            key = serialization.load_der_public_key(public)
        except (ValueError, UnsupportedAlgorithm):
            raise ValueError("Invalid RSA public key") from None
        if (not isinstance(key, rsa.RSAPublicKey) or key.key_size != 2048
                or key.public_numbers().e != 65537 or self._encode(key) != public):
            raise ValueError("Invalid RSA public key")
        secret = secrets.token_bytes(32)
        return key.encrypt(secret, self._padding), secret

    def decapsulate(self, private: rsa.RSAPrivateKey, ciphertext: bytes) -> bytes:
        """Unwrap exactly one 32-byte secret or raise a data-free error."""
        require_bytes(ciphertext, "RSA ciphertext", self.ciphertext_size)
        if (not isinstance(private, rsa.RSAPrivateKey) or private.key_size != 2048
                or private.public_key().public_numbers().e != 65537):
            raise ValueError("Invalid RSA private key")
        try:
            secret = private.decrypt(ciphertext, self._padding)
        except ValueError:
            raise ValueError("Invalid RSA key transport") from None
        require_bytes(secret, "shared secret", 32)
        return secret


@dataclass(frozen=True)
class Suite(Generic[Private]):
    wire_id: int
    engine: KeyEstablishment[Private]


DEFAULT_SUITE = "ml-kem-768"
SUITES = {
    DEFAULT_SUITE: Suite(1, ML_KEM_768),
    "ml-kem-512": Suite(2, MLKEM(ml_kem_512)),
    "ml-kem-1024": Suite(3, MLKEM(ml_kem_1024)),
    "rsa-2048-oaep": Suite(4, RSAOAEP()),
}
