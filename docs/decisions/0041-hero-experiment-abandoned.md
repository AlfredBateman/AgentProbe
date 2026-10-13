# 0041: Hero experiment abandoned, superseded by the UI overhaul

Status: accepted (2026-10-13).

## Context
Commit `14fe293` rebuilt the landing hero as a full-viewport, self-hosted video stage with its own warm palette, and ADR 0040 recorded that palette as a scoped deviation from DESIGN.md. The experiment is not continuing; the landing page and the rest of the UI are being reworked in the `ui-overhaul` branch instead.

## Decision
- The hero is removed: its components and tests, the e2e spec, the video and poster in `apps/web/public`, the `media-src 'self'` CSP directive and its test, the jsdom `matchMedia` and `play` stubs, the Dockerfile `COPY` of `public/`, and the DESIGN.md "Landing Hero" section.
- ADR 0040 is deleted, and ADR 0039's note about it is reverted. No ADR is renumbered, so 0040 stays unused.
- `/` renders the page it rendered before the experiment.
- The `design-refs/` ignore rule, added in the same commit, stays: local design references are never tracked.

## Consequences
- The CSP has no `media-src`, so media falls back to `default-src`. Anything that needs media later must add a directive with its own ADR.
- The video, poster and ADR 0040 remain in git history. Rewriting history is not part of this decision.
- DESIGN.md governs the whole UI again, with no scoped exceptions.
