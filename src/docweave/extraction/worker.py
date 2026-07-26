"""Disposable Qt PDF extraction worker.

The parent process communicates through standard input and standard output.
This module is an internal process boundary, not a general command-line tool.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QBuffer, QByteArray, QIODeviceBase, qVersion
from PySide6.QtPdf import QPdfDocument

from docweave.extraction.contracts import ExtractionStatus


def main() -> int:
    """Read one request, emit one path-free result, and exit."""
    try:
        request = json.load(sys.stdin)
        result = _extract(request)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        result = _failure(ExtractionStatus.WORKER_FAILED, "invalid_request")
    except Exception:
        result = _failure(ExtractionStatus.WORKER_FAILED, "unexpected_worker_error")
    json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    return 0


def _extract(request: Any) -> dict[str, Any]:  # noqa: PLR0911
    if not isinstance(request, dict):
        raise TypeError
    source = Path(_required_string(request, "source_path"))
    root = Path(_required_string(request, "authorized_root"))
    expected_digest = _required_string(request, "expected_sha256")
    limits = request["limits"]
    if not isinstance(limits, dict):
        raise TypeError
    maximum_file_bytes = _positive_int(limits, "maximum_file_bytes")
    maximum_pages = _positive_int(limits, "maximum_pages")
    maximum_characters = _positive_int(limits, "maximum_characters")

    resolved_source = _validated_source(source, root)
    if resolved_source is None:
        return _failure(ExtractionStatus.SOURCE_REJECTED, "source_validation_failed")

    try:
        source_bytes = resolved_source.stat().st_size
        if source_bytes > maximum_file_bytes:
            return _failure(
                ExtractionStatus.FILE_LIMIT_EXCEEDED,
                source_bytes=source_bytes,
            )
        content = resolved_source.read_bytes()
    except OSError:
        return _failure(ExtractionStatus.SOURCE_REJECTED, "source_read_failed")

    if len(content) > maximum_file_bytes:
        return _failure(
            ExtractionStatus.FILE_LIMIT_EXCEEDED,
            source_bytes=len(content),
        )
    digest = hashlib.sha256(content).hexdigest()
    if digest != expected_digest:
        return _failure(
            ExtractionStatus.SOURCE_CHANGED,
            source_sha256=digest,
            source_bytes=len(content),
        )

    data = QByteArray(content)
    buffer = QBuffer()
    buffer.setData(data)
    if not buffer.open(QIODeviceBase.OpenModeFlag.ReadOnly):
        return _failure(
            ExtractionStatus.WORKER_FAILED,
            "buffer_open_failed",
            source_sha256=digest,
            source_bytes=len(content),
        )

    document = QPdfDocument()
    document.load(buffer)
    error = document.error()
    base: dict[str, Any] = {
        "source_sha256": digest,
        "source_bytes": len(content),
        "extractor": f"qt-pdf/{qVersion()}",
    }
    error_result = _load_error(error, base)
    if error_result is not None:
        return error_result

    page_count = document.pageCount()
    base["document_page_count"] = page_count
    if page_count > maximum_pages:
        return _failure(ExtractionStatus.PAGE_LIMIT_EXCEEDED, **base)

    pages: list[dict[str, Any]] = []
    total_characters = 0
    for page_index in range(page_count):
        text = document.getAllText(page_index).text()
        total_characters += len(text)
        if total_characters > maximum_characters:
            return _failure(ExtractionStatus.CHARACTER_LIMIT_EXCEEDED, **base)
        pages.append(
            {
                "page_index": page_index,
                "page_label": document.pageLabel(page_index),
                "text": text,
            }
        )

    status = (
        ExtractionStatus.COMPLETED
        if total_characters > 0
        else ExtractionStatus.NO_EXTRACTABLE_TEXT
    )
    return {"status": status.value, "pages": pages, **base}


def _validated_source(source: Path, root: Path) -> Path | None:
    try:
        if source.is_symlink():
            return None
        resolved_root = root.resolve(strict=True)
        resolved_source = source.resolve(strict=True)
        resolved_source.relative_to(resolved_root)
    except (OSError, ValueError):
        return None
    if not resolved_source.is_file() or resolved_source.suffix.casefold() != ".pdf":
        return None
    return resolved_source


def _load_error(
    error: QPdfDocument.Error, base: dict[str, Any]
) -> dict[str, Any] | None:
    if error is QPdfDocument.Error.None_:
        return None
    status = {
        QPdfDocument.Error.IncorrectPassword: ExtractionStatus.ENCRYPTED,
        QPdfDocument.Error.InvalidFileFormat: ExtractionStatus.MALFORMED,
        QPdfDocument.Error.UnsupportedSecurityScheme: (
            ExtractionStatus.UNSUPPORTED_SECURITY
        ),
    }.get(error, ExtractionStatus.WORKER_FAILED)
    return _failure(status, f"qt_pdf_{error.name.casefold()}", **base)


def _failure(
    status: ExtractionStatus,
    error_code: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status.value, "pages": [], **fields}
    if error_code is not None:
        result["error_code"] = error_code
    return result


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise TypeError
    return value


def _positive_int(payload: dict[str, Any], key: str) -> int:
    value = payload[key]
    if type(value) is not int or value <= 0:
        raise TypeError
    return value


if __name__ == "__main__":
    raise SystemExit(main())
