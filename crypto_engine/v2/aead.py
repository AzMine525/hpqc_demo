"""Session-local AES-256-GCM with authenticated metadata and bounded nonce state."""

from dataclasses import dataclass
import secrets
import struct
from threading import Lock

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ._validation import require_bytes, require_uint

MAX_RECORDS = 1 << 16
MAX_PAYLOAD = (2 << 20) - 44 - 16


class SessionExhausted(RuntimeError):
    """A new session with fresh keys is required."""


@dataclass(frozen=True)
class DirectionContext:
    version: int
    suite: int
    session_id: bytes
    direction: int

    def __post_init__(self) -> None:
        require_uint(self.version, "version", 8)
        require_uint(self.suite, "suite", 8)
        require_bytes(self.session_id, "session ID", 16)
        require_uint(self.direction, "direction", 1)

    def build_aad(self, message_type: int, sequence: int, nonce: bytes,
                  ciphertext_length: int) -> bytes:
        """Encode exactly 44 bytes, with the tag excluded from ciphertext_length."""
        require_uint(message_type, "message type", 8)
        require_uint(sequence, "sequence", 64)
        require_bytes(nonce, "nonce", 12)
        require_uint(ciphertext_length, "ciphertext length", 32)
        return struct.pack("!BBB16sBQ12sI", self.version, message_type, self.suite,
                           self.session_id, self.direction, sequence, nonce, ciphertext_length)


class DirectionCipher:
    """Own one directional key and its nonce history for the entire session."""

    def __init__(self, key: bytes, context: DirectionContext, *, limit: int = MAX_RECORDS):
        require_bytes(key, "AES key", 32)
        if not isinstance(context, DirectionContext):
            raise ValueError("Invalid direction context")
        if type(limit) is not int or not 1 <= limit <= MAX_RECORDS:
            raise ValueError("Invalid record limit")
        self._cipher = AESGCM(key)
        self._context = context
        self._limit = limit
        self._used: set[bytes] = set()
        self._lock = Lock()

    def _check_capacity(self) -> None:
        if len(self._used) >= self._limit:
            raise SessionExhausted("Fresh session keys required")

    def encrypt(self, plaintext: bytes, *, message_type: int,
                sequence: int) -> tuple[bytes, bytes]:
        """Return (random nonce, ciphertext with tag). Reserve nonce before encryption."""
        if type(plaintext) is not bytes or len(plaintext) > MAX_PAYLOAD:
            raise ValueError("Invalid plaintext")
        with self._lock:
            self._check_capacity()
            for _ in range(8):
                nonce = secrets.token_bytes(12)
                if nonce not in self._used:
                    aad = self._context.build_aad(message_type, sequence, nonce, len(plaintext))
                    self._used.add(nonce)
                    return nonce, self._cipher.encrypt(nonce, plaintext, aad)
            self._limit = 0
            raise SessionExhausted("Fresh session keys required")

    def decrypt(self, nonce: bytes, sealed: bytes, *, message_type: int, sequence: int) -> bytes:
        """Return authenticated plaintext and record the nonce only after verification."""
        if type(sealed) is not bytes or not 16 <= len(sealed) <= MAX_PAYLOAD + 16:
            raise ValueError("Invalid ciphertext or tag length")
        aad = self._context.build_aad(message_type, sequence, nonce, len(sealed) - 16)
        with self._lock:
            self._check_capacity()
            if nonce in self._used:
                raise InvalidTag
            plaintext = self._cipher.decrypt(nonce, sealed, aad)
            self._used.add(nonce)
            return plaintext
