# 0002: Web toolchain on TypeScript 5 and ESLint 9

Status: accepted (2026-09-24)

## Context
The latest stable majors on 2026-09-24 are TypeScript 7.0.2 and ESLint 10.11.0. However, `create-next-app@16.3.6`, which matches the current Next.js release, still generates projects on `typescript@^5` and `eslint@^9`. That signals those are the majors Next.js tests against:
- `next build` and the Next TypeScript plugin use the TypeScript compiler API.
- The `eslint-config-next` plugins target ESLint 9.

## Decision
Pin the newest release within the majors Next.js ships with:
- `typescript@5.9.3`
- `eslint@9.39.5`
- `@types/node@22.20.4` (matches Node 22)

Everything else is on the latest stable release:
- `next@16.3.6`
- `react@19.3.0`
- `tailwindcss@4.3.3`
- `vitest@5.0.1`

## Consequences
Revisit when `create-next-app` moves to TypeScript 7 or ESLint 10.
