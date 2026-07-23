"""Content fingerprinting for local file identity checks."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

DEFAULT_READ_CHUNK_SIZE = 1024 * 1024
SHA256_DIGEST_SIZE = 32


@dataclass(frozen=True, slots=True)
class ContentFingerprint:
    """A stable content digest and observed size for one file read."""

    algorithm: str
    digest: bytes
    byte_size: int

    @property
    def hex_digest(self) -> str:
        return self.digest.hex()


def compute_sha256_fingerprint(
    path: Path,
    *,
    chunk_size: int = DEFAULT_READ_CHUNK_SIZE,
) -> ContentFingerprint:
    """Compute a SHA-256 fingerprint by streaming file bytes."""
    if chunk_size < 1:
        msg = "chunk_size must be at least 1"
        raise ValueError(msg)

    digest = sha256()
    byte_size = 0

    with path.open("rb") as file:
        while chunk := file.read(chunk_size):
            byte_size += len(chunk)
            digest.update(chunk)

    return ContentFingerprint(
        algorithm="sha256",
        digest=digest.digest(),
        byte_size=byte_size,
    )


def is_sha256_digest(value: bytes) -> bool:
    """Return whether the value has the expected SHA-256 byte length."""
    return len(value) == SHA256_DIGEST_SIZE
