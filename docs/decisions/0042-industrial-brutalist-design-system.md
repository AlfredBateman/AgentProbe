# 0042: Industrial brutalist design system

Status: accepted (2026-10-13). Supersedes [ADR 0028](0028-dashboard-adaptations.md) (dashboard adaptations) and [ADR 0004](0004-font-substitution.md) (fonts).

## Context
DESIGN.md described a marketing site (white pills, gradient cards, a blue accent, Inter and Geist), and ADR 0028 listed what a test-results dashboard had to bend. The whole UI is being reworked, so DESIGN.md is rewritten as one system for the dashboard and the landing page: industrial brutalism in its dark "tactical telemetry" form. Near-black panels divided by 1px lines, heavy uppercase Archivo headlines, small uppercase JetBrains Mono for labels and data, no radius, no gradient, no blur, no soft shadow.

This step replaces the tokens and adds design boards at `/dev/design` (dev server only). No page is rebuilt yet.

## Decision

### 1. Deviations from the usual brutalist rules
The dark brutalist convention is: one accent, hazard red; optional terminal green for a single element.

- **The brand accent is acid lime, `#CAFF00`**, not red. It marks the brand, the primary action, focus, selection, the active nav item and an improvement verdict.
- **Red is reserved for failure, regression and destructive actions.** It is never an accent or decoration. A page where nothing failed has no red.
- **Red is `#FF2A2A`, not `#E61919`.** `#E61919` fails WCAG AA as small text on every surface, and no text colour in the palette passes on a `#E61919` fill. One red covers text, borders and fills.
- **No green and no amber.** A pass is plain foreground, so a table of passes stays quiet. Lime is not a pass colour.

Measured WCAG contrast (text needs 4.5:1; control borders and marks need 3:1):

| Colour | canvas #0A0A0A | surface-1 #121212 | surface-2 #1A1A1A |
|---|---|---|---|
| `ink` #EAEAEA | 16.46 | 15.57 | 14.47 |
| `ink-muted` #9A9A9A | 7.04 | 6.66 | 6.19 |
| `accent` #CAFF00 | 16.80 | 15.89 | 14.76 |
| `fail` #FF2A2A | 5.30 | 5.01 | 4.65 |
| `hairline-strong` #707070 | 4.00 | 3.78 | 3.51 |
| rejected `#E61919` | 4.26 | 4.03 | 3.74 |

`on-accent` on `accent` is 16.80 and `on-fail` on `fail` is 5.30. `hairline` (#2E2E2E, 1.46 on canvas) is decoration only and never the only edge of a control. `theme.test.ts` checks every pair above.

### 2. Status without hue
With one alarm colour, four statuses cannot be told apart by colour. Each has its own 8px mark and always carries its label: pass is a filled square in `ink`, fail a filled square in `fail`, flaky a hatched square with a dashed chip border, error a hollow square in `ink-muted`, stable a 2px bar. Verdicts: regression is a red fill, improvement a lime fill, no change an `ink` outline.

### 3. Fonts
Archivo (variable weight and width) for headlines and prose, JetBrains Mono for labels, data, controls and code. Both come from `next/font/google`, which downloads them at build time and serves them from the app's origin, so the Content-Security-Policy is unchanged (`font-src 'self'`). Inter, Geist, Geist Mono and the `inter-ui` dependency are removed.

Uppercase belongs to the interface's own words. Case ids, YAML, tool arguments and agent output are shown exactly as written.

### 4. Tokens and generated CSS
The tokens stay in DESIGN.md's front matter and `gen-theme.mjs` still generates `theme.css`. New groups: `fonts`, `borders`, `zIndex`, `motion` and `aliases`. The generator also emits one `type-<tier>` utility per type tier, because a tier is now a family, a case and a width as much as a size. Spacing stays a px scale (`--spacing: 1px`), for the reason ADR 0028 §7 gave.

`border-radius: 0 !important` on every element, in `globals.css`, enforces the radius rule against utilities, arbitrary values and library inline styles.

The focus ring is 2px lime, 2px off the element, so it also shows on a lime fill.

### 5. Old pages run on aliases until rebuilt
About 550 class uses in 40 files name the old tokens. Rather than edit pages that are about to be rebuilt, the old names are aliases of new tokens (`aliases` in DESIGN.md, marked Legacy): `primary`, `on-primary`, `accent-blue`, `hairline-soft`, `chart-1` to `chart-4`, and the type tiers `dash-title`, `dash-title-sm`, `dash-heading`, `data-label`, `caption` and `subhead`. `--shadow-float` and `--font-display` are kept the same way. Old pages therefore pick up the new colours, fonts and square corners at once and look in-between.

Each page rebuild replaces its legacy names; the last one deletes the Legacy entries.

`GradientCard` is now a flat panel with a 2px lime border: the system has no gradients, and `ink` on its violet stop was 4.40:1.

### 6. Charts
The four hued series of ADR 0028 are gone. `chart-1` to `chart-4` alias lime and three neutrals so existing charts keep rendering, but grey steps alone do not separate series. When the chart pages are rebuilt, series are told apart by dash pattern and direct labels, and the palette is re-validated.

### 7. Runtime dependencies
The overhaul may add two runtime dependencies and no others:
- `gsap`, for motion;
- `three`, on the landing page only, loaded lazily so no dashboard route pays for it.

anime.js is rejected: it would duplicate GSAP. Neither `gsap` nor `three` is installed in this step, because nothing uses them yet.

## Consequences
- ADR 0028's result colours, chart series, dashboard type tiers, blue focus ring and gradient card no longer apply. Its px spacing scale, its breakpoints (810 and 1199px) and its rule that tables scroll inside their panel below 810px carry over.
- Until a page is rebuilt it mixes the new tokens with its old layout. The landing headline is the roughest case: its old `display-xxl` class now resolves to the new fluid size.
- `next build` downloads Archivo and JetBrains Mono, so it still needs network access.
- A new token goes into DESIGN.md first, then `pnpm --filter web gen:theme`. `theme.css` is never edited by hand.

## Amendment 2026-10-14 (D1 review)
The design boards were reviewed and approved with revisions. Only tokens, global CSS and `/dev/design` changed; no page was rebuilt.

1. **Word spacing is part of each tight tier.** Heavy caps at −0.02 to −0.04em tracking, and Archivo's kerning against the space glyph, left word gaps of 0.08em at the 75%-width tiers and 0.12 to 0.17em elsewhere, so "AT YOUR" read "ATYOUR". `display-xxl`/`xl` get `wordSpacing: 0.2em`, `display-lg` 0.18em, `display-md` 0.17em and `headline` 0.16em, which brings the narrowest kerned space to 0.28em or more (measured in a browser on kerned phrases). `gen-theme.mjs` emits `word-spacing`, and `theme.test.ts` fails when a tier tracked below zero has none.
2. **`display-xxl` is sized against its container.** `clamp(56px, 15vw, 232px)` overflowed at 320 to 414px and at 810px, because the 56px floor and the fixed gutters around the hero are not proportional to the viewport (REGRESSIONS is 5.75em wide). It is now `clamp(28px, 15cqi, 232px)`, used inside an `@container`; with no container it falls back to the viewport width, as before. `display-xl`'s floor went from 44px to 36px. Checked: no display text overflows at 320, 360, 390, 414, 600, 809, 810, 1199, 1200 and 1440px.
3. **Marks gained a shape cue and grew from 8px to 10px.** Fail is a filled square with a knocked-out cross (`mark-fail`) and error is a hollow square with a `!` (`mark-error`). At 8px the `!` does not resolve, so all five marks are 10px; pass, flaky and stable keep their shapes. The error mark's `ink-muted` is 7.04, 6.66 and 6.19:1 on the three surfaces, above the 4.5:1 text floor, and `theme.test.ts` already checks it. The attempt matrix uses the same marks and has a legend.
4. **`IMPROVEMENT` is a lime outline, not a fill.** A solid lime fill now means only the primary action or the single emphasised hero panel. This supersedes §2's "improvement is a lime fill".
5. **Mono uppercase is for labels and data.** Text longer than about 8 words is Archivo in sentence case (`body`/`body-sm`). `design.test.tsx` enforces it on the boards.
6. **`REV` marks read the package version** (`apps/web/package.json`) instead of a typed number.

