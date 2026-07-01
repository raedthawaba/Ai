# ══════════════════════════════════════════════════════════════════════════════
# Hajeen AI Platform — Production Dockerfile
# Multi-stage build: builder → runtime
# ══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim as builder

ARG ENVIRONMENT=production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY hajeen_platform/requirements.txt .
COPY hajeen_platform/requirements-prod.txt* ./

RUN pip install --upgrade pip && \
    pip install --user -r requirements.txt && \
    if [ -f requirements-prod.txt ]; then pip install --user -r requirements-prod.txt; fi

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim as runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH" \
    PYTHONPATH="/app"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
COPY hajeen_platform/ .

RUN mkdir -p \
    /app/logs \
    /app/storage_data/vector_index \
    /app/storage_data/raw \
    /app/storage_data/bronze \
    /app/storage_data/silver \
    /app/storage_data/gold \
    /app/storage_data/metadata

RUN addgroup --system hajeen && \
    adduser --system --group hajeen && \
    chown -R hajeen:hajeen /app

USER hajeen

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--access-log", \
     "--log-level", "info"]
