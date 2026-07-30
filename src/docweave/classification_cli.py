"""Command-line entrypoint for one real classification runtime slice."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

from docweave.analysis.confidence import compute_uncalibrated_confidence
from docweave.application_runtime import (
    ConfiguredClassificationRuntime,
    RuntimeConfigurationError,
    RuntimeEnvironmentConfig,
    build_configured_classification_runtime,
)
from docweave.core.fingerprints import compute_sha256_fingerprint
from docweave.extraction import PdfExtractionRequest
from docweave.operations import classification_proposal_fingerprint
from docweave.persistence import (
    ClassificationPipelineError,
    ClassificationRunIdentity,
    PersistedClassificationRun,
)

_IDENTITY_NAMESPACE = UUID("7f5461df-2c2f-4f8d-b504-83ddf8e0d00a")
_MAX_BATCH_SIZE = 1_000

BatchItemStatus = Literal["succeeded", "failed"]


@dataclass(frozen=True, slots=True)
class ClassificationEvidenceDetail:
    """One validated evidence detail safe for local UI review."""

    evidence_id: str
    page_number: int
    quote: str


@dataclass(frozen=True, slots=True)
class ClassificationMetadataDetail:
    """One validated metadata proposal safe for local UI review."""

    name: str
    value: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClassificationCommandResult:
    """Content-minimized result safe for terminal output."""

    proposed_class: str
    document_disposition: str
    taxonomy_disposition: str
    proposal_disposition: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: str | None
    proposal_id: UUID | None = None
    document_language: str = "und"
    rationale: str = ""
    evidence_count: int = 0
    metadata_count: int = 0
    evidence_details: tuple[ClassificationEvidenceDetail, ...] = ()
    metadata_details: tuple[ClassificationMetadataDetail, ...] = ()
    alternative_class: str | None = None
    raw_confidence: str | None = None
    classification_confidence: str | None = None
    metadata_confidence: str | None = None
    proposal_fingerprint: str | None = None
    retry_attempts: int = 0


@dataclass(frozen=True, slots=True)
class ClassificationBatchItemResult:
    """One content-minimized batch item result safe for terminal output."""

    source_path: Path
    relative_path: str
    status: BatchItemStatus
    result: ClassificationCommandResult | None = None
    error_category: str | None = None


@dataclass(frozen=True, slots=True)
class ClassificationBatchCommandResult:
    """Observed result of one bounded command-line classification batch."""

    source_root: Path
    authorized_root: Path
    discovered_count: int
    attempted_count: int
    succeeded_count: int
    failed_count: int
    limit: int
    stopped_on_failure: bool
    items: tuple[ClassificationBatchItemResult, ...]


def build_content_addressed_identity(
    config: RuntimeEnvironmentConfig,
    *,
    source_sha256: str,
    idempotency_key: str | None,
) -> ClassificationRunIdentity:
    """Build stable initial identities for a first content-addressed CLI slice."""
    key = (
        idempotency_key.strip()
        if idempotency_key is not None and idempotency_key.strip()
        else f"classification.v1:{config.workspace_id}:{source_sha256}"
    )
    document_id = uuid5(
        _IDENTITY_NAMESPACE,
        f"{config.workspace_id}:document:{source_sha256}",
    )
    document_version_id = uuid5(
        _IDENTITY_NAMESPACE,
        f"{document_id}:version:{source_sha256}",
    )
    agent_run_id = uuid5(
        _IDENTITY_NAMESPACE,
        f"{document_version_id}:agent-run:{key}",
    )
    proposal_id = uuid5(
        _IDENTITY_NAMESPACE,
        f"{document_version_id}:proposal:{key}",
    )
    return ClassificationRunIdentity(
        workspace_id=config.workspace_id,
        document_id=document_id,
        document_version_id=document_version_id,
        taxonomy_version_id=config.taxonomy_version_id,
        approved_by_actor_id=config.approved_by_actor_id,
        agent_run_id=agent_run_id,
        proposal_id=proposal_id,
        version_number=1,
        idempotency_key=key,
        prompt_version=config.classification_prompt_version,
    )


def classify_pdf_once(
    source_path: Path,
    *,
    authorized_root: Path,
    idempotency_key: str | None = None,
) -> ClassificationCommandResult:
    """Run one configured extraction, Bedrock, and CockroachDB classification."""
    configured = build_configured_classification_runtime()
    return _classify_pdf_once_with_runtime(
        configured,
        source_path,
        authorized_root=authorized_root,
        idempotency_key=idempotency_key,
    )


def classify_pdf_batch(
    source_root: Path,
    *,
    authorized_root: Path,
    limit: int = _MAX_BATCH_SIZE,
    stop_on_failure: bool = False,
    idempotency_prefix: str = "classification-batch.v1",
) -> ClassificationBatchCommandResult:
    """Run a bounded, resumable classification batch over authorized PDFs.

    Resumability is provided by stable per-file idempotency keys derived from
    the workspace, source content hash, relative path, and caller prefix. A
    retry of the same batch reuses repository idempotency instead of
    fabricating local success.
    """
    pdfs = discover_batch_pdfs(
        source_root,
        authorized_root=authorized_root,
        limit=limit,
    )
    configured = build_configured_classification_runtime()
    resolved_authorized_root = authorized_root.resolve(strict=True)
    items: list[ClassificationBatchItemResult] = []
    stopped_on_failure = False
    for source_path in pdfs:
        relative_path = source_path.relative_to(resolved_authorized_root).as_posix()
        try:
            fingerprint = compute_sha256_fingerprint(source_path)
            result = _classify_pdf_once_with_runtime(
                configured,
                source_path,
                authorized_root=resolved_authorized_root,
                idempotency_key=(
                    f"{idempotency_prefix}:"
                    f"{configured.config.workspace_id}:"
                    f"{fingerprint.hex_digest}:"
                    f"{relative_path}"
                ),
                source_sha256=fingerprint.hex_digest,
            )
        except Exception as error:
            items.append(
                ClassificationBatchItemResult(
                    source_path=source_path,
                    relative_path=relative_path,
                    status="failed",
                    error_category=type(error).__name__,
                )
            )
            if stop_on_failure:
                stopped_on_failure = True
                break
            continue
        items.append(
            ClassificationBatchItemResult(
                source_path=source_path,
                relative_path=relative_path,
                status="succeeded",
                result=result,
            )
        )
    succeeded_count = sum(1 for item in items if item.status == "succeeded")
    failed_count = sum(1 for item in items if item.status == "failed")
    return ClassificationBatchCommandResult(
        source_root=source_root.resolve(strict=True),
        authorized_root=resolved_authorized_root,
        discovered_count=len(pdfs),
        attempted_count=len(items),
        succeeded_count=succeeded_count,
        failed_count=failed_count,
        limit=limit,
        stopped_on_failure=stopped_on_failure,
        items=tuple(items),
    )


def batch_result_to_report(
    result: ClassificationBatchCommandResult,
) -> dict[str, object]:
    """Return a sanitized machine-readable batch report."""
    return {
        "schema_version": "docweave.classification_batch_report.v1",
        "discovered_count": result.discovered_count,
        "attempted_count": result.attempted_count,
        "succeeded_count": result.succeeded_count,
        "failed_count": result.failed_count,
        "limit": result.limit,
        "stopped_on_failure": result.stopped_on_failure,
        "items": [_batch_item_to_report(item) for item in result.items],
    }


def write_batch_report(
    result: ClassificationBatchCommandResult,
    report_path: Path,
) -> None:
    """Write one sanitized report without overwriting an existing file."""
    payload = batch_result_to_report(result)
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _batch_item_to_report(
    item: ClassificationBatchItemResult,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "relative_path": item.relative_path,
        "status": item.status,
    }
    if item.status == "failed":
        payload["error_category"] = item.error_category
        return payload
    assert item.result is not None
    payload.update(
        {
            "proposed_class": item.result.proposed_class,
            "document_disposition": item.result.document_disposition,
            "taxonomy_disposition": item.result.taxonomy_disposition,
            "proposal_disposition": item.result.proposal_disposition,
            "proposal_id": (
                None
                if item.result.proposal_id is None
                else str(item.result.proposal_id)
            ),
            "input_tokens": item.result.input_tokens,
            "output_tokens": item.result.output_tokens,
            "total_tokens": item.result.total_tokens,
            "estimated_cost_usd": item.result.estimated_cost_usd,
            "evidence_count": item.result.evidence_count,
            "metadata_count": item.result.metadata_count,
            "raw_confidence": item.result.raw_confidence,
            "classification_confidence": item.result.classification_confidence,
            "metadata_confidence": item.result.metadata_confidence,
            "proposal_fingerprint": item.result.proposal_fingerprint,
            "retry_attempts": item.result.retry_attempts,
        }
    )
    return payload


def discover_batch_pdfs(
    source_root: Path,
    *,
    authorized_root: Path,
    limit: int = _MAX_BATCH_SIZE,
) -> tuple[Path, ...]:
    """Return deterministic PDF candidates within the authorized root."""
    if not 0 < limit <= _MAX_BATCH_SIZE:
        raise ValueError("limit must be between 1 and 1000")
    resolved_source_root = source_root.resolve(strict=True)
    resolved_authorized_root = authorized_root.resolve(strict=True)
    if not resolved_source_root.is_dir():
        raise ValueError("source_root must be a directory")
    try:
        resolved_source_root.relative_to(resolved_authorized_root)
    except ValueError as error:
        raise ValueError("source_root must be inside authorized_root") from error
    candidates = (
        path
        for path in resolved_source_root.rglob("*")
        if path.is_file() and path.suffix.casefold() == ".pdf"
    )
    return tuple(
        sorted(candidates, key=lambda path: path.as_posix().casefold())[:limit]
    )


def _classify_pdf_once_with_runtime(
    configured: ConfiguredClassificationRuntime,
    source_path: Path,
    *,
    authorized_root: Path,
    idempotency_key: str | None = None,
    source_sha256: str | None = None,
) -> ClassificationCommandResult:
    """Run one classification through a caller-supplied configured runtime."""
    fingerprint_hex = (
        source_sha256
        if source_sha256 is not None
        else compute_sha256_fingerprint(source_path).hex_digest
    )
    identity = build_content_addressed_identity(
        configured.config,
        source_sha256=fingerprint_hex,
        idempotency_key=idempotency_key,
    )
    persisted = configured.runtime.classify_and_persist(
        PdfExtractionRequest(
            source_path=source_path,
            authorized_root=authorized_root,
        ),
        identity=identity,
    )
    return _command_result(persisted, proposal_id=identity.proposal_id)


def main(argv: list[str] | None = None) -> int:
    """Run the command and print sanitized, reproducible outcome fields."""
    parser = argparse.ArgumentParser(
        description=(
            "Classify one PDF through the configured DocWeave extraction, "
            "Amazon Bedrock, and CockroachDB runtime."
        )
    )
    parser.add_argument("source_pdf", type=Path)
    parser.add_argument(
        "--authorized-root",
        type=Path,
        required=True,
        help="Authorized folder containing the PDF.",
    )
    parser.add_argument(
        "--idempotency-key",
        help="Optional stable key for retrying the same classification request.",
    )
    args = parser.parse_args(argv)

    try:
        result = classify_pdf_once(
            args.source_pdf,
            authorized_root=args.authorized_root,
            idempotency_key=args.idempotency_key,
        )
    except RuntimeConfigurationError as error:
        print(
            f"Configuration failed: {error.code.value} ({error.variable_name})",
            file=sys.stderr,
        )
        return 2
    except ClassificationPipelineError as error:
        print(
            "Classification failed: "
            f"{error.code.value} ({error.extraction_status.value})",
            file=sys.stderr,
        )
        return 3

    print(f"Proposed class: {result.proposed_class}")
    print(f"Document memory: {result.document_disposition}")
    print(f"Taxonomy memory: {result.taxonomy_disposition}")
    print(f"Proposal memory: {result.proposal_disposition}")
    print(
        "Bedrock tokens: "
        f"input={result.input_tokens} "
        f"output={result.output_tokens} "
        f"total={result.total_tokens}"
    )
    if result.estimated_cost_usd is not None:
        print(f"Estimated Bedrock cost USD: {result.estimated_cost_usd}")
    return 0


def batch_main(argv: list[str] | None = None) -> int:
    """Run a bounded batch command and print sanitized progress fields."""
    parser = argparse.ArgumentParser(
        description=(
            "Classify a bounded PDF batch through the configured DocWeave "
            "extraction, Amazon Bedrock, and CockroachDB runtime."
        )
    )
    parser.add_argument("source_root", type=Path)
    parser.add_argument(
        "--authorized-root",
        type=Path,
        required=True,
        help="Authorized folder containing the PDF batch.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_MAX_BATCH_SIZE,
        help="Maximum PDFs to attempt, capped at 1000.",
    )
    parser.add_argument(
        "--idempotency-prefix",
        default="classification-batch.v1",
        help="Stable prefix used to derive per-file retry keys.",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop after the first per-document failure.",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        help="Optional sanitized JSON report path. Existing files are not overwritten.",
    )
    args = parser.parse_args(argv)

    try:
        result = classify_pdf_batch(
            args.source_root,
            authorized_root=args.authorized_root,
            limit=args.limit,
            stop_on_failure=args.stop_on_failure,
            idempotency_prefix=args.idempotency_prefix,
        )
    except RuntimeConfigurationError as error:
        print(
            f"Configuration failed: {error.code.value} ({error.variable_name})",
            file=sys.stderr,
        )
        return 2
    except ValueError as error:
        print(f"Batch validation failed: {error}", file=sys.stderr)
        return 2

    print(f"Discovered PDFs: {result.discovered_count}")
    print(f"Attempted PDFs: {result.attempted_count}")
    print(f"Succeeded PDFs: {result.succeeded_count}")
    print(f"Failed PDFs: {result.failed_count}")
    if result.stopped_on_failure:
        print("Batch stopped after first failure.")
    for item in result.items:
        if item.status == "failed":
            print(f"[FAIL] {item.relative_path}: {item.error_category}")
            continue
        assert item.result is not None
        print(
            f"[OK] {item.relative_path}: "
            f"class={item.result.proposed_class} "
            f"tokens={item.result.total_tokens}"
        )
    if args.json_report is not None:
        try:
            write_batch_report(result, args.json_report)
        except FileExistsError:
            print("Batch report failed: target already exists", file=sys.stderr)
            return 2
        print(f"JSON report: {args.json_report}")
    return 1 if result.failed_count else 0


def _command_result(
    persisted: PersistedClassificationRun,
    *,
    proposal_id: UUID | None = None,
) -> ClassificationCommandResult:
    provenance = persisted.model_run.provenance
    proposal = persisted.model_run.proposal
    usage = provenance.usage
    estimated_cost = provenance.estimated_cost_usd
    confidence = compute_uncalibrated_confidence(proposal, persisted.extraction)
    return ClassificationCommandResult(
        proposed_class=proposal.proposed_class.value,
        document_disposition=persisted.document_disposition.value,
        taxonomy_disposition=persisted.taxonomy_disposition.value,
        proposal_disposition=persisted.proposal_disposition.value,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        estimated_cost_usd=str(estimated_cost) if estimated_cost is not None else None,
        proposal_id=proposal_id,
        document_language=proposal.document_language,
        rationale=proposal.rationale,
        evidence_count=len(proposal.evidence),
        metadata_count=len(proposal.candidate_metadata),
        evidence_details=tuple(
            ClassificationEvidenceDetail(
                evidence_id=item.evidence_id,
                page_number=item.page_index + 1,
                quote=item.quote,
            )
            for item in proposal.evidence[:3]
        ),
        metadata_details=tuple(
            ClassificationMetadataDetail(
                name=item.name,
                value=item.value,
                evidence_ids=item.evidence_ids,
            )
            for item in proposal.candidate_metadata[:6]
        ),
        alternative_class=(
            None
            if not proposal.alternative_classes
            else proposal.alternative_classes[0].class_code.value
        ),
        raw_confidence=str(confidence.raw),
        classification_confidence=str(confidence.classification),
        metadata_confidence=str(confidence.metadata),
        proposal_fingerprint=classification_proposal_fingerprint(proposal),
        retry_attempts=provenance.retry_attempts,
    )


if __name__ == "__main__":
    raise SystemExit(main())
