# Gorzenautonomy — reproducible build
# Python 3.11 for backend API

FROM python:3.11-slim

WORKDIR /app

# Copy backend
COPY backend/pyproject.toml backend/
COPY backend/src backend/src

# Install backend with dev deps (for tests)
RUN pip install --no-cache-dir -e "./backend[dev]"

# Run API
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "gorzen.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
