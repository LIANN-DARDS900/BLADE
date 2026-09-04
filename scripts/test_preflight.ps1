Set-ExecutionPolicy Bypass -Scope Process -Force
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$result = powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command `
    "Set-ExecutionPolicy Bypass -Scope Process -Force; & '$root\scripts\blade_operations.ps1' -Operation 'preflight'"
$result | ConvertFrom-Json | ConvertTo-Json -Depth 10
