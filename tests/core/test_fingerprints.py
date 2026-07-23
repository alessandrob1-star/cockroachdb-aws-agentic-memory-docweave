from hashlib import sha256
from pathlib import Path

import pytest

from docweave.core.fingerprints import (
    SHA256_DIGEST_SIZE,
    compute_sha256_fingerprint,
    is_sha256_digest,
)


def test_compute_sha256_fingerprint_streams_file_content(tmp_path: Path) -> None:
    path = tmp_path / "document.pdf"
    content = b"%PDF-1.7\n" + (b"invoice body\n" * 128)
    path.write_bytes(content)

    fingerprint = compute_sha256_fingerprint(path, chunk_size=17)

    assert fingerprint.algorithm == "sha256"
    assert fingerprint.digest == sha256(content).digest()
    assert fingerprint.hex_digest == sha256(content).hexdigest()
    assert fingerprint.byte_size == len(content)
    assert len(fingerprint.digest) == SHA256_DIGEST_SIZE


def test_empty_file_has_stable_sha256_digest(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")

    fingerprint = compute_sha256_fingerprint(path)

    assert fingerprint.digest == sha256(b"").digest()
    assert fingerprint.byte_size == 0


def test_rejects_invalid_chunk_size(tmp_path: Path) -> None:
    path = tmp_path / "document.pdf"
    path.write_bytes(b"content")

    with pytest.raises(ValueError, match="chunk_size"):
        compute_sha256_fingerprint(path, chunk_size=0)


def test_propagates_file_read_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError):
        compute_sha256_fingerprint(missing)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (b"x" * SHA256_DIGEST_SIZE, True),
        (b"", False),
        (b"x" * (SHA256_DIGEST_SIZE - 1), False),
        (b"x" * (SHA256_DIGEST_SIZE + 1), False),
    ],
)
def test_validates_sha256_digest_length(value: bytes, expected: bool) -> None:
    assert is_sha256_digest(value) is expected
