# syntax=docker/dockerfile:1
# One image for the API (default command: migrate, then serve) and the Redis worker
# (docker-compose.yml overrides the command). Build context is the repo root.
ARG PYTHON_IMAGE=python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

FROM ghcr.io/astral-sh/uv:0.12.18@sha256:3adc3706091ce7c2fe595e669628caedd6d951551b92b258b7e7dbe06d9440bc AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
# Every workspace member's pyproject.toml: `uv sync --locked` checks the lock against all of them.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/
COPY packages/cli/pyproject.toml packages/cli/
COPY apps/api/pyproject.toml apps/api/
COPY demo-agents/pyproject.toml demo-agents/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --package agentprobe-api
COPY packages/core/src packages/core/src
COPY apps/api/src apps/api/src
# Non-editable: the venv is self-contained, so the final image needs no source tree.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --package agentprobe-api

FROM ${PYTHON_IMAGE}
RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /app/.venv .venv
COPY apps/api/alembic.ini ./
COPY apps/api/migrations migrations
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 8000
# No HEALTHCHECK here: the worker runs this image too and has no HTTP port. docker-compose.yml
# gives the api service its /health check.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn agentprobe_api.main:app --host 0.0.0.0 --port 8000"]
