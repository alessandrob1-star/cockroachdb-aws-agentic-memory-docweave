from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, cast
from uuid import UUID

from sqlalchemy.engine import Engine

from docweave.memory_evidence_report import (
    EXPECTED_SIMPLE_SCHEMA,
    REQUIRED_TABLES,
    collect_memory_evidence_from_engine,
    main,
)


class _FakeScalarResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object | None:
        return self._value

    def scalar_one(self) -> object:
        return self._value


class _FakeRows:
    def __init__(self, rows: Iterable[tuple[object, ...]]) -> None:
        self._rows = tuple(rows)

    def __iter__(self) -> Iterable[tuple[object, ...]]:
        return iter(self._rows)


class _FakeConnection:
    def __init__(
        self,
        *,
        tables: set[str],
        revision: str | None = EXPECTED_SIMPLE_SCHEMA,
    ) -> None:
        self.tables = tables
        self.revision = revision
        self.counts: dict[str, int] = dict.fromkeys(tables, 0)
        self.workspace_filtered_tables: list[str] = []

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(
        self,
        statement: object,
        parameters: dict[str, object] | None = None,
    ) -> object:
        sql = str(statement)
        if "information_schema.tables" in sql:
            return _FakeRows((name,) for name in sorted(self.tables))
        if "SELECT count(*) FROM docweave." in sql:
            table_name = sql.split("docweave.", 1)[1].split(maxsplit=1)[0]
            if parameters and "workspace_id" in parameters:
                self.workspace_filtered_tables.append(table_name)
            return _FakeScalarResult(self.counts.get(table_name, 0))
        raise AssertionError(f"unexpected SQL: {sql}")


class _FakeEngine:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    def connect(self) -> _FakeConnection:
        return self.connection


def test_collects_read_only_memory_table_counts() -> None:
    connection = _FakeConnection(tables=set(REQUIRED_TABLES))
    connection.counts["proposals"] = 3
    connection.counts["human_decisions"] = 2
    connection.counts["file_history"] = 5

    report = collect_memory_evidence_from_engine(
        cast(Engine, _FakeEngine(connection)),
    )

    assert report.schema_ready
    counts = {row.table_name: row.row_count for row in report.table_counts}
    assert counts["proposals"] == 3
    assert counts["human_decisions"] == 2
    assert counts["file_history"] == 5


def test_reports_missing_memory_tables_without_claiming_readiness() -> None:
    tables = set(REQUIRED_TABLES)
    tables.remove("file_history")

    report = collect_memory_evidence_from_engine(
        cast(Engine, _FakeEngine(_FakeConnection(tables=tables))),
    )

    missing = [row for row in report.table_counts if not row.present]
    assert not report.schema_ready
    assert [row.table_name for row in missing] == ["file_history"]
    assert missing[0].row_count is None


def test_workspace_scope_filters_only_tables_with_workspace_id() -> None:
    connection = _FakeConnection(tables=set(REQUIRED_TABLES))
    workspace_id = UUID("11111111-1111-4111-8111-111111111111")

    collect_memory_evidence_from_engine(
        cast(Engine, _FakeEngine(connection)),
        workspace_id=workspace_id,
    )

    assert connection.workspace_filtered_tables == []


def test_main_fails_closed_without_database_url(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.delenv("DOCWEAVE_DATABASE_URL", raising=False)

    result = main([])

    output = capsys.readouterr().out
    assert result == 2
    assert (
        "memory_evidence: fail (database_url_missing:DOCWEAVE_DATABASE_URL)" in output
    )
    assert "password" not in output.casefold()


def test_json_report_contains_only_sanitized_fields(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    connection = _FakeConnection(tables=set(REQUIRED_TABLES))

    def fake_collect(*, workspace_id: UUID | None = None) -> object:
        return collect_memory_evidence_from_engine(
            cast(Engine, _FakeEngine(connection)),
            workspace_id=workspace_id,
        )

    monkeypatch.setattr(
        "docweave.memory_evidence_report.collect_memory_evidence",
        fake_collect,
    )

    result = main(["--json"])

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert result == 0
    assert payload["schema_ready"] is True
    assert payload["alembic_revision"] == EXPECTED_SIMPLE_SCHEMA
    assert "DOCWEAVE_DATABASE_URL" not in output
