"""Create cloud analysis operational memory.

Revision ID: 0005_cloud_analysis_memory
Revises: 0004_file_lineage_memory
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_cloud_analysis_memory"
down_revision: str | None = "0004_file_lineage_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_NAME = "docweave"


def upgrade() -> None:
    """Create AWS worker memory tables for classified cloud objects."""
    _create_cloud_analysis_jobs()
    _create_cloud_analysis_objects()
    _create_indexes()


def downgrade() -> None:
    """Remove cloud analysis memory in dependency order."""
    op.drop_table("cloud_analysis_objects", schema=SCHEMA_NAME)
    op.drop_table("cloud_analysis_jobs", schema=SCHEMA_NAME)


def _create_cloud_analysis_jobs() -> None:
    op.create_table(
        "cloud_analysis_jobs",
        sa.Column("cloud_analysis_job_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_service", sa.String(length=64), nullable=False),
        sa.Column("result_artifact_key", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(job_id)) > 0",
            name="ck_cloud_analysis_jobs_job_id_nonempty",
        ),
        sa.CheckConstraint(
            "status IN ('classified', 'persisted', 'failed')",
            name="ck_cloud_analysis_jobs_status",
        ),
        sa.CheckConstraint(
            "source_service IN ('aws_lambda_worker')",
            name="ck_cloud_analysis_jobs_source_service",
        ),
        sa.CheckConstraint(
            "result_artifact_key IS NULL OR length(trim(result_artifact_key)) > 0",
            name="ck_cloud_analysis_jobs_result_artifact_key_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            [f"{SCHEMA_NAME}.workspaces.workspace_id"],
            name="fk_cloud_analysis_jobs_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "cloud_analysis_job_id",
            name="pk_cloud_analysis_jobs",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "cloud_analysis_job_id",
            name="uq_cloud_analysis_jobs_workspace_identity",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "job_id",
            name="uq_cloud_analysis_jobs_workspace_job",
        ),
        schema=SCHEMA_NAME,
    )


def _create_cloud_analysis_objects() -> None:
    op.create_table(
        "cloud_analysis_objects",
        sa.Column("cloud_analysis_object_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("cloud_analysis_job_id", sa.Uuid(), nullable=False),
        sa.Column("object_sequence", sa.Integer(), nullable=False),
        sa.Column("s3_object_key", sa.String(length=1024), nullable=False),
        sa.Column("content_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("model_id", sa.String(length=256), nullable=False),
        sa.Column("proposed_class", sa.String(length=64), nullable=False),
        sa.Column("confidence_signal", sa.String(length=32), nullable=False),
        sa.Column(
            "proposal",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "usage",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "persisted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "object_sequence BETWEEN 1 AND 1000",
            name="ck_cloud_analysis_objects_sequence",
        ),
        sa.CheckConstraint(
            "length(trim(s3_object_key)) > 0",
            name="ck_cloud_analysis_objects_key_nonempty",
        ),
        sa.CheckConstraint(
            "octet_length(content_sha256) = 32",
            name="ck_cloud_analysis_objects_content_digest",
        ),
        sa.CheckConstraint(
            "byte_size >= 0",
            name="ck_cloud_analysis_objects_byte_size",
        ),
        sa.CheckConstraint(
            "length(trim(model_id)) > 0",
            name="ck_cloud_analysis_objects_model_id_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(proposed_class)) > 0",
            name="ck_cloud_analysis_objects_proposed_class_nonempty",
        ),
        sa.CheckConstraint(
            "confidence_signal IN ('weak', 'moderate', 'strong')",
            name="ck_cloud_analysis_objects_confidence_signal",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "cloud_analysis_job_id"],
            [
                f"{SCHEMA_NAME}.cloud_analysis_jobs.workspace_id",
                f"{SCHEMA_NAME}.cloud_analysis_jobs.cloud_analysis_job_id",
            ],
            name="fk_cloud_analysis_objects_job_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "cloud_analysis_object_id",
            name="pk_cloud_analysis_objects",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "cloud_analysis_object_id",
            name="uq_cloud_analysis_objects_workspace_identity",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "cloud_analysis_job_id",
            "object_sequence",
            name="uq_cloud_analysis_objects_job_sequence",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "cloud_analysis_job_id",
            "s3_object_key",
            name="uq_cloud_analysis_objects_job_key",
        ),
        schema=SCHEMA_NAME,
    )


def _create_indexes() -> None:
    op.create_index(
        "ix_cloud_analysis_jobs_workspace_status",
        "cloud_analysis_jobs",
        ["workspace_id", "status", "completed_at"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_cloud_analysis_objects_workspace_class",
        "cloud_analysis_objects",
        ["workspace_id", "proposed_class", "persisted_at"],
        schema=SCHEMA_NAME,
    )
    op.create_index(
        "ix_cloud_analysis_objects_content_hash",
        "cloud_analysis_objects",
        ["workspace_id", "content_sha256"],
        schema=SCHEMA_NAME,
    )
