from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine

from docweave.application_runtime import (
    DOCWEAVE_APPROVED_BY_ACTOR_ID,
    DOCWEAVE_DATABASE_URL,
    DOCWEAVE_TAXONOMY_VERSION_ID,
    DOCWEAVE_WORKSPACE_ID,
    RuntimeConfigurationError,
    RuntimeConfigurationErrorCode,
    build_configured_classification_runtime,
    build_configured_review_decision_runtime,
    load_runtime_environment_config,
    runtime_integration_snapshot,
)
from docweave.persistence import (
    CockroachSimpleMemoryRepository,
    CockroachTransactionRunner,
)
from docweave.persistence.simple_memory_repository import SerializableTransactionRunner

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
TAXONOMY_VERSION_ID = "22222222-2222-4222-8222-222222222222"
ACTOR_ID = "33333333-3333-4333-8333-333333333333"


def _valid_environment() -> dict[str, str]:
    return {
        DOCWEAVE_DATABASE_URL: "cockroachdb://user:secret@example.test/docweave",
        DOCWEAVE_WORKSPACE_ID: WORKSPACE_ID,
        DOCWEAVE_TAXONOMY_VERSION_ID: TAXONOMY_VERSION_ID,
        DOCWEAVE_APPROVED_BY_ACTOR_ID: ACTOR_ID,
    }


def test_runtime_snapshot_reports_configuration_without_secret_values() -> None:
    snapshot = runtime_integration_snapshot(
        {DOCWEAVE_DATABASE_URL: "cockroachdb://user:secret@example.test/db"}
    )

    assert snapshot.cockroachdb_configured
    assert snapshot.cockroachdb_status == "Configured"
    assert snapshot.bedrock_status == "Client configured"
    assert "secret" not in snapshot.cockroachdb_status


def test_runtime_config_requires_database_url_without_echoing_value() -> None:
    environment = _valid_environment()
    environment[DOCWEAVE_DATABASE_URL] = " "

    with pytest.raises(RuntimeConfigurationError) as captured:
        load_runtime_environment_config(environment)

    assert captured.value.code is RuntimeConfigurationErrorCode.DATABASE_URL_MISSING
    assert captured.value.variable_name == DOCWEAVE_DATABASE_URL
    assert "secret" not in str(captured.value)


def test_runtime_config_rejects_invalid_identifiers_safely() -> None:
    environment = _valid_environment()
    environment[DOCWEAVE_WORKSPACE_ID] = "not-a-uuid"

    with pytest.raises(RuntimeConfigurationError) as captured:
        load_runtime_environment_config(environment)

    assert captured.value.code is RuntimeConfigurationErrorCode.IDENTIFIER_INVALID
    assert captured.value.variable_name == DOCWEAVE_WORKSPACE_ID


def test_runtime_config_loads_required_persistent_identity_values() -> None:
    config = load_runtime_environment_config(_valid_environment())

    assert config.database_url.startswith("cockroachdb://")
    assert config.workspace_id == UUID(WORKSPACE_ID)
    assert config.taxonomy_version_id == UUID(TAXONOMY_VERSION_ID)
    assert config.approved_by_actor_id == UUID(ACTOR_ID)


def test_configured_runtime_composition_is_lazy() -> None:
    calls: list[str] = []

    class FakeSession:
        def client(self, service_name: str, **kwargs: Any) -> object:
            calls.append(f"client:{service_name}:{kwargs['region_name']}")
            return object()

    def fake_engine_factory(url: str, **kwargs: Any) -> Engine:
        calls.append(f"engine:{url}:{kwargs['pool_pre_ping']}")
        return cast(Engine, object())

    configured = build_configured_classification_runtime(
        _valid_environment(),
        session=FakeSession(),
        engine_factory=fake_engine_factory,
    )

    assert configured.config.workspace_id == UUID(WORKSPACE_ID)
    assert configured.engine is not None
    assert configured.gateway is not None
    assert calls == [
        "engine:cockroachdb://user:secret@example.test/docweave:True",
        "client:bedrock-runtime:eu-central-1",
    ]


def test_configured_review_decision_runtime_composition_is_lazy() -> None:
    calls: list[str] = []

    def fake_engine_factory(url: str, **kwargs: Any) -> Engine:
        calls.append(f"engine:{url}:{kwargs['pool_pre_ping']}")
        return cast(Engine, object())

    def fake_transaction_runner_factory(engine: Engine) -> CockroachTransactionRunner:
        assert engine is not None
        calls.append("transactions")
        return cast(CockroachTransactionRunner, object())

    def fake_repository_factory(
        transaction_runner: SerializableTransactionRunner,
    ) -> CockroachSimpleMemoryRepository:
        assert transaction_runner is not None
        calls.append("simple_memory_repository")
        return cast(CockroachSimpleMemoryRepository, object())

    configured = build_configured_review_decision_runtime(
        _valid_environment(),
        engine_factory=fake_engine_factory,
        transaction_runner_factory=fake_transaction_runner_factory,
        repository_factory=fake_repository_factory,
    )

    assert configured.config.approved_by_actor_id == UUID(ACTOR_ID)
    assert calls == [
        "engine:cockroachdb://user:secret@example.test/docweave:True",
        "transactions",
        "simple_memory_repository",
    ]
