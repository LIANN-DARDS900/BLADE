# Run from an elevated PowerShell window or through START_DEV.bat.
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
$Requirements = Join-Path $ProjectRoot 'requirements.txt'
$Marker = Join-Path $ProjectRoot '.venv\.requirements.sha256'
$RequirementsHash = (Get-FileHash $Requirements -Algorithm SHA256).Hash
$InstalledHash = if (Test-Path $Marker) { (Get-Content $Marker -Raw -ErrorAction SilentlyContinue).Trim() } else { '' }

if ($InstalledHash -ne $RequirementsHash) {
    Write-Host 'Installing or updating project requirements...' -ForegroundColor Cyan
    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'Failed to upgrade pip.' }

    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install project requirements.' }

    Set-Content -Path $Marker -Value $RequirementsHash -Encoding ASCII -Force
}
else {
    Write-Host 'Project requirements are already ready.' -ForegroundColor Green
}

& $Python .\main.py
if ($LASTEXITCODE -ne 0) { throw "The application exited with code $LASTEXITCODE." }
