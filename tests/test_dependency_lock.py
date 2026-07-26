import tomllib
from importlib.metadata import version
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_RUNTIME_REQUIREMENTS = {
    "boto3==1.43.56",
    "psycopg[binary]==3.3.4",
    "PySide6==6.11.1",
    "SQLAlchemy==2.0.51",
    "sqlalchemy-cockroachdb==2.0.4",
}
EXPECTED_INSTALLED_VERSIONS = {
    "alembic": "1.18.5",
    "boto3": "1.43.56",
    "botocore": "1.43.56",
    "jmespath": "1.1.0",
    "psycopg": "3.3.4",
    "psycopg-binary": "3.3.4",
    "PySide6": "6.11.1",
    "PySide6-Addons": "6.11.1",
    "PySide6-Essentials": "6.11.1",
    "shiboken6": "6.11.1",
    "s3transfer": "0.19.2",
    "six": "1.17.0",
    "SQLAlchemy": "2.0.51",
    "sqlalchemy-cockroachdb": "2.0.4",
    "python-dateutil": "2.9.0.post0",
    "urllib3": "2.7.0",
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
    assert "PySide6==6.11.1" in locked_requirements
    assert "PySide6_Addons==6.11.1" in locked_requirements
    assert "PySide6_Essentials==6.11.1" in locked_requirements
    assert "shiboken6==6.11.1" in locked_requirements
    assert "SQLAlchemy==2.0.51" in locked_requirements
    assert "sqlalchemy-cockroachdb==2.0.4" in locked_requirements
    assert "alembic==1.18.5" in locked_requirements
    assert "boto3==1.43.56" in locked_requirements
    assert "botocore==1.43.56" in locked_requirements
    assert all("==" in requirement for requirement in locked_requirements)


def test_installed_migration_dependencies_match_approved_versions() -> None:
    installed_versions = {
        package_name: version(package_name)
        for package_name in EXPECTED_INSTALLED_VERSIONS
    }

    assert installed_versions == EXPECTED_INSTALLED_VERSIONS
