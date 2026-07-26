"""Explicit extraction, Bedrock, and CockroachDB classification orchestration."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import NoReturn, Protocol
from uuid import UUID

from sqlalchemy.engine import Engine

from docweave.analysis import (
    CLASSIFICATION_CONTRACT_VERSION,
    TAXONOMY_VERSION,
    BedrockClassificationRun,
)
from docweave.extraction import (
    ExtractedPage,
    ExtractionStatus,
    PdfExtractionRequest,
    PdfExtractionResult,
    extract_pdf_text,
)
from docweave.persistence.classification_repository import (
    ClassificationPersistenceIdentity,
    ClassificationScores,
    CockroachClassificationRepository,
    map_bedrock_classification_run,
)
from docweave.persistence.contracts import PersistenceDisposition
from docweave.persistence.memory_foundation_repository import (
    CockroachMemoryFoundationRepository,
    EnsureApprovedTaxonomy,
    RegisterDocumentVersion,
)
from docweave.persistence.transactions import (
    CockroachTransactionRunner,
    TransactionRetryHooks,
    TransactionRetryPolicy,
)

Clock = Callable[[], datetime]
Extractor = Callable[[PdfExtractionRequest], PdfExtractionResult]
ScoreProvider = Callable[
    [BedrockClassificationRun, PdfExtractionResult],
    ClassificationScores,
]
_DIGEST_SIZE = 32


class ClassificationGateway(Protocol):
    """Validated model gateway surface required by the runtime."""

    def classify(
        self,
        pages: tuple[ExtractedPage, ...],
    ) -> BedrockClassificationRun:
        """Return one validated, non-authoritative proposal."""


class ClassificationPipelineErrorCode(StrEnum):
    """Content-free pipeline failure safe for application reporting."""

    EXTRACTION_NOT_CLASSIFIABLE = "extraction_not_classifiable"
    EXTRACTION_PROVENANCE_MISSING = "extraction_provenance_missing"


class ClassificationPipelineError(RuntimeError):
    """Fail-closed error that retains no path or document content."""

    def __init__(
        self,
        code: ClassificationPipelineErrorCode,
        *,
        extraction_status: ExtractionStatus,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.extraction_status = extraction_status


@dataclass(frozen=True, slots=True)
class ClassificationRunIdentity:
    """Stable caller-authorized identities for one classification attempt."""

    workspace_id: UUID
    document_id: UUID
    document_version_id: UUID
    taxonomy_version_id: UUID
    approved_by_actor_id: UUID
    agent_run_id: UUID
    proposal_id: UUID
    version_number: int
    idempotency_key: str
    prompt_version: str

    def __post_init__(self) -> None:
        if self.version_number <= 0:
            raise ValueError("version_number must be positive")
        for name in ("idempotency_key", "prompt_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True, slots=True)
class PersistedClassificationRun:
    """Observed result of the explicit multi-boundary workflow."""

    extraction: PdfExtractionResult
    model_run: BedrockClassificationRun
    document_disposition: PersistenceDisposition
    taxonomy_disposition: PersistenceDisposition
    proposal_disposition: PersistenceDisposition


@dataclass(frozen=True, slots=True)
class ClassificationRuntimeOptions:
    """Optional deterministic dependencies for runtime composition."""

    retry_policy: TransactionRetryPolicy | None = None
    retry_hooks: TransactionRetryHooks | None = None
    extractor: Extractor = extract_pdf_text
    clock: Clock = lambda: datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class ClassificationRuntime:
    """Production-shaped dependencies with no hidden confidence fallback."""

    gateway: ClassificationGateway
    foundation_repository: CockroachMemoryFoundationRepository
    classification_repository: CockroachClassificationRepository
    score_provider: ScoreProvider
    extractor: Extractor = extract_pdf_text
    clock: Clock = lambda: datetime.now(UTC)

    def classify_and_persist(
        self,
        request: PdfExtractionRequest,
        *,
        identity: ClassificationRunIdentity,
    ) -> PersistedClassificationRun:
        """Extract, classify, and persist while keeping external effects separate."""
        extraction = self.extractor(request)
        pages = _classifiable_pages(extraction)
        observed_at = _as_utc(self.clock())
        digest = _required_digest(extraction)
        document_disposition = self.foundation_repository.register_document_version(
            RegisterDocumentVersion(
                workspace_id=identity.workspace_id,
                document_id=identity.document_id,
                document_version_id=identity.document_version_id,
                version_number=identity.version_number,
                sha256=digest,
                byte_size=_required_source_bytes(extraction),
                page_count=_required_page_count(extraction),
                extraction_status="ready",
                registered_at_utc=observed_at,
            )
        )
        taxonomy_command = EnsureApprovedTaxonomy(
            workspace_id=identity.workspace_id,
            taxonomy_version_id=identity.taxonomy_version_id,
            approved_by_actor_id=identity.approved_by_actor_id,
            approved_at_utc=observed_at,
        )
        taxonomy_disposition = self.foundation_repository.ensure_approved_taxonomy(
            taxonomy_command
        )

        model_run = self.gateway.classify(pages)
        scores = self.score_provider(model_run, extraction)
        persistence_command = map_bedrock_classification_run(
            model_run,
            identity=ClassificationPersistenceIdentity(
                workspace_id=identity.workspace_id,
                document_version_id=identity.document_version_id,
                taxonomy_version_id=identity.taxonomy_version_id,
                agent_run_id=identity.agent_run_id,
                proposal_id=identity.proposal_id,
                idempotency_key=identity.idempotency_key,
                request_sha256=_classification_request_digest(
                    pages,
                    prompt_version=identity.prompt_version,
                ),
                prompt_version=identity.prompt_version,
                completed_at_utc=_as_utc(self.clock()),
                scores=scores,
            ),
            taxonomy_class_ids=taxonomy_command.class_ids,
        )
        proposal_disposition = self.classification_repository.persist(
            persistence_command
        )
        return PersistedClassificationRun(
            extraction=extraction,
            model_run=model_run,
            document_disposition=document_disposition,
            taxonomy_disposition=taxonomy_disposition,
            proposal_disposition=proposal_disposition,
        )


def build_classification_runtime(
    engine: Engine,
    *,
    gateway: ClassificationGateway,
    score_provider: ScoreProvider,
    options: ClassificationRuntimeOptions | None = None,
) -> ClassificationRuntime:
    """Compose the pipeline without connecting or invoking Bedrock.

    Credential resolution, actor authorization, identity allocation, and
    selection of the confidence method remain caller responsibilities.
    """
    runtime_options = options or ClassificationRuntimeOptions()
    transaction_runner = CockroachTransactionRunner(
        engine,
        policy=runtime_options.retry_policy,
        hooks=runtime_options.retry_hooks,
    )
    return ClassificationRuntime(
        gateway=gateway,
        foundation_repository=CockroachMemoryFoundationRepository(transaction_runner),
        classification_repository=CockroachClassificationRepository(transaction_runner),
        score_provider=score_provider,
        extractor=runtime_options.extractor,
        clock=runtime_options.clock,
    )


def _classifiable_pages(
    extraction: PdfExtractionResult,
) -> tuple[ExtractedPage, ...]:
    if extraction.status is not ExtractionStatus.COMPLETED or not extraction.pages:
        raise ClassificationPipelineError(
            ClassificationPipelineErrorCode.EXTRACTION_NOT_CLASSIFIABLE,
            extraction_status=extraction.status,
        )
    return extraction.pages


def _required_digest(extraction: PdfExtractionResult) -> bytes:
    value = extraction.source_sha256
    if value is None:
        _raise_missing_provenance(extraction)
    try:
        digest = bytes.fromhex(value)
    except ValueError:
        _raise_missing_provenance(extraction)
    if len(digest) != _DIGEST_SIZE:
        _raise_missing_provenance(extraction)
    return digest


def _required_source_bytes(extraction: PdfExtractionResult) -> int:
    value = extraction.source_bytes
    if value is None:
        _raise_missing_provenance(extraction)
    return value


def _required_page_count(extraction: PdfExtractionResult) -> int:
    value = extraction.document_page_count
    if value is None or value <= 0:
        _raise_missing_provenance(extraction)
    return value


def _raise_missing_provenance(extraction: PdfExtractionResult) -> NoReturn:
    raise ClassificationPipelineError(
        ClassificationPipelineErrorCode.EXTRACTION_PROVENANCE_MISSING,
        extraction_status=extraction.status,
    )


def _classification_request_digest(
    pages: tuple[ExtractedPage, ...],
    *,
    prompt_version: str,
) -> bytes:
    payload: Mapping[str, object] = {
        "contract_version": CLASSIFICATION_CONTRACT_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "prompt_version": prompt_version,
        "pages": [
            {
                "page_index": page.page_index,
                "page_label": page.page_label,
                "text": page.text,
            }
            for page in pages
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return sha256(canonical).digest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware timestamp")
    return value.astimezone(UTC)
