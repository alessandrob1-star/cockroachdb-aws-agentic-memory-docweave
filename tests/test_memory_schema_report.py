from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy.engine import Engine

from docweave.live_memory_validation import EXPECTED_HEAD
from docweave.memory_schema_report import (
    collect_memory_schema_from_engine,
    main,
)


class _FakeScalarResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object | None:
        return self._value


class _FakeRows:
    def __init__(self, rows: Iterable[tuple[object, ...]]) -> None:
        self._rows = tuple(rows)

    def __iter__(self) -> Iterable[tuple[object, ...]]:
        return iter(self._rows)


class _FakeConnection:
    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: object) -> object:
        sql = str(statement)
        if "public.alembic_version" in sql:
            return _FakeScalarResult(EXPECTED_HEAD)
        if "information_schema.tables" in sql:
            return _FakeRows((("documents",), ("proposals",)))
        if "information_schema.columns" in sql:
            return _FakeRows(
                (
                    ("documents", "document_id", "UUID", "NO"),
                    ("documents", "workspace_id", "UUID", "NO"),
                    ("proposals", "proposal_id", "UUID", "NO"),
                    ("proposals", "document_id", "UUID", "NO"),
                )
            )
        if "PRIMARY KEY" in sql:
            return _FakeRows(
                (
                    ("documents", "document_id", 1),
                    ("proposals", "proposal_id", 1),
                )
            )
        if "FOREIGN KEY" in sql:
            return _FakeRows(
                (
                    (
                        "proposals",
                        "document_id",
                        "documents",
                        "document_id",
                        "fk_proposals_document",
                    ),
                )
            )
        raise AssertionError(f"unexpected SQL: {sql}")


class _FakeEngine:
    def connect(self) -> _FakeConnection:
        return _FakeConnection()


def test_collects_cockroach_memory_schema_shape() -> None:
    report = collect_memory_schema_from_engine(cast(Engine, _FakeEngine()))

    assert report.alembic_revision == EXPECTED_HEAD
    assert [table.table_name for table in report.tables] == [
        "documents",
        "proposals",
    ]
    proposals = report.tables[1]
    assert proposals.primary_key_columns == ("proposal_id",)
    assert proposals.foreign_keys[0].column_name == "document_id"
    assert proposals.foreign_keys[0].foreign_table_name == "documents"


def test_main_fails_closed_without_database_url(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.delenv("DOCWEAVE_DATABASE_URL", raising=False)

    result = main([])

    output = capsys.readouterr().out
    assert result == 2
    assert "memory_schema: fail (database_url_missing:DOCWEAVE_DATABASE_URL)" in output
    assert "password" not in output.casefold()


def test_json_output_is_sanitized(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(
        "docweave.memory_schema_report.collect_memory_schema",
        lambda: collect_memory_schema_from_engine(cast(Engine, _FakeEngine())),
    )

    result = main(["--json"])

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert result == 0
    assert payload["alembic_revision"] == EXPECTED_HEAD
    assert payload["tables"][1]["foreign_keys"][0]["constraint_name"] == (
        "fk_proposals_document"
    )
    assert "DOCWEAVE_DATABASE_URL" not in output
