<#
.SYNOPSIS
    Run the test suite. Extra arguments are passed through to pytest.
.EXAMPLE
    .\scripts\test.ps1
    .\scripts\test.ps1 -- -k scoring -v
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Error 'No .venv found. Run .\scripts\setup.ps1 first.'
}

& $venvPython -m pytest @PytestArgs
exit $LASTEXITCODE
