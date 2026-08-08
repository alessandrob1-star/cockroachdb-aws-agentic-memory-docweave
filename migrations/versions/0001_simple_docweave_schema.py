"""Create the simple DocWeave hackathon memory schema.

Revision ID: 0001_simple_docweave_schema
Revises:
Create Date: 2026-08-08
"""

from __future__ import annotations

from alembic import op

revision = "0001_simple_docweave_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the six tables used by the dashboard, CockroachDB, and AWS."""
    op.execute("CREATE SCHEMA IF NOT EXISTS docweave")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS docweave.documents (
            document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_label STRING NOT NULL,
            original_directory STRING NOT NULL,
            original_filename STRING NOT NULL,
            current_directory STRING NOT NULL,
            current_filename STRING NOT NULL,
            content_sha256 BYTES NOT NULL,
            page_count INT8 NULL CHECK (page_count IS NULL OR page_count > 0),
            status STRING NOT NULL CHECK (
                status IN ('discovered', 'proposed', 'approved', 'rejected', 'moved')
            ),
            discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_documents_workspace_content
                UNIQUE (workspace_label, content_sha256)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS docweave.agent_runs (
            agent_run_id UUID PRIMARY KEY,
            document_id UUID NOT NULL,
            provider STRING NOT NULL,
            model_id STRING NOT NULL,
            task STRING NOT NULL,
            status STRING NOT NULL CHECK (
                status IN ('started', 'succeeded', 'failed')
            ),
            started_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ NULL,
            input_sha256 BYTES NOT NULL,
            output_json JSONB NOT NULL,
            summary STRING NOT NULL,
            CONSTRAINT fk_agent_runs_document
                FOREIGN KEY (document_id) REFERENCES docweave.documents (document_id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS docweave.proposals (
            proposal_id UUID PRIMARY KEY,
            document_id UUID NOT NULL,
            agent_run_id UUID NOT NULL,
            proposed_category STRING NOT NULL,
            proposed_directory STRING NOT NULL,
            proposed_filename STRING NOT NULL,
            confidence DECIMAL(8, 6) NOT NULL CHECK (
                confidence >= 0 AND confidence <= 1
            ),
            evidence_summary STRING NOT NULL,
            status STRING NOT NULL CHECK (
                status IN ('needs_review', 'approved', 'rejected')
            ),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_proposals_document
                FOREIGN KEY (document_id) REFERENCES docweave.documents (document_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_proposals_agent_run
                FOREIGN KEY (agent_run_id) REFERENCES docweave.agent_runs (agent_run_id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS docweave.human_decisions (
            human_decision_id UUID PRIMARY KEY,
            proposal_id UUID NOT NULL,
            actor_label STRING NOT NULL,
            decision STRING NOT NULL CHECK (
                decision IN ('approve', 'reject', 'request_changes')
            ),
            reason STRING NULL,
            decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_human_decisions_proposal
                FOREIGN KEY (proposal_id) REFERENCES docweave.proposals (proposal_id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS docweave.file_history (
            file_history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL,
            proposal_id UUID NOT NULL,
            human_decision_id UUID NOT NULL,
            event_sequence INT8 NOT NULL,
            operation STRING NOT NULL CHECK (
                operation IN ('move', 'rename', 'rename_and_move')
            ),
            previous_directory STRING NOT NULL,
            previous_filename STRING NOT NULL,
            next_directory STRING NOT NULL,
            next_filename STRING NOT NULL,
            status STRING NOT NULL CHECK (
                status IN ('planned', 'succeeded', 'failed')
            ),
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            note STRING NULL,
            CONSTRAINT uq_file_history_document_sequence
                UNIQUE (document_id, event_sequence),
            CONSTRAINT fk_file_history_document
                FOREIGN KEY (document_id) REFERENCES docweave.documents (document_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_file_history_proposal
                FOREIGN KEY (proposal_id) REFERENCES docweave.proposals (proposal_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_file_history_decision
                FOREIGN KEY (human_decision_id)
                REFERENCES docweave.human_decisions (human_decision_id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS docweave.document_relationships (
            relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_document_id UUID NOT NULL,
            target_document_id UUID NOT NULL,
            relationship_type STRING NOT NULL,
            confidence DECIMAL(8, 6) NOT NULL CHECK (
                confidence >= 0 AND confidence <= 1
            ),
            evidence_summary STRING NOT NULL,
            created_by_agent_run_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT fk_relationship_agent_run
                FOREIGN KEY (created_by_agent_run_id)
                REFERENCES docweave.agent_runs (agent_run_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_document_relationships_source
                FOREIGN KEY (source_document_id)
                REFERENCES docweave.documents (document_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_document_relationships_target
                FOREIGN KEY (target_document_id)
                REFERENCES docweave.documents (document_id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_documents_workspace_status
        ON docweave.documents (workspace_label, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_file_history_timeline
        ON docweave.file_history (document_id, occurred_at DESC)
        """
    )


def downgrade() -> None:
    """Drop only the simple DocWeave schema."""
    op.execute("DROP SCHEMA IF EXISTS docweave CASCADE")
