"""Create non-authoritative classification memory.

Revision ID: 0002_classification_memory
Revises: 0001_operational_foundation
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_classification_memory"
down_revision: str | None = "0001_operational_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "docweave"


def upgrade() -> None:
    """Create document, taxonomy, run, proposal, and evidence tables."""
    _create_documents()
    _create_document_versions()
    _create_taxonomy_versions()
    _create_taxonomy_classes()
    _create_agent_runs()
    _create_proposals()
    _create_classification_proposals()
    _create_proposal_evidence()
    _create_indexes()


def downgrade() -> None:
    """Remove classification memory in dependency order."""
    op.drop_table("proposal_evidence", schema=SCHEMA_NAME)
    op.drop_table("classification_proposals", schema=SCHEMA_NAME)
    op.drop_table("proposals", schema=SCHEMA_NAME)
    op.drop_table("agent_runs", schema=SCHEMA_NAME)
    op.drop_table("taxonomy_classes", schema=SCHEMA_NAME)
    op.drop_table("taxonomy_versions", schema=SCHEMA_NAME)
    op.drop_table("document_versions", schema=SCHEMA_NAME)
    op.drop_table("documents", schema=SCHEMA_NAME)


def _create_documents() -> None:
    op.create_table(
        "documents",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "lifecycle_status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("current_classification_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "lifecycle_status IN ('active', 'retired')",
            name="ck_documents_lifecycle_status",
        ),
        sa.CheckConstraint(
            "(lifecycle_status = 'retired' AND retired_at IS NOT NULL) "
            "OR (lifecycle_status = 'active' AND retired_at IS NULL)",
            name="ck_documents_retirement",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{SCHEMA_NAME}.workspaces.workspace_id"],
            name="fk_documents_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("document_id", name="pk_documents"),
        sa.UniqueConstraint(
            "workspace_id",
            "document_id",
            name="uq_documents_workspace_identity",
        ),
        schema=SCHEMA_NAME,
    )


def _create_document_versions() -> None:
    op.create_table(
        "document_versions",
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extraction_status", sa.String(length=32), nullable=False),
        sa.Column("predecessor_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("version_number > 0", name="ck_document_versions_number"),
        sa.CheckConstraint("byte_size >= 0", name="ck_document_versions_size"),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count > 0",
            name="ck_document_versions_page_count",
        ),
        sa.CheckConstraint(
            "octet_length(sha256) = 32",
            name="ck_document_versions_digest",
        ),
        sa.CheckConstraint(
            "extraction_status IN "
            "('pending', 'ready', 'text_free', 'encrypted', 'unsupported', 'failed')",
            name="ck_document_versions_extraction_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            [
                f"{SCHEMA_NAME}.documents.workspace_id",
                f"{SCHEMA_NAME}.documents.document_id",
            ],
            name="fk_document_versions_document_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "predecessor_version_id"],
            [
                f"{SCHEMA_NAME}.document_versions.workspace_id",
                f"{SCHEMA_NAME}.document_versions.document_version_id",
            ],
            name="fk_document_versions_predecessor_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "document_version_id",
            name="pk_document_versions",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "document_version_id",
            name="uq_document_versions_workspace_identity",
        ),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_number",
        ),
        schema=SCHEMA_NAME,
    )


def _create_taxonomy_versions() -> None:
    op.create_table(
        "taxonomy_versions",
        sa.Column("taxonomy_version_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("version_label", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("approved_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'retired')",
            name="ck_taxonomy_versions_status",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND approved_by_actor_id IS NOT NULL "
            "AND approved_at IS NOT NULL) OR status <> 'active'",
            name="ck_taxonomy_versions_activation",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{SCHEMA_NAME}.workspaces.workspace_id"],
            name="fk_taxonomy_versions_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_actor_id"],
            [f"{SCHEMA_NAME}.actors.actor_id"],
            name="fk_taxonomy_versions_approver",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "taxonomy_version_id",
            name="pk_taxonomy_versions",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "taxonomy_version_id",
            name="uq_taxonomy_versions_workspace_identity",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "version_label",
            name="uq_taxonomy_versions_label",
        ),
        schema=SCHEMA_NAME,
    )


def _create_taxonomy_classes() -> None:
    op.create_table(
        "taxonomy_classes",
        sa.Column("taxonomy_class_id", sa.Uuid(), nullable=False),
        sa.Column("taxonomy_version_id", sa.Uuid(), nullable=False),
        sa.Column("class_code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("expected_evidence", sa.Text(), nullable=False),
        sa.Column(
            "is_abstention",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("sort_order >= 0", name="ck_taxonomy_classes_sort_order"),
        sa.ForeignKeyConstraint(
            ["taxonomy_version_id"],
            [f"{SCHEMA_NAME}.taxonomy_versions.taxonomy_version_id"],
            name="fk_taxonomy_classes_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("taxonomy_class_id", name="pk_taxonomy_classes"),
        sa.UniqueConstraint(
            "taxonomy_version_id",
            "taxonomy_class_id",
            name="uq_taxonomy_classes_version_identity",
        ),
        sa.UniqueConstraint(
            "taxonomy_version_id",
            "class_code",
            name="uq_taxonomy_classes_code",
        ),
        schema=SCHEMA_NAME,
    )


def _create_agent_runs() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("agent_responsibility", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.String(length=64), nullable=False),
        sa.Column("taxonomy_version", sa.String(length=128), nullable=False),
        sa.Column("model_provider", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=256), nullable=True),
        sa.Column("inference_profile_id", sa.String(length=256), nullable=True),
        sa.Column("region_name", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stop_reason", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False),
        sa.Column("service_latency_ms", sa.BigInteger(), nullable=False),
        sa.Column("observed_duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("observed_cost_usd", sa.Numeric(19, 10), nullable=True),
        sa.Column("provider_request_id", sa.String(length=128), nullable=True),
        sa.Column(
            "outcome",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "agent_responsibility = 'classification'",
            name="ck_agent_runs_responsibility",
        ),
        sa.CheckConstraint(
            "status = 'succeeded'",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0 "
            "AND total_tokens >= input_tokens + output_tokens",
            name="ck_agent_runs_tokens",
        ),
        sa.CheckConstraint(
            "service_latency_ms >= 0 AND observed_duration_ms >= 0 "
            "AND retry_count >= 0",
            name="ck_agent_runs_metrics",
        ),
        sa.CheckConstraint(
            "observed_cost_usd IS NULL OR observed_cost_usd >= 0",
            name="ck_agent_runs_cost",
        ),
        sa.CheckConstraint(
            "octet_length(request_sha256) = 32",
            name="ck_agent_runs_request_digest",
        ),
        sa.CheckConstraint(
            "completed_at >= started_at",
            name="ck_agent_runs_completion_time",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "document_version_id"],
            [
                f"{SCHEMA_NAME}.document_versions.workspace_id",
                f"{SCHEMA_NAME}.document_versions.document_version_id",
            ],
            name="fk_agent_runs_document_version_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("agent_run_id", name="pk_agent_runs"),
        sa.UniqueConstraint(
            "workspace_id",
            "agent_run_id",
            name="uq_agent_runs_workspace_identity",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_agent_runs_idempotency",
        ),
        schema=SCHEMA_NAME,
    )


def _create_proposals() -> None:
    op.create_table(
        "proposals",
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_type", sa.String(length=32), nullable=False),
        sa.Column("proposal_status", sa.String(length=32), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("supersedes_proposal_id", sa.Uuid(), nullable=True),
        sa.Column("raw_confidence", sa.Numeric(6, 5), nullable=False),
        sa.Column("calibrated_confidence", sa.Numeric(6, 5), nullable=True),
        sa.Column("confidence_method_version", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "proposal_type = 'classification'",
            name="ck_proposals_type",
        ),
        sa.CheckConstraint(
            "proposal_status IN ('needs_review', 'approved', 'rejected', 'superseded')",
            name="ck_proposals_status",
        ),
        sa.CheckConstraint(
            "raw_confidence BETWEEN 0 AND 1 AND "
            "(calibrated_confidence IS NULL "
            "OR calibrated_confidence BETWEEN 0 AND 1)",
            name="ck_proposals_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "document_version_id"],
            [
                f"{SCHEMA_NAME}.document_versions.workspace_id",
                f"{SCHEMA_NAME}.document_versions.document_version_id",
            ],
            name="fk_proposals_document_version_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "agent_run_id"],
            [
                f"{SCHEMA_NAME}.agent_runs.workspace_id",
                f"{SCHEMA_NAME}.agent_runs.agent_run_id",
            ],
            name="fk_proposals_agent_run_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "supersedes_proposal_id"],
            [
                f"{SCHEMA_NAME}.proposals.workspace_id",
                f"{SCHEMA_NAME}.proposals.proposal_id",
            ],
            name="fk_proposals_supersedes_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("proposal_id", name="pk_proposals"),
        sa.UniqueConstraint(
            "workspace_id",
            "proposal_id",
            name="uq_proposals_workspace_identity",
        ),
        sa.UniqueConstraint("agent_run_id", name="uq_proposals_agent_run"),
        schema=SCHEMA_NAME,
    )


def _create_classification_proposals() -> None:
    op.create_table(
        "classification_proposals",
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("taxonomy_version_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_class_id", sa.Uuid(), nullable=False),
        sa.Column("alternative_class_id", sa.Uuid(), nullable=True),
        sa.Column("abstention_reason", sa.Text(), nullable=True),
        sa.Column("extraction_confidence", sa.Numeric(6, 5), nullable=False),
        sa.Column("classification_confidence", sa.Numeric(6, 5), nullable=False),
        sa.Column("metadata_confidence", sa.Numeric(6, 5), nullable=False),
        sa.Column("contradiction_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "extraction_confidence BETWEEN 0 AND 1 "
            "AND classification_confidence BETWEEN 0 AND 1 "
            "AND metadata_confidence BETWEEN 0 AND 1",
            name="ck_classification_proposals_confidence",
        ),
        sa.CheckConstraint(
            "contradiction_count >= 0",
            name="ck_classification_proposals_contradictions",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            [f"{SCHEMA_NAME}.proposals.proposal_id"],
            name="fk_classification_proposals_proposal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["taxonomy_version_id", "proposed_class_id"],
            [
                f"{SCHEMA_NAME}.taxonomy_classes.taxonomy_version_id",
                f"{SCHEMA_NAME}.taxonomy_classes.taxonomy_class_id",
            ],
            name="fk_classification_proposals_class",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["taxonomy_version_id", "alternative_class_id"],
            [
                f"{SCHEMA_NAME}.taxonomy_classes.taxonomy_version_id",
                f"{SCHEMA_NAME}.taxonomy_classes.taxonomy_class_id",
            ],
            name="fk_classification_proposals_alternative",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "proposal_id",
            name="pk_classification_proposals",
        ),
        schema=SCHEMA_NAME,
    )


def _create_proposal_evidence() -> None:
    op.create_table(
        "proposal_evidence",
        sa.Column("proposal_evidence_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("document_chunk_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_kind", sa.String(length=32), nullable=False),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("character_start", sa.BigInteger(), nullable=True),
        sa.Column("character_end", sa.BigInteger(), nullable=True),
        sa.Column("strength", sa.Numeric(6, 5), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "evidence_kind IN ('span', 'validator', 'memory', 'contradiction')",
            name="ck_proposal_evidence_kind",
        ),
        sa.CheckConstraint(
            "length(trim(quoted_text)) > 0",
            name="ck_proposal_evidence_quote",
        ),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number > 0",
            name="ck_proposal_evidence_page",
        ),
        sa.CheckConstraint(
            "(character_start IS NULL AND character_end IS NULL) OR "
            "(character_start >= 0 AND character_end > character_start)",
            name="ck_proposal_evidence_span",
        ),
        sa.CheckConstraint(
            "strength IS NULL OR strength BETWEEN 0 AND 1",
            name="ck_proposal_evidence_strength",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "proposal_id"],
            [
                f"{SCHEMA_NAME}.proposals.workspace_id",
                f"{SCHEMA_NAME}.proposals.proposal_id",
            ],
            name="fk_proposal_evidence_proposal_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "proposal_evidence_id",
            name="pk_proposal_evidence",
        ),
        sa.UniqueConstraint(
            "proposal_id",
            "proposal_evidence_id",
            name="uq_proposal_evidence_identity",
        ),
        schema=SCHEMA_NAME,
    )


def _create_indexes() -> None:
    op.create_index(
        "ix_documents_workspace_activity",
        "documents",
        ["workspace_id", "lifecycle_status", "created_at"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_document_versions_workspace_hash",
        "document_versions",
        ["workspace_id", "sha256"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ux_taxonomy_versions_active",
        "taxonomy_versions",
        ["workspace_id"],
        unique=True,
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_agent_runs_document_trace",
        "agent_runs",
        ["workspace_id", "document_version_id", "completed_at"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_proposals_pending_review",
        "proposals",
        ["workspace_id", "proposal_type", "calibrated_confidence", "created_at"],
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("proposal_status = 'needs_review'"),
    )
    op.create_index(
        "ix_proposal_evidence_proposal",
        "proposal_evidence",
        ["workspace_id", "proposal_id", "page_number"],
        schema=SCHEMA_NAME,
    )
