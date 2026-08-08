from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy.engine import Connection
from sqlalchemy.sql import Executable

from docweave.persistence import (
    CockroachSimpleMemoryRepository,
    PersistenceDisposition,
    PersistSimpleAnalysis,
    TransactionRun,
)
from docweave.persistence.simple_memory_repository import split_relative_path

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000001")
RUN_ID = UUID("00000000-0000-4000-8000-000000000002")
PROPOSAL_ID = UUID("00000000-0000-4000-8000-000000000003")
DIGEST = bytes.fromhex("ab" * 32)


class FakeResult:
    def __init__(self, *, scalar: object | None = None) -> None:
        self._scalar = scalar

    def scalar_one(self) -> object:
        if self._scalar is None:
            raise AssertionError("expected scalar")
        return self._scalar

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class FakeConnection:
    def __init__(self, responses: Sequence[FakeResult]) -> None:
        self.responses = list(responses)
        self.calls: list[
            tuple[str, Mapping[str, object] | Sequence[Mapping[str, object]] | None]
        ] = []

    def execute(
        self,
        statement: Executable,
        parameters: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
    ) -> FakeResult:
        self.calls.append((str(statement), parameters))
        if not self.responses:
            raise AssertionError("unexpected database call")
        return self.responses.pop(0)


class FakeTransactionRunner:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.run_count = 0

    def run[T](self, work: Callable[[Connection], T]) -> TransactionRun[T]:
        self.run_count += 1
        return TransactionRun(
            value=work(cast(Connection, self.connection)),
            attempts=1,
        )


def command() -> PersistSimpleAnalysis:
    return PersistSimpleAnalysis(
        workspace_label="demo-workspace",
        document_id=DOCUMENT_ID,
        agent_run_id=RUN_ID,
        proposal_id=PROPOSAL_ID,
        original_directory="incoming",
        original_filename="scan_000184.pdf",
        content_sha256=DIGEST,
        page_count=2,
        provider="amazon_bedrock",
        model_id="eu.amazon.nova-2-lite-v1:0",
        task="classify_and_propose_file_organization",
        status="succeeded",
        started_at_utc=NOW,
        completed_at_utc=NOW,
        input_sha256=DIGEST,
        output_json='{"proposed_class":"invoice"}',
        summary="Invoice number and total are explicit.",
        proposed_category="invoice",
        proposed_directory="DocWeave Organized/Invoices",
        proposed_filename="invoice-inv-17.pdf",
        confidence=Decimal("0.8000"),
        evidence_summary="Page 1: INVOICE INV-17",
    )


def repository(
    responses: Sequence[FakeResult],
) -> tuple[CockroachSimpleMemoryRepository, FakeTransactionRunner]:
    runner = FakeTransactionRunner(FakeConnection(responses))
    return CockroachSimpleMemoryRepository(runner), runner


def test_persists_document_run_and_proposal_to_simple_memory() -> None:
    adapter, runner = repository(
        [
            FakeResult(scalar=DOCUMENT_ID),
            FakeResult(scalar=RUN_ID),
            FakeResult(scalar=PROPOSAL_ID),
        ]
    )

    result = adapter.persist_analysis(command())

    assert result is PersistenceDisposition.APPLIED
    assert runner.run_count == 1
    statements = "\n".join(statement for statement, _ in runner.connection.calls)
    assert "INSERT INTO docweave.documents" in statements
    assert "INSERT INTO docweave.agent_runs" in statements
    assert "INSERT INTO docweave.proposals" in statements
    first_parameters = cast(Mapping[str, object], runner.connection.calls[0][1])
    assert first_parameters["original_filename"] == "scan_000184.pdf"
    assert first_parameters["content_sha256"] == DIGEST
    assert "INVOICE INV-17" not in runner.connection.calls[2][0]


def test_replays_existing_proposal_without_duplicate_child_rows() -> None:
    adapter, runner = repository(
        [
            FakeResult(scalar=DOCUMENT_ID),
            FakeResult(scalar=None),
            FakeResult(scalar=None),
            FakeResult(scalar=PROPOSAL_ID),
        ]
    )

    result = adapter.persist_analysis(command())

    assert result is PersistenceDisposition.IDEMPOTENT_REPLAY
    assert len(runner.connection.calls) == 4


def test_splits_root_and_nested_paths_for_readable_history() -> None:
    assert split_relative_path("scan.pdf") == (".", "scan.pdf")
    assert split_relative_path("incoming/scan.pdf") == ("incoming", "scan.pdf")
