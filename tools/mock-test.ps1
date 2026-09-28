# PostgreSQL connection is read from AGENTDB_TEST_URL or the ignored root .env file.
# The test creates and drops its own database; the supplied database is not modified.
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$cargo = Get-Command cargo -ErrorAction SilentlyContinue
if ($cargo) {
    $cargoPath = $cargo.Source
} else {
    $cargoPath = Join-Path $env:USERPROFILE '.cargo\bin\cargo.exe'
    if (-not (Test-Path -LiteralPath $cargoPath)) { throw 'Cargo was not found. Install Rust or add Cargo to PATH.' }
}
Push-Location $project
try {
    & $cargoPath test --locked -- --include-ignored --nocapture
    if ($LASTEXITCODE -ne 0) { throw 'Mock integration tests failed; inspect the output and results/mock-*/report.json.' }
    & $cargoPath clippy --locked --all-targets -- -D warnings
    if ($LASTEXITCODE -ne 0) { throw 'Clippy failed.' }
    & $cargoPath fmt --check
    if ($LASTEXITCODE -ne 0) { throw 'Formatting check failed.' }
    Write-Host 'All tests passed. Integration reports and optimizer audit logs are in results/mock-*.'
} finally {
    Pop-Location
}
