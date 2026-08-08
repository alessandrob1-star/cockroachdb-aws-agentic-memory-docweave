from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy.engine import Engine

from docweave.live_memory_validation import (
    EXPECTED_HEAD,
    REQUIRED_TABLES,
    REQUIRED_VIEWS,
    collect_live_schema_evidence_from_engine,
    collect_offline_evidence,
    main,
)


class _FakeResult:
    def __init__(self, rows: Iterable[tuple[object, ...]]) -> None:
        self._rows = tuple(rows)

    def __iter__(self) -> Iterable[tuple[object, ...]]:
        return iter(self._rows)


class _FakeConnection:
    def __init__(self, *, tables: set[str], views: set[str]) -> None:
        self._tables = tables
        self._views = views

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: object) -> _FakeResult:
        sql = str(statement)
        if "information_schema.tables" in sql and "table_type = 'VIEW'" in sql:
            return _FakeResult((name,) for name in sorted(self._views))
        if "information_schema.tables" in sql and "table_type = 'BASE TABLE'" in sql:
            return _FakeResult((name,) for name in sorted(self._tables))
        raise AssertionError(f"unexpected SQL: {sql}")


class _FakeEngine:
    def __init__(
        self,
        *,
        tables: set[str],
        views: set[str] | None = None,
    ) -> None:
        self._tables = tables
        self._views = views if views is not None else set(REQUIRED_VIEWS)

    def connect(self) -> _FakeConnection:
        return _FakeConnection(tables=self._tables, views=self._views)


def test_collects_sanitized_offline_simple_schema_evidence() -> None:
    evidence = collect_offline_evidence()

    assert evidence.succeeded
    assert evidence.head_revision == EXPECTED_HEAD
    assert evidence.required_tables_present == evidence.required_tables_total
    assert evidence.required_views_present == 0
    assert evidence.required_views_total == 0
    assert len(evidence.sql_sha256) == 64
    assert evidence.sql_characters > 1_000
    assert not evidence.contains_transaction_boundary
    assert not evidence.contains_connection_secret_marker


def test_live_schema_evidence_reports_expected_simple_tables() -> None:
    evidence = collect_live_schema_evidence_from_engine(
        cast(Engine, _FakeEngine(tables=set(REQUIRED_TABLES)))
    )

    assert evidence.succeeded
    assert evidence.alembic_revision == EXPECTED_HEAD
    assert evidence.required_tables_present == len(REQUIRED_TABLES)
    assert evidence.required_views_present == 0
    assert evidence.missing_tables == ()
    assert evidence.missing_views == ()


def test_live_schema_evidence_reports_missing_table_without_secret_values() -> None:
    tables = set(REQUIRED_TABLES)
    tables.remove("file_history")

    evidence = collect_live_schema_evidence_from_engine(
        cast(Engine, _FakeEngine(tables=tables))
    )

    assert not evidence.succeeded
    assert evidence.alembic_revision == EXPECTED_HEAD
    assert evidence.missing_tables == ("file_history",)


def test_main_skips_live_work_by_default(capsys: Any) -> None:
    result = main([])

    output = capsys.readouterr().out
    assert result == 0
    assert "migration_head: ok" in output
    assert "offline_required_views: 0/0" in output
    assert "live_schema: skip (not_requested)" in output
    assert "DOCWEAVE_DATABASE_URL" not in output


def test_main_fails_closed_for_live_inspection_without_database_url(
    monkeypatch: Any,
    capsys: Any,
) -> None:
    monkeypatch.delenv("DOCWEAVE_DATABASE_URL", raising=False)

    result = main(["--inspect-live"])

    output = capsys.readouterr().out
    assert result == 2
    assert "live_schema: fail (database_url_missing:DOCWEAVE_DATABASE_URL)" in output
    assert "password" not in output.casefold()
