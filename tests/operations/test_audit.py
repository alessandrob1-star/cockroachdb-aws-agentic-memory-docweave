from datetime import UTC, datetime, timedelta

import pytest

from docweave.operations import (
    AppendOnlyAuditTrail,
    AuditActorType,
    AuditEvent,
    AuditEventType,
)


def audit_event(
    *,
    event_id: str = "event-001",
    occurred_at_utc: datetime | None = None,
    source_relative_path: str | None = "inbox/invoice.pdf",
    reason: str | None = "planned",
) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        workspace_id="workspace-001",
        batch_id="batch-001",
        batch_item_id="item-001",
        event_type=AuditEventType.ITEM_PLANNED,
        actor_type=AuditActorType.SYSTEM,
        actor_id="local-core",
        occurred_at_utc=occurred_at_utc or datetime(2026, 7, 24, 8, 0),
        correlation_id="correlation-001",
        source_relative_path=source_relative_path,
        destination_relative_path="organized/invoice.pdf",
        reason=reason,
    )


def test_normalizes_timestamp_and_returns_immutable_append_order() -> None:
    trail = AppendOnlyAuditTrail()
    first = audit_event()
    second = audit_event(
        event_id="event-002",
        occurred_at_utc=first.occurred_at_utc + timedelta(seconds=1),
    )

    trail.append(first)
    trail.append(second)

    assert trail.events == (first, second)
    assert trail.events[0].occurred_at_utc.tzinfo is UTC


def test_rejects_duplicate_event_identifier() -> None:
    trail = AppendOnlyAuditTrail()
    event = audit_event()
    trail.append(event)

    with pytest.raises(ValueError, match="event_id must be unique"):
        trail.append(event)


def test_rejects_event_time_regression() -> None:
    trail = AppendOnlyAuditTrail()
    current = audit_event()
    trail.append(current)

    with pytest.raises(ValueError, match="must not move backward"):
        trail.append(
            audit_event(
                event_id="event-002",
                occurred_at_utc=current.occurred_at_utc - timedelta(seconds=1),
            )
        )


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"event_id": " "}, "event_id must not be empty"),
        ({"workspace_id": " "}, "workspace_id must not be empty"),
        ({"batch_id": " "}, "batch_id must not be empty"),
        ({"actor_id": " "}, "actor_id must not be empty"),
        ({"correlation_id": " "}, "correlation_id must not be empty"),
    ],
)
def test_rejects_blank_required_identifiers(
    replacement: dict[str, str],
    message: str,
) -> None:
    values = {
        "event_id": "event-001",
        "workspace_id": "workspace-001",
        "batch_id": "batch-001",
        "actor_id": "local-core",
        "correlation_id": "correlation-001",
    }
    values.update(replacement)

    with pytest.raises(ValueError, match=message):
        AuditEvent(
            event_id=values["event_id"],
            workspace_id=values["workspace_id"],
            batch_id=values["batch_id"],
            event_type=AuditEventType.BATCH_CREATED,
            actor_type=AuditActorType.SYSTEM,
            actor_id=values["actor_id"],
            occurred_at_utc=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
            correlation_id=values["correlation_id"],
        )


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/private/invoice.pdf",
        "../invoice.pdf",
        r"inbox\..\invoice.pdf",
        "inbox//invoice.pdf",
    ],
)
def test_rejects_non_relative_or_traversing_audit_paths(path: str) -> None:
    with pytest.raises(ValueError, match="normalized relative path"):
        audit_event(source_relative_path=path)


@pytest.mark.parametrize(
    ("field_name", "value", "maximum"),
    [
        ("reason", "x" * 257, 256),
        ("error_class", "x" * 129, 128),
        ("error_category", "x" * 129, 128),
    ],
)
def test_rejects_unbounded_diagnostic_text(
    field_name: str,
    value: str,
    maximum: int,
) -> None:
    values: dict[str, str] = {field_name: value}

    with pytest.raises(ValueError, match=f"at most {maximum}"):
        AuditEvent(
            event_id="event-001",
            workspace_id="workspace-001",
            batch_id="batch-001",
            event_type=AuditEventType.ITEM_EXECUTION_FAILED,
            actor_type=AuditActorType.SYSTEM,
            actor_id="local-core",
            occurred_at_utc=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
            correlation_id="correlation-001",
            **values,
        )


def test_event_contract_contains_no_document_payload_field() -> None:
    event = audit_event(reason=None)

    assert "document_bytes" not in event.__dataclass_fields__
    assert "document_text" not in event.__dataclass_fields__
