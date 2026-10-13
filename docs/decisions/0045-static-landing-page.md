# 0045: Static landing page on the brutalist system

Status: accepted (2026-10-14). Builds on [ADR 0042](0042-industrial-brutalist-design-system.md) (tokens, DESIGN.md), [ADR 0043](0043-ui-primitives-on-the-brutalist-system.md) (primitives) and [ADR 0036](0036-free-tier-deploy-on-render.md) (cold starts).

## Context
`/` was the last page on the pre-overhaul layout, and it carried typed figures (`p = 0.0040`, a PR number) that no file backed. The rebuild is layout only: a top bar, a hero, three cards, a proof card, an install snippet and a footer, as bordered compartments. No 3D and no scroll animation yet, no new dependency, and the per-request CSP unchanged.

## Decision

### 1. No figure on the page is typed
`apps/web/scripts/gen-landing-facts.mjs` (`pnpm --filter web gen:facts`) reads `docs/metrics.md` and `README.md` and writes `src/components/landing/facts.json`, which the page imports. It follows `gen-theme.mjs`: the output is committed, so a build needs neither document, and `facts.test.ts` fails when it is stale. A figure that is not where the generator expects it throws; nothing is left blank.

| Shown | Source |
|---|---|
| Planted flaws detected, demo agents, negative controls, measured date | `docs/metrics.md`, the mock detection block |
| The regression's case, pass counts, p-value and threshold, attempts per case | `docs/metrics.md`, the detection table |
| False alarms: naive rate, shipped rate with its 95% interval, the scenario | `docs/metrics.md`, the false-alarm result |
| The seeded runs' pass rates | `README.md`, "What it looks like" |
| Version and release tag | `apps/web/package.json` |

The seeded runs' pass-rate confidence interval is recorded in no file, so the card says `CI unmeasured` instead of showing one. `page.test.tsx` fails on any numeric token in the page that is not in `facts.json`, the version or the year (the card indexes, `FIG. 01`, `UNIT D-01` and `95% CI` are the named exceptions). The install lines are built from the package version, and the same test requires them to appear in `README.md`.

### 2. Two lime buttons, one action
DESIGN.md allows one primary button per view. The page has `GET STARTED` in the top bar and again in the hero: the same action, to `/register`, shown twice. To keep lime scarce, no card takes the lime panel fill the hero board had, and the test allows a lime fill only on a link to `/register`. Under 360px the top-bar copy is hidden, because the bar has no room for it.

### 3. The demo link is configuration
There is no public project. `TRY THE DEMO` goes to `NEXT_PUBLIC_DEMO_URL`, meant to be a share link to a seeded run (the read-only `/shared/<token>` view). Only a same-origin path or an `https://` URL is accepted; unset or anything else, the button and its wake note are not rendered, so the page never has a dead link.

### 4. The status chip reports the API
`StatusChip` is the page's only client code. It calls the existing `awakeFetch` on `/api/health` once per visit and shows `API CHECKING`, `API WAKING`, `API ONLINE` or `API UNREACHABLE` with the matching status mark. The chip has a fixed minimum width, so its text changing moves nothing. Reusing `awakeFetch` means a visit also starts a sleeping API waking, and the existing "Waking the server" notice appears on this page too. `connect-src 'self'` already covers the request; `proxy.ts` is unchanged.

### 5. Layout choices
- The headline is one `h1` in `display-xxl`, three lines, the last one outlined. The headline, the visual box and their offsets are all in `cqi` inside one `@container`, so the composition keeps its proportions from 320 to 1440px with no breakpoint.
- The visual is an inline SVG grid of 2px squares in a box sized by `aspect-ratio`, labelled illustrative. The later 3D piece takes the same box, so swapping it in moves nothing. Squares because the system has no radius.
- Below 810px the nav links are a native `<details>` whose list is absolutely positioned: no script and no shift.
- The cards are the `Panel` primitive with `href`. Their header is set not to wrap, so a long title wraps inside its own width and the arrow stays in the corner.
- Mono sentences on the cards and the wake note are kept to 8 words, DESIGN.md's limit for mono uppercase. The callout values are `display-md`, as on the hero board; only their labels are mono.
- The footer says `LICENSE NOT SET`: the repository has no licence file yet.

## Consequences
- `docs/metrics.md` or the README's "What it looks like" sentence changing fails `facts.test.ts` until `gen:facts` is run; rewording either so a pattern no longer matches fails the generator itself.
- The hero section has no `crosshair` marks: on a full-width section the corner mark sits half outside the frame and made the page 3px wider than the viewport.
- `page.test.tsx` was rewritten. Its old assertions (the previous pitch sentence, Sign in as a secondary button) described the page this replaces.
- Measured in Chromium at 1440, 810 and 390px against `next dev`: cumulative layout shift 0, no horizontal overflow (also at 320, 360, 414, 600, 809, 1199 and 1200px), every `border-radius` 0, the nonce CSP present and no console error.
- Not done here: motion and the 3D piece, a real public demo project, and a licence.
