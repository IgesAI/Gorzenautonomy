#!/usr/bin/env bash
# Start the Vite frontend. From repo root: ./scripts/dev-frontend.sh
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/frontend"
echo "Starting frontend (cwd: $(pwd))"
exec npm run dev
