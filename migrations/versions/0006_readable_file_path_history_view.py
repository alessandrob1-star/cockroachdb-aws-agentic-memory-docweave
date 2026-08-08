"""Create readable file path history view.

Revision ID: 0006_readable_file_path_history_view
Revises: 0005_cloud_analysis_memory
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_readable_file_path_history_view"
down_revision: str | None = "0005_cloud_analysis_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Expose append-only file path memory through a human-readable view."""
    op.execute(
        """
        CREATE VIEW docweave.file_path_history AS
        SELECT
            workspace_id,
            logical_document_key,
            lineage_sequence,
            action,
            status,
            occurred_at,
            original_directory,
            original_filename,
            previous_directory,
            previous_filename,
            next_directory,
            next_filename,
            original_relative_path,
            previous_relative_path,
            next_relative_path,
            operation_batch_id,
            file_operation_id,
            proposal_id,
            file_lineage_event_id
        FROM docweave.file_lineage_events
        """
    )


def downgrade() -> None:
    """Remove the readable file path history view."""
    op.execute("DROP VIEW IF EXISTS docweave.file_path_history")
