# 0040: The landing hero's palette and type are scoped deviations from DESIGN.md

Status: accepted (2026-10-13)

## Context
The landing page's hero was rebuilt from a reference design: one full-viewport stage on a
1280 × 800 design frame, a looping video backdrop (a figure in a mirrored helmet, a thin amber
arc, low haze), a 48-column hairline grid, a three-line poster headline and a one-time
entrance. That design is warm: brown-black grounds and an amber light. DESIGN.md allows a
near-black canvas, white, one blue and the gradient cards, and nothing amber.

The hero is the one place where the product is a poster and not a dashboard, so the deviation
is allowed there and nowhere else (user decision). This ADR lists everything the hero bends, so
DESIGN.md stays the reference for the rest.

## Decision

### 1. The warm palette exists only inside the hero
The colors are custom properties on `.hero` in
`apps/web/src/components/landing/hero.module.css`. They are not DESIGN.md tokens, so they are
not in `theme.css` and no Tailwind utility can reach them from another page.

| Property | Value | Use |
|---|---|---|
| ground | `#0d0905` → `#130e09`, eight stops | the stage's vertical gradient |
| `--ink` | `#ffffff` | all text |
| `--rule` | `rgba(255,255,255,0.115)` | the rule under the services |
| `--grid` | `rgba(255,255,255,0.0265)` | the 48 column lines |
| `--menu-bg` / `--menu-ink` | `#fcfcfc` / `#141414` | the "Get started" block |
| `--scrim` | `13 9 5` (the ground's darkest stop) | scrim and label pads |

The amber itself is only in the video. The sections under the hero on the same page (How it
works, the CLI example, the gradient card, the footer) keep `canvas` and the existing tokens;
the hero ends in a hard cut to `canvas`, which is DESIGN.md's own way of separating bands.

### 2. What else the hero bends, and what it keeps
- **A gradient ground and a video on a whole section.** DESIGN.md keeps gradients on cards.
- **The primary CTA is a squared white block, and "Sign in" is plain text**, as in the
  reference. Everywhere else CTAs stay pills (`buttonClasses`).
- **Small type is 12.6 design px**, floored at 10 px (11.28 px from 480 px of height, 12 px in
  the portrait layouts). That is below DESIGN.md's 12 px `micro` only on short landscape
  windows.
- **The headline is weight 700**, not the display tiers' 500, at 170.94 design px. Its
  tracking is DESIGN.md's display percentage (−5%).
- **Focus is a 1 px white outline at 3 px offset.** The blue ring (ADR 0028 §4) was measured
  against `surface-1`; over the video and next to the white block, white is the visible one.
- **Touch targets** are 44 px hit areas around the drawn shapes under `pointer: coarse`, not
  44 px pills. The two stacked GitHub links get 24 px each, so their areas don't overlap.
- **Kept: the fonts.** Geist draws the headline and the wordmark, Inter the small type
  (ADR 0004). The reference's own grotesque was not adopted, so its per-letter placement table
  does not apply: each line is set as text, centred, with its baseline pinned in CSS. A line
  may be up to 6.3 em wide; REGRESSION, the widest, measures 6.06 em.
- **Kept: dark only**, and the wordmark instead of the reference's logo.

### 3. The video is self-hosted
The reference's video URL was reachable without credentials, so it was downloaded once and
re-encoded; the page never requests the original host.

| | Source | Shipped (`apps/web/public/hero.mp4`) |
|---|---|---|
| Size | 1212 × 756, 5.6 MB | 1154 × 720, 1.1 MB |
| Codec | H.264 Main | H.264 High, yuv420p, CRF 20, faststart, no audio track |
| Length | 10.04 s at 24 fps | the same |

`hero-poster.webp` (14 KB) is its first frame, so the poster and the start of playback match.

- The element is `muted`, `loop`, `playsInline`, `preload="metadata"`, and has **no `autoplay`
  attribute**. A client component starts playback, and only when `prefers-reduced-motion` is
  not `reduce`. With reduced motion, without JavaScript, or when the browser refuses autoplay,
  the poster stays.
- The plate's box is reserved by `aspect-ratio` and absolute positioning, so nothing shifts
  when the poster or the video arrives.
- The CSP gains an explicit `media-src 'self'` (amends ADR 0039). Nothing else changed:
  `default-src 'self'` already limited media to this origin, and the poster is covered by the
  existing `img-src`.
- The web Docker image now copies `public/`; it had none before.

### 4. The entrance is CSS only
The reference starts its entrance from an inline script that runs before first paint. The CSP
allows no script without the per-request nonce, and a hydrated component would run after the
first paint and flash the finished page first. So the entrance is plain CSS animations inside
`@media (prefers-reduced-motion: no-preference)`: the same keyframes, durations, delays and
easings, starting with the first paint. Every animation fills backwards only and the clips are
themselves animations, so nothing is left running or clipped afterwards (measured: no running
animation and no clip-path in the hero 3 s after load). What is lost is the reference's wait
for web fonts before it starts; `next/font` preloads them.

### 5. Contrast over the video
A scrim sits between the video and the grid: a wash of the ground color under the headline
(50%), and a soft pad of it behind each service label (72%), because the helmet's highlights
and the arc pass under them. On landscape phones the frame is short enough that the top bar's
text crosses the helmet too, so that layout adds the same wash behind the bar (72%).

Measured in Chrome against the worst case: the poster replaced by the per-channel maximum of
all 241 frames (an upper bound on every pixel's luminance over the loop), the text hidden, and
the brightest pixel under each text box compared with white. Small text needs 4.5:1, the
headline 3:1.

| Viewport | Lowest small text | Lowest headline line |
|---|---|---|
| 1440 × 900 | 5.55 | 3.71 |
| 1280 × 800 | 5.27 | 3.74 |
| 1920 × 1080 | 5.70 | 3.66 |
| 810 × 1080 | 5.41 | 17.31 |
| 390 × 844 | 5.28 | 18.79 |
| 320 × 568 | 5.30 | 18.44 |
| 844 × 390 | 6.10 | 3.70 |
| 667 × 375 | 4.83 | 3.66 |
| 568 × 320 | 5.04 | 3.71 |

768 × 1024, 1024 × 768, 740 × 360, 932 × 430 and 540 × 400 were measured as well and pass. Above
the landscape-phone layout the lowest small text is always a service label, and the top bar
never falls below 16.8. The frames' peak luma under the label rows is 220 to 224 of 255, about
1.3:1 against white with no scrim; before the bar's wash, small text measured 1.09 at
568 × 320. "Get started" is `#141414` on
`#fcfcfc`, 17.96:1.

### 6. Layout notes
- The breakpoints are the reference's composition breakpoints (aspect ratio first), not
  DESIGN.md's 810/1199, and apply to the hero only.
- The service labels are longer than the reference's. Under 680 px in the portrait layout they
  wrap to two lines and the rule moves down a line; the reference only wraps under 310 px.
- No `viewport-fit=cover`: the sections under the hero are not safe-area aware. The hero's
  `env(safe-area-inset-*)` terms resolve to 0 until that changes.

## Consequences
- A hero color never goes into DESIGN.md's front matter. If another page needs one, that is a
  new decision, not a reuse.
- Changing the headline means checking the new lines' width (6.3 em) and re-running the
  contrast measurement if the scrim or the video changes.
- The repository carries a 1.1 MB binary. A replacement video must be re-encoded the same way
  (H.264, no audio, at most 1280 × 720 and 6 MB) and get a matching first-frame poster.
- Vitest covers the headline, links and reduced-motion behaviour; the e2e spec covers the CTAs,
  the self-hosted media and CSP violations. Playwright's Chromium has no H.264 decoder, so
  playback itself is checked by hand in Chrome.
