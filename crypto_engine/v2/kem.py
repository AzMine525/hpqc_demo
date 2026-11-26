"""Sized byte interfaces to pqcrypto and the original ML-KEM-768 API."""

from types import ModuleType

from pqcrypto.kem import ml_kem_768

from ._validation import require_bytes


class MLKEM:
    """Apply the same input and output checks for each ML-KEM parameter set."""

    def __init__(self, backend: ModuleType):
        self.backend = backend
        self.public_size = backend.PUBLIC_KEY_SIZE
        self.ciphertext_size = backend.CIPHERTEXT_SIZE

    def generate_keypair(self) -> tuple[bytes, bytes]:
        """Generate a fresh encapsulation key and expanded decapsulation key."""
        public, private = self.backend.keygen()
        require_bytes(public, "public key", self.public_size)
        require_bytes(private, "private key", self.backend.SECRET_KEY_SIZE)
        return public, private

    def encapsulate(self, public: bytes) -> tuple[bytes, bytes]:
        """Validate the public key and return ciphertext and a 32-byte secret."""
        require_bytes(public, "public key", self.public_size)
        try:
            ciphertext, secret = self.backend.encaps(public)
        except ValueError:
            raise ValueError("Invalid ML-KEM encapsulation key") from None
        require_bytes(ciphertext, "KEM ciphertext", self.ciphertext_size)
        require_bytes(secret, "shared secret", 32)
        return ciphertext, secret

    def decapsulate(self, private: bytes, ciphertext: bytes) -> bytes:
        """Return the 32-byte decapsulation result, including implicit rejection."""
        require_bytes(private, "private key", self.backend.SECRET_KEY_SIZE)
        require_bytes(ciphertext, "KEM ciphertext", self.ciphertext_size)
        try:
            secret = self.backend.decaps(private, ciphertext)
        except ValueError:
            raise ValueError("Invalid ML-KEM decapsulation input") from None
        require_bytes(secret, "shared secret", 32)
        return secret


ML_KEM_768 = MLKEM(ml_kem_768)
generate_keypair = ML_KEM_768.generate_keypair
encapsulate = ML_KEM_768.encapsulate
decapsulate = ML_KEM_768.decapsulate
