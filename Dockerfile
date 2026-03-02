FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install uv (pinned for reproducible builds)
COPY --from=ghcr.io/astral-sh/uv:0.6.3 /uv /usr/local/bin/uv

# Install dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source
COPY src/ src/
COPY scripts/ scripts/

# Non-root user for security
ENV UV_CACHE_DIR=/tmp/.uv-cache
RUN addgroup --system app && \
    adduser --system --ingroup app --home /home/app app
USER app

EXPOSE 8000

CMD ["sh", "-c", "uv run uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
