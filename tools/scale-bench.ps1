param(
    [ValidateRange(1000, 5000000)][int]$Rows = 1000000,
    [ValidateRange(1, 128)][int]$Agents = 24,
    [ValidateRange(8, 1000)][int]$Tasks = 48,
    [ValidateRange(1, 10)][int]$Rounds = 3,
    [ValidateRange(1, 128)][int]$Pool = 16,
    [uint32]$Seed = 42
)
$ErrorActionPreference = 'Stop'
$cargo = Get-Command cargo -ErrorAction SilentlyContinue
$cargoPath = if ($cargo) { $cargo.Source } else { Join-Path $env:USERPROFILE '.cargo\bin\cargo.exe' }
if (-not (Test-Path -LiteralPath $cargoPath)) { throw 'Cargo was not found.' }
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    & $cargoPath run --locked -- --pool $Pool bench --rows $Rows --agents $Agents --tasks $Tasks --rounds $Rounds --seed $Seed
    if ($LASTEXITCODE -ne 0) { throw 'Benchmark failed. See results/bench-* for details.' }
} finally {
    Pop-Location
}
