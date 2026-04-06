# Optional: run pytest SITL placeholder when a simulator is up.
# Prerequisites: PX4 SITL listening on UDP (e.g. 14540), GORZEN_SITL=1
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $RepoRoot "backend")
$env:PYTHONPATH = "src"
$env:GORZEN_SITL = "1"
Write-Host "Running optional SITL tests (expect skip until harness is implemented)..."
python -m pytest ..\tests\backend\test_sitl_mission_optional.py -v
