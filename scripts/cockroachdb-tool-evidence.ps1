param(
    [string]$ClusterId = "b5ed9ba5-5130-409c-b22b-6e5f8ba64e44"
)

$ErrorActionPreference = "Stop"

$ccloudCommand = Get-Command ccloud -ErrorAction SilentlyContinue
$ccloudPath = if ($null -eq $ccloudCommand) { $null } else { $ccloudCommand.Source }
if ($null -eq $ccloudPath) {
    $candidate = Join-Path $env:APPDATA "ccloud\ccloud.exe"
    if (Test-Path $candidate) {
        $ccloudPath = $candidate
    }
}

if ($null -eq $ccloudPath) {
    throw "ccloud CLI is required. Install it from CockroachDB Cloud documentation."
}

Write-Output "== CockroachDB tool: ccloud CLI =="
& $ccloudPath version
& $ccloudPath auth whoami
& $ccloudPath cluster info $ClusterId -o json
& $ccloudPath cluster user list $ClusterId -o json

Write-Output "== CockroachDB tool: Agent Skills Repo =="
Write-Output "Repo: https://github.com/cockroachlabs/cockroachdb-skills"
Write-Output "Pinned HEAD used for DocWeave review: e14e86d23ce8ee2e7e40a34ce2944c2502b6eadd"
Write-Output "Skills applied: cockroachdb-sql; designing-application-transactions"
