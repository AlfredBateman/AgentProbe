# 0046: Landing motion and the 3D hero figure

Status: accepted (2026-10-14). Builds on [ADR 0044](0044-motion-layer.md) (motion layer) and [ADR 0045](0045-static-landing-page.md) (the static landing page, whose layout is unchanged).

## Context
The static landing page reserved a 4:3 box in the hero for a 3D piece and had no motion. This step adds both. The page must stay the same layout, keep the nonce CSP strict (no `eval`, no inline script), and leave every other route's bundle untouched.

## Decision

### 1. Motion is client islands over the server page
`components/landing/motion.tsx` holds four small client components: `SplitHeading` (the `h1`), `CountUp`, `Reveal` and `Stagger`. Each renders the same element, classes and text the static page had, so the server HTML is unchanged apart from a `data-motion="hidden"` first-paint guard. All animation comes from the lib/motion hooks. Their props are strings, because they cross from server code. The hero callouts and two proof tiles count up; the three cards stagger in; the proof card and the install block clip in.

### 2. ScrollTrigger only for the proof scrub, loaded on demand
`proof-scrub.tsx` (`ScrubValue`) steps two proof figures from the baseline value to the candidate value (`10/10` to `0/10` passed, `98.9%` to `86.7%`) as the card's top edge moves from 75% to 25% of the viewport. The steps use DESIGN.md's `steps(6)`. The scrub runs both ways. `gsap/ScrollTrigger` is a dynamic `import()` inside it, run only where motion is allowed. Until it loads, the figure shows the baseline; if it fails to load, it shows the candidate. Without motion, the figures are the candidate values as rendered. Everything else keeps ADR 0044's IntersectionObserver.

### 3. The headline's first-paint guard expires after 600ms
The split reveal kept the `h1`, the page's LCP element, hidden until GSAP hydrated. On a simulated slow phone, LCP went from 1.0s to 2.9s. In `globals.css`, an `h1[data-motion="hidden"]` now shows by itself after 600ms (a zero-length CSS animation that sets `clip-path: none`). `useSplitHeading` skips the reveal when it finds the heading already shown, so a late script never flashes it. On a fast load the reveal plays as before.

### 4. One 3D figure, loaded only when the device can take it
`hero-visual.tsx` keeps the static SVG in the box and decides once, on mount, with `wants3D`:
- no on `prefers-reduced-motion` (or the `/dev` reduce switch);
- no on a viewport under 600px;
- no on `hardwareConcurrency <= 2`;
- otherwise it creates a WebGL2 context, and has no WebGL on a failure.

The context check runs last, so a no never creates a context. On a yes it imports `hero-scene.ts` (three) and hands it that canvas and context to reuse. On a no, three is never requested.

The scene is a 20 x 15 instanced grid of tiles, one per attempt of one case, inside a wireframe box. As the hero scrolls out, a fixed 30% of the tiles flip over like split-flap tiles, from pass to fail. A deterministic hash picks the tiles, so every visit is the same.
- Pass tiles are filled `accent` squares. Fail tiles are DESIGN.md's fail mark, a `fail` square with a knocked-out cross. The cross is a shape, so pass and fail differ by more than hue.
- The frame is `hairline-strong`.
- Materials are unlit `MeshBasicMaterial`/`LineBasicMaterial`, so every pixel is a flat token colour. There is no light, fog, glow or post-processing, and colours are read from the CSS variables at mount.
- Mouse parallax is at most 3 degrees, mouse only.

Frames are requested only while the box is on screen (IntersectionObserver) and the tab is visible, and are drawn only when the scroll or the parallax changed. `devicePixelRatio` is capped at 2. On unmount, the geometries, materials and renderer are disposed, the context is force-lost and the canvas is removed. The box keeps an `ILLUSTRATIVE` tag on its bottom edge, and the caption reads `Fig. 01 /// Attempt grid /// Illustrative`.

### 5. Deviation: lime as the pass colour, in this figure only
DESIGN.md says lime is never a pass colour. The brief for this figure asked for tiles that flip from lime (pass) to red (fail), like a regression appearing. That holds here because the figure is illustrative, decorative (`aria-hidden`) and is the hero's one emphasised element, which DESIGN.md allows to be lime. Status displays of real data keep `ink` for pass.

## Consequences
- **Bundle** (`next build`, gzip level 9, first-load JS per route from `route-bundle-stats.json`): every route except `/` is byte-identical to before. `/` goes from 141.0 to 176.4 kB (gsap core, CSSPlugin, CustomEase, SplitText and the islands).
- **Async chunks:** three is 133.3 kB gzip (541.9 kB raw, 109.3 kB brotli), loaded only on a capable desktop. ScrollTrigger is 17.5 kB gzip. Neither contains `eval` or `new Function`.
- **three:** `three@0.186.1` and `@types/three@0.186.0`, pinned exactly in `apps/web` only. The scene imports named exports only, so the bundler can tree-shake the rest; the result is within the 200 kB budget.
- **Web vitals** (Chromium, median of 3; "slow" is 4x CPU, 150ms RTT, 1.6 Mbps):

  | Width | LCP before | LCP after | LCP slow, before | LCP slow, after | CLS after |
  |---|---|---|---|---|---|
  | 1440 | 172ms | 744ms | 1088ms | 1736ms | 0.012 |
  | 810 | 164ms | 708ms | 1076ms | 1656ms | 0.010 |
  | 390 | 164ms | 752ms | 1032ms | 1564ms | 0.005 |

  CLS is unchanged from the static page, and scrolling through the page adds at most 0.0002. Fast LCP grows by the reveal itself (about 0.6s); slow LCP is capped by decision 3. Lighthouse is not installed, so these come from Chromium's PerformanceObserver.
- **Tests:**
  - `hero-visual.test.tsx`: the fallback decision table, that three is never imported on a no, and that unmount tears the scene down.
  - `components/landing/motion.test.tsx`: each animated figure formats back to its own text, and the final figures show without motion.
  - lib/motion's tests gained the guard-expiry cases.
  - `e2e/14-landing.spec.ts`: on desktop the canvas renders, the scrub reaches the candidate figures, and there is no console error, CSP violation, overflow or CLS of 0.1 or more. With reduced motion and at 390px the SVG stays and `window.__THREE__` is never set.
