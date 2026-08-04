"""Runtime preflight checks for configured DocWeave integrations."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from docweave.application_runtime import (
    RuntimeConfigurationError,
    RuntimeEnvironmentConfig,
    build_configured_classification_runtime,
)


class PreflightState(StrEnum):
    """Sanitized preflight state."""

    OK = "ok"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    """One content-free preflight result."""

    name: str
    state: PreflightState
    detail: str


@dataclass(frozen=True, slots=True)
class RuntimePreflightReport:
    """Preflight summary safe for terminal output."""

    checks: tuple[PreflightCheck, ...]

    @property
    def succeeded(self) -> bool:
        """Return true when no check failed."""
        return all(check.state is not PreflightState.FAIL for check in self.checks)


class RuntimeBundle(Protocol):
    """Configured runtime attributes needed by preflight checks."""

    @property
    def config(self) -> RuntimeEnvironmentConfig:
        """Return loaded runtime configuration."""

    @property
    def engine(self) -> Engine:
        """Return configured SQLAlchemy engine."""


RuntimeBuilder = Callable[[], RuntimeBundle]


def _default_runtime_builder() -> RuntimeBundle:
    """Build the configured runtime through the application factory."""
    return build_configured_classification_runtime()


def run_preflight(
    *,
    check_database: bool = False,
    runtime_builder: RuntimeBuilder = _default_runtime_builder,
) -> RuntimePreflightReport:
    """Run configuration and optional database preflight checks."""
    checks: list[PreflightCheck] = []
    try:
        runtime = runtime_builder()
    except RuntimeConfigurationError as error:
        return RuntimePreflightReport(
            checks=(
                PreflightCheck(
                    "runtime_config",
                    PreflightState.FAIL,
                    f"{error.code.value}:{error.variable_name}",
                ),
            )
        )

    checks.append(PreflightCheck("runtime_config", PreflightState.OK, "loaded"))
    checks.append(
        PreflightCheck(
            "bedrock_client",
            PreflightState.OK,
            f"{runtime.config.bedrock_config.region_name}:configured",
        )
    )

    if check_database:
        checks.extend(_database_checks(runtime.engine))
    else:
        checks.append(
            PreflightCheck(
                "cockroachdb_connection",
                PreflightState.SKIP,
                "not_requested",
            )
        )

    return RuntimePreflightReport(checks=tuple(checks))


def main(argv: list[str] | None = None) -> int:
    """Run runtime preflight and print sanitized results."""
    parser = argparse.ArgumentParser(
        description="Check configured DocWeave CockroachDB and Bedrock readiness."
    )
    parser.add_argument(
        "--database",
        action="store_true",
        help="Open the configured database and verify required schema tables.",
    )
    args = parser.parse_args(argv)

    report = run_preflight(check_database=args.database)
    for check in report.checks:
        print(f"{check.name}: {check.state.value} ({check.detail})")
    return 0 if report.succeeded else 2


def _database_checks(engine: Engine) -> tuple[PreflightCheck, ...]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            existing_tables = _docweave_tables(connection)
    except SQLAlchemyError:
        return (
            PreflightCheck(
                "cockroachdb_connection",
                PreflightState.FAIL,
                "unavailable",
            ),
        )

    required_tables = {
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
    missing = sorted(required_tables - existing_tables)
    checks = [PreflightCheck("cockroachdb_connection", PreflightState.OK, "reachable")]
    if missing:
        checks.append(
            PreflightCheck(
                "docweave_schema",
                PreflightState.FAIL,
                f"missing:{','.join(missing)}",
            )
        )
    else:
        checks.append(PreflightCheck("docweave_schema", PreflightState.OK, "ready"))
    return tuple(checks)


def _docweave_tables(connection: Connection) -> set[str]:
    rows = connection.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'docweave'
              AND table_type = 'BASE TABLE'
            """
        )
    )
    table_names: set[str] = set()
    for row in rows:
        value: Any = row[0]
        if isinstance(value, str):
            table_names.add(value)
    return table_names


if __name__ == "__main__":
    raise SystemExit(main())
