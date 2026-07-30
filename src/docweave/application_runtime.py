"""Application-level composition for CockroachDB and Amazon Bedrock runtime use.

This module intentionally performs no database or model input/output during
configuration. It validates local configuration, creates lazy clients, and
hands the resulting dependencies to the already tested classification runtime.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from docweave.analysis import (
    APPROVED_BEDROCK_MODEL_ID,
    APPROVED_BEDROCK_REGION,
    CLASSIFICATION_CONTRACT_VERSION,
    BedrockClassificationGateway,
    BedrockGatewayConfig,
    create_bedrock_runtime_client,
)
from docweave.persistence import (
    ClassificationRuntime,
    CockroachReviewDecisionRepository,
    CockroachTransactionRunner,
    build_classification_runtime,
)
from docweave.persistence.classification_runtime import ClassificationGateway

DOCWEAVE_DATABASE_URL = "DOCWEAVE_DATABASE_URL"
DOCWEAVE_WORKSPACE_ID = "DOCWEAVE_WORKSPACE_ID"
DOCWEAVE_TAXONOMY_VERSION_ID = "DOCWEAVE_TAXONOMY_VERSION_ID"
DOCWEAVE_APPROVED_BY_ACTOR_ID = "DOCWEAVE_APPROVED_BY_ACTOR_ID"
DOCWEAVE_CLASSIFICATION_PROMPT_VERSION = "DOCWEAVE_CLASSIFICATION_PROMPT_VERSION"


class RuntimeConfigurationErrorCode(StrEnum):
    """Content-free runtime configuration failure categories."""

    DATABASE_URL_MISSING = "database_url_missing"
    IDENTIFIER_MISSING = "identifier_missing"
    IDENTIFIER_INVALID = "identifier_invalid"
    PROMPT_VERSION_INVALID = "prompt_version_invalid"


class RuntimeConfigurationError(RuntimeError):
    """Sanitized configuration error that never includes secret values."""

    def __init__(
        self,
        code: RuntimeConfigurationErrorCode,
        *,
        variable_name: str,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.variable_name = variable_name


@dataclass(frozen=True, slots=True)
class RuntimeIntegrationSnapshot:
    """Read-only startup visibility for configured external integrations."""

    cockroachdb_configured: bool
    bedrock_region: str
    bedrock_model_id: str

    @property
    def cockroachdb_status(self) -> str:
        """Return a compact user-interface status without exposing secrets."""
        return "Configured" if self.cockroachdb_configured else "Not configured"

    @property
    def bedrock_status(self) -> str:
        """Return the approved Bedrock client configuration status."""
        return "Client configured"


@dataclass(frozen=True, slots=True)
class RuntimeEnvironmentConfig:
    """Validated application configuration required for persistent analysis."""

    database_url: str
    workspace_id: UUID
    taxonomy_version_id: UUID
    approved_by_actor_id: UUID
    classification_prompt_version: str = CLASSIFICATION_CONTRACT_VERSION
    bedrock_config: BedrockGatewayConfig = field(default_factory=BedrockGatewayConfig)

    def __post_init__(self) -> None:
        if not self.database_url.strip():
            raise RuntimeConfigurationError(
                RuntimeConfigurationErrorCode.DATABASE_URL_MISSING,
                variable_name=DOCWEAVE_DATABASE_URL,
            )
        if not self.classification_prompt_version.strip():
            raise RuntimeConfigurationError(
                RuntimeConfigurationErrorCode.PROMPT_VERSION_INVALID,
                variable_name=DOCWEAVE_CLASSIFICATION_PROMPT_VERSION,
            )


@dataclass(frozen=True, slots=True)
class ConfiguredClassificationRuntime:
    """Lazily composed runtime dependencies for real classification work."""

    config: RuntimeEnvironmentConfig
    engine: Engine
    gateway: ClassificationGateway
    runtime: ClassificationRuntime


@dataclass(frozen=True, slots=True)
class ConfiguredReviewDecisionRuntime:
    """Lazily composed runtime dependencies for durable review decisions."""

    config: RuntimeEnvironmentConfig
    engine: Engine
    transaction_runner: CockroachTransactionRunner
    repository: CockroachReviewDecisionRepository


class SessionLike(Protocol):
    """Narrow boto3 session surface accepted by the Bedrock client factory."""

    def client(self, service_name: str, **kwargs: Any) -> Any:
        """Create one AWS service client."""


class EngineFactory(Protocol):
    """Narrow SQLAlchemy engine factory used for deterministic tests."""

    def __call__(self, url: str, **kwargs: Any) -> Engine:
        """Create a lazy SQLAlchemy engine without opening a connection."""


class RuntimeFactory(Protocol):
    """Narrow runtime factory used for deterministic tests."""

    def __call__(
        self,
        engine: Engine,
        *,
        gateway: ClassificationGateway,
    ) -> ClassificationRuntime:
        """Build a runtime around an engine and a validated gateway."""


class TransactionRunnerFactory(Protocol):
    """Narrow transaction runner factory used for deterministic tests."""

    def __call__(self, engine: Engine) -> CockroachTransactionRunner:
        """Create a serializable transaction runner."""


class ReviewRepositoryFactory(Protocol):
    """Narrow review repository factory used for deterministic tests."""

    def __call__(
        self,
        transaction_runner: CockroachTransactionRunner,
    ) -> CockroachReviewDecisionRepository:
        """Create a review decision repository."""


def runtime_integration_snapshot(
    environment: Mapping[str, str] | None = None,
) -> RuntimeIntegrationSnapshot:
    """Inspect configuration presence without connecting to external services."""
    values = environment if environment is not None else os.environ
    return RuntimeIntegrationSnapshot(
        cockroachdb_configured=bool(values.get(DOCWEAVE_DATABASE_URL, "").strip()),
        bedrock_region=APPROVED_BEDROCK_REGION,
        bedrock_model_id=APPROVED_BEDROCK_MODEL_ID,
    )


def load_runtime_environment_config(
    environment: Mapping[str, str] | None = None,
) -> RuntimeEnvironmentConfig:
    """Load and validate the explicit environment needed for persistent analysis."""
    values = environment if environment is not None else os.environ
    return RuntimeEnvironmentConfig(
        database_url=_required_secret_like_value(values, DOCWEAVE_DATABASE_URL),
        workspace_id=_required_uuid(values, DOCWEAVE_WORKSPACE_ID),
        taxonomy_version_id=_required_uuid(values, DOCWEAVE_TAXONOMY_VERSION_ID),
        approved_by_actor_id=_required_uuid(values, DOCWEAVE_APPROVED_BY_ACTOR_ID),
        classification_prompt_version=values.get(
            DOCWEAVE_CLASSIFICATION_PROMPT_VERSION,
            CLASSIFICATION_CONTRACT_VERSION,
        ),
    )


def build_configured_classification_runtime(
    environment: Mapping[str, str] | None = None,
    *,
    session: SessionLike | None = None,
    engine_factory: EngineFactory = create_engine,
    runtime_factory: RuntimeFactory = build_classification_runtime,
) -> ConfiguredClassificationRuntime:
    """Compose CockroachDB and Bedrock dependencies without invoking either service."""
    config = load_runtime_environment_config(environment)
    engine = engine_factory(
        config.database_url,
        pool_pre_ping=True,
        future=True,
    )
    client = create_bedrock_runtime_client(
        config=config.bedrock_config,
        session=session,
    )
    gateway = BedrockClassificationGateway(
        client,
        config=config.bedrock_config,
    )
    runtime = runtime_factory(engine, gateway=gateway)
    return ConfiguredClassificationRuntime(
        config=config,
        engine=engine,
        gateway=gateway,
        runtime=runtime,
    )


def build_configured_review_decision_runtime(
    environment: Mapping[str, str] | None = None,
    *,
    engine_factory: EngineFactory = create_engine,
    transaction_runner_factory: TransactionRunnerFactory = CockroachTransactionRunner,
    repository_factory: ReviewRepositoryFactory = CockroachReviewDecisionRepository,
) -> ConfiguredReviewDecisionRuntime:
    """Compose CockroachDB review-decision dependencies without database I/O."""
    config = load_runtime_environment_config(environment)
    engine = engine_factory(
        config.database_url,
        pool_pre_ping=True,
        future=True,
    )
    transaction_runner = transaction_runner_factory(engine)
    repository = repository_factory(transaction_runner)
    return ConfiguredReviewDecisionRuntime(
        config=config,
        engine=engine,
        transaction_runner=transaction_runner,
        repository=repository,
    )


def _required_secret_like_value(values: Mapping[str, str], variable_name: str) -> str:
    value = values.get(variable_name, "")
    if not value.strip():
        raise RuntimeConfigurationError(
            RuntimeConfigurationErrorCode.DATABASE_URL_MISSING,
            variable_name=variable_name,
        )
    return value


def _required_uuid(values: Mapping[str, str], variable_name: str) -> UUID:
    raw_value = values.get(variable_name, "")
    if not raw_value.strip():
        raise RuntimeConfigurationError(
            RuntimeConfigurationErrorCode.IDENTIFIER_MISSING,
            variable_name=variable_name,
        )
    try:
        return UUID(raw_value)
    except ValueError as error:
        raise RuntimeConfigurationError(
            RuntimeConfigurationErrorCode.IDENTIFIER_INVALID,
            variable_name=variable_name,
        ) from error


__all__ = [
    "DOCWEAVE_APPROVED_BY_ACTOR_ID",
    "DOCWEAVE_CLASSIFICATION_PROMPT_VERSION",
    "DOCWEAVE_DATABASE_URL",
    "DOCWEAVE_TAXONOMY_VERSION_ID",
    "DOCWEAVE_WORKSPACE_ID",
    "ConfiguredClassificationRuntime",
    "ConfiguredReviewDecisionRuntime",
    "RuntimeConfigurationError",
    "RuntimeConfigurationErrorCode",
    "RuntimeEnvironmentConfig",
    "RuntimeIntegrationSnapshot",
    "build_configured_classification_runtime",
    "build_configured_review_decision_runtime",
    "load_runtime_environment_config",
    "runtime_integration_snapshot",
]
