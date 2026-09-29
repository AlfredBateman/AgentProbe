# syntax=docker/dockerfile:1
# The bundled demo agents (deliberately vulnerable; fake data only). docker-compose.yml keeps
# them on the compose network with no published port. Build context is the repo root.
ARG PYTHON_IMAGE=python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

FROM ghcr.io/astral-sh/uv:0.12.18@sha256:3adc3706091ce7c2fe595e669628caedd6d951551b92b258b7e7dbe06d9440bc AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Every workspace member's pyproject.toml: `uv sync --locked` checks the lock against all of them.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/
COPY packages/cli/pyproject.toml packages/cli/
COPY apps/api/pyproject.toml apps/api/
COPY demo-agents/pyproject.toml demo-agents/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --package agentprobe-demo-agents
COPY packages/core/src packages/core/src
COPY demo-agents/src demo-agents/src
COPY demo-agents/prompts demo-agents/prompts
# Editable, unlike the API image: the support bots read ../../prompts relative to their own
# source file (routes_support.py), so the source tree stays in place.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package agentprobe-demo-agents

FROM ${PYTHON_IMAGE}
RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /app /app
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 9000
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/health', timeout=2)"]
# 0.0.0.0 inside the container only; `python -m agentprobe_demo_agents` binds 127.0.0.1.
CMD ["uvicorn", "agentprobe_demo_agents.main:app", "--host", "0.0.0.0", "--port", "9000"]
