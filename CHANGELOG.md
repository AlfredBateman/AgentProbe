# Changelog

## 0.2.0 (2026-10-17)

### New look
- Redesigned landing page and app on a new design system, with a left navigation rail and light motion.
- The landing page's 3D hero figure loads only on larger screens. Phones, low-power devices and reduced-motion settings get a static figure instead.

### Clearer results
- Failure clusters now read as plain statements of what failed.
- Attempts that gave the same output are grouped into one row ("10 attempts, identical output") that opens to the attempts themselves.
- The mock summarizer writes readable summaries.
- Tables that are wider than the screen on mobile scroll sideways inside a labelled region with a visible hint.

### Fixes
- Saving an attempt now holds the run's lock only for the final counter update, not for the whole save. This fixes slow saves and flaky end-to-end tests.
- Failure clustering computes each pairwise distance once instead of recomputing them on every merge.

### Housekeeping
- Removed the unused card variants.
- Added an accessibility check that covers every page of the app at 1440, 810 and 390 px.

## 0.1.0 (2026-10-04)

First release. See the [v0.1.0 release notes](https://github.com/AlfredBateman/AgentProbe/releases/tag/v0.1.0).
