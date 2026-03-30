# Build wheel (runtime dependencies only — no [dev])
FROM python:3.11-slim AS builder

WORKDIR /app
COPY backend/pyproject.toml backend/
COPY backend/src backend/src
RUN pip install --no-cache-dir --upgrade pip \
    && pip wheel --no-cache-dir -w /wheels ./backend

# Runtime image — no pytest/ruff/pyright
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir --upgrade pip \
    && useradd -m -u 1000 gorzen
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/gorzen-*.whl && rm -rf /wheels

# Migrations (not in wheel)
COPY backend/alembic.ini /app/backend/alembic.ini
COPY backend/alembic /app/backend/alembic
RUN mkdir -p /app/storage/logs /app/storage/events && chown -R gorzen:gorzen /app
WORKDIR /app/backend

USER gorzen
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

CMD ["uvicorn", "gorzen.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
