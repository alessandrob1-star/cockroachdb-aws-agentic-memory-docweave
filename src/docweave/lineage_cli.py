"""Command-line entrypoint for durable file lineage memory."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from docweave.application_runtime import (
    ConfiguredFileLineageRuntime,
    RuntimeConfigurationError,
    build_configured_file_lineage_runtime,
)
from docweave.operations import FileLineageAction
from docweave.persistence import (
    FileLineageEventSnapshot,
    FileLineageHistoryQuery,
    PersistenceDisposition,
    PersistFileLineageEvent,
)


@dataclass(frozen=True, slots=True)
class FileLineageRecordInput:
    """Validated command fields supplied by a file-lineage boundary."""

    logical_document_key: str
    lineage_sequence: int
    idempotency_key: str
    action: FileLineageAction
    original_relative_path: str
    previous_relative_path: str
    next_relative_path: str
    status: str
    plan_fingerprint: str
    file_lineage_event_id: UUID | None = None
    operation_batch_id: UUID | None = None
    file_operation_id: UUID | None = None
    batch_item_id: str | None = None
    proposal_id: UUID | None = None
    occurred_at_utc: datetime | None = None
    source_digest_before: str | None = None
    destination_digest_after: str | None = None


@dataclass(frozen=True, slots=True)
class FileLineageRecordResult:
    """Sanitized durable file lineage write result."""

    file_lineage_event_id: UUID
    logical_document_key: str
    disposition: PersistenceDisposition


@dataclass(frozen=True, slots=True)
class FileLineageListInput:
    """Bounded list command fields for durable file lineage memory."""

    logical_document_key: str | None = None
    limit: int = 100


def record_file_lineage(
    command_input: FileLineageRecordInput,
) -> FileLineageRecordResult:
    """Persist one file lineage event through the configured runtime."""
    configured = build_configured_file_lineage_runtime()
    return _record_file_lineage_with_runtime(configured, command_input)


def _record_file_lineage_with_runtime(
    configured: ConfiguredFileLineageRuntime,
    command_input: FileLineageRecordInput,
) -> FileLineageRecordResult:
    event_id = command_input.file_lineage_event_id or uuid4()
    original_directory, original_filename = _split_relative_path(
        command_input.original_relative_path
    )
    previous_directory, previous_filename = _split_relative_path(
        command_input.previous_relative_path
    )
    next_directory, next_filename = _split_relative_path(
        command_input.next_relative_path
    )
    disposition = configured.repository.persist(
        PersistFileLineageEvent(
            workspace_id=configured.config.workspace_id,
            file_lineage_event_id=event_id,
            logical_document_key=command_input.logical_document_key,
            lineage_sequence=command_input.lineage_sequence,
            idempotency_key=command_input.idempotency_key,
            action=command_input.action,
            operation_batch_id=command_input.operation_batch_id,
            file_operation_id=command_input.file_operation_id,
            batch_item_id=command_input.batch_item_id,
            proposal_id=command_input.proposal_id,
            original_relative_path=command_input.original_relative_path,
            previous_relative_path=command_input.previous_relative_path,
            next_relative_path=command_input.next_relative_path,
            original_directory=original_directory,
            original_filename=original_filename,
            previous_directory=previous_directory,
            previous_filename=previous_filename,
            next_directory=next_directory,
            next_filename=next_filename,
            status=command_input.status,
            occurred_at_utc=command_input.occurred_at_utc,
            plan_fingerprint=command_input.plan_fingerprint,
            source_digest_before=command_input.source_digest_before,
            destination_digest_after=command_input.destination_digest_after,
        )
    )
    return FileLineageRecordResult(
        file_lineage_event_id=event_id,
        logical_document_key=command_input.logical_document_key,
        disposition=disposition,
    )


def list_file_lineage(
    command_input: FileLineageListInput,
) -> tuple[FileLineageEventSnapshot, ...]:
    """Load file lineage history through the configured runtime."""
    configured = build_configured_file_lineage_runtime()
    return _list_file_lineage_with_runtime(configured, command_input)


def _list_file_lineage_with_runtime(
    configured: ConfiguredFileLineageRuntime,
    command_input: FileLineageListInput,
) -> tuple[FileLineageEventSnapshot, ...]:
    return configured.repository.load_history(
        FileLineageHistoryQuery(
            workspace_id=configured.config.workspace_id,
            logical_document_key=command_input.logical_document_key,
            limit=command_input.limit,
        )
    )


def main(argv: list[str] | None = None) -> int:
    """Run durable file lineage commands with sanitized terminal output."""
    parser = argparse.ArgumentParser(
        description="Record or list DocWeave file lineage memory in CockroachDB."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--logical-document-key", required=True)
    record_parser.add_argument("--lineage-sequence", required=True, type=int)
    record_parser.add_argument("--idempotency-key", required=True)
    record_parser.add_argument(
        "--action",
        required=True,
        choices=[action.value for action in FileLineageAction],
    )
    record_parser.add_argument("--original-relative-path", required=True)
    record_parser.add_argument("--previous-relative-path", required=True)
    record_parser.add_argument("--next-relative-path", required=True)
    record_parser.add_argument(
        "--status",
        required=True,
        choices=["blocked", "succeeded", "failed", "verification_failed"],
    )
    record_parser.add_argument("--plan-fingerprint", required=True)
    record_parser.add_argument("--file-lineage-event-id", type=UUID)
    record_parser.add_argument("--operation-batch-id", type=UUID)
    record_parser.add_argument("--file-operation-id", type=UUID)
    record_parser.add_argument("--batch-item-id")
    record_parser.add_argument("--proposal-id", type=UUID)
    record_parser.add_argument("--occurred-at-utc", type=_parse_utc_datetime)
    record_parser.add_argument("--source-digest-before")
    record_parser.add_argument("--destination-digest-after")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--logical-document-key")
    list_parser.add_argument("--limit", type=int, default=100)

    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            result = record_file_lineage(
                FileLineageRecordInput(
                    logical_document_key=args.logical_document_key,
                    lineage_sequence=args.lineage_sequence,
                    idempotency_key=args.idempotency_key,
                    action=FileLineageAction(args.action),
                    original_relative_path=args.original_relative_path,
                    previous_relative_path=args.previous_relative_path,
                    next_relative_path=args.next_relative_path,
                    status=args.status,
                    plan_fingerprint=args.plan_fingerprint,
                    file_lineage_event_id=args.file_lineage_event_id,
                    operation_batch_id=args.operation_batch_id,
                    file_operation_id=args.file_operation_id,
                    batch_item_id=args.batch_item_id,
                    proposal_id=args.proposal_id,
                    occurred_at_utc=args.occurred_at_utc,
                    source_digest_before=args.source_digest_before,
                    destination_digest_after=args.destination_digest_after,
                )
            )
            print(f"File lineage memory: {result.disposition.value}")
            print(f"Lineage event id: {result.file_lineage_event_id}")
            print(f"Logical document: {result.logical_document_key}")
            return 0

        rows = list_file_lineage(
            FileLineageListInput(
                logical_document_key=args.logical_document_key,
                limit=args.limit,
            )
        )
        _print_history(rows)
        return 0
    except RuntimeConfigurationError as error:
        print(
            f"File lineage failed: {error.code.value}:{error.variable_name}",
            file=sys.stderr,
        )
        return 2
    except Exception as error:
        print(
            f"File lineage failed: {type(error).__name__}",
            file=sys.stderr,
        )
        return 3


def _print_history(rows: tuple[FileLineageEventSnapshot, ...]) -> None:
    print(f"File lineage rows: {len(rows)}")
    for row in rows:
        occurred = (
            "not-recorded"
            if row.occurred_at_utc is None
            else row.occurred_at_utc.isoformat()
        )
        print(
            "\t".join(
                (
                    row.logical_document_key,
                    str(row.lineage_sequence),
                    row.action.value,
                    row.status,
                    row.previous_relative_path,
                    row.next_relative_path,
                    occurred,
                )
            )
        )


def _split_relative_path(relative_path: str) -> tuple[str, str]:
    path = PurePosixPath(relative_path)
    filename = path.name
    directory = path.parent.as_posix()
    if directory == ".":
        directory = ""
    return directory, filename


def _parse_utc_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an ISO-8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("datetime must include a timezone")
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
