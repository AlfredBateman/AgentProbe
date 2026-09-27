# 0028: Dashboard adaptations of DESIGN.md

Status: accepted (2026-09-28). Implements PLAN.md §4 (E0).

## Context
DESIGN.md describes Framer's marketing site: one accent color, poster-sized type and a 5px spacing rhythm. A test-results dashboard needs things that document never had to express: pass/fail/flaky states, dense tables, charts, focus and error states. Every rule this ADR bends is listed here, so DESIGN.md stays the reference and the deviations stay visible.

The tokens themselves live in DESIGN.md's front matter, including the additions below. `apps/web/scripts/gen-theme.mjs` generates `apps/web/src/app/theme.css` from them. `theme.test.ts` fails if the generated file is stale, and it also checks every contrast ratio in this ADR.

## Decision

### 1. Result colors
DESIGN.md's rule "don't combine more than one chromatic accent" can't express test results. A pass, a fail and a flaky case must read differently at a glance, and a single blue can't do that. Blue also has to stay reserved for links, focus and selection. So three tokens join the existing `semantic-success`:

| Token | Alias | Value | Meaning |
|---|---|---|---|
| `semantic-success` | `pass` | #22c55e | pass (unchanged) |
| `semantic-danger` | `fail` | #f87171 | fail, regression |
| `semantic-warning` | `flaky` | #f59e0b | flaky |
| `semantic-neutral` | `neutral` | #999999 | error, skipped |

`semantic-neutral` is ink-muted's value, not a new gray, because DESIGN.md forbids other mid-grays. Like the success green, these color **glyphs and badge text only, never surfaces**. A badge is surface-2 with colored text and a status mark.

Measured WCAG contrast (text needs 4.5:1; chart marks need 3:1 under WCAG 1.4.11):

| Token | Value | canvas | surface-1 | surface-2 |
|---|---|---|---|---|
| `ink` | #ffffff | 19.91 | 18.42 | 17.04 |
| `ink-muted` | #999999 | 6.99 | 6.47 | 5.98 |
| `accent-blue` | #0099ff | 6.64 | 6.14 | 5.68 |
| `semantic-success` | #22c55e | 8.74 | 8.08 | 7.48 |
| `semantic-danger` | #f87171 | 7.20 | 6.66 | 6.16 |
| `semantic-warning` | #f59e0b | 9.27 | 8.58 | 7.94 |
| `semantic-neutral` | #999999 | 6.99 | 6.47 | 5.98 |
| `chart-1` | #6a4cf5 | 3.76 | 3.48 | 3.22 |
| `chart-2` | #e5672a | 5.98 | 5.53 | 5.12 |
| `chart-3` | #d44df0 | 5.80 | 5.37 | 4.97 |
| `chart-4` | #f24f70 | 5.81 | 5.38 | 4.97 |

**Pass green and fail red are indistinguishable to deuteranopes.** Their OKLab ΔE is 1.1 under deuteranopia simulation, measured with the dataviz palette validator. So a result is never told apart by those two colors alone:
- every Badge carries its text label;
- each StatusDot status has its own shape: a circle for pass, a diamond for fail, a half-filled circle for flaky, a ring for error, a bar for stable;
- charts don't use green/red series.

### 2. Chart series
PLAN.md §4 suggested ink, ink-muted and the gradient anchors as series colors. The validator rejects the grays for categorical use, because they fall below the chroma floor and read as "no color". It also found orange and coral above the dark-mode lightness band (OKLCH L 0.73 and 0.69 against a 0.48–0.67 band).
- The categorical series are `chart-1` to `chart-4`: violet, orange, magenta and coral, in that fixed order. Orange and coral are stepped into the band (#e5672a and #f24f70; same hue, L 0.66). The palette passes every validator check on all three surfaces, and its worst adjacent-pair CVD ΔE is 20.9.
- A fifth series folds into "Other"; hues are never cycled.
- Ink is the single-series and "current" line. A baseline is a dashed ink-muted line.
- `accent-blue` is never a series.

### 3. Dashboard type
The display sizes from 62px up are for marketing, so they aren't used. The new tiers derive from the scale and keep each parent tier's tracking as a percentage of size, as DESIGN.md requires:

| Token | Font | Size / weight / line height | Tracking | Use |
|---|---|---|---|---|
| `dash-title` | Geist | 32 / 500 / 1.13 | −1.0px (display-md's −3.1%) | Page title, ≥810px |
| `dash-title-sm` | Geist | 24 / 500 / 1.13 | −0.75px (same %) | Page title, <810px |
| `dash-heading` | Geist | 18 / 500 / 1.2 | −0.65px (headline's −3.6%) | Panel and dialog titles |
| `data` | Inter Variable | 13 / 400 / 1.4 | −0.13px (−1%) | Table cells, with `tabular-nums` |
| `data-label` | Inter Variable | 12 / 500 / 1.2 | −0.12px | Column headers, labels, badges |
| `code` | Geist Mono | 13 / 400 / 1.5 | 0 | Traces, YAML, ids |

### 4. Focus ring
DESIGN.md's level-3 focus treatment is a 1px `rgba(0,153,255,0.15)` ring. It measures 1.22:1 against surface-1, so a keyboard user can't see it, and it fails WCAG 1.4.11. The ring is now a solid 1px `accent-blue` (6.14:1) with the 0.15 halo spread to 4px around it (`--shadow-focus`). It is still blue, and still a ring.

### 5. Input error state
DESIGN.md's Known Gaps leave form errors undefined. An input with `aria-invalid` gets a `fail` border, and its message is `fail`-colored text linked with `aria-describedby`.

### 6. Gradient card
White text fails WCAG AA on three of the four gradient anchors:

| Anchor | White text contrast |
|---|---|
| violet | 5.30 |
| magenta | 3.43 |
| orange | 2.59 |
| coral | 3.08 |

`GradientCard` is violet only. It runs from #6a4cf5 to a darker #3b2799 (10.85), so contrast only improves across the card. DESIGN.md allows one or two per page; a dashboard viewport gets one. A second mounted card logs a warning in development.

### 7. Spacing is a px scale
Tailwind 4 resolves `max-w-md` from `--spacing-md` before `--container-md`. Emitting DESIGN.md's spacing names (xs…xl) would therefore silently turn `max-w-md` into 15px (user decision). Instead `--spacing: 1px`: every numeric utility is px, so `p-15` is 15px and `h-56` is 56px. Every DESIGN.md spacing value is a whole px, and the generator checks that. The catch is that `p-4` means 4px, not 16px. CLAUDE.md says so.

### 8. Layout details
- **Breakpoints** follow DESIGN.md: `tablet` at 810px and `desktop` at 1199px. Below 810 the nav links collapse into a menu while the project switcher stays on the bar. From 810 to 1198 the account email is hidden (it stays in the sign-out button's title), so the bar fits at 810 without overlap. Measured from 810 to 1440 with a long project name.
- **Nav height** is exactly 56px. Its bottom rule is an inset shadow, not a border, which would make the bar 57px.
- **Data tables** scroll horizontally inside their panel below 810px. They don't turn into accordions: that is DESIGN.md's rule for the pricing table, and per-case run data has too many columns for it.
- **Touch targets**: pills are at least 44px tall and tabs 40px; the icon button is 40px, or 44px under `pointer-coarse`, as DESIGN.md specifies.
- **Actions on a surface-1 container** (a card, a dialog) use the translucent (surface-2) button, not secondary. Secondary is surface-1 and would vanish into it (DESIGN.md: "lift, not color").
- **Skeletons** are `hairline` (#262626). Surface-2 on a surface-1 card is invisible.

## Consequences
- DESIGN.md gains the tokens, five `badge-*` component entries and a "Dashboard Adaptations" section. `@google/design.md lint` reports no new findings, and one existing orphaned-token warning is gone.
- A new token goes into DESIGN.md first, then `pnpm --filter web gen:theme`. `theme.css` is never edited by hand.
- New status or series colors must pass `theme.test.ts`'s contrast checks, and new series must pass the dataviz validator.
