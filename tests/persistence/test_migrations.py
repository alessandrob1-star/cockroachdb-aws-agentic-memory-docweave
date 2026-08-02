from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG_PATH = REPOSITORY_ROOT / "alembic.ini"
DATABASE_URL_ENVIRONMENT_VARIABLE = "DOCWEAVE_DATABASE_URL"
INITIAL_REVISION = "0001_operational_foundation"
CLASSIFICATION_REVISION = "0002_classification_memory"
REVIEW_REVISION = "0003_review_decision_memory"
FILE_LINEAGE_REVISION = "0004_file_lineage_memory"


def alembic_config() -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    return config


def render_upgrade_sql() -> str:
    output = StringIO()
    config = alembic_config()
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    return output.getvalue()


def render_downgrade_sql() -> str:
    output = StringIO()
    config = alembic_config()
    config.output_buffer = output
    command.downgrade(config, "head:base", sql=True)
    return output.getvalue()


def test_migration_history_has_one_expected_head() -> None:
    script = ScriptDirectory.from_config(alembic_config())

    assert script.get_heads() == [FILE_LINEAGE_REVISION]
    assert script.get_base() == INITIAL_REVISION


def test_offline_upgrade_creates_approved_non_vector_memory_tables() -> None:
    sql = render_upgrade_sql()

    expected_tables = {
        "workspaces",
        "actors",
        "workspace_members",
        "operation_batches",
        "file_operations",
        "audit_events",
        "documents",
        "document_versions",
        "taxonomy_versions",
        "taxonomy_classes",
        "agent_runs",
        "proposals",
        "classification_proposals",
        "proposal_evidence",
        "review_decisions",
        "file_lineage_events",
    }
    for table_name in expected_tables:
        assert f"CREATE TABLE docweave.{table_name}" in sql

    assert "CREATE SCHEMA IF NOT EXISTS docweave" in sql
    assert "VECTOR" not in sql
    assert "document_chunks" not in sql
    assert "document_classifications" not in sql
    assert "CREATE ROLE" not in sql


def test_classification_memory_separates_proposals_from_canonical_state() -> None:
    sql = render_upgrade_sql()

    assert "uq_agent_runs_idempotency" in sql
    assert "request_sha256" in sql
    assert "fk_proposals_agent_run_workspace" in sql
    assert "fk_classification_proposals_class" in sql
    assert "fk_proposal_evidence_proposal_workspace" in sql
    assert "proposal_status" in sql
    assert "'needs_review'" in sql
    assert "outcome JSONB NOT NULL" in sql


def test_review_decision_memory_is_attributable_and_bound_to_proposal() -> None:
    sql = render_upgrade_sql()

    assert "CREATE TABLE docweave.review_decisions" in sql
    assert "reviewer_actor_id" in sql
    assert "proposal_sha256" in sql
    assert "operation_plan_sha256" in sql
    assert "fk_review_decisions_proposal_workspace" in sql
    assert "fk_review_decisions_reviewer" in sql
    assert "uq_review_decisions_proposal" in sql
    assert "ck_review_decisions_reason_required" in sql
    assert "ix_review_decisions_workspace_chronology" in sql


def test_file_lineage_memory_records_append_only_path_history() -> None:
    sql = render_upgrade_sql()

    assert "CREATE TABLE docweave.file_lineage_events" in sql
    assert "logical_document_key" in sql
    assert "lineage_sequence" in sql
    assert "original_directory" in sql
    assert "original_filename" in sql
    assert "previous_directory" in sql
    assert "previous_filename" in sql
    assert "next_directory" in sql
    assert "next_filename" in sql
    assert "fk_file_lineage_events_operation_workspace" in sql
    assert "fk_file_lineage_events_proposal_workspace" in sql
    assert "uq_file_lineage_events_document_sequence" in sql
    assert "uq_file_lineage_events_idempotency" in sql
    assert "ck_file_lineage_events_blocked_path" in sql
    assert "ix_file_lineage_events_document_history" in sql


def test_offline_upgrade_enforces_workspace_and_idempotency_boundaries() -> None:
    sql = render_upgrade_sql()

    assert "uq_operation_batches_idempotency" in sql
    assert "uq_file_operations_idempotency" in sql
    assert "fk_file_operations_batch_workspace" in sql
    assert "fk_audit_events_operation_workspace" in sql
    assert "fk_audit_events_previous_workspace" in sql
    assert "BETWEEN 1 AND 1000" in sql


def test_offline_upgrade_contains_operation_recovery_contracts() -> None:
    sql = render_upgrade_sql()

    assert "expected_source_sha256" in sql
    assert "intent_recorded_at" in sql
    assert "lease_expires_at" in sql
    assert "reconciliation_state" in sql
    assert "verification_failed" in sql
    assert "ix_file_operations_reconciliation" in sql
    assert "octet_length(plan_sha256) = 32" in sql
    assert "ck_file_operations_execution_intent" in sql
    assert "ck_file_operations_success_evidence" in sql
    assert "ck_file_operations_failed_verification_reconciliation" in sql


def test_offline_upgrade_contains_append_only_audit_storage_shape() -> None:
    sql = render_upgrade_sql()

    assert "event_sequence" in sql
    assert "previous_event_id" in sql
    assert "previous_event_sha256" in sql
    assert "event_sha256" in sql
    assert "ix_audit_events_workspace_chronology" in sql
    assert "ix_audit_events_subject_history" in sql
    assert "document_text" not in sql
    assert "document_bytes" not in sql


def test_offline_downgrade_drops_tables_in_dependency_order() -> None:
    sql = render_downgrade_sql()
    expected_order = [
        "DROP TABLE docweave.file_lineage_events",
        "DROP TABLE docweave.review_decisions",
        "DROP TABLE docweave.proposal_evidence",
        "DROP TABLE docweave.classification_proposals",
        "DROP TABLE docweave.proposals",
        "DROP TABLE docweave.agent_runs",
        "DROP TABLE docweave.taxonomy_classes",
        "DROP TABLE docweave.taxonomy_versions",
        "DROP TABLE docweave.document_versions",
        "DROP TABLE docweave.documents",
        "DROP TABLE docweave.audit_events",
        "DROP TABLE docweave.file_operations",
        "DROP TABLE docweave.operation_batches",
        "DROP TABLE docweave.workspace_members",
        "DROP TABLE docweave.actors",
        "DROP TABLE docweave.workspaces",
        "DROP SCHEMA IF EXISTS docweave",
    ]

    offsets = [sql.index(statement) for statement in expected_order]

    assert offsets == sorted(offsets)


def test_migrations_render_without_false_transactional_ddl_boundary() -> None:
    upgrade_sql = render_upgrade_sql()

    assert "BEGIN;" not in upgrade_sql
    assert "COMMIT;" not in upgrade_sql


def test_online_migration_fails_closed_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)

    with pytest.raises(
        RuntimeError,
        match="DOCWEAVE_DATABASE_URL is required for online migrations",
    ):
        command.upgrade(alembic_config(), "head")


def test_repository_configuration_contains_no_connection_secret() -> None:
    configuration_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ALEMBIC_CONFIG_PATH,
            REPOSITORY_ROOT / "migrations" / "env.py",
        )
    ).casefold()

    assert "docweave_admin" not in configuration_text
    assert "aws account" not in configuration_text
    assert "password=" not in configuration_text
    assert "postgresql://" not in configuration_text
