# 0044: Motion layer on GSAP

Status: accepted (2026-10-14). Builds on [ADR 0042](0042-industrial-brutalist-design-system.md) (DESIGN.md `motion` tokens) and [ADR 0043](0043-ui-primitives-on-the-brutalist-system.md).

## Context
The UI overhaul needs reveals, count-ups, staggered rows, a heading reveal and a page transition. The brief fixed GSAP as the one animation library, a hooks-only layer, reduced motion honoured everywhere, transform/opacity/clip-path only, and the nonce CSP (no inline scripts, no eval) untouched. DESIGN.md's Motion section adds: reveals clip or translate and do not fade, numbers count up once, no springs or bounce.

## Decision

### 1. Shape: `apps/web/src/lib/motion`
- `core.ts`: the DESIGN.md duration and easing tokens (in seconds), `whenMotionAllowed(scope, setup)`, `whenVisible(el, play)`. `tokens.test.ts` fails if they drift from DESIGN.md's front matter.
- `hooks.ts`: `useReveal`, `useStagger`, `useCountUp`. `split-heading.ts`: `useSplitHeading`, apart so SplitText ships only where used. `page-transition.tsx`: `PageTransition`.
- No barrel file; import the module you need.

### 2. Reduced motion is the absence of animation
Every hook builds its tweens inside one `gsap.matchMedia()` handler for `(prefers-reduced-motion: no-preference)`. Under `reduce` the handler never runs, so nothing is created, no inline style is written and the server-rendered markup is already the final state. GSAP reverts a handler's tweens, inline styles and SplitText when the query stops matching and on unmount. `<html data-reduce-motion>` forces the same path (the `/dev/components` switch); `gsap.matchMediaRefresh()` applies it live.

### 3. No opacity, no ScrollTrigger, no `@gsap/react`
- **No opacity.** DESIGN.md says reveals do not fade. Reveals animate `clip-path` and, for rows, a small `y` translate; both are cleared on completion, and `will-change` is never set.
- **No ScrollTrigger.** Every scroll need here is "play once when first visible". `IntersectionObserver` does that natively at zero bytes; ScrollTrigger would add about 12 kB. It can be added when a pinned or scrubbed effect exists.
- **No `@gsap/react`.** `gsap.matchMedia()` already owns a context and reverts it, and GSAP's guidance is not to nest `gsap.context()` inside it, so `useGSAP` would be a second wrapper around the same cleanup. One dependency, `gsap@3.15.0`, pinned exactly.

### 4. Count-up leaves the text node to React
`useCountUp` writes only `nodeValue` of the element's one text node, never replaces it. The hook returns the formatted final text for the caller to render, so React's own commit is the truth. Every end path (complete, cleanup, reduced motion, a value change mid-count) writes that text. It counts once, on mount; later values just show.

### 5. Page transition is enter-only and unwired
`PageTransition` is meant for `app/template.tsx`, which remounts per navigation. It is a clip wipe only (a transform on the wrapper would become the containing block of `position: fixed` dialogs and toasts), and it skips a tab's first mount, which is the server-rendered page. There is no exit animation: holding the old route in the tree fights streaming and Suspense. `children` stays a server slot, so streaming is untouched. It is not mounted in `app/template.tsx` yet: that is a change to every route, and the pages are still being rebuilt.

### 6. CSP
GSAP 3.15 contains no `eval` or `new Function` (checked in the files this layer imports and in the built chunk). It writes styles through the CSSOM, which `style-src` does not govern, and injects no script. `proxy.ts` is unchanged. The browser run showed no CSP violation under the dev policy.

### 7. First-paint guard
`[data-motion="hidden"]` in `globals.css` clips a server-rendered element until its hook runs, only under `(scripting: enabled) and (prefers-reduced-motion: no-preference)`; the hook removes the attribute in every case. Without scripts or with reduced motion the content is simply there.

## Consequences
- Measured with `next build` (route-bundle-stats, gzip) by temporarily mounting the layer in a root `template.tsx`: `PageTransition` alone adds **29.8 kB** to every route's first load (gsap core, CSSPlugin and CustomEase; a clip wipe is the cheapest effect and still pays for the engine); all four hooks plus SplitText add **33.5 kB** (30.2 kB brotli), so SplitText itself is 3.7 kB. Base first loads are 133 to 253 kB, so that is +12 to +25%. No ScrollTrigger, Flip, Draggable or other plugin code is in the chunk.
- The cost is paid once and shared: the plugins are in a single chunk. If it matters, the next lever is loading GSAP with a dynamic `import()` from the effect, which takes it out of first load at the price of async setup and cleanup in `whenMotionAllowed`. Not done: no route uses it yet, so there is nothing to optimise.
- Rows past the first 40 in a stagger just appear, which bounds the tween count on long tables.
- A content change that arrives after a reveal (streamed Suspense children, live run rows) is not animated; only elements present at mount are.
