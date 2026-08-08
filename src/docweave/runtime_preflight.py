"""Runtime preflight checks for configured DocWeave integrations."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

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
CloudHealthFetcher = Callable[[str], Mapping[str, Any]]


def _default_runtime_builder() -> RuntimeBundle:
    """Build the configured runtime through the application factory."""
    return build_configured_classification_runtime()


def run_preflight(
    *,
    check_database: bool = False,
    check_cloud: bool = False,
    cloud_api_url: str | None = None,
    runtime_builder: RuntimeBuilder = _default_runtime_builder,
    cloud_health_fetcher: CloudHealthFetcher | None = None,
) -> RuntimePreflightReport:
    """Run configuration and optional database preflight checks."""
    checks: list[PreflightCheck] = []
    try:
        runtime = runtime_builder()
    except RuntimeConfigurationError as error:
        checks.append(
            PreflightCheck(
                "runtime_config",
                PreflightState.FAIL,
                f"{error.code.value}:{error.variable_name}",
            )
        )
        if check_cloud:
            checks.extend(
                _cloud_checks(
                    cloud_api_url or os.environ.get("DOCWEAVE_CLOUD_API_URL") or "",
                    cloud_health_fetcher=cloud_health_fetcher or _fetch_cloud_health,
                )
            )
        return RuntimePreflightReport(checks=tuple(checks))

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

    if check_cloud:
        checks.extend(
            _cloud_checks(
                cloud_api_url or os.environ.get("DOCWEAVE_CLOUD_API_URL") or "",
                cloud_health_fetcher=cloud_health_fetcher or _fetch_cloud_health,
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
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Call the configured DocWeave cloud API health endpoint.",
    )
    parser.add_argument(
        "--cloud-api-url",
        help=(
            "DocWeave cloud API base URL. Defaults to DOCWEAVE_CLOUD_API_URL "
            "when --cloud is used."
        ),
    )
    args = parser.parse_args(argv)

    report = run_preflight(
        check_database=args.database,
        check_cloud=args.cloud,
        cloud_api_url=args.cloud_api_url,
    )
    for check in report.checks:
        print(f"{check.name}: {check.state.value} ({check.detail})")
    return 0 if report.succeeded else 2


def _database_checks(engine: Engine) -> tuple[PreflightCheck, ...]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            existing_tables = _docweave_tables(connection)
            existing_views = _docweave_views(connection)
            judged_tables = _judged_tables(connection)
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
    missing_views = sorted({"file_path_history"} - existing_views)
    required_judged_tables = {
        "documents",
        "agent_runs",
        "proposals",
        "human_decisions",
        "file_history",
        "document_relationships",
    }
    missing_judged = sorted(required_judged_tables - judged_tables)
    checks = [PreflightCheck("cockroachdb_connection", PreflightState.OK, "reachable")]
    if missing or missing_views or missing_judged:
        missing_parts = []
        if missing:
            missing_parts.append(f"tables:{','.join(missing)}")
        if missing_views:
            missing_parts.append(f"views:{','.join(missing_views)}")
        if missing_judged:
            missing_parts.append(f"judged:{','.join(missing_judged)}")
        checks.append(
            PreflightCheck(
                "docweave_schema",
                PreflightState.FAIL,
                f"missing:{';'.join(missing_parts)}",
            )
        )
    else:
        checks.append(PreflightCheck("docweave_schema", PreflightState.OK, "ready"))
    return tuple(checks)


def _cloud_checks(
    cloud_api_url: str,
    *,
    cloud_health_fetcher: CloudHealthFetcher,
) -> tuple[PreflightCheck, ...]:
    clean_url = cloud_api_url.strip()
    if not clean_url:
        return (
            PreflightCheck(
                "cloud_api",
                PreflightState.FAIL,
                "cloud_api_url_missing:DOCWEAVE_CLOUD_API_URL",
            ),
        )
    parsed = urlparse(clean_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        return (PreflightCheck("cloud_api", PreflightState.FAIL, "invalid_url"),)

    try:
        payload = cloud_health_fetcher(clean_url)
    except (
        HTTPError,
        TimeoutError,
        URLError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ):
        return (PreflightCheck("cloud_api", PreflightState.FAIL, "unavailable"),)

    status = str(payload.get("status", "")).casefold()
    services = payload.get("aws_services", {})
    if not isinstance(services, Mapping):
        services = {}
    if status != "ready":
        return (PreflightCheck("cloud_api", PreflightState.FAIL, "not_ready"),)

    bedrock_status = str(services.get("amazon_bedrock", "unknown")).casefold()
    lambda_status = str(services.get("aws_lambda", "unknown")).casefold()
    cockroach_status = str(services.get("cockroachdb_secret", "unknown")).casefold()
    detail = (
        f"ready;lambda={lambda_status};bedrock={bedrock_status};"
        f"cockroachdb_secret={cockroach_status}"
    )
    return (PreflightCheck("cloud_api", PreflightState.OK, detail),)


def _fetch_cloud_health(cloud_api_url: str) -> Mapping[str, Any]:
    health_url = urljoin(cloud_api_url.rstrip("/") + "/", "health")
    with urlopen(health_url, timeout=10) as response:  # noqa: S310
        raw_payload = response.read(128 * 1024)
    payload = json.loads(raw_payload.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("cloud health payload must be an object")
    return payload


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


def _docweave_views(connection: Connection) -> set[str]:
    rows = connection.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'docweave'
              AND table_type = 'VIEW'
            """
        )
    )
    view_names: set[str] = set()
    for row in rows:
        value: Any = row[0]
        if isinstance(value, str):
            view_names.add(value)
    return view_names


def _judged_tables(connection: Connection) -> set[str]:
    rows = connection.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'docweave_judged'
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
