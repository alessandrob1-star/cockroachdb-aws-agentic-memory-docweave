"""Create durable human review decision memory.

Revision ID: 0003_review_decision_memory
Revises: 0002_classification_memory
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_review_decision_memory"
down_revision: str | None = "0002_classification_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "docweave"


def upgrade() -> None:
    """Create append-only human review decision storage."""
    _create_review_decisions()
    _create_indexes()


def downgrade() -> None:
    """Remove review decision memory in dependency order."""
    op.drop_table("review_decisions", schema=SCHEMA_NAME)


def _create_review_decisions() -> None:
    op.create_table(
        "review_decisions",
        sa.Column("review_decision_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("proposal_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("operation_plan_sha256", sa.LargeBinary(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('approve', 'reject', 'request_changes', 'escalate')",
            name="ck_review_decisions_action",
        ),
        sa.CheckConstraint(
            "octet_length(proposal_sha256) = 32",
            name="ck_review_decisions_proposal_digest",
        ),
        sa.CheckConstraint(
            "operation_plan_sha256 IS NULL OR octet_length(operation_plan_sha256) = 32",
            name="ck_review_decisions_operation_plan_digest",
        ),
        sa.CheckConstraint(
            "action = 'approve' OR length(trim(coalesce(reason, ''))) > 0",
            name="ck_review_decisions_reason_required",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "proposal_id"],
            [
                f"{SCHEMA_NAME}.proposals.workspace_id",
                f"{SCHEMA_NAME}.proposals.proposal_id",
            ],
            name="fk_review_decisions_proposal_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_actor_id"],
            [f"{SCHEMA_NAME}.actors.actor_id"],
            name="fk_review_decisions_reviewer",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "review_decision_id",
            name="pk_review_decisions",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "review_decision_id",
            name="uq_review_decisions_workspace_identity",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "proposal_id",
            name="uq_review_decisions_proposal",
        ),
        schema=SCHEMA_NAME,
    )


def _create_indexes() -> None:
    op.create_index(
        "ix_review_decisions_workspace_chronology",
        "review_decisions",
        ["workspace_id", "decided_at", "review_decision_id"],
        schema=SCHEMA_NAME,
    )
