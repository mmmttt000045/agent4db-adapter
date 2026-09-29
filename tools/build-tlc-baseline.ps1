# Build the reviewed 6fb11ba code with exactly the current real-data harness.
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$cargo = Join-Path $env:USERPROFILE '.cargo/bin/cargo.exe'
Push-Location $project
try {
    New-Item -ItemType Directory -Path target -Force | Out-Null
    git archive --format=zip --output=target/replay-baseline.zip 6fb11ba
    if ($LASTEXITCODE -ne 0) { throw 'Baseline commit is unavailable.' }
    Expand-Archive -LiteralPath target/replay-baseline.zip -DestinationPath target/replay-baseline -Force
    Copy-Item -LiteralPath src/realbench.rs -Destination target/replay-baseline/src/realbench.rs
    $taskMainPath = Join-Path $project 'target/replay-baseline/src/main.rs'
    $taskMain = [IO.File]::ReadAllText($taskMainPath)
    $taskMain = $taskMain.Replace('mod research;', "mod research;`nmod realbench;")
    $taskMain = $taskMain.Replace('enum Cmd {', "enum Cmd {`n    RealBench(realbench::Options),")
    $taskMain = $taskMain.Replace('    match cli.cmd {', "    match cli.cmd {`n        Cmd::RealBench(options) => realbench::run(&cli.db, cli.pool, &cli.out, options).await?,")
    [IO.File]::WriteAllText($taskMainPath, $taskMain, [Text.UTF8Encoding]::new($false))
    & $cargo build --manifest-path target/replay-baseline/Cargo.toml --target-dir target/baseline-build --locked --release
    if ($LASTEXITCODE -ne 0) { throw 'Baseline build failed.' }
} finally { Pop-Location }
