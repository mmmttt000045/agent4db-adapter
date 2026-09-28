param(
    [ValidateRange(1000, 50000000)][int]$Rows = 100000,
    [ValidateRange(1, 128)][int]$Agents = 24,
    [ValidateRange(1, 1024)][int]$Variants = 16,
    [ValidateRange(1, 16)][int]$Repeats = 2,
    [ValidateRange(1, 40)][int]$Rounds = 5,
    [ValidateRange(1, 128)][int]$Pool = 16,
    [uint64]$Seed = 42,
    [switch]$NoResultCache,
    [switch]$CapacityOnly,
    [string]$Corpus,
    [string]$Resume
)
$ErrorActionPreference = 'Stop'
$cargo = Get-Command cargo -ErrorAction SilentlyContinue
$cargoPath = if ($cargo) { $cargo.Source } else { Join-Path $env:USERPROFILE '.cargo\bin\cargo.exe' }
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    $options = @('run', '--release', '--locked', '--', '--pool', $Pool, 'research', '--rows', $Rows,
        '--agents', $Agents, '--variants', $Variants, '--repeats', $Repeats, '--rounds', $Rounds, '--seed', $Seed)
    if ($NoResultCache) { $options += '--no-result-cache' }
    if ($CapacityOnly) { $options += '--capacity-only' }
    if ($Corpus) { $options += @('--corpus', $Corpus) }
    if ($Resume) { $options += @('--resume', $Resume) }
    & $cargoPath @options
    if ($LASTEXITCODE -ne 0) { throw 'Research run failed; inspect results/research-*/failure.json.' }
} finally { Pop-Location }
