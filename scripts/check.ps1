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
Invoke-Check -Command @("-m", "pytest")
