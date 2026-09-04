[CmdletBinding()]
param(
    [switch]$OneFile
)

# Temporary process-only bypass. No CurrentUser or LocalMachine policy is changed.
Set-ExecutionPolicy Bypass -Scope Process -Force
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
. (Join-Path $PSScriptRoot 'python_resolver.ps1')

$PythonCommand = Resolve-ProjectPython
Write-Host "Using Python command: $PythonCommand" -ForegroundColor Cyan

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Host 'Creating the project virtual environment...' -ForegroundColor Cyan
    & $PythonCommand -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create .venv.' }
}

$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Failed to upgrade pip.' }

& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Failed to install project requirements.' }

$mode = if ($OneFile) { '--onefile' } else { '--onedir' }

# --onedir is recommended: it starts faster and is easier to troubleshoot.
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --uac-admin `
    $mode `
    --name 'BLADE' `
    --icon 'assets\bitlocker_assistant.ico' `
    --add-data 'scripts\blade_operations.ps1;scripts' `
    --add-data 'assets\bitlocker_assistant.ico;assets' `
    --add-data 'assets\bitlocker_assistant.png;assets' `
    --add-data 'config.json;.' `
    .\main.py

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }

Write-Host ''
Write-Host 'Build complete:' -ForegroundColor Green
if ($OneFile) {
    Write-Host '  dist\BLADE.exe'
} else {
    Write-Host '  dist\BLADE\BLADE.exe'
}
