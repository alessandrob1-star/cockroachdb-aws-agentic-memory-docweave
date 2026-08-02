from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy.engine import Engine

from docweave.live_memory_validation import (
    EXPECTED_HEAD,
    REQUIRED_TABLES,
    collect_live_schema_evidence_from_engine,
    collect_offline_evidence,
    main,
)


class _FakeResult:
    def __init__(self, rows: Iterable[tuple[object, ...]]) -> None:
        self._rows = tuple(rows)

    def __iter__(self) -> Iterable[tuple[object, ...]]:
        return iter(self._rows)

    def scalar_one_or_none(self) -> object | None:
        if not self._rows:
            return None
        return self._rows[0][0]


class _FakeConnection:
    def __init__(self, *, revision: str | None, tables: set[str]) -> None:
        self._revision = revision
        self._tables = tables

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, statement: object) -> _FakeResult:
        sql = str(statement)
        if "alembic_version" in sql:
            return (
                _FakeResult(())
                if self._revision is None
                else _FakeResult(((self._revision,),))
            )
        if "information_schema.tables" in sql:
            return _FakeResult((name,) for name in sorted(self._tables))
        raise AssertionError(f"unexpected SQL: {sql}")


class _FakeEngine:
    def __init__(self, *, revision: str | None, tables: set[str]) -> None:
        self._revision = revision
        self._tables = tables

    def connect(self) -> _FakeConnection:
        return _FakeConnection(revision=self._revision, tables=self._tables)


def test_collects_sanitized_offline_memory_migration_evidence() -> None:
    evidence = collect_offline_evidence()

    assert evidence.succeeded
    assert evidence.head_revision == EXPECTED_HEAD
    assert evidence.required_tables_present == evidence.required_tables_total
    assert len(evidence.sql_sha256) == 64
    assert evidence.sql_characters > 10_000
    assert not evidence.contains_transaction_boundary
    assert not evidence.contains_connection_secret_marker


def test_live_schema_evidence_reports_expected_memory_tables() -> None:
    evidence = collect_live_schema_evidence_from_engine(
        cast(
            Engine,
            _FakeEngine(revision=EXPECTED_HEAD, tables=set(REQUIRED_TABLES)),
        )
    )

    assert evidence.succeeded
    assert evidence.alembic_revision == EXPECTED_HEAD
    assert evidence.required_tables_present == len(REQUIRED_TABLES)
    assert evidence.missing_tables == ()


def test_live_schema_evidence_reports_missing_tables_without_secret_values() -> None:
    tables = set(REQUIRED_TABLES)
    tables.remove("file_lineage_events")

    evidence = collect_live_schema_evidence_from_engine(
        cast(Engine, _FakeEngine(revision="0003_review_decision_memory", tables=tables))
    )

    assert not evidence.succeeded
    assert evidence.alembic_revision == "0003_review_decision_memory"
    assert evidence.missing_tables == ("file_lineage_events",)


def test_main_skips_live_work_by_default(capsys: Any) -> None:
    result = main([])

    output = capsys.readouterr().out
    assert result == 0
    assert "migration_head: ok" in output
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
