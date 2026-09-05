<#
.SYNOPSIS
    Start the development server with auto-reload.
.EXAMPLE
    .\scripts\run.ps1
    .\scripts\run.ps1 -Port 8000
#>
[CmdletBinding()]
param(
    [int]$Port = 5000,
    [string]$AppHost = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Error 'No .venv found. Run .\scripts\setup.ps1 first.'
}

# Debug mode gives auto-reload and tracebacks. Local only - never in production.
$env:FLASK_DEBUG = '1'
$env:HOST = $AppHost
$env:PORT = "$Port"

Write-Host "Word Scramble -> http://${AppHost}:${Port}  (Ctrl+C to stop)" -ForegroundColor Green
& $venvPython app.py
