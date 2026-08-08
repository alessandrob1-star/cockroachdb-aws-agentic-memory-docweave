"""Create judged hackathon memory schema.

Revision ID: 0007_judged_memory_schema
Revises: 0006_readable_file_path_history_view
Create Date: 2026-08-08
"""

# ruff: noqa: E501

from collections.abc import Sequence

from alembic import op

revision: str = "0007_judged_memory_schema"
down_revision: str | None = "0006_readable_file_path_history_view"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the simple CockroachDB memory graph used for judging."""
    op.execute("CREATE SCHEMA IF NOT EXISTS docweave_judged")
    op.execute(
        """
        CREATE TABLE docweave_judged.documents (
            document_id UUID NOT NULL DEFAULT gen_random_uuid(),
            workspace_label STRING NOT NULL,
            original_directory STRING NOT NULL,
            original_filename STRING NOT NULL,
            current_directory STRING NOT NULL,
            current_filename STRING NOT NULL,
            content_sha256 BYTES NOT NULL,
            page_count INT8 NULL,
            status STRING NOT NULL DEFAULT 'discovered',
            discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_judged_documents PRIMARY KEY (document_id),
            CONSTRAINT uq_judged_documents_content UNIQUE (workspace_label, content_sha256),
            CONSTRAINT ck_judged_documents_original_filename CHECK (length(trim(original_filename)) > 0),
            CONSTRAINT ck_judged_documents_current_filename CHECK (length(trim(current_filename)) > 0),
            CONSTRAINT ck_judged_documents_content_sha CHECK (octet_length(content_sha256) = 32),
            CONSTRAINT ck_judged_documents_status CHECK (
                status IN ('discovered', 'analyzed', 'proposed', 'approved', 'moved', 'restored', 'blocked')
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE docweave_judged.agent_runs (
            agent_run_id UUID NOT NULL DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL,
            provider STRING NOT NULL,
            model_id STRING NOT NULL,
            task STRING NOT NULL,
            status STRING NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ NULL,
            input_sha256 BYTES NOT NULL,
            output_json JSONB NOT NULL,
            summary STRING NOT NULL,
            CONSTRAINT pk_judged_agent_runs PRIMARY KEY (agent_run_id),
            CONSTRAINT fk_judged_agent_runs_document FOREIGN KEY (document_id)
                REFERENCES docweave_judged.documents (document_id) ON DELETE RESTRICT,
            CONSTRAINT ck_judged_agent_runs_input_sha CHECK (octet_length(input_sha256) = 32),
            CONSTRAINT ck_judged_agent_runs_status CHECK (
                status IN ('succeeded', 'failed', 'blocked')
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE docweave_judged.proposals (
            proposal_id UUID NOT NULL DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL,
            agent_run_id UUID NOT NULL,
            proposed_category STRING NOT NULL,
            proposed_directory STRING NOT NULL,
            proposed_filename STRING NOT NULL,
            confidence DECIMAL(5, 4) NOT NULL,
            evidence_summary STRING NOT NULL,
            status STRING NOT NULL DEFAULT 'needs_review',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_judged_proposals PRIMARY KEY (proposal_id),
            CONSTRAINT fk_judged_proposals_document FOREIGN KEY (document_id)
                REFERENCES docweave_judged.documents (document_id) ON DELETE RESTRICT,
            CONSTRAINT fk_judged_proposals_agent_run FOREIGN KEY (agent_run_id)
                REFERENCES docweave_judged.agent_runs (agent_run_id) ON DELETE RESTRICT,
            CONSTRAINT ck_judged_proposals_filename CHECK (length(trim(proposed_filename)) > 0),
            CONSTRAINT ck_judged_proposals_confidence CHECK (confidence >= 0 AND confidence <= 1),
            CONSTRAINT ck_judged_proposals_status CHECK (
                status IN ('needs_review', 'approved', 'rejected', 'executed', 'blocked')
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE docweave_judged.human_decisions (
            human_decision_id UUID NOT NULL DEFAULT gen_random_uuid(),
            proposal_id UUID NOT NULL,
            actor_label STRING NOT NULL,
            decision STRING NOT NULL,
            reason STRING NULL,
            decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_judged_human_decisions PRIMARY KEY (human_decision_id),
            CONSTRAINT fk_judged_human_decisions_proposal FOREIGN KEY (proposal_id)
                REFERENCES docweave_judged.proposals (proposal_id) ON DELETE RESTRICT,
            CONSTRAINT ck_judged_human_decisions_actor CHECK (length(trim(actor_label)) > 0),
            CONSTRAINT ck_judged_human_decisions_decision CHECK (
                decision IN ('approve', 'reject', 'request_changes')
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE docweave_judged.file_history (
            file_history_id UUID NOT NULL DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL,
            proposal_id UUID NULL,
            human_decision_id UUID NULL,
            event_sequence INT8 NOT NULL,
            operation STRING NOT NULL,
            previous_directory STRING NOT NULL,
            previous_filename STRING NOT NULL,
            next_directory STRING NOT NULL,
            next_filename STRING NOT NULL,
            status STRING NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            note STRING NULL,
            CONSTRAINT pk_judged_file_history PRIMARY KEY (file_history_id),
            CONSTRAINT uq_judged_file_history_sequence UNIQUE (document_id, event_sequence),
            CONSTRAINT fk_judged_file_history_document FOREIGN KEY (document_id)
                REFERENCES docweave_judged.documents (document_id) ON DELETE RESTRICT,
            CONSTRAINT fk_judged_file_history_proposal FOREIGN KEY (proposal_id)
                REFERENCES docweave_judged.proposals (proposal_id) ON DELETE RESTRICT,
            CONSTRAINT fk_judged_file_history_decision FOREIGN KEY (human_decision_id)
                REFERENCES docweave_judged.human_decisions (human_decision_id) ON DELETE RESTRICT,
            CONSTRAINT ck_judged_file_history_sequence CHECK (event_sequence > 0),
            CONSTRAINT ck_judged_file_history_operation CHECK (
                operation IN ('scan', 'propose', 'approve', 'rename', 'move', 'rename_and_move', 'restore', 'blocked')
            ),
            CONSTRAINT ck_judged_file_history_filenames CHECK (
                length(trim(previous_filename)) > 0 AND length(trim(next_filename)) > 0
            ),
            CONSTRAINT ck_judged_file_history_status CHECK (
                status IN ('planned', 'succeeded', 'failed', 'blocked')
            )
        )
        """
    )
    op.execute(
        """
        CREATE TABLE docweave_judged.document_relationships (
            relationship_id UUID NOT NULL DEFAULT gen_random_uuid(),
            source_document_id UUID NOT NULL,
            target_document_id UUID NOT NULL,
            relationship_type STRING NOT NULL,
            confidence DECIMAL(5, 4) NOT NULL,
            evidence_summary STRING NOT NULL,
            created_by_agent_run_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_judged_document_relationships PRIMARY KEY (relationship_id),
            CONSTRAINT fk_judged_relationship_source FOREIGN KEY (source_document_id)
                REFERENCES docweave_judged.documents (document_id) ON DELETE RESTRICT,
            CONSTRAINT fk_judged_relationship_target FOREIGN KEY (target_document_id)
                REFERENCES docweave_judged.documents (document_id) ON DELETE RESTRICT,
            CONSTRAINT fk_judged_relationship_agent_run FOREIGN KEY (created_by_agent_run_id)
                REFERENCES docweave_judged.agent_runs (agent_run_id) ON DELETE RESTRICT,
            CONSTRAINT ck_judged_relationship_distinct CHECK (source_document_id <> target_document_id),
            CONSTRAINT ck_judged_relationship_confidence CHECK (confidence >= 0 AND confidence <= 1),
            CONSTRAINT ck_judged_relationship_type CHECK (
                relationship_type IN ('purchase_order_to_invoice', 'invoice_to_payment', 'contract_to_invoice', 'same_dossier', 'possible_duplicate')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_judged_documents_current_path
            ON docweave_judged.documents (workspace_label, current_directory, current_filename)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_judged_proposals_review_queue
            ON docweave_judged.proposals (status, confidence DESC, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_judged_file_history_timeline
            ON docweave_judged.file_history (document_id, event_sequence)
        """
    )


def downgrade() -> None:
    """Remove the judged hackathon schema."""
    op.execute("DROP SCHEMA IF EXISTS docweave_judged CASCADE")
