# 0047: App shell, session ownership and the page transition

Status: accepted (2026-10-14). Builds on [ADR 0042](0042-industrial-brutalist-design-system.md) and [ADR 0044](0044-motion-layer.md); amends both where noted.

## Context
The signed-in pages ran inside a top bar (`[projectId]/layout.tsx` for a project's pages, a page-local `BareHeader` for `/projects`). The overhaul brief asks for a left rail with mono nav items, a top strip carrying the project switcher, an environment/version label and a "services awake?" chip, a skip link and keyboard navigation, and for `PageTransition` to be mounted in the `(app)` layout.

Two of those conflict with what was written down. DESIGN.md's Navigation section says "a 56px top bar, the active item is lime and bracketed". ADR 0044 §5 says `PageTransition` is for `app/template.tsx` because a template remounts per navigation.

## Decision

### 1. A left rail and a top strip (deviation from DESIGN.md Navigation)
- **Top strip, 56px** (`top-nav` token height): wordmark, project switcher, `ENV` and `REV` marks, the API status chip, the account and Sign out.
- **Left rail, 220px**, from 810px up: `[ PROJECTS ]`, then the open project's name (a link to its overview), then `[ AGENTS ]`, `[ SUITES ]`, `[ RUNS ]`, `[ SETTINGS ]`. The active item has a 3px lime edge bar and lime text. Every item is bracketed, not only the active one: with an edge bar carrying the state, the brackets are the item's own style.
- **Below 810px** the rail collapses into the menu the top bar already had (same 810px breakpoint, same Escape-to-close). The switcher stays in the strip.
- On `/projects` no project is open, so the rail offers `[ PROJECTS ]` and a one-line hint, not dead links; the switcher shows a disabled "Select a project".
- A skip link is the first tab stop and lands on `#main-content`. ArrowUp, ArrowDown, Home and End move between rail links, on top of Tab.
- `ENV` is `NODE_ENV` (inlined at build time, so server and client agree): `Dev` or `Prod`, which says which build it is, not which host. `REV` is the package version, as DESIGN.md requires.

The red/lime rules are unchanged: lime is the active item (an outline-class use, a 3px bar and text), red appears nowhere in the shell.

### 2. The (app) layout owns the session
`(app)/layout.tsx` renders `AppFrame` (client), which loads `/auth/me` and `/projects` once, draws the shell and shares the result through `useAppSession()`. `[projectId]/layout.tsx` is deleted and `/projects` reads the context instead of fetching.

It reloads exactly where the code it replaces did: entering `/projects`, and entering a project from outside one. Moving between a project's pages or between projects reuses the load, as the old project layout did. The call set is unchanged.

### 3. `PageTransition` mounts in `(app)/layout.tsx` and keys on the pathname (amends ADR 0044 §5)
A layout never remounts, so `PageTransition` as ADR 0044 wrote it (an effect that runs on mount) would have run once and been skipped as the first mount. A template does not fix it: Next keys a template by the cache key of its direct child segment (`stateKey` in `next/dist/client/components/layout-router.js`, Next 16.3.8), and inside `(app)` that child is `projects` for every page, so an `(app)/template.tsx` would never remount either.

`PageTransition` now reads `usePathname()` and plays the clip wipe in a layout effect when the pathname changes. It never remounts anything, so page state, scroll and focus survive. The properties ADR 0044 required are kept and tested:
- **Enter only**; no exit.
- **The first run of an instance is skipped**, and so is a render that keeps the pathname (a search-param change).
- **Clip-path only**, cleared on completion, so `position: fixed` descendants keep the viewport as their containing block.
- **Streaming:** `children` is still a server slot. A test suspends a boundary inside, changes the pathname, resolves it mid-wipe and checks the content arrives in the same wrapper and nothing stays clipped.
- **CSP:** it injects no script or style element and writes only through the CSSOM. A test pins the policy's `style-src`/`script-src` it depends on; `e2e/15` fails on any CSP violation.
- **Reduced motion:** nothing is created and the markup is untouched.

It sits inside the shell's `<main>`, so the rail and the strip never wipe. It is mounted nowhere else: the landing page, the auth pages and the shared run view have no transition.

### 4. The status chip is passive and reports the API only
`wakeStatus` (`lib/api/wake.ts`) reads what the app's own requests have shown: `checking` until something answers, `waking` while the notice is up, `awake` after an answer, `down` once the 150 s wake budget is spent. It sends nothing, so the chip adds no request.

It is labelled `API`, not "services". The background pings to the demo agents' host (`NEXT_PUBLIC_WAKE_URLS`) are opaque (`no-cors`): they resolve for a 502 as for a 200, so they cannot tell awake from asleep. The chip's title says the agents' host is woken in the background.

The shell's chip never probes, because the shell's own calls answer it. The chip in `BareHeader` (auth, error and share pages) does: `probe` asks `/api/health` once through `awakeFetch` when nothing has answered, because `/register` and the error pages make no API call and would otherwise read "Checking" for good. It is the landing page's existing chip behaviour, and it starts a sleeping API waking while the visitor types.

`wakeStatus` has its own listener set. Reusing `wakeNotice`'s would have fired its subscribers for health changes and broken its existing test.

### 5. 404 and 500
`not-found.tsx`, `error.tsx` and `global-error.tsx` share `ErrorScreen`: an outlined code, a plain sentence, the ways out. They never print the error's message (it can carry server detail), only its digest. `global-error` replaces the root layout, so it brings its own `<html>`, fonts (`app/fonts.ts`, shared with the layout) and stylesheet, and its Home link is a plain anchor, because the router may be what failed.

`proxy.ts` sends a visitor with no session cookie to `/login` for every non-public path, so a 404 is only seen when signed in or on a public prefix. That is existing behaviour and is left alone.

### 6. Settings has a slot for alerts
Settings is a wide API-keys column and a narrow column of read-only panels. The narrow column ends with an `Alerts` panel marked "Not available yet" that says what reports a regression today (the CLI run and the GitHub Action check). It is a placeholder, labelled as one; there is no alert setting behind it.

## Consequences
- DESIGN.md's Navigation bullet is out of date for the app (it still describes the landing page's top bar correctly). It is not edited: ADR 0028 set the precedent that dashboard deviations live in an ADR.
- `useAppSession` throws outside the `(app)` layout, which is the point: a page that needs the session cannot be mounted without one.
- A project created in another tab does not appear in the switcher until `/projects` is entered or the page is reloaded.
- GSAP is now on every `(app)` route's first load. ADR 0044 measured 29.8 kB gzip for the wipe alone; the auth pages already load it through `useReveal`. It has not been re-measured here.
- The `[ ]` brackets and `///` are generated or `aria-hidden`, so accessible names stay "Projects", "Agents" and so on.
