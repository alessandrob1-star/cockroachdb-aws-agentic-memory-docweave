from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG_PATH = REPOSITORY_ROOT / "alembic.ini"
DATABASE_URL_ENVIRONMENT_VARIABLE = "DOCWEAVE_DATABASE_URL"
SIMPLE_SCHEMA_REVISION = "0001_simple_docweave_schema"


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


def test_migration_history_has_one_simple_head() -> None:
    script = ScriptDirectory.from_config(alembic_config())

    assert script.get_heads() == [SIMPLE_SCHEMA_REVISION]
    assert script.get_base() == SIMPLE_SCHEMA_REVISION


def test_offline_upgrade_creates_only_simple_docweave_memory_tables() -> None:
    sql = render_upgrade_sql()

    expected_tables = {
        "documents",
        "agent_runs",
        "proposals",
        "human_decisions",
        "file_history",
        "document_relationships",
    }
    for table_name in expected_tables:
        assert f"CREATE TABLE IF NOT EXISTS docweave.{table_name}" in sql

    removed_tables = {
        "workspaces",
        "actors",
        "operation_batches",
        "file_operations",
        "classification_proposals",
        "review_decisions",
        "file_lineage_events",
        "cloud_analysis_jobs",
        "cloud_analysis_objects",
    }
    for table_name in removed_tables:
        assert f"docweave.{table_name}" not in sql

    assert "CREATE SCHEMA IF NOT EXISTS docweave" in sql
    assert "docweave_judged" not in sql
    assert "CREATE VIEW" not in sql
    assert "VECTOR" not in sql
    assert "CREATE ROLE" not in sql


def test_simple_schema_records_original_current_and_reviewed_paths() -> None:
    sql = render_upgrade_sql()

    assert "original_directory" in sql
    assert "original_filename" in sql
    assert "current_directory" in sql
    assert "current_filename" in sql
    assert "previous_directory" in sql
    assert "previous_filename" in sql
    assert "next_directory" in sql
    assert "next_filename" in sql
    assert "fk_file_history_document" in sql
    assert "fk_file_history_proposal" in sql
    assert "fk_file_history_decision" in sql
    assert "ix_file_history_timeline" in sql


def test_simple_schema_keeps_model_run_and_human_decision_separate() -> None:
    sql = render_upgrade_sql()

    assert "CREATE TABLE IF NOT EXISTS docweave.agent_runs" in sql
    assert "provider STRING NOT NULL" in sql
    assert "model_id STRING NOT NULL" in sql
    assert "output_json JSONB NOT NULL" in sql
    assert "CREATE TABLE IF NOT EXISTS docweave.human_decisions" in sql
    assert "actor_label STRING NOT NULL" in sql
    assert "decision STRING NOT NULL" in sql
    assert "fk_human_decisions_proposal" in sql


def test_offline_downgrade_drops_only_docweave_schema() -> None:
    sql = render_downgrade_sql()

    assert "DROP SCHEMA IF EXISTS docweave CASCADE" in sql
    assert "docweave_judged" not in sql


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
