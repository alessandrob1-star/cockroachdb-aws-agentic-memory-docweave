"""Create append-only file lineage memory.

Revision ID: 0004_file_lineage_memory
Revises: 0003_review_decision_memory
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_file_lineage_memory"
down_revision: str | None = "0003_review_decision_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "docweave"


def upgrade() -> None:
    """Create append-only file lineage event storage."""
    _create_file_lineage_events()
    _create_indexes()


def downgrade() -> None:
    """Remove file lineage memory in dependency order."""
    op.drop_table("file_lineage_events", schema=SCHEMA_NAME)


def _create_file_lineage_events() -> None:
    op.create_table(
        "file_lineage_events",
        sa.Column("file_lineage_event_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("logical_document_key", sa.String(length=128), nullable=False),
        sa.Column("lineage_sequence", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("operation_batch_id", sa.Uuid(), nullable=True),
        sa.Column("file_operation_id", sa.Uuid(), nullable=True),
        sa.Column("batch_item_id", sa.String(length=128), nullable=True),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("original_relative_path", sa.String(length=2048), nullable=False),
        sa.Column("previous_relative_path", sa.String(length=2048), nullable=False),
        sa.Column("next_relative_path", sa.String(length=2048), nullable=False),
        sa.Column("original_directory", sa.String(length=2048), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("previous_directory", sa.String(length=2048), nullable=False),
        sa.Column("previous_filename", sa.String(length=255), nullable=False),
        sa.Column("next_directory", sa.String(length=2048), nullable=False),
        sa.Column("next_filename", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("source_sha256_before", sa.LargeBinary(length=32), nullable=True),
        sa.Column(
            "destination_sha256_after",
            sa.LargeBinary(length=32),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(logical_document_key)) > 0",
            name="ck_file_lineage_events_document_key",
        ),
        sa.CheckConstraint(
            "lineage_sequence > 0",
            name="ck_file_lineage_events_sequence",
        ),
        sa.CheckConstraint(
            "length(trim(idempotency_key)) > 0",
            name="ck_file_lineage_events_idempotency",
        ),
        sa.CheckConstraint(
            "action IN ('copy', 'move', 'rename', 'rename_and_move', 'blocked')",
            name="ck_file_lineage_events_action",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'succeeded', 'failed', 'verification_failed')",
            name="ck_file_lineage_events_status",
        ),
        sa.CheckConstraint(
            "octet_length(plan_sha256) = 32",
            name="ck_file_lineage_events_plan_digest",
        ),
        sa.CheckConstraint(
            "source_sha256_before IS NULL OR octet_length(source_sha256_before) = 32",
            name="ck_file_lineage_events_source_digest",
        ),
        sa.CheckConstraint(
            "destination_sha256_after IS NULL "
            "OR octet_length(destination_sha256_after) = 32",
            name="ck_file_lineage_events_destination_digest",
        ),
        sa.CheckConstraint(
            "length(trim(original_filename)) > 0 "
            "AND length(trim(previous_filename)) > 0 "
            "AND length(trim(next_filename)) > 0",
            name="ck_file_lineage_events_filename_nonempty",
        ),
        sa.CheckConstraint(
            "(action = 'blocked' AND previous_relative_path = next_relative_path) "
            "OR action <> 'blocked'",
            name="ck_file_lineage_events_blocked_path",
        ),
        sa.CheckConstraint(
            "operation_batch_id IS NULL OR batch_item_id IS NOT NULL",
            name="ck_file_lineage_events_batch_item_identity",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{SCHEMA_NAME}.workspaces.workspace_id"],
            name="fk_file_lineage_events_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "operation_batch_id"],
            [
                f"{SCHEMA_NAME}.operation_batches.workspace_id",
                f"{SCHEMA_NAME}.operation_batches.operation_batch_id",
            ],
            name="fk_file_lineage_events_batch_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "file_operation_id"],
            [
                f"{SCHEMA_NAME}.file_operations.workspace_id",
                f"{SCHEMA_NAME}.file_operations.file_operation_id",
            ],
            name="fk_file_lineage_events_operation_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "proposal_id"],
            [
                f"{SCHEMA_NAME}.proposals.workspace_id",
                f"{SCHEMA_NAME}.proposals.proposal_id",
            ],
            name="fk_file_lineage_events_proposal_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "file_lineage_event_id",
            name="pk_file_lineage_events",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "file_lineage_event_id",
            name="uq_file_lineage_events_workspace_identity",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "logical_document_key",
            "lineage_sequence",
            name="uq_file_lineage_events_document_sequence",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_file_lineage_events_idempotency",
        ),
        schema=SCHEMA_NAME,
    )


def _create_indexes() -> None:
    op.create_index(
        "ix_file_lineage_events_document_history",
        "file_lineage_events",
        ["workspace_id", "logical_document_key", "lineage_sequence"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_file_lineage_events_operation",
        "file_lineage_events",
        ["workspace_id", "operation_batch_id", "file_operation_id"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_file_lineage_events_current_path",
        "file_lineage_events",
        ["workspace_id", "next_relative_path", "lineage_sequence"],
        schema=SCHEMA_NAME,
    )
