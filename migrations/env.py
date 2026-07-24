"""Fail-closed Alembic environment for DocWeave CockroachDB migrations."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

DATABASE_URL_ENVIRONMENT_VARIABLE = "DOCWEAVE_DATABASE_URL"
OFFLINE_DIALECT_URL = (
    "cockroachdb+psycopg://docweave_offline@localhost:26257/"
    "docweave_offline?sslmode=verify-full"
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _configured_database_url(*, offline: bool) -> str:
    database_url = os.environ.get(DATABASE_URL_ENVIRONMENT_VARIABLE)
    if database_url:
        return database_url
    if offline:
        return OFFLINE_DIALECT_URL
    raise RuntimeError(
        f"{DATABASE_URL_ENVIRONMENT_VARIABLE} is required for online migrations"
    )


def run_migrations_offline() -> None:
    """Render migration SQL without opening a database connection."""
    context.configure(
        url=_configured_database_url(offline=True),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        transactional_ddl=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run explicitly authorized migrations against the configured target."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _configured_database_url(offline=False)
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            transactional_ddl=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
