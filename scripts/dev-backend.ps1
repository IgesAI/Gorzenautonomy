# Start the FastAPI backend (run from any directory).
# Terminal 1:  .\scripts\dev-backend.ps1
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $RepoRoot "backend")
Write-Host "Starting backend at http://127.0.0.1:8000 (cwd: $(Get-Location))"
Write-Host "Tip: activate your venv first, then: pip install -e `".[dev]`" from backend if needed."

$uvicornArgs = @(
    "-m", "uvicorn", "gorzen.api.app:create_app",
    "--factory", "--host", "0.0.0.0", "--port", "8000"
)

# On Windows, `py -3` is often available when `python` is not on PATH.
if (Get-Command py -ErrorAction SilentlyContinue) {
    Write-Host "Using: py -3"
    py -3 @uvicornArgs
    exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "Using: python"
    python @uvicornArgs
    exit $LASTEXITCODE
}

Write-Host @"

Could not find Python. Try one of:

  1) Install Python 3.11+ from https://www.python.org/downloads/
     — check 'Add python.exe to PATH' during setup.

  2) Settings -> Apps -> Advanced app settings -> App execution aliases
     — turn OFF 'python.exe' and 'python3.exe' (they point at the Store stub).

  3) If Python is already installed, add it to PATH or run with full path, e.g.:
     & '$env:LOCALAPPDATA\Programs\Python\Python311\python.exe' -m uvicorn ...

"@

exit 1
