"""Create the non-vector operational persistence foundation.

Revision ID: 0001_operational_foundation
Revises:
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_operational_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "docweave"


def upgrade() -> None:
    """Create workspace, operation, and audit persistence tables."""
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}")
    _create_workspaces()
    _create_actors()
    _create_workspace_members()
    _create_operation_batches()
    _create_file_operations()
    _create_audit_events()
    _create_indexes()


def downgrade() -> None:
    """Remove the foundation only in an approved disposable environment."""
    op.drop_table("audit_events", schema=SCHEMA_NAME)
    op.drop_table("file_operations", schema=SCHEMA_NAME)
    op.drop_table("operation_batches", schema=SCHEMA_NAME)
    op.drop_table("workspace_members", schema=SCHEMA_NAME)
    op.drop_table("actors", schema=SCHEMA_NAME)
    op.drop_table("workspaces", schema=SCHEMA_NAME)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME}")


def _create_workspaces() -> None:
    op.create_table(
        "workspaces",
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workspace_key", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(trim(workspace_key)) > 0",
            name="ck_workspaces_key_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(display_name)) > 0",
            name="ck_workspaces_display_name_nonempty",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'archived')",
            name="ck_workspaces_status",
        ),
        sa.CheckConstraint(
            "(status = 'archived' AND archived_at IS NOT NULL) "
            "OR (status <> 'archived' AND archived_at IS NULL)",
            name="ck_workspaces_archive_time",
        ),
        sa.PrimaryKeyConstraint("workspace_id", name="pk_workspaces"),
        sa.UniqueConstraint("workspace_key", name="uq_workspaces_workspace_key"),
        schema=SCHEMA_NAME,
    )


def _create_actors() -> None:
    op.create_table(
        "actors",
        sa.Column(
            "actor_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("external_subject", sa.String(length=256), nullable=True),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "actor_type IN ('human', 'service', 'agent')",
            name="ck_actors_actor_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_actors_status",
        ),
        sa.CheckConstraint(
            "length(trim(display_name)) > 0",
            name="ck_actors_display_name_nonempty",
        ),
        sa.PrimaryKeyConstraint("actor_id", name="pk_actors"),
        sa.UniqueConstraint(
            "external_subject",
            name="uq_actors_external_subject",
        ),
        schema=SCHEMA_NAME,
    )


def _create_workspace_members() -> None:
    op.create_table(
        "workspace_members",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("granted_by_actor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(trim(role_code)) > 0",
            name="ck_workspace_members_role_nonempty",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= granted_at",
            name="ck_workspace_members_revocation_time",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{SCHEMA_NAME}.workspaces.workspace_id"],
            name="fk_workspace_members_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            [f"{SCHEMA_NAME}.actors.actor_id"],
            name="fk_workspace_members_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_actor_id"],
            [f"{SCHEMA_NAME}.actors.actor_id"],
            name="fk_workspace_members_grantor",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "workspace_id",
            "actor_id",
            "role_code",
            "granted_at",
            name="pk_workspace_members",
        ),
        schema=SCHEMA_NAME,
    )


def _create_operation_batches() -> None:
    op.create_table(
        "operation_batches",
        sa.Column(
            "operation_batch_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("external_batch_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("operation_type", sa.String(length=16), nullable=False),
        sa.Column("preview_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("preview_version", sa.BigInteger(), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_by_actor_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.String(length=128), nullable=True),
        sa.Column("approved_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approval_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("total_item_count", sa.Integer(), nullable=False),
        sa.Column(
            "succeeded_item_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "blocked_item_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "failed_item_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "verification_failed_item_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "skipped_item_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "operation_type IN ('copy', 'move')",
            name="ck_operation_batches_operation_type",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'draft', 'ready_for_approval', 'approved', 'executing', "
            "'completed', 'completed_with_failures', 'cancelled'"
            ")",
            name="ck_operation_batches_status",
        ),
        sa.CheckConstraint(
            "preview_version > 0",
            name="ck_operation_batches_preview_version",
        ),
        sa.CheckConstraint(
            "octet_length(preview_sha256) = 32",
            name="ck_operation_batches_preview_digest",
        ),
        sa.CheckConstraint(
            "total_item_count BETWEEN 1 AND 1000",
            name="ck_operation_batches_item_limit",
        ),
        sa.CheckConstraint(
            "succeeded_item_count >= 0 "
            "AND blocked_item_count >= 0 "
            "AND failed_item_count >= 0 "
            "AND verification_failed_item_count >= 0 "
            "AND skipped_item_count >= 0",
            name="ck_operation_batches_result_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "succeeded_item_count + blocked_item_count + failed_item_count "
            "+ verification_failed_item_count + skipped_item_count "
            "<= total_item_count",
            name="ck_operation_batches_result_counts_bounded",
        ),
        sa.CheckConstraint(
            "(approval_id IS NULL AND approved_by_actor_id IS NULL "
            "AND approved_at IS NULL AND approval_expires_at IS NULL) "
            "OR (approval_id IS NOT NULL AND approved_by_actor_id IS NOT NULL "
            "AND approved_at IS NOT NULL AND approval_expires_at > approved_at)",
            name="ck_operation_batches_approval_complete",
        ),
        sa.CheckConstraint(
            "(status IN ('completed', 'completed_with_failures') "
            "AND completed_at IS NOT NULL) "
            "OR (status NOT IN ('completed', 'completed_with_failures') "
            "AND completed_at IS NULL)",
            name="ck_operation_batches_completion_time",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{SCHEMA_NAME}.workspaces.workspace_id"],
            name="fk_operation_batches_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_actor_id"],
            [f"{SCHEMA_NAME}.actors.actor_id"],
            name="fk_operation_batches_creator",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_actor_id"],
            [f"{SCHEMA_NAME}.actors.actor_id"],
            name="fk_operation_batches_approver",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "operation_batch_id",
            name="pk_operation_batches",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "operation_batch_id",
            name="uq_operation_batches_workspace_identity",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "external_batch_id",
            name="uq_operation_batches_external_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_operation_batches_idempotency",
        ),
        schema=SCHEMA_NAME,
    )


def _create_file_operations() -> None:
    op.create_table(
        "file_operations",
        sa.Column(
            "file_operation_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("operation_batch_id", sa.Uuid(), nullable=False),
        sa.Column("batch_item_id", sa.String(length=128), nullable=False),
        sa.Column("operation_type", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("plan_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("approval_id", sa.String(length=128), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("document_version_id", sa.Uuid(), nullable=True),
        sa.Column("source_instance_id", sa.Uuid(), nullable=True),
        sa.Column("source_root_reference", sa.String(length=512), nullable=False),
        sa.Column("source_relative_path", sa.String(length=2048), nullable=False),
        sa.Column(
            "destination_root_reference",
            sa.String(length=512),
            nullable=False,
        ),
        sa.Column(
            "destination_relative_path",
            sa.String(length=2048),
            nullable=False,
        ),
        sa.Column(
            "expected_source_sha256",
            sa.LargeBinary(length=32),
            nullable=True,
        ),
        sa.Column("expected_source_size", sa.BigInteger(), nullable=True),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("execution_id", sa.String(length=256), nullable=True),
        sa.Column("executor_actor_id", sa.Uuid(), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "actual_source_relative_path",
            sa.String(length=2048),
            nullable=True,
        ),
        sa.Column(
            "actual_destination_relative_path",
            sa.String(length=2048),
            nullable=True,
        ),
        sa.Column("actual_sha256", sa.LargeBinary(length=32), nullable=True),
        sa.Column("actual_size", sa.BigInteger(), nullable=True),
        sa.Column("source_exists_after", sa.Boolean(), nullable=True),
        sa.Column("destination_exists_after", sa.Boolean(), nullable=True),
        sa.Column(
            "result_disposition",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "reconciliation_state",
            sa.String(length=64),
            server_default=sa.text("'not_required'"),
            nullable=False,
        ),
        sa.Column("error_category", sa.String(length=128), nullable=True),
        sa.Column("safe_error_summary", sa.String(length=256), nullable=True),
        sa.Column("compensates_operation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "intent_recorded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "operation_type IN ('copy', 'move')",
            name="ck_file_operations_operation_type",
        ),
        sa.CheckConstraint(
            "state IN ("
            "'planned', 'blocked', 'approved', 'executing', 'succeeded', "
            "'failed', 'verification_failed', 'skipped'"
            ")",
            name="ck_file_operations_state",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_file_operations_attempt_count",
        ),
        sa.CheckConstraint(
            "expected_source_size IS NULL OR expected_source_size >= 0",
            name="ck_file_operations_expected_size",
        ),
        sa.CheckConstraint(
            "actual_size IS NULL OR actual_size >= 0",
            name="ck_file_operations_actual_size",
        ),
        sa.CheckConstraint(
            "octet_length(plan_sha256) = 32",
            name="ck_file_operations_plan_digest",
        ),
        sa.CheckConstraint(
            "expected_source_sha256 IS NULL "
            "OR octet_length(expected_source_sha256) = 32",
            name="ck_file_operations_expected_digest",
        ),
        sa.CheckConstraint(
            "actual_sha256 IS NULL OR octet_length(actual_sha256) = 32",
            name="ck_file_operations_actual_digest",
        ),
        sa.CheckConstraint(
            "reconciliation_state IN ('not_required', 'required', 'reconciled')",
            name="ck_file_operations_reconciliation_state",
        ),
        sa.CheckConstraint(
            "(lease_token IS NULL AND lease_expires_at IS NULL) "
            "OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_file_operations_lease_complete",
        ),
        sa.CheckConstraint(
            "state NOT IN ('approved', 'executing', 'succeeded') "
            "OR (approval_id IS NOT NULL "
            "AND expected_source_sha256 IS NOT NULL "
            "AND expected_source_size IS NOT NULL)",
            name="ck_file_operations_approved_preconditions",
        ),
        sa.CheckConstraint(
            "(state IN ("
            "'blocked', 'succeeded', 'failed', 'verification_failed', 'skipped'"
            ") "
            "AND completed_at IS NOT NULL) "
            "OR (state NOT IN ("
            "'blocked', 'succeeded', 'failed', 'verification_failed', 'skipped'"
            ") "
            "AND completed_at IS NULL)",
            name="ck_file_operations_completion_time",
        ),
        sa.CheckConstraint(
            "state NOT IN ('executing', 'succeeded', 'failed', "
            "'verification_failed') "
            "OR (idempotency_key IS NOT NULL "
            "AND intent_recorded_at IS NOT NULL "
            "AND execution_id IS NOT NULL)",
            name="ck_file_operations_execution_intent",
        ),
        sa.CheckConstraint(
            "state <> 'succeeded' "
            "OR (actual_sha256 IS NOT NULL "
            "AND actual_size IS NOT NULL "
            "AND destination_exists_after IS TRUE)",
            name="ck_file_operations_success_evidence",
        ),
        sa.CheckConstraint(
            "state <> 'verification_failed' OR reconciliation_state = 'required'",
            name="ck_file_operations_failed_verification_reconciliation",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "operation_batch_id"],
            [
                f"{SCHEMA_NAME}.operation_batches.workspace_id",
                f"{SCHEMA_NAME}.operation_batches.operation_batch_id",
            ],
            name="fk_file_operations_batch_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["executor_actor_id"],
            [f"{SCHEMA_NAME}.actors.actor_id"],
            name="fk_file_operations_executor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["compensates_operation_id"],
            [f"{SCHEMA_NAME}.file_operations.file_operation_id"],
            name="fk_file_operations_compensates",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "file_operation_id",
            name="pk_file_operations",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "file_operation_id",
            name="uq_file_operations_workspace_identity",
        ),
        sa.UniqueConstraint(
            "operation_batch_id",
            "batch_item_id",
            name="uq_file_operations_batch_item",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_file_operations_idempotency",
        ),
        schema=SCHEMA_NAME,
    )


def _create_audit_events() -> None:
    op.create_table(
        "audit_events",
        sa.Column(
            "event_sequence",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("subject_kind", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("operation_batch_id", sa.Uuid(), nullable=True),
        sa.Column("file_operation_id", sa.Uuid(), nullable=True),
        sa.Column("causation_event_id", sa.Uuid(), nullable=True),
        sa.Column("previous_event_id", sa.Uuid(), nullable=True),
        sa.Column("previous_event_sha256", sa.LargeBinary(length=32), nullable=True),
        sa.Column("event_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("previous_state", sa.String(length=64), nullable=True),
        sa.Column("new_state", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("plan_sha256", sa.LargeBinary(length=32), nullable=True),
        sa.Column("approval_id", sa.String(length=128), nullable=True),
        sa.Column("source_relative_path", sa.String(length=2048), nullable=True),
        sa.Column(
            "destination_relative_path",
            sa.String(length=2048),
            nullable=True,
        ),
        sa.Column("error_class", sa.String(length=128), nullable=True),
        sa.Column("error_category", sa.String(length=128), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::JSONB"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(event_type)) > 0",
            name="ck_audit_events_event_type_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(subject_kind)) > 0 AND length(trim(subject_id)) > 0",
            name="ck_audit_events_subject_nonempty",
        ),
        sa.CheckConstraint(
            "octet_length(event_sha256) = 32",
            name="ck_audit_events_digest",
        ),
        sa.CheckConstraint(
            "previous_event_sha256 IS NULL OR octet_length(previous_event_sha256) = 32",
            name="ck_audit_events_previous_digest",
        ),
        sa.CheckConstraint(
            "plan_sha256 IS NULL OR octet_length(plan_sha256) = 32",
            name="ck_audit_events_plan_digest",
        ),
        sa.CheckConstraint(
            "(previous_event_id IS NULL AND previous_event_sha256 IS NULL) "
            "OR (previous_event_id IS NOT NULL "
            "AND previous_event_sha256 IS NOT NULL)",
            name="ck_audit_events_predecessor_complete",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{SCHEMA_NAME}.workspaces.workspace_id"],
            name="fk_audit_events_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            [f"{SCHEMA_NAME}.actors.actor_id"],
            name="fk_audit_events_actor",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "operation_batch_id"],
            [
                f"{SCHEMA_NAME}.operation_batches.workspace_id",
                f"{SCHEMA_NAME}.operation_batches.operation_batch_id",
            ],
            name="fk_audit_events_batch_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "file_operation_id"],
            [
                f"{SCHEMA_NAME}.file_operations.workspace_id",
                f"{SCHEMA_NAME}.file_operations.file_operation_id",
            ],
            name="fk_audit_events_operation_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "causation_event_id"],
            [
                f"{SCHEMA_NAME}.audit_events.workspace_id",
                f"{SCHEMA_NAME}.audit_events.event_id",
            ],
            name="fk_audit_events_causation_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "previous_event_id"],
            [
                f"{SCHEMA_NAME}.audit_events.workspace_id",
                f"{SCHEMA_NAME}.audit_events.event_id",
            ],
            name="fk_audit_events_previous_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "workspace_id",
            "event_sequence",
            name="pk_audit_events",
        ),
        sa.UniqueConstraint("event_id", name="uq_audit_events_event_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "event_id",
            name="uq_audit_events_workspace_identity",
        ),
        schema=SCHEMA_NAME,
    )


def _create_indexes() -> None:
    op.create_index(
        "ix_workspace_members_active_actor",
        "workspace_members",
        ["workspace_id", "actor_id"],
        unique=False,
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_operation_batches_workspace_status",
        "operation_batches",
        ["workspace_id", "status", "created_at"],
        unique=False,
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_file_operations_executable",
        "file_operations",
        ["workspace_id", "state", "lease_expires_at"],
        unique=False,
        schema=SCHEMA_NAME,
        postgresql_where=sa.text(
            "state IN ('approved', 'executing', 'verification_failed')"
        ),
    )
    op.create_index(
        "ix_file_operations_reconciliation",
        "file_operations",
        ["workspace_id", "reconciliation_state", "completed_at"],
        unique=False,
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("reconciliation_state = 'required'"),
    )
    op.create_index(
        "ix_audit_events_workspace_chronology",
        "audit_events",
        ["workspace_id", "event_sequence"],
        unique=False,
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_audit_events_subject_history",
        "audit_events",
        ["workspace_id", "subject_kind", "subject_id", "event_sequence"],
        unique=False,
        schema=SCHEMA_NAME,
    )
