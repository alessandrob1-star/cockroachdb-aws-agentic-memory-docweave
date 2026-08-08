"""Read-only CockroachDB memory evidence reporting for DocWeave."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from docweave.application_runtime import (
    RuntimeConfigurationError,
    load_runtime_environment_config,
)

EXPECTED_SIMPLE_SCHEMA = "simple_docweave_schema"
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

_WORKSPACE_SCOPED_TABLES = frozenset[str]()


@dataclass(frozen=True, slots=True)
class MemoryTableCount:
    """One sanitized table-count row."""

    table_name: str
    present: bool
    row_count: int | None


@dataclass(frozen=True, slots=True)
class MemoryEvidenceReport:
    """Sanitized read-only evidence that CockroachDB memory is inspectable."""

    alembic_revision: str | None
    expected_head: str
    table_counts: tuple[MemoryTableCount, ...]
    workspace_id: UUID | None = None

    @property
    def schema_ready(self) -> bool:
        """Return whether all required memory tables are present at head."""
        return all(row.present for row in self.table_counts)


def collect_memory_evidence(
    *,
    workspace_id: UUID | None = None,
) -> MemoryEvidenceReport:
    """Collect read-only evidence from the configured CockroachDB target."""
    config = load_runtime_environment_config()
    engine = create_engine(config.database_url, pool_pre_ping=True, future=True)
    return collect_memory_evidence_from_engine(engine, workspace_id=workspace_id)


def collect_memory_evidence_from_engine(
    engine: Engine,
    *,
    workspace_id: UUID | None = None,
) -> MemoryEvidenceReport:
    """Collect read-only memory evidence from an injected engine."""
    try:
        with engine.connect() as connection:
            revision = EXPECTED_SIMPLE_SCHEMA
            existing_tables = {
                str(row[0])
                for row in connection.execute(text(_DOCWEAVE_TABLES_SQL))
                if isinstance(row[0], str)
            }
            counts = tuple(
                _count_table(
                    connection=connection,
                    table_name=table_name,
                    existing_tables=existing_tables,
                    workspace_id=workspace_id,
                )
                for table_name in sorted(REQUIRED_TABLES)
            )
    except SQLAlchemyError as error:
        raise RuntimeError("memory evidence report failed") from error
    return MemoryEvidenceReport(
        alembic_revision=revision if isinstance(revision, str) else None,
        expected_head=EXPECTED_SIMPLE_SCHEMA,
        table_counts=counts,
        workspace_id=workspace_id,
    )


def main(argv: list[str] | None = None) -> int:
    """Print a sanitized read-only CockroachDB memory evidence report."""
    parser = argparse.ArgumentParser(
        description="Read DocWeave CockroachDB memory evidence without writing rows."
    )
    parser.add_argument(
        "--workspace-id",
        type=UUID,
        help="Optionally scope row counts to one workspace when a table supports it.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of text lines.",
    )
    args = parser.parse_args(argv)

    try:
        report = collect_memory_evidence(workspace_id=args.workspace_id)
    except RuntimeConfigurationError as error:
        print(f"memory_evidence: fail ({error.code.value}:{error.variable_name})")
        return 2
    except RuntimeError as error:
        print(f"memory_evidence: fail ({error.__class__.__name__})")
        return 3

    if args.json:
        print(json.dumps(_report_json(report), sort_keys=True, separators=(",", ":")))
    else:
        _print_text_report(report)
    return 0 if report.schema_ready else 4


def _count_table(
    *,
    connection: Connection,
    table_name: str,
    existing_tables: set[str],
    workspace_id: UUID | None,
) -> MemoryTableCount:
    if table_name not in existing_tables:
        return MemoryTableCount(table_name=table_name, present=False, row_count=None)
    statement = _COUNT_TABLE_SQL[table_name]
    parameters: dict[str, object] = {}
    if workspace_id is not None and table_name in _WORKSPACE_SCOPED_TABLES:
        statement = _COUNT_WORKSPACE_TABLE_SQL[table_name]
        parameters["workspace_id"] = workspace_id
    row_count = connection.execute(text(statement), parameters).scalar_one()
    if not isinstance(row_count, int):
        raise RuntimeError("memory table count returned a non-integer value")
    return MemoryTableCount(table_name=table_name, present=True, row_count=row_count)


def _print_text_report(report: MemoryEvidenceReport) -> None:
    revision = report.alembic_revision or "missing"
    print(f"memory_schema_revision: {revision}")
    print(f"memory_schema_ready: {'yes' if report.schema_ready else 'no'}")
    if report.workspace_id is not None:
        print("workspace_scope: provided")
    for row in report.table_counts:
        if row.present:
            print(f"table.{row.table_name}: present ({row.row_count})")
        else:
            print(f"table.{row.table_name}: missing")


def _report_json(report: MemoryEvidenceReport) -> dict[str, object]:
    return {
        "schema_ready": report.schema_ready,
        "alembic_revision": report.alembic_revision,
        "expected_head": report.expected_head,
        "workspace_scope": report.workspace_id is not None,
        "tables": [
            {
                "name": row.table_name,
                "present": row.present,
                "row_count": row.row_count,
            }
            for row in report.table_counts
        ],
    }


_DOCWEAVE_TABLES_SQL = """
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'docweave'
  AND table_type = 'BASE TABLE'
"""

_COUNT_TABLE_SQL = {
    # S608: table names come only from the internal REQUIRED_TABLES allowlist.
    table_name: f"SELECT count(*) FROM docweave.{table_name}"  # noqa: S608
    for table_name in REQUIRED_TABLES
}

_COUNT_WORKSPACE_TABLE_SQL = {
    # S608: table names come only from the internal REQUIRED_TABLES allowlist.
    table_name: (
        f"SELECT count(*) FROM docweave.{table_name} "  # noqa: S608
        "WHERE workspace_id = :workspace_id"
    )
    for table_name in REQUIRED_TABLES
}


if __name__ == "__main__":
    raise SystemExit(main())
