---
version: alpha
name: AgentProbe
description: "Industrial brutalism for a test-results instrument: a near-black panel divided by 1px lines, heavy uppercase grotesque headlines, small uppercase monospace telemetry, one acid-lime accent, and red only where something failed. Dark mode only. No radius, gradient, glow, blur or soft shadow anywhere."

colors:
  canvas: "#0A0A0A"
  surface-1: "#121212"
  surface-2: "#1A1A1A"
  hairline: "#2E2E2E"
  hairline-strong: "#707070"
  ink: "#EAEAEA"
  ink-muted: "#9A9A9A"
  accent: "#CAFF00"
  on-accent: "#0A0A0A"
  fail: "#FF2A2A"
  on-fail: "#0A0A0A"

# CSS font variables (globals.css) by family: `sans` is --font-sans, `mono` is --font-mono.
fonts:
  sans: Archivo
  mono: JetBrains Mono

typography:
  display-xxl:
    fontFamily: Archivo
    fontSize: clamp(56px, 15vw, 232px)
    fontWeight: 900
    lineHeight: 0.85
    letterSpacing: -0.04em
    textTransform: uppercase
    fontStretch: 75%
  display-xl:
    fontFamily: Archivo
    fontSize: clamp(44px, 9vw, 120px)
    fontWeight: 900
    lineHeight: 0.88
    letterSpacing: -0.04em
    textTransform: uppercase
    fontStretch: 75%
  display-lg:
    fontFamily: Archivo
    fontSize: clamp(34px, 5vw, 64px)
    fontWeight: 800
    lineHeight: 0.9
    letterSpacing: -0.04em
    textTransform: uppercase
  display-md:
    fontFamily: Archivo
    fontSize: clamp(24px, 3vw, 36px)
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: -0.03em
    textTransform: uppercase
  headline:
    fontFamily: Archivo
    fontSize: 18px
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: -0.02em
    textTransform: uppercase
  body-lg:
    fontFamily: Archivo
    fontSize: 17px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0em
  body:
    fontFamily: Archivo
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0em
  body-sm:
    fontFamily: Archivo
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: 0em
  label:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: 0.08em
    textTransform: uppercase
  micro:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0.1em
    textTransform: uppercase
  data:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: 0.05em
    textTransform: uppercase
  button:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: 700
    lineHeight: 1
    letterSpacing: 0.08em
    textTransform: uppercase
  code:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0em

rounded:
  none: 0px

spacing:
  hair: 1px
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  section: 96px

borders:
  hair: 1px
  rule: 2px

zIndex:
  base: 0
  raised: 10
  nav: 40
  overlay: 50
  dialog: 60
  toast: 70
  noise: 90

motion:
  duration:
    instant: 80ms
    fast: 120ms
    base: 200ms
    slow: 400ms
    count: 800ms
  easing:
    step: steps(6, end)
    linear: linear
    mech: cubic-bezier(0.2, 0, 0, 1)

# Other names for the tokens above (ADR 0042). Status names say what a colour means. The
# legacy names keep pages that have not been rebuilt yet resolving; each rebuild removes its
# uses, and the last one deletes the legacy entries.
aliases:
  colors:
    pass: ink
    flaky: ink
    neutral: ink-muted
    # Legacy
    primary: accent
    on-primary: on-accent
    accent-blue: accent
    hairline-soft: hairline
    chart-1: accent
    chart-2: ink
    chart-3: ink-muted
    chart-4: hairline-strong
  typography:
    # Legacy
    dash-title: display-md
    dash-title-sm: display-md
    dash-heading: headline
    data-label: label
    caption: label
    subhead: body-lg

components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: 0px 16px
    height: 40px
  button-secondary:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline-strong}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: 0px 16px
    height: 40px
  button-danger:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.fail}"
    borderColor: "{colors.fail}"
    typography: "{typography.button}"
    rounded: "{rounded.none}"
    padding: 0px 16px
    height: 40px
  panel:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: 16px
  panel-raised:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline-strong}"
    typography: "{typography.body}"
    rounded: "{rounded.none}"
    padding: 16px
  text-input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline-strong}"
    typography: "{typography.code}"
    rounded: "{rounded.none}"
    padding: 0px 12px
    height: 40px
  top-nav:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink-muted}"
    borderColor: "{colors.hairline-strong}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    height: 56px
  table-header:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.micro}"
    rounded: "{rounded.none}"
    padding: 8px 12px
  table-row:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline}"
    typography: "{typography.data}"
    rounded: "{rounded.none}"
    padding: 10px 12px
  stat-tile:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.display-lg}"
    rounded: "{rounded.none}"
    padding: 16px
  chip-pass:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.hairline-strong}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: 3px 8px
  chip-fail:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.fail}"
    borderColor: "{colors.fail}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: 3px 8px
  chip-flaky:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    borderColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: 3px 8px
  chip-error:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink-muted}"
    borderColor: "{colors.hairline-strong}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: 3px 8px
  verdict-regression:
    backgroundColor: "{colors.fail}"
    textColor: "{colors.on-fail}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: 3px 8px
  verdict-improvement:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: 3px 8px
---

## Overview

AgentProbe looks like a declassified instrument panel: dense, exact and mechanical. The page is a near-black sheet cut into compartments by 1px lines. Headlines are heavy uppercase Archivo set tight enough to read as blocks. Everything that is a label, a number or a control is small uppercase JetBrains Mono. There is one brand colour, acid lime, and one alarm colour, red.

The system is dark only. [ADR 0042](docs/decisions/0042-industrial-brutalist-design-system.md) records where it departs from the usual brutalist rules and why.

**Hard rules, on every page:**
- `border-radius` is 0. No pills, no rounded cards, no circular buttons. `globals.css` enforces this for every element.
- No gradients, glow, blur, glass or soft shadows. Depth comes from 1px and 2px borders and from surface steps.
- Panels are separated by visible 1px lines.
- Lime is the only brand colour. Red means failure, regression or a destructive action, and nothing else.
- Body text meets WCAG AA, focus is always visible, nothing flickers, and motion respects `prefers-reduced-motion`.

## Colors

| Token | Value | Use |
|---|---|---|
| `{colors.canvas}` | #0A0A0A | Page and panel background. Never pure black. |
| `{colors.surface-1}` | #121212 | Table headers, raised panels, hover rows. |
| `{colors.surface-2}` | #1A1A1A | One more step: selected rows, dialogs, toasts. |
| `{colors.hairline}` | #2E2E2E | The 1px lines between panels and rows. Decoration only: it is 1.5:1 on canvas. |
| `{colors.hairline-strong}` | #707070 | Borders that mark a control or an outer frame: inputs, buttons, dialogs. At least 3:1 on every surface. |
| `{colors.ink}` | #EAEAEA | Text, and the pass state. |
| `{colors.ink-muted}` | #9A9A9A | Labels, metadata, secondary text. The only grey used for text. |
| `{colors.accent}` | #CAFF00 | Brand, primary action, focus ring, selection, the active nav item, an improvement verdict. |
| `{colors.on-accent}` | #0A0A0A | Text on a lime fill. |
| `{colors.fail}` | #FF2A2A | Failure, regression, destructive actions. As text, border or fill. |
| `{colors.on-fail}` | #0A0A0A | Text on a red fill. |

Rules:
- No other hue. There is no green and no amber. Greys are neutral; none is tinted.
- Lime is never a "pass" colour. A passing case is plain `ink`, so a table of passes stays quiet and a failure stands out.
- Red is never decoration. If nothing failed and nothing is being destroyed, there is no red on the page.
- Text uses `ink`, `ink-muted`, `accent` or `fail` on the three surfaces, or `on-accent` / `on-fail` on their fills. `theme.test.ts` checks every one of those pairs at 4.5:1.

### Status encoding

A status is never told by colour alone. Each has its own mark and always carries its text label.

| Status | Mark (8px) | Colour | Chip border |
|---|---|---|---|
| Pass | filled square | `ink` | 1px `hairline-strong` |
| Fail | filled square | `fail` | 1px `fail` |
| Flaky | hatched square (`///`) | `ink` | 1px dashed `ink` |
| Error | hollow square | `ink-muted` | 1px `hairline-strong` |
| Stable | 2px bar | `ink` | 1px `hairline-strong` |

Verdicts: `REGRESSION` is a red fill with `on-fail` text, `IMPROVEMENT` is a lime fill with `on-accent` text, `NO CHANGE` is an `ink` outline.

## Typography

Two families, both loaded with `next/font` and served from the app's own origin.

- **Archivo** (variable weight and width): headlines and prose.
- **JetBrains Mono**: every label, number, control and piece of code.

| Token | Font | Size | Weight | Line height | Tracking | Case | Use |
|---|---|---|---|---|---|---|---|
| `{typography.display-xxl}` | Archivo, 75% width | clamp(56px, 15vw, 232px) | 900 | 0.85 | −0.04em | upper | The landing headline. |
| `{typography.display-xl}` | Archivo, 75% width | clamp(44px, 9vw, 120px) | 900 | 0.88 | −0.04em | upper | Section openers on the landing page. |
| `{typography.display-lg}` | Archivo | clamp(34px, 5vw, 64px) | 800 | 0.9 | −0.04em | upper | Stat values, large numbers. |
| `{typography.display-md}` | Archivo | clamp(24px, 3vw, 36px) | 800 | 0.95 | −0.03em | upper | Page titles. |
| `{typography.headline}` | Archivo | 18px | 800 | 1.1 | −0.02em | upper | Panel and dialog titles. |
| `{typography.body-lg}` | Archivo | 17px | 400 | 1.5 | 0 | sentence | Lead paragraphs. |
| `{typography.body}` | Archivo | 15px | 400 | 1.5 | 0 | sentence | Prose: descriptions, findings, errors. |
| `{typography.body-sm}` | Archivo | 13px | 400 | 1.45 | 0 | sentence | Help text. |
| `{typography.label}` | JetBrains Mono | 11px | 500 | 1.3 | 0.08em | upper | Field labels, nav, chips, column groups. |
| `{typography.micro}` | JetBrains Mono | 10px | 500 | 1.2 | 0.1em | upper | Table headers, REV/UNIT marks, footnotes. |
| `{typography.data}` | JetBrains Mono | 13px | 400 | 1.4 | 0.05em | upper | Table cells and readouts. |
| `{typography.button}` | JetBrains Mono | 12px | 700 | 1 | 0.08em | upper | Buttons. |
| `{typography.code}` | JetBrains Mono | 13px | 400 | 1.5 | 0 | as written | Ids, YAML, JSON, traces, agent output. |

Rules:
- Use one `type-<token>` class per element (`type-label`, `type-display-md`). It sets family, size, weight, line height, tracking, case and width together.
- Display sizes are fluid `clamp()` values. Do not add breakpoint overrides for them.
- **Verbatim data is never case-changed.** Case ids, suite YAML, tool arguments and agent output are shown exactly as written, in `{typography.code}`. Uppercase is for the interface's own words.
- Prose stays in sentence case and under about 65 characters per line.
- An outlined word (`text-outline`) is a display-size device only: stroke, no fill, so what is behind it shows through.

## Layout

- **Spacing** is a px scale: `{spacing.hair}` 1 · `{spacing.xxs}` 4 · `{spacing.xs}` 8 · `{spacing.sm}` 12 · `{spacing.md}` 16 · `{spacing.lg}` 24 · `{spacing.xl}` 32 · `{spacing.xxl}` 48 · `{spacing.section}` 96. Tailwind's numeric utilities are px (`p-16` is 16px).
- **Grid lines.** A group of panels is a CSS grid with `gap: 1px` over a `{colors.hairline}` background, with each cell on `{colors.canvas}` (`grid-lines`). Lines come from the gap, not from per-cell borders, so intersections are exact.
- **Compartments are visible.** Every region has an edge. Outer frames are `{colors.hairline-strong}`; inner divisions are `{colors.hairline}`.
- **Borders**: `{borders.hair}` 1px for structure, `{borders.rule}` 2px for emphasis (the focus ring, a selected item, a panel that must stand out).
- **Density is bimodal.** Data regions are tight (8 to 12px cell padding). Around display type there is a lot of empty canvas.
- **Container**: 1440px maximum, 16px side gutters below 810px, 32px above.
- **Stacking**: `{zIndex.nav}` 40, `{zIndex.overlay}` 50, `{zIndex.dialog}` 60, `{zIndex.toast}` 70, `{zIndex.noise}` 90. No other values.

## Details

Used sparingly; each is graphic, not informational.

- ASCII framing in mono: `[ RUNS ]` for the active item or a section mark, `>>>` before a primary action, `///` as a separator.
- `®`, `©` and `™` as marks next to the wordmark or a display word.
- `REV` and `UNIT` labels in `{typography.micro}`.
- Crosshair `+` marks at some panel corners (`crosshair`).
- Hairline leader lines from a callout to what it describes.
- A small arrow in the top-right corner of a clickable panel.
- One global noise layer (`noise`): fixed, low opacity, `pointer-events: none`.
- An optional scanline overlay (`scanlines`) on a hero panel: static, subtle, `pointer-events: none`.
- Hard-stop line patterns (the flaky hatch, scanlines) are allowed. A colour fade is not.

## Components

- **Buttons** are 40px tall rectangles (44px on coarse pointers). Primary is a lime fill; secondary is a `hairline-strong` outline; destructive is a red outline. Hover inverts or brightens the border; press moves the button down 1px. At most one primary button per view.
- **Panels** have a header strip: title on the left in `{typography.headline}` or `{typography.label}`, metadata or actions on the right, a 1px line under it.
- **Tables** have a `{colors.surface-1}` header in `{typography.micro}`, rows divided by `{colors.hairline}`, numbers right-aligned. Below 810px a table scrolls sideways inside its panel.
- **Stat tiles** sit in a `grid-lines` row: a `{typography.label}` name, a `{typography.display-lg}` value, a `{typography.micro}` note.
- **Inputs** are `canvas` with a `hairline-strong` border and mono text. An invalid input has a red border and a red message linked with `aria-describedby`.
- **Dialogs and toasts** are `surface-2` with a 1px `hairline-strong` border. No shadow.
- **Navigation** is a 56px top bar. The active item is lime and bracketed. Below 810px the links collapse into a menu.

## Motion

Motion is short and mechanical.

- Durations: `{motion.duration.instant}` 80ms (press), `{motion.duration.fast}` 120ms (hover), `{motion.duration.base}` 200ms (reveal), `{motion.duration.slow}` 400ms (panel), `{motion.duration.count}` 800ms (numbers counting up).
- Easing: `{motion.easing.step}` or `{motion.easing.linear}`; `{motion.easing.mech}` where a move needs to settle. No springs, no bounce.
- Reveals clip or translate. They do not fade.
- Numbers count up once.
- Nothing loops, except one decorative element per page.
- With `prefers-reduced-motion`, everything is shown in its final state at once.

## Accessibility

- Text contrast is at least 4.5:1; borders that identify a control are at least 3:1.
- The focus ring is 2px lime, 2px away from the element, on every interactive element.
- No flicker or strobing, in any overlay or animation.
- Touch targets are at least 40px, 44px on coarse pointers.
- Decorative marks (crosshairs, ASCII, noise) are hidden from assistive technology.

## Responsive Behavior

| Name | Width | Changes |
|---|---|---|
| Mobile | below 810px | One column. Nav links collapse into a menu. Tables scroll inside their panel. Stat tiles go two-up. |
| Tablet | 810px | Two- and three-column grids. Full nav. |
| Desktop | 1199px | Full layouts; callouts sit beside display type. |

Display type scales by its own `clamp()`; it is never swapped for a smaller tier at a breakpoint.

## Do's and Don'ts

### Do
- Give every region a visible edge.
- Put one lime element in a view where the eye should land first.
- Keep failures loud and passes quiet.
- Label every status and every placeholder figure.
- Write short, plain, uppercase labels: attempts, cases, suites, baseline, candidate, regression, flaky, verdict.

### Don't
- Don't round anything.
- Don't add a second accent, a green pass, or an amber warning.
- Don't use red for emphasis, links or branding.
- Don't fade, blur or glow.
- Don't uppercase data the user or an agent wrote.
- Don't show an invented number. A figure is real, or it is marked as illustrative.

## Iteration Guide

1. Change a token here first, then run `pnpm --filter web gen:theme`. `apps/web/src/app/theme.css` is generated and never edited by hand.
2. `theme.test.ts` fails if the generated file is stale or a text pair drops below its contrast floor.
3. The boards at `/dev/design` (dev server only) show every token and the reference compositions. Check a change there at 1440, 810 and 390px.
4. When a page is rebuilt, replace its legacy class names (the `aliases` entries marked Legacy) with the tokens they point to.
