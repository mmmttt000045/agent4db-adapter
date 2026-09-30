[CmdletBinding()]
param()

$taskSource = Join-Path $PSScriptRoot 'main.tex'
$taskTarget = Join-Path $PSScriptRoot 'main-en.tex'
$taskUtf8 = [System.Text.UTF8Encoding]::new($false)
$taskText = [System.IO.File]::ReadAllText($taskSource, $taskUtf8)
$taskSwitch = '(?m)^\\bilingualtrue\s*$'
if ([regex]::Matches($taskText, $taskSwitch).Count -ne 1) {
    throw 'Expected exactly one bilingual switch in main.tex.'
}
$taskEnglish = [regex]::Replace($taskText, $taskSwitch, '\bilingualfalse')
$taskEnglish = $taskEnglish.Replace('% !TeX program = xelatex', '% !TeX program = pdflatex')
$taskEnglish = $taskEnglish.TrimEnd() + "`n"
[System.IO.File]::WriteAllText($taskTarget, $taskEnglish, $taskUtf8)
Write-Output 'Updated main-en.tex from main.tex.'
