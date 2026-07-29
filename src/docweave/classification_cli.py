"""Command-line entrypoint for one real classification runtime slice."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid5

from docweave.analysis.confidence import compute_uncalibrated_confidence
from docweave.application_runtime import (
    RuntimeConfigurationError,
    RuntimeEnvironmentConfig,
    build_configured_classification_runtime,
)
from docweave.core.fingerprints import compute_sha256_fingerprint
from docweave.extraction import PdfExtractionRequest
from docweave.persistence import (
    ClassificationPipelineError,
    ClassificationRunIdentity,
    PersistedClassificationRun,
)

_IDENTITY_NAMESPACE = UUID("7f5461df-2c2f-4f8d-b504-83ddf8e0d00a")


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
    document_language: str = "und"
    rationale: str = ""
    evidence_count: int = 0
    metadata_count: int = 0
    alternative_class: str | None = None
    raw_confidence: str | None = None
    classification_confidence: str | None = None
    metadata_confidence: str | None = None
    retry_attempts: int = 0


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
    fingerprint = compute_sha256_fingerprint(source_path)
    identity = build_content_addressed_identity(
        configured.config,
        source_sha256=fingerprint.hex_digest,
        idempotency_key=idempotency_key,
    )
    persisted = configured.runtime.classify_and_persist(
        PdfExtractionRequest(
            source_path=source_path,
            authorized_root=authorized_root,
        ),
        identity=identity,
    )
    return _command_result(persisted)


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


def _command_result(
    persisted: PersistedClassificationRun,
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
        document_language=proposal.document_language,
        rationale=proposal.rationale,
        evidence_count=len(proposal.evidence),
        metadata_count=len(proposal.candidate_metadata),
        alternative_class=(
            None
            if not proposal.alternative_classes
            else proposal.alternative_classes[0].class_code.value
        ),
        raw_confidence=str(confidence.raw),
        classification_confidence=str(confidence.classification),
        metadata_confidence=str(confidence.metadata),
        retry_attempts=provenance.retry_attempts,
    )


if __name__ == "__main__":
    raise SystemExit(main())
