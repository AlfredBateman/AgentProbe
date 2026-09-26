# Positioning

Status: decided 2026-09-26 (user decision). This records **what AgentProbe is for**, so that scope
arguments and cut decisions have something to appeal to. Scope stays in [SPEC.md](../SPEC.md);
build order in [PLAN.md](PLAN.md).

## 1. The pitch

> **AgentProbe is statistically-corrected, flakiness-aware regression detection for LLM agents,
> wired into a real CI-gate workflow, and judged on traces and tool calls rather than just final
> text.** It runs every case many times and fails a pull request only when a drop is statistically
> meaningful — not when a flaky case happened to fail this time.

## 2. What it is not

Not "a combined eval + red-team + dashboard platform". That framing is what most of this space
already claims, it competes on breadth, and breadth is the one axis a single-author project loses
on. Everything in the repo now gets judged by whether it serves the sentence above.

The parts that do serve it:
- multi-run execution with per-case pass rates and flaky labels;
- one-sided Fisher exact per case with a Tarone–Holm step-down, a paired sign-flip test for the
  suite, and `alpha` split over the two so the verdict's false-alarm rate is the one configured
  ([ADR 0014](decisions/0014-statistics-implementation.md#verdict));
- traces and tool-call judgments produced by AgentProbe itself, so judges can assert on
  `tool_not_called` / `tool_args_match`, not only on output text;
- the CLI's exit codes, `/ci/report`, branch baselines and the GitHub Action — the actual gate.

## 3. Where the differentiation sits

Three groups, by how they treat run-to-run variance. Sources and caveat in §6.

| | What it is | Traces + tool-call judgments it produces itself | Multi-run significance testing, corrected | Its own PR-blocking gate |
|---|---|---|---|---|
| **promptfoo, DeepEval, LangSmith, Braintrust** | Eval harnesses and observability platforms. Run a suite, score it, show it, often with a CI step. | Varies; LangSmith and Braintrust capture rich traces, and assertions are mostly over outputs and scores | **No** — a threshold or a raw score delta, with no significance test or multiple-comparison correction | Threshold-based pass/fail |
| **sigeval, agent-eval, evaltrust** | Statistics layers: take numbers someone else produced and test them properly. | **No** — they consume metrics, not runs | Yes, but as an after-the-fact audit of exported numbers | **No** — no adapters, no runner, no gate of their own |
| **AgentProbe** | A runner that is also the statistician and the gate. | **Yes** — adapters call the agent, capture the trace, and judge tool calls and arguments | **Yes** — corrected per case and at suite level, `alpha` budgeted across both | **Yes** — exit codes, `/ci/report`, branch baselines, the Action's PR comment |

The gap AgentProbe fills is the seam between rows one and two: group one has the runs but treats a
flaky failure as a regression; group two has the statistics but never sees a run. Owning both ends
is what makes "this PR made the agent worse" a claim with a false-alarm rate attached to it —
measured at 2.8% worst case against a configured 5% ([docs/metrics.md](metrics.md)).

## 4. MCP

The MCP adapter (PLAN C3) is **one adapter type, for breadth of what AgentProbe can point at** —
alongside HTTP and the CLI-only Python adapter. It is not a product claim.

AgentProbe is deliberately **not** marketed as an MCP-security scanner: that space already has
dedicated tools, and competing there would mean competing on scanner coverage, which is breadth
again. An MCP server is simply another thing whose tool calls can be judged and regression-tested.

## 5. What this means for the build

Priorities follow from §1. If time runs short, these go first, in this order, because neither
carries the positioning:

1. **C4, failure clustering** (embeddings, pgvector, LLM cluster summaries, `/runs/{id}/findings`).
   It is a presentation nicety over failures that have already been detected and judged. Nothing in
   the pitch needs it, and it is the single largest remaining chunk of work. Cutting it also drops
   `top_findings` from `/ci/report` (already `[]`) and the Findings dashboard page (E6).
2. **Attack-library breadth — obfuscation variety** (base64, leetspeak, split-word,
   Hinglish/Hindi packs; SPEC §4.4's "Obfuscation" row and the stretch packs). The attack
   *categories* that the golden tests and the demo agents' planted flaws rely on stay, because
   "detected X of Y planted flaws" is evidence for the judging half of the pitch. Adding a
   tenth obfuscation variant is not.

Kept even under time pressure, because the pitch collapses without them: the statistics
(B1.6 and its calibration), the trace and tool-call judges (B1.5), multi-run execution (B1.7),
golden tests (B1.8), and the whole CI-gate path (D1/D2/F1/F2).

## 6. How the comparison was established, and its shelf life

The competitor assessment in §3 is the user's, from reading those projects' own documentation and
third-party comparisons (2026-09). It is recorded here as the basis for the decision, not as
independently re-verified by this repo.

Treat it as perishable. These products ship quickly, and "no significance testing" is exactly the
kind of gap a competitor closes in one release. **Before any of this goes into the README, a
resume, or anything else public, re-check each claim against current documentation.** A specific
claim about a named product that has gone stale is worse than no comparison at all.

## 7. Open: SPEC.md still carries the old framing

[SPEC.md](../SPEC.md) §1 still opens with "Automated testing, red-teaming and regression detection
for LLM agents" and "pytest + Playwright + a security scanner", and §16's first resume bullet says
"a full-stack testing and red-teaming platform". That is the framing §2 moves away from.

SPEC.md is the approved source of truth for scope (CLAUDE.md), so its headline and resume bullets
are left unchanged pending an explicit decision rather than edited to match. [PLAN.md](PLAN.md) §0
carries the new pitch in the meantime.
