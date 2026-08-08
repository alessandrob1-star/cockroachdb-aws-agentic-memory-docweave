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
    foreign_table_schema: str
    foreign_table_name: str
    foreign_column_name: str
    constraint_name: str


@dataclass(frozen=True, slots=True)
class MemoryTableSchema:
    """One DocWeave memory table and its relational shape."""

    schema_name: str
    table_name: str
    object_type: str
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
            revision = "simple_docweave_schema"
            objects = tuple(
                (str(row[0]), str(row[1]), _normalize_object_type(str(row[2])))
                for row in connection.execute(text(_TABLES_SQL))
                if (
                    isinstance(row[0], str)
                    and isinstance(row[1], str)
                    and isinstance(row[2], str)
                )
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
            schema_name=schema_name,
            table_name=table_name,
            object_type=object_type,
            columns=columns.get((schema_name, table_name), ()),
            primary_key_columns=primary_keys.get((schema_name, table_name), ()),
            foreign_keys=foreign_keys.get((schema_name, table_name), ()),
        )
        for schema_name, table_name, object_type in objects
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


def _group_columns(rows: Any) -> dict[tuple[str, str], tuple[MemoryColumnSchema, ...]]:
    grouped: dict[tuple[str, str], list[MemoryColumnSchema]] = {}
    for row in rows:
        schema_name, table_name, column_name, data_type, is_nullable = row[:5]
        if not all(
            isinstance(value, str)
            for value in (
                schema_name,
                table_name,
                column_name,
                data_type,
                is_nullable,
            )
        ):
            continue
        grouped.setdefault((schema_name, table_name), []).append(
            MemoryColumnSchema(
                name=column_name,
                data_type=data_type,
                nullable=is_nullable.upper() == "YES",
            )
        )
    return {table: tuple(columns) for table, columns in grouped.items()}


def _group_primary_keys(rows: Any) -> dict[tuple[str, str], tuple[str, ...]]:
    grouped: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for row in rows:
        schema_name, table_name, column_name, ordinal_position = row[:4]
        if not all(
            isinstance(value, str) for value in (schema_name, table_name, column_name)
        ):
            continue
        grouped.setdefault((schema_name, table_name), []).append(
            (int(ordinal_position), column_name)
        )
    return {
        table: tuple(column for _, column in sorted(columns))
        for table, columns in grouped.items()
    }


def _group_foreign_keys(
    rows: Any,
) -> dict[tuple[str, str], tuple[MemoryForeignKeySchema, ...]]:
    grouped: dict[tuple[str, str], list[MemoryForeignKeySchema]] = {}
    for row in rows:
        (
            schema_name,
            table_name,
            column_name,
            foreign_table_schema,
            foreign_table_name,
            foreign_column_name,
            constraint_name,
        ) = row[:7]
        if not all(
            isinstance(value, str)
            for value in (
                schema_name,
                table_name,
                column_name,
                foreign_table_schema,
                foreign_table_name,
                foreign_column_name,
                constraint_name,
            )
        ):
            continue
        grouped.setdefault((schema_name, table_name), []).append(
            MemoryForeignKeySchema(
                column_name=column_name,
                foreign_table_schema=foreign_table_schema,
                foreign_table_name=foreign_table_name,
                foreign_column_name=foreign_column_name,
                constraint_name=constraint_name,
            )
        )
    return {
        table: tuple(sorted(keys, key=lambda key: key.constraint_name))
        for table, keys in grouped.items()
    }


def _normalize_object_type(table_type: str) -> str:
    normalized = table_type.casefold().replace("base ", "")
    return "view" if normalized == "view" else "table"


def _print_object_explorer_report(report: MemorySchemaReport) -> None:
    print("DocWeave CockroachDB Object Explorer")
    print(f"Revision: {report.alembic_revision or 'missing'}")
    print("Database: docweave")
    print("Schemas: docweave")
    table_count = sum(1 for table in report.tables if table.object_type == "table")
    view_count = sum(1 for table in report.tables if table.object_type == "view")
    print(f"Tables: {table_count}")
    print(f"Views: {view_count}")
    for table in report.tables:
        primary_key_columns = set(table.primary_key_columns)
        print("")
        print(f"[{table.object_type}] {table.schema_name}.{table.table_name}")
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
                    f"{foreign_key.foreign_table_schema}."
                    f"{foreign_key.foreign_table_name}."
                    f"{foreign_key.foreign_column_name} "
                    f"({foreign_key.constraint_name})"
                )
        else:
            print("    - none")


def _print_flat_text_report(report: MemorySchemaReport) -> None:
    print(f"memory_schema_revision: {report.alembic_revision or 'missing'}")
    table_count = sum(1 for table in report.tables if table.object_type == "table")
    view_count = sum(1 for table in report.tables if table.object_type == "view")
    print(f"memory_schema_tables: {table_count}")
    print(f"memory_schema_views: {view_count}")
    for table in report.tables:
        primary_key = ", ".join(table.primary_key_columns) or "none"
        print(f"{table.object_type} {table.schema_name}.{table.table_name}")
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
                    f"{foreign_key.foreign_table_schema}."
                    f"{foreign_key.foreign_table_name}."
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
                "schema_name": table.schema_name,
                "object_type": table.object_type,
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
                        "foreign_table_schema": foreign_key.foreign_table_schema,
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


_TABLES_SQL = """
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'docweave'
ORDER BY table_name
"""

_COLUMNS_SQL = """
SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'docweave'
ORDER BY table_schema, table_name, ordinal_position
"""

_PRIMARY_KEYS_SQL = """
SELECT kcu.table_schema, kcu.table_name, kcu.column_name, kcu.ordinal_position
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
    AND tc.table_name = kcu.table_name
WHERE tc.constraint_type = 'PRIMARY KEY'
    AND tc.table_schema = 'docweave'
ORDER BY kcu.table_schema, kcu.table_name, kcu.ordinal_position
"""

_FOREIGN_KEYS_SQL = """
SELECT
    tc.table_schema,
    tc.table_name,
    kcu.column_name,
    ccu.table_schema AS foreign_table_schema,
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
ORDER BY tc.table_schema, tc.table_name, tc.constraint_name, kcu.ordinal_position
"""


if __name__ == "__main__":
    raise SystemExit(main())
