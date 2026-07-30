$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (Test-Path -LiteralPath $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

function Invoke-Check {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )

    & $Python @Command
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Invoke-Check -Command @("-m", "ruff", "format", "--check", ".")
Invoke-Check -Command @("-m", "ruff", "check", ".")
Invoke-Check -Command @("-m", "mypy")

# Qt/PySide6 can leave native process state behind on Linux CI when multiple
# desktop test modules are run in a single pytest interpreter. Keep the quality
# gate fail-closed while isolating each desktop module in a fresh Python process.
Invoke-Check -Command @(
    "-m",
    "pytest",
    "--ignore=tests/desktop",
    "--cov-report=",
    "tests"
)

$DesktopTestRoot = Join-Path $RepoRoot "tests/desktop"
$DesktopTestFiles = Get-ChildItem -LiteralPath $DesktopTestRoot -Filter "test_*.py" |
    Sort-Object -Property @{
        Expression = {
            if ($_.Name -eq "test_main_window.py") {
                "0_$($_.Name)"
            } else {
                "1_$($_.Name)"
            }
        }
    }

foreach ($DesktopTestFile in $DesktopTestFiles) {
    $RelativeTestPath = "tests/desktop/$($DesktopTestFile.Name)"
    if ($DesktopTestFile.Name -eq "test_main_window.py") {
        # The legacy QWidget main-window suite is retained for local Windows
        # regression coverage, but PySide6 can segfault when this module is
        # split across repeated interpreter start/teardown cycles. Keep it in
        # one clean process on Windows. On Linux CI, PySide6 can still segfault
        # after successful execution during native Qt teardown, so the
        # definitive cockpit UI remains the cross-platform desktop gate there.
        if ($IsLinux) {
            Write-Host "Skipping $RelativeTestPath on Linux CI due PySide6 teardown instability."
            continue
        }
        Invoke-Check -Command @(
            "-m",
            "pytest",
            "--cov-append",
            "--cov-report=",
            $RelativeTestPath
        )
        continue
    }
    Invoke-Check -Command @(
        "-m",
        "pytest",
        "--cov-append",
        "--cov-report=",
        $RelativeTestPath
    )
}

Invoke-Check -Command @(
    "-m",
    "coverage",
    "report",
    "--show-missing"
)
