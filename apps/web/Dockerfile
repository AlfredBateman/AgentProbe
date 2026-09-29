# syntax=docker/dockerfile:1
# The dashboard: Next.js standalone output on Node, run as the image's `node` user.
# Build context is the repo root: docker compose build web.
ARG NODE_IMAGE=node:22.23.3-alpine3.24@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402

FROM ${NODE_IMAGE} AS build
RUN npm install --global pnpm@11.2.2
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm-store \
    pnpm install --frozen-lockfile --store-dir /pnpm-store
COPY apps/web apps/web
# Both are fixed at build time: rewrites are compiled into the routes manifest, and NEXT_PUBLIC_*
# is inlined into the client bundle. API_INTERNAL_URL is where the server proxies /api (the
# compose network); NEXT_PUBLIC_API_URL is where the browser opens a run's SSE stream (ADR 0031).
ARG API_INTERNAL_URL=http://api:8000
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_OUTPUT=standalone NEXT_TELEMETRY_DISABLED=1 \
    API_INTERNAL_URL=${API_INTERNAL_URL} NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
RUN pnpm --filter web build \
    && test -f apps/web/.next/standalone/apps/web/server.js

FROM ${NODE_IMAGE}
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /app/apps/web/.next/static ./apps/web/.next/static
USER node
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --start-interval=2s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/login').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["node", "apps/web/server.js"]
