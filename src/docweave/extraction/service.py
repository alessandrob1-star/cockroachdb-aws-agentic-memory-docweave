"""Parent-side boundary for resource-limited PDF extraction."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from docweave.extraction.contracts import (
    ExtractedPage,
    ExtractionStatus,
    PdfExtractionRequest,
    PdfExtractionResult,
)
from docweave.inspection import inspect_pdf_signature

_DIGEST_HEX_LENGTH = 64
_WORKER_MODULE = "docweave.extraction.worker"


def extract_pdf_text(  # noqa: PLR0911
    request: PdfExtractionRequest,
) -> PdfExtractionResult:
    """Extract PDF text in a disposable worker with bounded resources."""
    source = _validated_source(request)
    if source is None:
        return PdfExtractionResult(status=ExtractionStatus.SOURCE_REJECTED)

    try:
        source_bytes = source.stat().st_size
    except OSError:
        return PdfExtractionResult(status=ExtractionStatus.SOURCE_REJECTED)

    if source_bytes > request.limits.maximum_file_bytes:
        return PdfExtractionResult(
            status=ExtractionStatus.FILE_LIMIT_EXCEEDED,
            source_bytes=source_bytes,
        )

    try:
        expected_digest = _sha256_file(source)
    except OSError:
        return PdfExtractionResult(status=ExtractionStatus.SOURCE_REJECTED)

    payload = {
        "source_path": str(source),
        "authorized_root": str(request.authorized_root.resolve(strict=True)),
        "expected_sha256": expected_digest,
        "limits": {
            "maximum_file_bytes": request.limits.maximum_file_bytes,
            "maximum_pages": request.limits.maximum_pages,
            "maximum_characters": request.limits.maximum_characters,
        },
    }
    try:
        # The executable and module are fixed application constants. Only the
        # JSON standard-input payload contains request data.
        completed = subprocess.run(  # noqa: S603
            [sys.executable, "-m", _WORKER_MODULE],
            input=json.dumps(payload),
            capture_output=True,
            check=False,
            text=True,
            timeout=request.limits.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return PdfExtractionResult(
            status=ExtractionStatus.TIMED_OUT,
            source_sha256=expected_digest,
            source_bytes=source_bytes,
        )
    except OSError:
        return PdfExtractionResult(
            status=ExtractionStatus.WORKER_FAILED,
            source_sha256=expected_digest,
            source_bytes=source_bytes,
            error_code="worker_start_failed",
        )

    if completed.returncode != 0:
        return PdfExtractionResult(
            status=ExtractionStatus.WORKER_FAILED,
            source_sha256=expected_digest,
            source_bytes=source_bytes,
            error_code="worker_exit_failed",
        )

    return _decode_worker_result(
        completed.stdout,
        expected_digest=expected_digest,
        maximum_pages=request.limits.maximum_pages,
        maximum_characters=request.limits.maximum_characters,
    )


def _validated_source(request: PdfExtractionRequest) -> Path | None:
    try:
        if request.source_path.is_symlink():
            return None
        root = request.authorized_root.resolve(strict=True)
        source = request.source_path.resolve(strict=True)
        source.relative_to(root)
    except (OSError, ValueError):
        return None

    if not source.is_file() or source.suffix.casefold() != ".pdf":
        return None
    if not inspect_pdf_signature(source).is_valid:
        return None
    return source


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_worker_result(
    raw_output: str,
    *,
    expected_digest: str,
    maximum_pages: int,
    maximum_characters: int,
) -> PdfExtractionResult:
    try:
        payload = json.loads(raw_output)
        if not isinstance(payload, dict):
            raise TypeError
        status = ExtractionStatus(_required_string(payload, "status"))
        digest = _optional_string(payload, "source_sha256")
        source_bytes = _optional_nonnegative_int(payload, "source_bytes")
        page_count = _optional_nonnegative_int(payload, "document_page_count")
        extractor = _optional_string(payload, "extractor")
        error_code = _optional_string(payload, "error_code")
        pages = _decode_pages(payload.get("pages", []), maximum_pages)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return PdfExtractionResult(
            status=ExtractionStatus.WORKER_FAILED,
            source_sha256=expected_digest,
            error_code="invalid_worker_response",
        )

    if digest is not None and (
        len(digest) != _DIGEST_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        return PdfExtractionResult(
            status=ExtractionStatus.WORKER_FAILED,
            source_sha256=expected_digest,
            error_code="invalid_worker_response",
        )
    if digest is not None and digest != expected_digest:
        return PdfExtractionResult(
            status=ExtractionStatus.SOURCE_CHANGED,
            source_sha256=digest,
            source_bytes=source_bytes,
            extractor=extractor,
        )
    if sum(len(page.text) for page in pages) > maximum_characters:
        return PdfExtractionResult(
            status=ExtractionStatus.WORKER_FAILED,
            source_sha256=expected_digest,
            error_code="worker_budget_violation",
        )

    return PdfExtractionResult(
        status=status,
        pages=pages,
        source_sha256=digest,
        source_bytes=source_bytes,
        document_page_count=page_count,
        extractor=extractor,
        error_code=error_code,
    )


def _decode_pages(value: Any, maximum_pages: int) -> tuple[ExtractedPage, ...]:
    if not isinstance(value, list) or len(value) > maximum_pages:
        raise TypeError
    pages: list[ExtractedPage] = []
    for expected_index, item in enumerate(value):
        if not isinstance(item, dict):
            raise TypeError
        page_index = item.get("page_index")
        page_label = item.get("page_label")
        text = item.get("text")
        if (
            type(page_index) is not int
            or page_index != expected_index
            or not isinstance(page_label, str)
            or not isinstance(text, str)
        ):
            raise TypeError
        pages.append(
            ExtractedPage(
                page_index=page_index,
                page_label=page_label,
                text=text,
            )
        )
    return tuple(pages)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise TypeError
    return value


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is not None and not isinstance(value, str):
        raise TypeError
    return value


def _optional_nonnegative_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is not None and (type(value) is not int or value < 0):
        raise TypeError
    return value
