# 0004: Font substitution for GT Walsheim

Status: accepted (2026-09-25)

## Context
DESIGN.md specifies GT Walsheim Medium for display type. It's a proprietary commercial font (Framer's), not available to ship in an open build. DESIGN.md's own "Note on Font Substitutes" section names Mona Sans, Geist, or Inter at 600–700 weight as candidates.

## Decision
- **Display type** (`display-xxl` through `display-md`, headline): **Geist**, the open-source typeface from Vercel. It's geometric and confident at large sizes, matching GT Walsheim's character, and its variable weight axis covers the 500 weight DESIGN.md specifies throughout.
- **Monospace** (YAML editor content, trace payload dumps, code-shaped text): **Geist Mono**, for the same family pairing.
- **Body type**: unchanged — **Inter Variable**, exactly as DESIGN.md specifies, with the documented OpenType character variants (`cv01`, `cv05`, `cv09`, `cv11`, `ss03`, `ss07`).

All three are served as self-hosted variable fonts (or via `next/font`) rather than a third-party CDN, so no external font request leaks user data.

## Consequences
- The extreme negative letter-spacing values in DESIGN.md's typography tokens are kept as specified (percentage of size), since Geist supports tight tracking cleanly at display sizes.
- If Geist's display weights read too thin against Framer's screenshots once the dashboard is built, revisit with Mona Sans as the fallback DESIGN.md already names — no new ADR needed for that swap, just an update to this one.

## Amendment (2026-09-28, E0)
- **Inter is self-hosted from `inter-ui` (rsms' own variable build, Latin subset), not `next/font/google`.** Google's Inter, like `@fontsource-variable/inter`, ships without `cv01`, `cv05`, `cv09`, `cv11`, `ss03` and `ss07`, so the features DESIGN.md calls the brand voice silently did nothing. Inspecting the served font's GSUB table showed only `ccmp/locl/pnum/tnum`. `inter-ui@4.1.1`'s `InterVariable-subset.woff2` (97 KB) has all of them plus `dlig` and `tnum`. It is loaded with `next/font/local`, so it is self-hosted and needs no network at build. Playwright confirmed that turning the features on changes the rendered text.
- Geist (display) and Geist Mono (traces, YAML, code) stay on `next/font/google`, which self-hosts them at build.
- Display tracking stays the percentage of size DESIGN.md specifies, including in the dashboard tiers ([ADR 0028](0028-dashboard-adaptations.md) §3).
- Body text sets `cv01 cv05 cv09 cv11 ss03 ss07`. Tables and numbers add `tabular-nums`.
