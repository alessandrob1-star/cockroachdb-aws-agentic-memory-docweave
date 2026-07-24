import tomllib
from importlib.metadata import version
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_RUNTIME_REQUIREMENTS = {
    "psycopg[binary]==3.3.4",
    "SQLAlchemy==2.0.51",
    "sqlalchemy-cockroachdb==2.0.4",
}
EXPECTED_INSTALLED_VERSIONS = {
    "alembic": "1.18.5",
    "psycopg": "3.3.4",
    "psycopg-binary": "3.3.4",
    "SQLAlchemy": "2.0.51",
    "sqlalchemy-cockroachdb": "2.0.4",
}


def nonempty_lines(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def test_runtime_dependency_manifests_match() -> None:
    runtime_requirements = nonempty_lines(REPOSITORY_ROOT / "requirements.txt")
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert runtime_requirements == EXPECTED_RUNTIME_REQUIREMENTS
    assert set(pyproject["project"]["dependencies"]) == runtime_requirements


def test_resolved_lock_contains_every_direct_dependency() -> None:
    locked_requirements = nonempty_lines(REPOSITORY_ROOT / "requirements-lock.txt")

    assert "psycopg==3.3.4" in locked_requirements
    assert "psycopg-binary==3.3.4" in locked_requirements
    assert "SQLAlchemy==2.0.51" in locked_requirements
    assert "sqlalchemy-cockroachdb==2.0.4" in locked_requirements
    assert "alembic==1.18.5" in locked_requirements
    assert all("==" in requirement for requirement in locked_requirements)


def test_installed_migration_dependencies_match_approved_versions() -> None:
    installed_versions = {
        package_name: version(package_name)
        for package_name in EXPECTED_INSTALLED_VERSIONS
    }

    assert installed_versions == EXPECTED_INSTALLED_VERSIONS
