import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

CORPUS_ROOT = Path(__file__).parents[2] / "pdf_sintetici"
MANIFEST_PATH = (
    Path(__file__).parents[2] / "docs" / "synthetic" / "initial-corpus-manifest.json"
)


def _manifest() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
    )


def test_initial_corpus_contains_declared_pdf_files() -> None:
    files = sorted(CORPUS_ROOT.glob("*.pdf"))

    assert len(files) == _manifest()["document_count"]
    assert all(path.is_file() and path.suffix == ".pdf" for path in files)
    assert all(path.read_bytes().startswith(b"%PDF-") for path in files)


def test_manifest_matches_files_hashes_and_categories() -> None:
    manifest = _manifest()
    entries = manifest["documents"]
    files_by_name = {path.name: path for path in CORPUS_ROOT.glob("*.pdf")}

    assert manifest["document_count"] == 100
    assert manifest["contains_real_personal_data"] is False
    assert {entry["filename"] for entry in entries} == set(files_by_name)
    assert (
        Counter(entry["category"] for entry in entries) == manifest["category_counts"]
    )
    for entry in entries:
        content = files_by_name[entry["filename"]].read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
        assert entry["page_count"] == 2
        assert entry["synthetic"] is True
        assert entry["contains_real_personal_data"] is False
        assert entry["model_generated"] is False


def test_relationship_references_resolve_with_intentional_incomplete_cases() -> None:
    entries = _manifest()["documents"]
    known_ids = {entry["document_id"] for entry in entries}
    complete_dossier_ids = {f"DOS-2026-{index:03d}" for index in range(1, 7)}
    full_dossiers = Counter(
        entry["dossier_id"]
        for entry in entries
        if entry["dossier_id"] in complete_dossier_ids
    )

    assert all(
        related_id in known_ids
        for entry in entries
        for related_id in entry["related_document_ids"]
    )
    assert full_dossiers == {f"DOS-2026-{index:03d}": 4 for index in range(1, 7)}
    assert any(
        entry["status"] == "Reference missing" and not entry["related_document_ids"]
        for entry in entries
    )


def test_filenames_do_not_reveal_expected_category_or_document_identifier() -> None:
    forbidden_tokens = {
        "purchase",
        "order",
        "invoice",
        "payment",
        "delivery",
    }

    for entry in _manifest()["documents"]:
        filename = entry["filename"].casefold()
        assert forbidden_tokens.isdisjoint(filename.replace("-", "_").split("_"))
        assert entry["document_id"].casefold() not in filename
