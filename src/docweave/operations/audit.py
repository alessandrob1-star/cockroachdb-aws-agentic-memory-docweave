"""Append-only local audit event contracts.

The local trail is intentionally in-memory. CockroachDB persistence and
tamper-evident digest chaining remain separate implementation work.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from threading import RLock


class AuditActorType(StrEnum):
    """Actor categories permitted in material audit events."""

    HUMAN = "human"
    SYSTEM = "system"
    AGENT = "agent"


class AuditEventType(StrEnum):
    """Material local batch lifecycle event types."""

    BATCH_CREATED = "batch_created"
    ITEM_PLANNED = "item_planned"
    ITEM_BLOCKED = "item_blocked"
    BATCH_SUBMITTED_FOR_APPROVAL = "batch_submitted_for_approval"
    ITEM_APPROVED = "item_approved"
    BATCH_APPROVED = "batch_approved"
    ITEM_EXECUTION_INTENT_RECORDED = "item_execution_intent_recorded"
    ITEM_EXECUTION_SUCCEEDED = "item_execution_succeeded"
    ITEM_EXECUTION_FAILED = "item_execution_failed"
    ITEM_VERIFICATION_FAILED = "item_verification_failed"
    ITEM_EXECUTION_REPLAYED = "item_execution_replayed"
    ITEM_EXECUTION_RECONCILED = "item_execution_reconciled"
    ITEM_SKIPPED = "item_skipped"
    BATCH_COMPLETED = "batch_completed"
    BATCH_COMPLETED_WITH_FAILURES = "batch_completed_with_failures"
    BATCH_CANCELLED = "batch_cancelled"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Minimized immutable evidence for one material state transition."""

    event_id: str
    workspace_id: str
    batch_id: str
    event_type: AuditEventType
    actor_type: AuditActorType
    actor_id: str
    occurred_at_utc: datetime
    correlation_id: str
    batch_item_id: str | None = None
    idempotency_key: str | None = None
    previous_state: str | None = None
    new_state: str | None = None
    reason: str | None = None
    plan_fingerprint: str | None = None
    approval_id: str | None = None
    source_relative_path: str | None = None
    destination_relative_path: str | None = None
    error_class: str | None = None
    error_category: str | None = None

    def __post_init__(self) -> None:
        """Reject malformed identifiers, paths, and unsafe diagnostic payloads."""
        for field_name, value in (
            ("event_id", self.event_id),
            ("workspace_id", self.workspace_id),
            ("batch_id", self.batch_id),
            ("actor_id", self.actor_id),
            ("correlation_id", self.correlation_id),
        ):
            _require_non_empty(field_name, value)

        object.__setattr__(self, "occurred_at_utc", normalize_utc(self.occurred_at_utc))
        _validate_relative_path("source_relative_path", self.source_relative_path)
        _validate_relative_path(
            "destination_relative_path",
            self.destination_relative_path,
        )
        _validate_bounded_text("reason", self.reason, maximum=256)
        _validate_bounded_text("error_class", self.error_class, maximum=128)
        _validate_bounded_text("error_category", self.error_category, maximum=128)


class AppendOnlyAuditTrail:
    """Thread-safe in-memory audit sink with no update or delete operation."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._event_ids: set[str] = set()
        self._lock = RLock()

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        """Return an immutable snapshot in append order."""
        with self._lock:
            return tuple(self._events)

    def append(self, event: AuditEvent) -> None:
        """Append one unique event without permitting chronological regression."""
        with self._lock:
            if event.event_id in self._event_ids:
                raise ValueError("audit event_id must be unique")
            if (
                self._events
                and event.occurred_at_utc < self._events[-1].occurred_at_utc
            ):
                raise ValueError("audit events must not move backward in time")
            self._events.append(event)
            self._event_ids.add(event.event_id)


def normalize_utc(value: datetime) -> datetime:
    """Normalize naive or timezone-aware timestamps to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_non_empty(field_name: str, value: str) -> None:
    if value.strip() == "":
        raise ValueError(f"{field_name} must not be empty")


def _validate_relative_path(field_name: str, value: str | None) -> None:
    if value is None:
        return
    path = PurePosixPath(value)
    if (
        value.strip() == ""
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise ValueError(f"{field_name} must be a normalized relative path")


def _validate_bounded_text(
    field_name: str,
    value: str | None,
    *,
    maximum: int,
) -> None:
    if value is not None and len(value) > maximum:
        raise ValueError(f"{field_name} must contain at most {maximum} characters")
