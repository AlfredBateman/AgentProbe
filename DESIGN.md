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
    fontSize: clamp(28px, 15cqi, 232px)
    fontWeight: 900
    lineHeight: 0.85
    letterSpacing: -0.04em
    wordSpacing: 0.2em
    textTransform: uppercase
    fontStretch: 75%
  display-xl:
    fontFamily: Archivo
    fontSize: clamp(36px, 9vw, 120px)
    fontWeight: 900
    lineHeight: 0.88
    letterSpacing: -0.04em
    wordSpacing: 0.2em
    textTransform: uppercase
    fontStretch: 75%
  display-lg:
    fontFamily: Archivo
    fontSize: clamp(34px, 5vw, 64px)
    fontWeight: 800
    lineHeight: 0.9
    letterSpacing: -0.04em
    wordSpacing: 0.18em
    textTransform: uppercase
  display-md:
    fontFamily: Archivo
    fontSize: clamp(24px, 3vw, 36px)
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: -0.03em
    wordSpacing: 0.17em
    textTransform: uppercase
  headline:
    fontFamily: Archivo
    fontSize: 18px
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: -0.02em
    wordSpacing: 0.16em
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
  noise: -1

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
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.accent}"
    borderColor: "{colors.accent}"
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
| `{colors.accent}` | #CAFF00 | Brand, primary action (the one fill), focus ring, selection, the active nav item, an improvement verdict (outline only). |
| `{colors.on-accent}` | #0A0A0A | Text on a lime fill. |
| `{colors.fail}` | #FF2A2A | Failure, regression, destructive actions. As text, border or fill. |
| `{colors.on-fail}` | #0A0A0A | Text on a red fill. |

Rules:
- No other hue. There is no green and no amber. Greys are neutral; none is tinted.
- Lime is never a "pass" colour. A passing case is plain `ink`, so a table of passes stays quiet and a failure stands out.
- A solid lime fill means exactly two things: the primary action, and the single emphasised panel of a hero. Everything else that is lime (a verdict, a link, a rule, a nav item) is an outline or text, never a fill.
- Red is never decoration. If nothing failed and nothing is being destroyed, there is no red on the page.
- Text uses `ink`, `ink-muted`, `accent` or `fail` on the three surfaces, or `on-accent` / `on-fail` on their fills. `theme.test.ts` checks every one of those pairs at 4.5:1.

### Status encoding

A status is never told by colour alone. Each has its own mark, a shape that still reads in greyscale, and always carries its text label. Marks are 10px squares (`mark-fail` and `mark-error` in `globals.css` draw the two glyph marks, and scale down to attempt-matrix cells).

| Status | Mark (10px) | Colour | Chip border |
|---|---|---|---|
| Pass | filled square | `ink` | 1px `hairline-strong` |
| Fail | filled square with a knocked-out cross (`mark-fail`) | `fail` | 1px `fail` |
| Flaky | hatched square (`///`) | `ink` | 1px dashed `ink` |
| Error | hollow square with a `!` (`mark-error`) | `ink-muted` | 1px `hairline-strong` |
| Stable | 2px bar | `ink` | 1px `hairline-strong` |
| Running | hollow square, left half filled (`mark-running`) | `ink` | 1px `ink` |
| Queued | two stacked 2px bars (`mark-queued`) | `ink-muted` | 1px `hairline-strong` |
| Quarantined | hollow square struck through (`mark-quarantined`) | `ink-muted` | 1px dotted `hairline-strong` |

The cross is `on-fail` on a `fail` fill (5.30:1). The error mark's grey is `ink-muted`, 7.04:1 on `canvas`, 6.66:1 on `surface-1` and 6.19:1 on `surface-2`, all above the 4.5:1 text floor and the 3:1 mark floor. A legend for a chart or matrix uses the same marks.

Verdicts: `REGRESSION` is a red fill with `on-fail` text, `IMPROVEMENT` is a lime outline with lime text and no fill, `NO CHANGE` is an `ink` outline.

## Typography

Two families, both loaded with `next/font` and served from the app's own origin.

- **Archivo** (variable weight and width): headlines and prose.
- **JetBrains Mono**: every label, number, control and piece of code.

| Token | Font | Size | Weight | Line height | Tracking | Case | Use |
|---|---|---|---|---|---|---|---|
| `{typography.display-xxl}` | Archivo, 75% width | clamp(28px, 15cqi, 232px) | 900 | 0.85 | −0.04em | upper | The landing headline. |
| `{typography.display-xl}` | Archivo, 75% width | clamp(36px, 9vw, 120px) | 900 | 0.88 | −0.04em | upper | Section openers on the landing page. |
| `{typography.display-lg}` | Archivo | clamp(34px, 5vw, 64px) | 800 | 0.9 | −0.04em | upper | Stat values, large numbers. |
| `{typography.display-md}` | Archivo | clamp(24px, 3vw, 36px) | 800 | 0.95 | −0.03em | upper | Page titles. |
| `{typography.headline}` | Archivo | 18px | 800 | 1.1 | −0.02em | upper | Panel and dialog titles. |
| `{typography.body-lg}` | Archivo | 17px | 400 | 1.5 | 0 | sentence | Lead paragraphs. |
| `{typography.body}` | Archivo | 15px | 400 | 1.5 | 0 | sentence | Prose: descriptions, findings, errors. |
| `{typography.body-sm}` | Archivo | 13px | 400 | 1.45 | 0 | sentence | Help text. |
| `{typography.label}` | JetBrains Mono | 11px | 500 | 1.3 | 0.08em | upper | Field labels, nav, chips, column groups. |
| `{typography.micro}` | JetBrains Mono | 10px | 500 | 1.2 | 0.1em | upper | Table headers, REV/UNIT marks, short footnotes. |
| `{typography.data}` | JetBrains Mono | 13px | 400 | 1.4 | 0.05em | upper | Table cells and readouts. |
| `{typography.button}` | JetBrains Mono | 12px | 700 | 1 | 0.08em | upper | Buttons. |
| `{typography.code}` | JetBrains Mono | 13px | 400 | 1.5 | 0 | as written | Ids, YAML, JSON, traces, agent output. |

Rules:
- Use one `type-<token>` class per element (`type-label`, `type-display-md`). It sets family, size, weight, line height, tracking, case, width and word spacing together.
- Display sizes are fluid `clamp()` values. Do not add breakpoint overrides for them.
- `display-xxl` is sized against its container (`cqi`), so the widest headline word fits at any width and in any nesting. Put the headline inside an `@container` element; without one it falls back to the viewport width, as `vw` would.
- **Word spacing is part of the tier.** Tight tracking and heavy caps close up the space glyph (Archivo also kerns against it: "AT YOUR" collapses to "ATYOUR"), so every tier tracked below zero sets `wordSpacing` to bring the narrowest kerned space back to about 0.28em. `theme.test.ts` fails if a tier tracked below zero has none.
- **Mono uppercase is for labels and data only.** Anything longer than about 8 words is prose: set it in `{typography.body}` or `{typography.body-sm}`, Archivo, sentence case. That includes card descriptions, explanatory notes and captions with a full sentence in them. A chart or board note that is a short label (`Fig. 01 /// Attempt matrix`) stays in `{typography.micro}`.
- A `REV` mark shows the app's package version, read from `package.json`. Never type a version number into a design.
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
- **Stacking**: `{zIndex.nav}` 40, `{zIndex.overlay}` 50, `{zIndex.dialog}` 60, `{zIndex.toast}` 70. No other values, except `{zIndex.noise}` −1: the grain sits behind the content, so it never lowers the contrast of text.

## Details

Used sparingly; each is graphic, not informational.

- ASCII framing in mono: `[ RUNS ]` for the active item or a section mark, `>>>` before a primary action, `///` as a separator.
- `®`, `©` and `™` as marks next to the wordmark or a display word.
- `REV` and `UNIT` labels in `{typography.micro}`.
- Crosshair `+` marks at some panel corners (`crosshair`).
- Hairline leader lines from a callout to what it describes.
- A small arrow in the top-right corner of a clickable panel.
- One global noise layer (`noise`): fixed, low opacity, `pointer-events: none`, **behind** the content. It textures the canvas between panels; over text, its lightest pixels would take `fail` on `surface-2` from 4.65:1 to 4.16:1.
- An optional scanline overlay (`scanlines`) on a hero panel: static, subtle, `pointer-events: none`. Only over a figure: text inside the panel sits above the lines (`relative` with `{zIndex.raised}`).
- Hard-stop line patterns (the flaky hatch, scanlines) are allowed. A colour fade is not.

## Components

- **Buttons** are 40px tall rectangles (44px on coarse pointers). Primary is a lime fill; secondary is a `hairline-strong` outline; destructive is a red outline. Hover inverts or brightens the border; press moves the button down 1px. At most one primary button per view.
- **Panels** have a header strip: title on the left in `{typography.headline}` or `{typography.label}`, metadata or actions on the right, a 1px line under it.
- **Tables** have a `{colors.surface-1}` header in `{typography.micro}`, rows divided by `{colors.hairline}`, numbers right-aligned. A table wider than its panel scrolls sideways inside it (`ScrollRegion`): while it overflows it is a labelled, focusable region with a `Scroll sideways` strip above it whose arrows point to the hidden columns. A header is never cut off.
- **Stat tiles** sit in a `grid-lines` row: a `{typography.label}` name, a `{typography.display-lg}` value, a `{typography.micro}` note.
- **Inputs** are `canvas` with a `hairline-strong` border and mono text. An invalid input has a red border and a red message linked with `aria-describedby`.
- **Dialogs and toasts** are `surface-2` with a 1px `hairline-strong` border. No shadow.
- **Checkboxes and switches** are native inputs. A checkbox is an 18px square, checked is an `ink` square inside it; a switch has a sliding square thumb. Neither is ever a lime fill.
- **Tabs** are a bordered strip. The selected tab is lime, bracketed (`bracketed`) and one surface step up.
- **Tooltips** are `surface-2` with a 1px `hairline-strong` border, in `{typography.body-sm}`. They show on hover and on focus, and Escape dismisses them.
- **Pagination** is a row of 40px squares; the current page is a lime outline with lime text.
- **Skeletons** step through two greys in four hard steps. They never shimmer.
- **Sparklines** are a 1.5px line in the current colour with a square marker on the last value.
- **Navigation**, in the app (everything signed in): a 56px top strip (wordmark, project switcher, `ENV` and `REV` marks, API status, account) over a 220px left rail of mono items, `[ PROJECTS ]`, `[ AGENTS ]`, `[ SUITES ]`, `[ RUNS ]`, `[ SETTINGS ]`. The active item is a lime edge bar with lime text. Below 810px the rail collapses into a menu and the switcher stays in the strip. Skip link first; arrow keys move along the rail. See [ADR 0047](docs/decisions/0047-app-shell-and-page-transition.md).
- **Navigation**, on the landing and the public pages: a 56px top bar with the wordmark and links, collapsing into a menu below 810px.

## Charts

Charts follow the same rules as the rest of the system, plus these ([ADR 0050](docs/decisions/0050-compare-findings-shared-and-export.md)):

- **Lime marks the candidate.** In a chart, lime is the run under examination (a stroke, a marker, a bar, an attempt square). A baseline is `ink`. Red is failure only. This is the one place lime is used for "pass"; chips, badges and table cells keep the status encoding above.
- **Telemetry style.** Mono axis labels, 1px strokes, flat fills, a fixed 0 to 100% scale for rates, square markers. No colour fade, no shadow.
- **Direct labels, no legend.** Every row or marker names itself; a flaky bar is hatched, a failure is the cross mark, so no series is told by colour alone. One exception: a page whose attempt marks use lime for the candidate (compare) has a one-line key above its charts saying what lime, white and red mean there.
- **A table view.** Every figure carries its plotted values as a table (`ChartFigure` requires one).
- **Motion.** One stepped draw-in (`steps(6, end)`, 400ms, a clip) and nothing else; reduced motion shows the finished chart.
- **Few runs.** Below three runs a trend marks every point and leaves out its interval band. A series with nothing to plot (no cost recorded) is one line of text, not an empty frame.

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
- The focus ring is 2px lime, 2px away from the element, on every interactive element. It never transitions: a control that animates its colours lists them (`transition-[background-color,color]`), never `transition-colors`, which would fade the ring in.
- No flicker or strobing, in any overlay or animation.
- Touch targets are at least 40px, 44px on coarse pointers. A text link or a small control sized by its text takes the `tap` utility, which gives it 44px each way on a coarse pointer only. A link inside a sentence is underlined as well as lime.
- Decorative marks (crosshairs, ASCII, noise) are hidden from assistive technology.

## Responsive Behavior

| Name | Width | Changes |
|---|---|---|
| Mobile | below 810px | One column. Nav links collapse into a menu. Tables scroll inside their panel. Stat tiles go two-up. |
| Tablet | 810px | Two- and three-column grids. Full nav. |
| Desktop | 1199px | Full layouts; callouts sit beside display type. |

Display type scales by its own `clamp()`; it is never swapped for a smaller tier at a breakpoint. It must not overflow its container from 320 to 1440px; check the widest word (REGRESSIONS is 5.75em at `display-xxl`).

## Do's and Don'ts

### Do
- Give every region a visible edge.
- Put one lime element in a view where the eye should land first. Fill it only if it is the primary action or the one emphasised hero panel.
- Keep failures loud and passes quiet.
- Label every status and every placeholder figure.
- Write short, plain, uppercase labels: attempts, cases, suites, baseline, candidate, regression, flaky, verdict.

### Don't
- Don't round anything.
- Don't add a second accent, a green pass, or an amber warning.
- Don't use red for emphasis, links or branding.
- Don't fade, blur or glow.
- Don't uppercase data the user or an agent wrote.
- Don't set sentences in mono uppercase. Prose is Archivo in sentence case.
- Don't use a lime fill for a status or verdict.
- Don't tell a status by colour alone: every status has its own shape.
- Don't show an invented number. A figure is real, or it is marked as illustrative.

## Iteration Guide

1. Change a token here first, then run `pnpm --filter web gen:theme`. `apps/web/src/app/theme.css` is generated and never edited by hand.
2. `theme.test.ts` fails if the generated file is stale or a text pair drops below its contrast floor.
3. The boards at `/dev/design` (dev server only) show every token and the reference compositions. Check a change there at 1440, 810 and 390px.
4. There are no alias names. A status or a chart series uses the colour token it means (`ink` for pass, `fail` for failure), so one name always means one value.
