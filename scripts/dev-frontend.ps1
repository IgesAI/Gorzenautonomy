# Start the Vite frontend dev server (run from any directory).
# Terminal 2:  .\scripts\dev-frontend.ps1
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $RepoRoot "frontend")
Write-Host "Starting frontend dev server (cwd: $(Get-Location))"
npm run dev
