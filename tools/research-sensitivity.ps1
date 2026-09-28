param(
    [ValidateRange(1000, 50000000)][int]$Rows = 100000,
    [ValidateRange(1, 128)][int]$Agents = 64,
    [ValidateRange(1, 1024)][int]$Variants = 4,
    [ValidateRange(1, 40)][int]$Rounds = 5
)
# Sequential paired experiments: identical controls, only result-cache differs.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'research.ps1') -Rows $Rows -Agents $Agents -Variants $Variants -Rounds $Rounds
& (Join-Path $PSScriptRoot 'research.ps1') -Rows $Rows -Agents $Agents -Variants $Variants -Rounds $Rounds -NoResultCache
