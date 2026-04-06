#!/usr/bin/env bash
# Start the FastAPI backend. From repo root: ./scripts/dev-backend.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/backend"
echo "Starting backend at http://127.0.0.1:8000 (cwd: $(pwd))"
exec python -m uvicorn gorzen.api.app:create_app --factory --host 0.0.0.0 --port 8000
