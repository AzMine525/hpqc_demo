"""Sized byte interfaces to the ML-KEM-768 implementation in pqcrypto."""

from pqcrypto.kem import ml_kem_768

from ._validation import require_bytes


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate a fresh (encapsulation key, expanded decapsulation key)."""
    public, private = ml_kem_768.keygen()
    require_bytes(public, "public key", 1184)
    require_bytes(private, "private key", 2400)
    return public, private


def encapsulate(public: bytes) -> tuple[bytes, bytes]:
    """Return a 1088-byte ciphertext and its 32-byte shared secret."""
    require_bytes(public, "public key", 1184)
    try:
        ciphertext, secret = ml_kem_768.encaps(public)
    except ValueError:
        raise ValueError("Invalid ML-KEM encapsulation key") from None
    require_bytes(ciphertext, "KEM ciphertext", 1088)
    require_bytes(secret, "shared secret", 32)
    return ciphertext, secret


def decapsulate(private: bytes, ciphertext: bytes) -> bytes:
    """Return the 32-byte decapsulation result, including implicit rejection."""
    require_bytes(private, "private key", 2400)
    require_bytes(ciphertext, "KEM ciphertext", 1088)
    try:
        secret = ml_kem_768.decaps(private, ciphertext)
    except ValueError:
        raise ValueError("Invalid ML-KEM decapsulation input") from None
    require_bytes(secret, "shared secret", 32)
    return secret
