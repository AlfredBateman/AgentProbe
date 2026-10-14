# 0043: UI primitives on the brutalist system

Status: accepted (2026-10-14). Builds on [ADR 0042](0042-industrial-brutalist-design-system.md).

## Context
ADR 0042 replaced the tokens and left every primitive in `apps/web/src/components/ui` on the old look, running on aliases. This step rebuilds the primitives, the global stylesheet and `/dev/components` on the new tokens. No page is rebuilt, so every primitive keeps its name and props: pages compile unchanged.

## Decision

### 1. Names stay, looks change
- `Button` variants: `primary` (lime fill), `secondary` (outline), `danger` (red outline), `ghost`, `icon`. `translucent` stays as the secondary outline, because pages use it.
- `Card` is `Panel` under its old name (`export { Panel as Card }`), with `lifted`, `title` and `actions` unchanged. `Panel` adds `titleStyle`, `href` (the whole panel is one stretched link on its title, with the corner arrow) and `crosshair`.
- `GradientCard` keeps its name and is still a flat panel with a 2px lime border. A solid lime panel would put `text-ink` children on lime in the findings page; the hero that earns the fill is rebuilt with the landing page.
- `DataTable`, `Dialog`, `Tabs`, `ToastProvider`/`useToast`, `Skeleton`, `EmptyState`, `CodeBlock`, `PlainText`, `CopyButton`, `Input`, `Textarea`, `Select`, `Label`, `FieldError`, `Badge` and `StatusDot` keep their props. `Label` gains `caption`; `CodeBlock` and `PlainText` gain `as`.

### 2. New primitives
`Checkbox`, `Switch` (native inputs, so keyboard and form behaviour are the browser's), `Stat` and `StatGrid`, `Tooltip`, `Pagination`, `Sparkline`, `AsciiFrame` and `Crosshair`. Decorative marks are `aria-hidden`; generated-content marks (`crosshair`, `bracketed`) carry empty alt text.

### 3. Status vocabulary grows to eight
`running`, `queued` and `quarantined` join pass, fail, flaky, error and stable. They are grey or ink, never a hue, and each has its own 10px shape: running a hollow square with its left half filled, queued two stacked bars, quarantined a hollow square struck through. DESIGN.md's status table lists them.

### 4. Lime is never a control fill
A checked checkbox is an `ink` square inside the box and a switch's thumb slides, so on and off differ by shape and position. The current page in `Pagination` and the selected `Tab` are lime text and outline, not a fill. This keeps "a solid lime fill is the primary action or the one hero panel" true of every primitive.

### 5. No gradient keyword at all
`hatch` and `scanlines` were drawn with `repeating-linear-gradient`, and `mark-fail` and `mark-error` with `linear-gradient`. They are now an SVG mask (`hatch`), an SVG tile (`scanlines`) and positioned pseudo-elements (`mark-*`), so a search of the source for the word finds only the legacy `GradientCard` name. `no-radius-gradient.test.ts` fails on any `rounded-*`, `borderRadius`, rounded SVG shape, `gradient` or `bg-linear-*` in the source, and requires that the single `border-radius` declaration is the global `0 !important` reset. This also removed `rounded-*` from 17 page and component files (a mechanical edit; the global reset already made them square).

### 6. Layers
The noise layer is mounted once, in the root layout. Page-wide scanlines are off unless `<html data-scanlines>` is set. Both sit at `z-noise` (90), above the toast (70).

### 7. Details
- Table cells are `code` type, not `data`: `data` is uppercase, and a table cell is usually verbatim (case ids, agent output). A column opts into uppercase with `className`.
- `PlainText` and `CodeBlock` render `<pre><samp>` (agent output), `<pre><kbd>` (an attack payload typed at the agent) or `<pre><code>`. Text is still a text child only.
- Skeletons step through four greys over 1.2s and stop under reduced motion. That is a loop; it is a loading indicator and not decoration, and a static block would not say "loading".
- Transitions list `background-color`, `border-color` and `color` explicitly. `transition-colors` also animates `outline-color`, which made the focus ring fade in from the text colour.
- The focus ring is the global `:focus-visible` rule; primitives set no focus style of their own.
- Chart tooltips and active dots lose their radius (the active dot is a square).

## Consequences
- Pages still carry their own `rounded`-free but otherwise legacy class names (`text-accent-blue`, `text-data-label`, `font-display`) and mix the new primitives with old layouts until they are rebuilt.
- `Button` has no "one primary per view" guard; `/dev/components` shows several primaries because it is a catalogue.
- A `Stat` count-up needs `gsap`, which ADR 0042 allowed and which is not installed yet; the number appears at once.
- Hover and press are verified by eye on `/dev/components`; the focus ring is shown forced beside the real one.
