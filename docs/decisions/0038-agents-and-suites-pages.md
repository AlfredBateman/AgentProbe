# 0038: Agents and suites pages, and suite versions that keep their YAML (E3)

Status: accepted (2026-10-03). Scope confirmed by the user the same day, including migration 0005.

## Context
E3 had a minimal slice. The agents page did HTTP only, with a URL and three response paths, and its edit rebuilt the whole config from those fields. That reset any request template, header, method or timeout set through the API or CLI. Delete was one click, though deleting an agent cascades to its runs. The suites page could create and run a suite but not edit, browse or version one. Old versions kept their case rows (PLAN.md §2 #1), but each new version overwrote `suites.yaml_source`, so an old version's YAML was gone.

## Decision
**Agents page**
- The form edits every field of both server adapter configs: HTTP (method, JSON request template, plain headers, timeout, retries, redirects, the full response mapping) and MCP over HTTP (URL, headers, timeout, retries). The demo agents' shape is the default for a new agent.
- `lib/agent-form.ts` maps a stored config to a flat draft and back. Building the config spreads the stored config first, so a field the form doesn't know survives an edit. Switching adapter type starts clean. Unit tests pin the round trip.
- Auth header: write-only, as before (ADR 0003). The form shows that one is stored and offers Replace or Remove; the value is never shown or returned.
- The API now deletes a replaced or cleared header's ciphertext, and an agent's header when the agent is deleted. This resolves the old `ponytail:` note on orphaned secrets. The one exception: a queued or running run's snapshot still reads the old secret for its remaining attempts (ADR 0017), so it is kept then.
- Test connection: a draft is tested as a draft. An unedited saved agent is tested as saved (`POST /agents/{id}/test`), which sends its stored header. Each row also has a Test button. The form says when edited settings are tested without the stored header.
- Delete asks first, and says the agent's runs, results, traces and baselines go with it (`runs.agent_id` is `ON DELETE CASCADE`), with the count from the newest 200 runs.
- MCP agents can be saved and tested. Server runs still take HTTP agents only (ADR 0030), and the form says so.

**Suites**
- **Migration 0005: `suite_versions`** (suite, version, YAML, `created_at`), written on create and on every new version. It is backfilled with each suite's current YAML. A backfilled row's `created_at` is the suite's own only for version 1, and NULL otherwise, rather than the migration's time. Versions from before the migration have case rows but no YAML; the API says so (`has_yaml`), and the UI shows "Before history was kept".
- `GET /suites/{id}/versions`: each version's save time, case count and run count, newest first. `GET /suites/{id}/versions/{n}`: that version's YAML, or null. `GET /suites/{id}/cases?version=`: a version's cases from `test_cases`, in the YAML's order when its YAML was kept, otherwise by id. All are owner-scoped and IDOR-probed.
- The suite page (`/projects/{id}/suites/{suiteId}`) has three tabs:
  - **Editor:** validates 400 ms after typing stops, through `POST /suites/validate`. Each problem's line number jumps to that line. Saving makes a new version, and runs keep the version they used.
  - **Cases:** a case browser for any version.
  - **Versions:** each version expands to a folded line diff against the version before it (`lib/line-diff.ts`, an LCS of lines, with 3 lines of context) and its full YAML. Additions and removals are marked +/− and named for screen readers, never by color alone. YAML is rendered as text only.
- Run, from the suites list and the suite page, opens ADR 0037's run dialog. It no longer sends `mock: false` unasked.

## Consequences
- Old versions' YAML is available only from migration 0005 on.
- The line diff is O(n·m) and declines two texts whose line counts multiply past 4 million, about two 2,000-line suites (`ponytail:`). It says so instead.
- Deleting an agent still deletes its runs. Changing that to keep history would be a data-model change (`runs` needs an agent id or a name), and the confirmation is the agreed scope.
- The agents table puts the adapter under the name and caps the URL width below desktop, so it fits at 810px (ADR 0028 §8).
