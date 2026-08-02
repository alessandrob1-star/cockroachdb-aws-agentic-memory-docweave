from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from docweave import lineage_cli
from docweave.application_runtime import (
    ConfiguredFileLineageRuntime,
    RuntimeConfigurationError,
    RuntimeConfigurationErrorCode,
    RuntimeEnvironmentConfig,
)
from docweave.lineage_cli import (
    FileLineageListInput,
    FileLineageRecordInput,
    _list_file_lineage_with_runtime,
    _record_file_lineage_with_runtime,
)
from docweave.operations import FileLineageAction
from docweave.persistence import (
    FileLineageEventSnapshot,
    FileLineageHistoryQuery,
    PersistenceDisposition,
    PersistFileLineageEvent,
)

WORKSPACE_ID = UUID("11111111-1111-4111-8111-111111111111")
TAXONOMY_VERSION_ID = UUID("22222222-2222-4222-8222-222222222222")
ACTOR_ID = UUID("33333333-3333-4333-8333-333333333333")
LINEAGE_ID = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 8, 3, 9, 30, tzinfo=UTC)
PLAN_FINGERPRINT = "ab" * 32


class FakeLineageRepository:
    def __init__(self) -> None:
        self.commands: list[PersistFileLineageEvent] = []
        self.queries: list[FileLineageHistoryQuery] = []
        self.rows: tuple[FileLineageEventSnapshot, ...] = ()

    def persist(self, command: PersistFileLineageEvent) -> PersistenceDisposition:
        self.commands.append(command)
        return PersistenceDisposition.APPLIED

    def load_history(
        self,
        query: FileLineageHistoryQuery,
    ) -> tuple[FileLineageEventSnapshot, ...]:
        self.queries.append(query)
        return self.rows


def _configured(repository: FakeLineageRepository) -> ConfiguredFileLineageRuntime:
    return cast(
        ConfiguredFileLineageRuntime,
        SimpleNamespace(
            config=RuntimeEnvironmentConfig(
                database_url="cockroachdb://user:secret@example.test/docweave",
                workspace_id=WORKSPACE_ID,
                taxonomy_version_id=TAXONOMY_VERSION_ID,
                approved_by_actor_id=ACTOR_ID,
            ),
            repository=repository,
        ),
    )


def test_record_file_lineage_binds_cli_paths_to_durable_command() -> None:
    repository = FakeLineageRepository()

    result = _record_file_lineage_with_runtime(
        _configured(repository),
        FileLineageRecordInput(
            file_lineage_event_id=LINEAGE_ID,
            logical_document_key="sha256:doc-001",
            lineage_sequence=2,
            idempotency_key="lineage:doc-001:2",
            action=FileLineageAction.RENAME_AND_MOVE,
            original_relative_path="incoming/scan.pdf",
            previous_relative_path="incoming/scan.pdf",
            next_relative_path="DocWeave Organized/Invoices/invoice.pdf",
            status="succeeded",
            plan_fingerprint=PLAN_FINGERPRINT,
            occurred_at_utc=NOW,
            source_digest_before=PLAN_FINGERPRINT,
            destination_digest_after=PLAN_FINGERPRINT,
        ),
    )

    assert result.disposition is PersistenceDisposition.APPLIED
    assert result.file_lineage_event_id == LINEAGE_ID
    command = repository.commands[0]
    assert command.workspace_id == WORKSPACE_ID
    assert command.logical_document_key == "sha256:doc-001"
    assert command.original_directory == "incoming"
    assert command.original_filename == "scan.pdf"
    assert command.previous_directory == "incoming"
    assert command.next_directory == "DocWeave Organized/Invoices"
    assert command.next_filename == "invoice.pdf"
    assert command.plan_fingerprint == PLAN_FINGERPRINT


def test_list_file_lineage_uses_workspace_scoped_query() -> None:
    repository = FakeLineageRepository()
    repository.rows = (
        FileLineageEventSnapshot(
            file_lineage_event_id=LINEAGE_ID,
            workspace_id=WORKSPACE_ID,
            logical_document_key="sha256:doc-001",
            lineage_sequence=1,
            action=FileLineageAction.RENAME,
            original_relative_path="incoming/a.pdf",
            previous_relative_path="incoming/a.pdf",
            next_relative_path="incoming/b.pdf",
            original_directory="incoming",
            original_filename="a.pdf",
            previous_directory="incoming",
            previous_filename="a.pdf",
            next_directory="incoming",
            next_filename="b.pdf",
            status="succeeded",
            occurred_at_utc=NOW,
        ),
    )

    rows = _list_file_lineage_with_runtime(
        _configured(repository),
        FileLineageListInput(logical_document_key="sha256:doc-001", limit=20),
    )

    assert rows == repository.rows
    assert repository.queries == [
        FileLineageHistoryQuery(
            workspace_id=WORKSPACE_ID,
            logical_document_key="sha256:doc-001",
            limit=20,
        )
    ]


def test_lineage_main_prints_sanitized_record_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_record_file_lineage(
        command_input: lineage_cli.FileLineageRecordInput,
    ) -> lineage_cli.FileLineageRecordResult:
        assert command_input.action is FileLineageAction.RENAME
        assert command_input.plan_fingerprint == PLAN_FINGERPRINT
        return lineage_cli.FileLineageRecordResult(
            file_lineage_event_id=LINEAGE_ID,
            logical_document_key="sha256:doc-001",
            disposition=PersistenceDisposition.IDEMPOTENT_REPLAY,
        )

    monkeypatch.setattr(lineage_cli, "record_file_lineage", fake_record_file_lineage)

    result = lineage_cli.main(
        [
            "record",
            "--logical-document-key",
            "sha256:doc-001",
            "--lineage-sequence",
            "1",
            "--idempotency-key",
            "lineage:doc-001:1",
            "--action",
            "rename",
            "--original-relative-path",
            "incoming/a.pdf",
            "--previous-relative-path",
            "incoming/a.pdf",
            "--next-relative-path",
            "incoming/b.pdf",
            "--status",
            "succeeded",
            "--plan-fingerprint",
            PLAN_FINGERPRINT,
            "--file-lineage-event-id",
            str(LINEAGE_ID),
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "File lineage memory: idempotent_replay" in captured.out
    assert "secret" not in captured.out
    assert captured.err == ""


def test_lineage_main_prints_sanitized_history(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_list_file_lineage(
        command_input: lineage_cli.FileLineageListInput,
    ) -> tuple[FileLineageEventSnapshot, ...]:
        assert command_input.limit == 10
        return (
            FileLineageEventSnapshot(
                file_lineage_event_id=LINEAGE_ID,
                workspace_id=WORKSPACE_ID,
                logical_document_key="sha256:doc-001",
                lineage_sequence=1,
                action=FileLineageAction.RENAME,
                original_relative_path="incoming/a.pdf",
                previous_relative_path="incoming/a.pdf",
                next_relative_path="incoming/b.pdf",
                original_directory="incoming",
                original_filename="a.pdf",
                previous_directory="incoming",
                previous_filename="a.pdf",
                next_directory="incoming",
                next_filename="b.pdf",
                status="succeeded",
                occurred_at_utc=NOW,
            ),
        )

    monkeypatch.setattr(lineage_cli, "list_file_lineage", fake_list_file_lineage)

    result = lineage_cli.main(["list", "--limit", "10"])

    captured = capsys.readouterr()
    assert result == 0
    assert "File lineage rows: 1" in captured.out
    assert "incoming/a.pdf\tincoming/b.pdf" in captured.out
    assert "secret" not in captured.out


def test_lineage_main_reports_configuration_errors_without_secret_values(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_record_file_lineage(
        _: lineage_cli.FileLineageRecordInput,
    ) -> lineage_cli.FileLineageRecordResult:
        raise RuntimeConfigurationError(
            RuntimeConfigurationErrorCode.DATABASE_URL_MISSING,
            variable_name="DOCWEAVE_DATABASE_URL",
        )

    monkeypatch.setattr(lineage_cli, "record_file_lineage", fail_record_file_lineage)

    result = lineage_cli.main(
        [
            "record",
            "--logical-document-key",
            "sha256:doc-001",
            "--lineage-sequence",
            "1",
            "--idempotency-key",
            "lineage:doc-001:1",
            "--action",
            "rename",
            "--original-relative-path",
            "incoming/a.pdf",
            "--previous-relative-path",
            "incoming/a.pdf",
            "--next-relative-path",
            "incoming/b.pdf",
            "--status",
            "succeeded",
            "--plan-fingerprint",
            PLAN_FINGERPRINT,
        ]
    )

    captured = capsys.readouterr()
    assert result == 2
    assert "database_url_missing:DOCWEAVE_DATABASE_URL" in captured.err
    assert "secret" not in captured.err


def test_lineage_main_rejects_bad_rows_without_detail_leakage(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_list_file_lineage(
        _: lineage_cli.FileLineageListInput,
    ) -> tuple[FileLineageEventSnapshot, ...]:
        raise ValueError("secret row detail")

    monkeypatch.setattr(lineage_cli, "list_file_lineage", fail_list_file_lineage)

    result = lineage_cli.main(["list"])

    captured = capsys.readouterr()
    assert result == 3
    assert "File lineage failed: ValueError" in captured.err
    assert "secret row detail" not in captured.err
