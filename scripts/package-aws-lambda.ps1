$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SourceRoot = Join-Path $RepoRoot "services\api"
$DistRoot = Join-Path $RepoRoot "dist"
$PackagePath = Join-Path $DistRoot "docweave-cloud-api.zip"
$StagingRoot = Join-Path $DistRoot "docweave-cloud-api-staging"
$RequirementsPath = Join-Path $SourceRoot "requirements.txt"
$LambdaPlatform = if ($env:DOCWEAVE_LAMBDA_PACKAGE_PLATFORM) {
    $env:DOCWEAVE_LAMBDA_PACKAGE_PLATFORM
} else {
    "manylinux2014_aarch64"
}
$LambdaPythonVersion = if ($env:DOCWEAVE_LAMBDA_PACKAGE_PYTHON_VERSION) {
    $env:DOCWEAVE_LAMBDA_PACKAGE_PYTHON_VERSION
} else {
    "3.12"
}
$Python = if ($env:DOCWEAVE_LAMBDA_PACKAGE_PYTHON) {
    $env:DOCWEAVE_LAMBDA_PACKAGE_PYTHON
} else {
    "python"
}

if (-not (Test-Path -LiteralPath $SourceRoot)) {
    throw "Missing Lambda source root: $SourceRoot"
}

New-Item -ItemType Directory -Force -Path $DistRoot | Out-Null
if (Test-Path -LiteralPath $PackagePath) {
    Remove-Item -LiteralPath $PackagePath
}

if (Test-Path -LiteralPath $StagingRoot) {
    $ResolvedDistRoot = (Resolve-Path -LiteralPath $DistRoot).Path
    $ResolvedStagingRoot = (Resolve-Path -LiteralPath $StagingRoot).Path
    if (-not $ResolvedStagingRoot.StartsWith($ResolvedDistRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove unexpected Lambda staging root: $ResolvedStagingRoot"
    }
    Remove-Item -LiteralPath $StagingRoot -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $StagingRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $SourceRoot "docweave_cloud_api") -Destination $StagingRoot -Recurse

if (-not (Test-Path -LiteralPath $RequirementsPath)) {
    throw "Missing Lambda requirements manifest: $RequirementsPath"
}

& $Python -m pip install `
    --disable-pip-version-check `
    --no-input `
    --only-binary=:all: `
    --platform $LambdaPlatform `
    --implementation cp `
    --python-version $LambdaPythonVersion `
    --target $StagingRoot `
    -r $RequirementsPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$PackageItems = Get-ChildItem -LiteralPath $StagingRoot -Force
Compress-Archive -Path $PackageItems.FullName -DestinationPath $PackagePath

Write-Host "Created $PackagePath"
