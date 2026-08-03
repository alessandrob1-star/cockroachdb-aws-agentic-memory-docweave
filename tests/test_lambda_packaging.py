from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SCRIPT = REPOSITORY_ROOT / "scripts" / "package-aws-lambda.ps1"
SERVICE_REQUIREMENTS = REPOSITORY_ROOT / "services" / "api" / "requirements.txt"


def _nonempty_lines(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def test_lambda_package_installs_dedicated_cloud_requirements() -> None:
    script = PACKAGE_SCRIPT.read_text(encoding="utf-8")

    assert '$RequirementsPath = Join-Path $SourceRoot "requirements.txt"' in script
    assert "--only-binary=:all:" in script
    assert "--platform $LambdaPlatform" in script
    assert "--implementation cp" in script
    assert "--python-version $LambdaPythonVersion" in script
    assert "--target $StagingRoot" in script
    assert "-r $RequirementsPath" in script
    assert (
        'Copy-Item -LiteralPath (Join-Path $SourceRoot "docweave_cloud_api")' in script
    )


def test_lambda_package_removes_only_validated_staging_directory() -> None:
    script = PACKAGE_SCRIPT.read_text(encoding="utf-8")

    assert '$StagingRoot = Join-Path $DistRoot "docweave-cloud-api-staging"' in script
    assert "Resolve-Path -LiteralPath $StagingRoot" in script
    assert "StartsWith($ResolvedDistRoot" in script
    assert "Remove-Item -LiteralPath $StagingRoot -Recurse -Force" in script


def test_cloud_runtime_requirements_avoid_desktop_only_dependencies() -> None:
    requirements = _nonempty_lines(SERVICE_REQUIREMENTS)

    assert requirements == {
        "boto3==1.43.56",
        "botocore==1.43.56",
        "greenlet==3.2.5",
        "jmespath==1.1.0",
        "psycopg[binary]==3.3.4",
        "python-dateutil==2.9.0.post0",
        "s3transfer==0.19.2",
        "six==1.17.0",
        "SQLAlchemy==2.0.51",
        "sqlalchemy-cockroachdb==2.0.4",
        "typing_extensions==4.16.0",
        "tzdata==2026.3",
        "urllib3==2.7.0",
    }
    assert not any(requirement.startswith("PySide6") for requirement in requirements)
