from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = REPO_ROOT / "launch-docweave-dashboard.cmd"


def test_windows_dashboard_launcher_is_versioned() -> None:
    assert LAUNCHER_PATH.is_file()


def test_windows_dashboard_launcher_uses_local_environment() -> None:
    launcher = LAUNCHER_PATH.read_text(encoding="utf-8")

    assert "%~dp0" in launcher
    assert "%APPDATA%\\DocWeave\\launch-docweave-runtime.cmd" in launcher
    assert ".venv\\Scripts\\docweave-desktop.exe" in launcher
    assert "-m docweave.desktop.application" in launcher
    assert "PYTHONPATH=%DOCWEAVE_REPO_DIR%src;%PYTHONPATH%" in launcher


def test_windows_dashboard_launcher_does_not_embed_runtime_secrets() -> None:
    launcher = LAUNCHER_PATH.read_text(encoding="utf-8").lower()

    forbidden_fragments = (
        "docweave_database_url",
        "aws_secret",
        "aws_access_key",
        "password",
        "cockroachdb+",
    )

    assert all(fragment not in launcher for fragment in forbidden_fragments)
