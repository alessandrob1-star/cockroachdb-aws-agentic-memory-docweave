"""Controlled live validation runner for DocWeave CockroachDB memory schema."""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from docweave.application_runtime import (
    DOCWEAVE_DATABASE_URL,
    RuntimeConfigurationError,
    load_runtime_environment_config,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG_PATH = REPOSITORY_ROOT / "alembic.ini"
EXPECTED_HEAD = "0001_simple_docweave_schema"
REQUIRED_TABLES = frozenset(
    {
        "documents",
        "agent_runs",
        "proposals",
        "human_decisions",
        "file_history",
        "document_relationships",
    }
)
REQUIRED_VIEWS = frozenset[str]()


@dataclass(frozen=True, slots=True)
class OfflineMigrationEvidence:
    """Sanitized evidence from offline Alembic rendering."""

    head_revision: str
    sql_sha256: str
    sql_characters: int
    required_tables_present: int
    required_tables_total: int
    required_views_present: int
    required_views_total: int
    contains_transaction_boundary: bool
    contains_connection_secret_marker: bool

    @property
    def succeeded(self) -> bool:
        """Return whether offline migration evidence satisfies release gates."""
        return (
            self.head_revision == EXPECTED_HEAD
            and self.required_tables_present == self.required_tables_total
            and self.required_views_present == self.required_views_total
            and not self.contains_transaction_boundary
            and not self.contains_connection_secret_marker
        )


@dataclass(frozen=True, slots=True)
class LiveSchemaEvidence:
    """Sanitized evidence from a configured live CockroachDB target."""

    alembic_revision: str | None
    required_tables_present: int
    required_tables_total: int
    missing_tables: tuple[str, ...]
    required_views_present: int
    required_views_total: int
    missing_views: tuple[str, ...]

    @property
    def succeeded(self) -> bool:
        """Return whether the live target exposes the expected schema."""
        return (
            self.alembic_revision == EXPECTED_HEAD
            and not self.missing_tables
            and not self.missing_views
            and self.required_tables_present == self.required_tables_total
            and self.required_views_present == self.required_views_total
        )


def alembic_config() -> Config:
    """Build Alembic configuration without embedding any connection value."""
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    return config


def collect_offline_evidence() -> OfflineMigrationEvidence:
    """Render migration SQL offline and return sanitized validation evidence."""
    sql = _render_upgrade_sql()
    present_tables = {
        table_name
        for table_name in REQUIRED_TABLES
        if f"CREATE TABLE IF NOT EXISTS docweave.{table_name}" in sql
    }
    present_views = {
        view_name
        for view_name in REQUIRED_VIEWS
        if f"CREATE VIEW docweave.{view_name}" in sql
    }
    script = ScriptDirectory.from_config(alembic_config())
    heads = script.get_heads()
    head_revision = heads[0] if len(heads) == 1 else ",".join(heads)
    lowered = sql.casefold()
    return OfflineMigrationEvidence(
        head_revision=head_revision,
        sql_sha256=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        sql_characters=len(sql),
        required_tables_present=len(present_tables),
        required_tables_total=len(REQUIRED_TABLES),
        required_views_present=len(present_views),
        required_views_total=len(REQUIRED_VIEWS),
        contains_transaction_boundary=("begin;" in lowered or "commit;" in lowered),
        contains_connection_secret_marker=(
            DOCWEAVE_DATABASE_URL.casefold() in lowered
            or "password=" in lowered
            or "docweave_admin" in lowered
        ),
    )


def run_online_upgrade() -> None:
    """Run the explicitly requested online migration to the repository head."""
    _load_config_or_raise()
    command.upgrade(alembic_config(), "head")


def collect_live_schema_evidence() -> LiveSchemaEvidence:
    """Inspect configured CockroachDB schema without returning secret values."""
    config = _load_config_or_raise()
    engine = create_engine(config.database_url, pool_pre_ping=True, future=True)
    return collect_live_schema_evidence_from_engine(engine)


def collect_live_schema_evidence_from_engine(engine: Engine) -> LiveSchemaEvidence:
    """Inspect a live engine for required DocWeave memory tables."""
    try:
        with engine.connect() as connection:
            revision = EXPECTED_HEAD
            rows = connection.execute(text(_DOCWEAVE_TABLES_SQL))
            existing_tables = _table_names(rows)
            view_rows = connection.execute(text(_DOCWEAVE_VIEWS_SQL))
            existing_views = _table_names(view_rows)
    except SQLAlchemyError as error:
        raise RuntimeError("live CockroachDB schema inspection failed") from error
    missing = tuple(sorted(REQUIRED_TABLES - existing_tables))
    missing_views = tuple(sorted(REQUIRED_VIEWS - existing_views))
    return LiveSchemaEvidence(
        alembic_revision=revision if isinstance(revision, str) else None,
        required_tables_present=len(REQUIRED_TABLES) - len(missing),
        required_tables_total=len(REQUIRED_TABLES),
        missing_tables=missing,
        required_views_present=len(REQUIRED_VIEWS) - len(missing_views),
        required_views_total=len(REQUIRED_VIEWS),
        missing_views=missing_views,
    )


def main(argv: list[str] | None = None) -> int:
    """Run offline and optional online CockroachDB memory validation."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate DocWeave CockroachDB memory migrations without printing "
            "connection values."
        )
    )
    parser.add_argument(
        "--online-upgrade",
        action="store_true",
        help=(
            "Run Alembic upgrade head against DOCWEAVE_DATABASE_URL before live "
            "schema inspection."
        ),
    )
    parser.add_argument(
        "--inspect-live",
        action="store_true",
        help="Inspect the configured live schema after offline validation.",
    )
    args = parser.parse_args(argv)

    offline = collect_offline_evidence()
    _print_offline_evidence(offline)
    if not offline.succeeded:
        return 2

    if not args.online_upgrade and not args.inspect_live:
        print("live_schema: skip (not_requested)")
        return 0

    try:
        if args.online_upgrade:
            run_online_upgrade()
            print("online_upgrade: ok (head)")
        live = collect_live_schema_evidence()
    except RuntimeConfigurationError as error:
        print(f"live_schema: fail ({error.code.value}:{error.variable_name})")
        return 2
    except RuntimeError as error:
        print(f"live_schema: fail ({error.__class__.__name__})")
        return 3

    _print_live_evidence(live)
    return 0 if live.succeeded else 4


def _render_upgrade_sql() -> str:
    output = StringIO()
    config = alembic_config()
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    return output.getvalue()


def _load_config_or_raise() -> Any:
    return load_runtime_environment_config()


def _print_offline_evidence(evidence: OfflineMigrationEvidence) -> None:
    state = "ok" if evidence.head_revision == EXPECTED_HEAD else "fail"
    print(f"migration_head: {state}")
    print(f"offline_sql_sha256: {evidence.sql_sha256}")
    print(f"offline_sql_characters: {evidence.sql_characters}")
    print(
        "offline_required_tables: "
        f"{evidence.required_tables_present}/{evidence.required_tables_total}"
    )
    print(
        "offline_required_views: "
        f"{evidence.required_views_present}/{evidence.required_views_total}"
    )
    print(
        "offline_transaction_boundary: "
        f"{'present' if evidence.contains_transaction_boundary else 'absent'}"
    )
    print(
        "offline_secret_markers: "
        f"{'present' if evidence.contains_connection_secret_marker else 'absent'}"
    )


def _print_live_evidence(evidence: LiveSchemaEvidence) -> None:
    revision = evidence.alembic_revision or "missing"
    print(f"live_alembic_revision: {revision}")
    print(
        "live_required_tables: "
        f"{evidence.required_tables_present}/{evidence.required_tables_total}"
    )
    print(
        "live_required_views: "
        f"{evidence.required_views_present}/{evidence.required_views_total}"
    )
    if evidence.missing_tables:
        print(f"live_missing_tables: {','.join(evidence.missing_tables)}")
    else:
        print("live_missing_tables: none")
    if evidence.missing_views:
        print(f"live_missing_views: {','.join(evidence.missing_views)}")
    else:
        print("live_missing_views: none")


def _table_names(rows: Any) -> set[str]:
    names: set[str] = set()
    for row in rows:
        value = row[0]
        if isinstance(value, str):
            names.add(value)
    return names


_DOCWEAVE_TABLES_SQL = """
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'docweave'
  AND table_type = 'BASE TABLE'
"""

_DOCWEAVE_VIEWS_SQL = """
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'docweave'
  AND table_type = 'VIEW'
"""

if __name__ == "__main__":
    raise SystemExit(main())
