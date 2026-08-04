"""Read-only CockroachDB schema report for visible DocWeave memory tables."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from docweave.application_runtime import (
    RuntimeConfigurationError,
    load_runtime_environment_config,
)


@dataclass(frozen=True, slots=True)
class MemoryColumnSchema:
    """One sanitized column description."""

    name: str
    data_type: str
    nullable: bool


@dataclass(frozen=True, slots=True)
class MemoryForeignKeySchema:
    """One sanitized foreign-key edge."""

    column_name: str
    foreign_table_name: str
    foreign_column_name: str
    constraint_name: str


@dataclass(frozen=True, slots=True)
class MemoryTableSchema:
    """One DocWeave memory table and its relational shape."""

    table_name: str
    columns: tuple[MemoryColumnSchema, ...]
    primary_key_columns: tuple[str, ...]
    foreign_keys: tuple[MemoryForeignKeySchema, ...]


@dataclass(frozen=True, slots=True)
class MemorySchemaReport:
    """Sanitized schema report for the configured CockroachDB target."""

    alembic_revision: str | None
    tables: tuple[MemoryTableSchema, ...]


def collect_memory_schema() -> MemorySchemaReport:
    """Collect the configured CockroachDB schema without printing secret values."""
    config = load_runtime_environment_config()
    engine = create_engine(config.database_url, pool_pre_ping=True, future=True)
    return collect_memory_schema_from_engine(engine)


def collect_memory_schema_from_engine(engine: Engine) -> MemorySchemaReport:
    """Collect DocWeave schema metadata from an injected engine."""
    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text(_ALEMBIC_REVISION_SQL)
            ).scalar_one_or_none()
            table_names = tuple(
                str(row[0])
                for row in connection.execute(text(_TABLES_SQL))
                if isinstance(row[0], str)
            )
            columns = _group_columns(connection.execute(text(_COLUMNS_SQL)))
            primary_keys = _group_primary_keys(
                connection.execute(text(_PRIMARY_KEYS_SQL))
            )
            foreign_keys = _group_foreign_keys(
                connection.execute(text(_FOREIGN_KEYS_SQL))
            )
    except SQLAlchemyError as error:
        raise RuntimeError("memory schema report failed") from error

    tables = tuple(
        MemoryTableSchema(
            table_name=table_name,
            columns=columns.get(table_name, ()),
            primary_key_columns=primary_keys.get(table_name, ()),
            foreign_keys=foreign_keys.get(table_name, ()),
        )
        for table_name in table_names
    )
    return MemorySchemaReport(
        alembic_revision=revision if isinstance(revision, str) else None,
        tables=tables,
    )


def main(argv: list[str] | None = None) -> int:
    """Print a sanitized SQL Server Management Studio style schema inventory."""
    parser = argparse.ArgumentParser(
        description=(
            "Inspect DocWeave CockroachDB memory tables, columns, primary keys, "
            "and foreign keys without printing connection values."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of text lines.",
    )
    parser.add_argument(
        "--flat",
        action="store_true",
        help="Print the original flat table inventory instead of object explorer text.",
    )
    args = parser.parse_args(argv)

    try:
        report = collect_memory_schema()
    except RuntimeConfigurationError as error:
        print(f"memory_schema: fail ({error.code.value}:{error.variable_name})")
        return 2
    except RuntimeError as error:
        print(f"memory_schema: fail ({error.__class__.__name__})")
        return 3

    if args.json:
        print(json.dumps(_report_json(report), sort_keys=True, separators=(",", ":")))
    elif args.flat:
        _print_flat_text_report(report)
    else:
        _print_object_explorer_report(report)
    return 0


def _group_columns(rows: Any) -> dict[str, tuple[MemoryColumnSchema, ...]]:
    grouped: dict[str, list[MemoryColumnSchema]] = {}
    for row in rows:
        table_name, column_name, data_type, is_nullable = row[:4]
        if not all(
            isinstance(value, str)
            for value in (table_name, column_name, data_type, is_nullable)
        ):
            continue
        grouped.setdefault(table_name, []).append(
            MemoryColumnSchema(
                name=column_name,
                data_type=data_type,
                nullable=is_nullable.upper() == "YES",
            )
        )
    return {table_name: tuple(columns) for table_name, columns in grouped.items()}


def _group_primary_keys(rows: Any) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[tuple[int, str]]] = {}
    for row in rows:
        table_name, column_name, ordinal_position = row[:3]
        if not isinstance(table_name, str) or not isinstance(column_name, str):
            continue
        grouped.setdefault(table_name, []).append((int(ordinal_position), column_name))
    return {
        table_name: tuple(column for _, column in sorted(columns))
        for table_name, columns in grouped.items()
    }


def _group_foreign_keys(rows: Any) -> dict[str, tuple[MemoryForeignKeySchema, ...]]:
    grouped: dict[str, list[MemoryForeignKeySchema]] = {}
    for row in rows:
        (
            table_name,
            column_name,
            foreign_table_name,
            foreign_column_name,
            constraint_name,
        ) = row[:5]
        if not all(
            isinstance(value, str)
            for value in (
                table_name,
                column_name,
                foreign_table_name,
                foreign_column_name,
                constraint_name,
            )
        ):
            continue
        grouped.setdefault(table_name, []).append(
            MemoryForeignKeySchema(
                column_name=column_name,
                foreign_table_name=foreign_table_name,
                foreign_column_name=foreign_column_name,
                constraint_name=constraint_name,
            )
        )
    return {
        table_name: tuple(sorted(keys, key=lambda key: key.constraint_name))
        for table_name, keys in grouped.items()
    }


def _print_object_explorer_report(report: MemorySchemaReport) -> None:
    print("DocWeave CockroachDB Object Explorer")
    print(f"Revision: {report.alembic_revision or 'missing'}")
    print("Database: docweave")
    print("Schema: docweave")
    print(f"Tables: {len(report.tables)}")
    for table in report.tables:
        primary_key_columns = set(table.primary_key_columns)
        print("")
        print(f"[table] docweave.{table.table_name}")
        primary_key = ", ".join(table.primary_key_columns) or "none"
        print(f"  [primary key] {primary_key}")
        print("  [columns]")
        for column in table.columns:
            nullable = "NULL" if column.nullable else "NOT NULL"
            key_marker = " PK" if column.name in primary_key_columns else ""
            print(f"    - {column.name}: {column.data_type} {nullable}{key_marker}")
        print("  [foreign keys]")
        if table.foreign_keys:
            for foreign_key in table.foreign_keys:
                print(
                    "    - "
                    f"{foreign_key.column_name} -> "
                    f"docweave.{foreign_key.foreign_table_name}."
                    f"{foreign_key.foreign_column_name} "
                    f"({foreign_key.constraint_name})"
                )
        else:
            print("    - none")


def _print_flat_text_report(report: MemorySchemaReport) -> None:
    print(f"memory_schema_revision: {report.alembic_revision or 'missing'}")
    print(f"memory_schema_tables: {len(report.tables)}")
    for table in report.tables:
        primary_key = ", ".join(table.primary_key_columns) or "none"
        print(f"table docweave.{table.table_name}")
        print(f"  primary_key: {primary_key}")
        print("  columns:")
        for column in table.columns:
            nullable = "NULL" if column.nullable else "NOT NULL"
            print(f"    - {column.name}: {column.data_type} {nullable}")
        if table.foreign_keys:
            print("  foreign_keys:")
            for foreign_key in table.foreign_keys:
                print(
                    "    - "
                    f"{foreign_key.column_name} -> "
                    f"docweave.{foreign_key.foreign_table_name}."
                    f"{foreign_key.foreign_column_name} "
                    f"({foreign_key.constraint_name})"
                )
        else:
            print("  foreign_keys: none")


def _report_json(report: MemorySchemaReport) -> dict[str, object]:
    return {
        "alembic_revision": report.alembic_revision,
        "tables": [
            {
                "table_name": table.table_name,
                "primary_key_columns": list(table.primary_key_columns),
                "columns": [
                    {
                        "name": column.name,
                        "data_type": column.data_type,
                        "nullable": column.nullable,
                    }
                    for column in table.columns
                ],
                "foreign_keys": [
                    {
                        "column_name": foreign_key.column_name,
                        "foreign_table_name": foreign_key.foreign_table_name,
                        "foreign_column_name": foreign_key.foreign_column_name,
                        "constraint_name": foreign_key.constraint_name,
                    }
                    for foreign_key in table.foreign_keys
                ],
            }
            for table in report.tables
        ],
    }


_ALEMBIC_REVISION_SQL = """
SELECT version_num
FROM public.alembic_version
LIMIT 1
"""

_TABLES_SQL = """
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'docweave'
  AND table_type = 'BASE TABLE'
ORDER BY table_name
"""

_COLUMNS_SQL = """
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'docweave'
ORDER BY table_name, ordinal_position
"""

_PRIMARY_KEYS_SQL = """
SELECT kcu.table_name, kcu.column_name, kcu.ordinal_position
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
    AND tc.table_name = kcu.table_name
WHERE tc.constraint_type = 'PRIMARY KEY'
    AND tc.table_schema = 'docweave'
ORDER BY kcu.table_name, kcu.ordinal_position
"""

_FOREIGN_KEYS_SQL = """
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    tc.constraint_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
    AND tc.table_name = kcu.table_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
    AND ccu.table_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_schema = 'docweave'
ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position
"""


if __name__ == "__main__":
    raise SystemExit(main())
