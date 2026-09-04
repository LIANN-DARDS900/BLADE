Set-ExecutionPolicy Bypass -Scope Process -Force
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
. (Join-Path $PSScriptRoot 'python_resolver.ps1')

Write-Host 'BLADE - Development Environment Check' -ForegroundColor Cyan
Write-Host '--------------------------------------------------------'

$PythonCommand = Resolve-ProjectPython
Write-Host "Python command: $PythonCommand" -ForegroundColor Green
& $PythonCommand --version
& $PythonCommand -c "import sys, platform; print('Executable:', sys.executable); print('Architecture:', platform.architecture()[0])"

if ($LASTEXITCODE -ne 0) { throw 'Python verification failed.' }
Write-Host ''
Write-Host 'Environment is ready for START_DEV.bat.' -ForegroundColor Green
