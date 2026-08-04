from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine

from docweave import runtime_preflight
from docweave.application_runtime import (
    RuntimeConfigurationError,
    RuntimeConfigurationErrorCode,
    RuntimeEnvironmentConfig,
)
from docweave.runtime_preflight import PreflightState, run_preflight


@dataclass(frozen=True, slots=True)
class FakeRuntime:
    config: RuntimeEnvironmentConfig
    engine: Engine


class FakeRow:
    def __init__(self, value: str) -> None:
        self._value = value

    def __getitem__(self, index: int) -> str:
        assert index == 0
        return self._value


class FakeConnection:
    def __init__(self, tables: set[str]) -> None:
        self._tables = tables
        self.queries: list[str] = []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: object) -> Iterable[FakeRow]:
        raw_statement = str(statement)
        self.queries.append(raw_statement)
        if "information_schema.tables" not in raw_statement:
            return ()
        return tuple(FakeRow(table) for table in sorted(self._tables))


class FakeEngine:
    def __init__(self, tables: set[str]) -> None:
        self.connection = FakeConnection(tables)

    def connect(self) -> FakeConnection:
        return self.connection


def _config() -> RuntimeEnvironmentConfig:
    return RuntimeEnvironmentConfig(
        database_url="cockroachdb://user:secret@example.test/docweave",
        workspace_id=UUID("11111111-1111-4111-8111-111111111111"),
        taxonomy_version_id=UUID("22222222-2222-4222-8222-222222222222"),
        approved_by_actor_id=UUID("33333333-3333-4333-8333-333333333333"),
    )


def _runtime(tables: set[str]) -> FakeRuntime:
    return FakeRuntime(config=_config(), engine=cast(Engine, FakeEngine(tables)))


def _required_tables() -> set[str]:
    return {
        "workspaces",
        "actors",
        "documents",
        "document_versions",
        "agent_runs",
        "proposals",
        "classification_proposals",
        "proposal_evidence",
        "review_decisions",
        "file_lineage_events",
        "cloud_analysis_jobs",
        "cloud_analysis_objects",
    }


def test_preflight_reports_missing_runtime_config_without_secret_values() -> None:
    def fail_builder() -> FakeRuntime:
        raise RuntimeConfigurationError(
            RuntimeConfigurationErrorCode.DATABASE_URL_MISSING,
            variable_name="DOCWEAVE_DATABASE_URL",
        )

    report = run_preflight(runtime_builder=fail_builder)

    assert not report.succeeded
    assert report.checks[0].state is PreflightState.FAIL
    assert report.checks[0].detail == "database_url_missing:DOCWEAVE_DATABASE_URL"
    assert "secret" not in report.checks[0].detail


def test_preflight_skips_database_when_not_requested() -> None:
    report = run_preflight(runtime_builder=lambda: _runtime(set()))

    assert report.succeeded
    assert [check.name for check in report.checks] == [
        "runtime_config",
        "bedrock_client",
        "cockroachdb_connection",
    ]
    assert report.checks[-1].state is PreflightState.SKIP


def test_preflight_passes_database_when_required_schema_exists() -> None:
    report = run_preflight(
        check_database=True,
        runtime_builder=lambda: _runtime(_required_tables()),
    )

    assert report.succeeded
    assert report.checks[-2].detail == "reachable"
    assert report.checks[-1].detail == "ready"


def test_preflight_fails_database_when_required_schema_is_incomplete() -> None:
    report = run_preflight(
        check_database=True,
        runtime_builder=lambda: _runtime({"workspaces", "actors"}),
    )

    assert not report.succeeded
    assert report.checks[-1].state is PreflightState.FAIL
    assert "classification_proposals" in report.checks[-1].detail


def test_main_returns_failure_for_failed_preflight(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        runtime_preflight,
        "run_preflight",
        lambda *, check_database: runtime_preflight.RuntimePreflightReport(
            checks=(
                runtime_preflight.PreflightCheck(
                    "runtime_config",
                    PreflightState.FAIL,
                    "database_url_missing:DOCWEAVE_DATABASE_URL",
                ),
            )
        ),
    )

    result = runtime_preflight.main(["--database"])

    captured = capsys.readouterr()
    assert result == 2
    assert "runtime_config: fail" in captured.out
    assert "secret" not in captured.out
