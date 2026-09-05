<#
.SYNOPSIS
    Create the virtual environment and install dependencies.
.EXAMPLE
    .\scripts\setup.ps1
    .\scripts\setup.ps1 -Dev      # also install the test dependencies
#>
[CmdletBinding()]
param(
    [switch]$Dev = $true
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }

if (-not (Test-Path '.venv')) {
    Write-Host 'Creating virtual environment in .venv ...' -ForegroundColor Cyan
    & $python -m venv .venv
} else {
    Write-Host 'Using the existing .venv' -ForegroundColor DarkGray
}

$venvPython = Join-Path $root '.venv\Scripts\python.exe'

Write-Host 'Installing dependencies ...' -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r requirements.txt --quiet
if ($Dev) {
    & $venvPython -m pip install -r requirements-dev.txt --quiet
}

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Created .env from .env.example - fine as-is for local development.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Setup complete.' -ForegroundColor Green
Write-Host '  .\scripts\run.ps1     start the dev server'
Write-Host '  .\scripts\test.ps1    run the test suite'
