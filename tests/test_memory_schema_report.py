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
            return _FakeRows(
                (
                    ("docweave_judged", "documents", "BASE TABLE"),
                    ("docweave_judged", "file_history", "BASE TABLE"),
                    ("docweave_judged", "proposals", "BASE TABLE"),
                    ("docweave", "file_path_history", "VIEW"),
                )
            )
        if "information_schema.columns" in sql:
            return _FakeRows(
                (
                    ("docweave_judged", "documents", "document_id", "UUID", "NO"),
                    (
                        "docweave_judged",
                        "documents",
                        "original_filename",
                        "STRING",
                        "NO",
                    ),
                    (
                        "docweave_judged",
                        "file_history",
                        "previous_directory",
                        "STRING",
                        "NO",
                    ),
                    (
                        "docweave_judged",
                        "file_history",
                        "next_filename",
                        "STRING",
                        "NO",
                    ),
                    ("docweave_judged", "proposals", "proposal_id", "UUID", "NO"),
                    ("docweave_judged", "proposals", "document_id", "UUID", "NO"),
                    (
                        "docweave",
                        "file_path_history",
                        "previous_filename",
                        "VARCHAR",
                        "YES",
                    ),
                )
            )
        if "PRIMARY KEY" in sql:
            return _FakeRows(
                (
                    ("docweave_judged", "documents", "document_id", 1),
                    ("docweave_judged", "proposals", "proposal_id", 1),
                )
            )
        if "FOREIGN KEY" in sql:
            return _FakeRows(
                (
                    (
                        "docweave_judged",
                        "proposals",
                        "document_id",
                        "docweave_judged",
                        "documents",
                        "document_id",
                        "fk_judged_proposals_document",
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
    assert [(table.schema_name, table.table_name) for table in report.tables] == [
        ("docweave_judged", "documents"),
        ("docweave_judged", "file_history"),
        ("docweave_judged", "proposals"),
        ("docweave", "file_path_history"),
    ]
    assert report.tables[0].schema_name == "docweave_judged"
    assert report.tables[3].object_type == "view"
    assert report.tables[3].primary_key_columns == ()
    proposals = report.tables[2]
    assert proposals.primary_key_columns == ("proposal_id",)
    assert proposals.foreign_keys[0].column_name == "document_id"
    assert proposals.foreign_keys[0].foreign_table_schema == "docweave_judged"
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
    assert payload["tables"][0]["schema_name"] == "docweave_judged"
    assert payload["tables"][3]["object_type"] == "view"
    assert payload["tables"][2]["foreign_keys"][0]["constraint_name"] == (
        "fk_judged_proposals_document"
    )
    assert "DOCWEAVE_DATABASE_URL" not in output


def test_default_output_is_object_explorer_style(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(
        "docweave.memory_schema_report.collect_memory_schema",
        lambda: collect_memory_schema_from_engine(cast(Engine, _FakeEngine())),
    )

    result = main([])

    output = capsys.readouterr().out
    assert result == 0
    assert "DocWeave CockroachDB Object Explorer" in output
    assert "Database: docweave" in output
    assert "Schemas: docweave_judged, docweave" in output
    assert "[table] docweave_judged.documents" in output
    assert "Views: 1" in output
    assert "[view] docweave.file_path_history" in output
    assert "document_id: UUID NOT NULL PK" in output
    assert "document_id -> docweave_judged.documents.document_id" in output
    assert "DOCWEAVE_DATABASE_URL" not in output


def test_flat_output_remains_available(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(
        "docweave.memory_schema_report.collect_memory_schema",
        lambda: collect_memory_schema_from_engine(cast(Engine, _FakeEngine())),
    )

    result = main(["--flat"])

    output = capsys.readouterr().out
    assert result == 0
    assert "memory_schema_revision:" in output
    assert "memory_schema_views: 1" in output
    assert "table docweave_judged.documents" in output
    assert "view docweave.file_path_history" in output
