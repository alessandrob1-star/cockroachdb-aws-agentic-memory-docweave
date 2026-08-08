from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from sqlalchemy.engine import Engine

from docweave.live_memory_validation import (
    EXPECTED_HEAD,
    REQUIRED_JUDGED_TABLES,
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

    def scalar_one_or_none(self) -> object | None:
        if not self._rows:
            return None
        return self._rows[0][0]


class _FakeConnection:
    def __init__(
        self,
        *,
        revision: str | None,
        tables: set[str],
        views: set[str],
        judged_tables: set[str],
    ) -> None:
        self._revision = revision
        self._tables = tables
        self._views = views
        self._judged_tables = judged_tables

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
        if "information_schema.tables" in sql and "table_type = 'VIEW'" in sql:
            return _FakeResult((name,) for name in sorted(self._views))
        if "information_schema.tables" in sql and "docweave_judged" in sql:
            return _FakeResult((name,) for name in sorted(self._judged_tables))
        if "information_schema.tables" in sql and "table_type = 'BASE TABLE'" in sql:
            return _FakeResult((name,) for name in sorted(self._tables))
        raise AssertionError(f"unexpected SQL: {sql}")


class _FakeEngine:
    def __init__(
        self,
        *,
        revision: str | None,
        tables: set[str],
        views: set[str] | None = None,
        judged_tables: set[str] | None = None,
    ) -> None:
        self._revision = revision
        self._tables = tables
        self._views = views if views is not None else set(REQUIRED_VIEWS)
        self._judged_tables = (
            judged_tables if judged_tables is not None else set(REQUIRED_JUDGED_TABLES)
        )

    def connect(self) -> _FakeConnection:
        return _FakeConnection(
            revision=self._revision,
            tables=self._tables,
            views=self._views,
            judged_tables=self._judged_tables,
        )


def test_collects_sanitized_offline_memory_migration_evidence() -> None:
    evidence = collect_offline_evidence()

    assert evidence.succeeded
    assert evidence.head_revision == EXPECTED_HEAD
    assert evidence.required_tables_present == evidence.required_tables_total
    assert evidence.required_views_present == evidence.required_views_total
    assert evidence.required_judged_tables_present == (
        evidence.required_judged_tables_total
    )
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
    assert evidence.required_views_present == len(REQUIRED_VIEWS)
    assert evidence.required_judged_tables_present == len(REQUIRED_JUDGED_TABLES)
    assert evidence.missing_tables == ()
    assert evidence.missing_views == ()
    assert evidence.missing_judged_tables == ()


def test_live_schema_evidence_reports_missing_tables_without_secret_values() -> None:
    tables = set(REQUIRED_TABLES)
    tables.remove("file_lineage_events")

    evidence = collect_live_schema_evidence_from_engine(
        cast(Engine, _FakeEngine(revision="0003_review_decision_memory", tables=tables))
    )

    assert not evidence.succeeded
    assert evidence.alembic_revision == "0003_review_decision_memory"
    assert evidence.missing_tables == ("file_lineage_events",)


def test_live_schema_evidence_reports_missing_readable_path_history_view() -> None:
    evidence = collect_live_schema_evidence_from_engine(
        cast(
            Engine,
            _FakeEngine(
                revision=EXPECTED_HEAD, tables=set(REQUIRED_TABLES), views=set()
            ),
        )
    )

    assert not evidence.succeeded
    assert evidence.missing_tables == ()
    assert evidence.missing_views == ("file_path_history",)


def test_live_schema_evidence_reports_missing_judged_memory_tables() -> None:
    evidence = collect_live_schema_evidence_from_engine(
        cast(
            Engine,
            _FakeEngine(
                revision=EXPECTED_HEAD,
                tables=set(REQUIRED_TABLES),
                judged_tables={"documents"},
            ),
        )
    )

    assert not evidence.succeeded
    assert evidence.missing_tables == ()
    assert "file_history" in evidence.missing_judged_tables


def test_main_skips_live_work_by_default(capsys: Any) -> None:
    result = main([])

    output = capsys.readouterr().out
    assert result == 0
    assert "migration_head: ok" in output
    assert "offline_required_views: 1/1" in output
    assert "offline_required_judged_tables: 6/6" in output
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
