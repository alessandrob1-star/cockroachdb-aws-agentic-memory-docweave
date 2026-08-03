$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SourceRoot = Join-Path $RepoRoot "services\api"
$DistRoot = Join-Path $RepoRoot "dist"
$PackagePath = Join-Path $DistRoot "docweave-cloud-api.zip"

if (-not (Test-Path -LiteralPath $SourceRoot)) {
    throw "Missing Lambda source root: $SourceRoot"
}

New-Item -ItemType Directory -Force -Path $DistRoot | Out-Null
if (Test-Path -LiteralPath $PackagePath) {
    Remove-Item -LiteralPath $PackagePath
}

$SourceItems = Get-ChildItem -LiteralPath $SourceRoot -Force
Compress-Archive -Path $SourceItems.FullName -DestinationPath $PackagePath

Write-Host "Created $PackagePath"

