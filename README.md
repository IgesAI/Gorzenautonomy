# Gorzenautonomy

Digital-Twin Platform for VTOL Fleet Configuration and Perception-Constrained Autonomous Mission Planning.

## Overview

Gorzenautonomy is a physics-based digital twin that models VTOL aircraft (lift+cruise hybrid) for fleet configuration and mission planning. It evaluates operating envelopes (speed–altitude feasibility), fuel endurance, battery reserve, identification confidence, and mission completion probability under uncertainty.

## Architecture

- **Backend** (Python/FastAPI): 17-model chain (environment → airframe → propulsion → fuel/battery → perception → identification), UQ propagation (Monte Carlo, PCE, Unscented Transform), envelope solver
- **Frontend** (React/Vite/TypeScript): Parameter forms, envelope heatmap, MCP dial, sensitivity bars

## Requirements

- Python 3.11+
- Node.js 18+ (for frontend)

## Setup

### Backend

```bash
cd backend
pip install -e ".[dev]"
```

### Frontend

```bash
cd frontend
npm install
```

## Running

### Backend API

```bash
cd backend
uvicorn gorzen.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

### Frontend (dev)

```bash
cd frontend
npm run dev
```

The frontend proxies `/api` to `http://localhost:8000`.

### Serial / USB telemetry (Live tab)

MAVLink over COM/tty requires **[pyserial](https://pypi.org/project/pyserial/)** (`import serial`). It is listed in `backend/pyproject.toml`; if you see `No module named 'serial'`, reinstall deps from the backend venv:

```bash
cd backend
pip install pyserial
# or
pip install -e .
```

For **LoRa or other low-rate packet links**, use the Live tab checkbox *LoRa / low bandwidth* before connecting (or `POST /api/telemetry/connect` with `"link_profile": "low_bandwidth"`). That requests only essential MAVLink streams at 1&nbsp;Hz and slows server push / HTTP polling so the UI does not outrun the radio.

## Testing

```bash
cd backend
pytest -v
```

## Code Quality

- **Linting:** `cd backend && ruff check src/`
- **Formatting:** `cd backend && ruff format src/`
- **Security:** `cd backend && bandit -r src/`

## Reproducibility

- **Docker:** `docker build -t gorzen . && docker run -p 8000:8000 gorzen`
- **Lock file:** For exact dependency versions, run `cd backend && pip install -e ".[dev]" && pip freeze > requirements-lock.txt`

## Documentation

- [Architecture](docs/ARCHITECTURE.md) – Data flow, model chain, Mermaid diagrams

## License

MIT – see [LICENSE](LICENSE).
