# 0021: Attack library and LLM mutator

Status: accepted (2026-09-26). Implements PLAN.md C1 and C2.

## Context
`packages/core/suite/attacks.py` (ADR 0010) has been a 2-id placeholder frozenset since B1.1:
enough for the suite schema to validate `Case.attack` against something, but no real
generator behind either id. C1 asks for the real attack library (SPEC.md §4.4's categories,
parameterized `generate(params, seed) -> list[Payload]`, composable obfuscation transforms)
and C2 for an LLM-powered mutator that expands a case via `mutations: N`. Neither had a
concrete shape yet: how many ids per category, how a generator stays deterministic, how
obfuscation composes with an attack, and how the mutator behaves in mock mode or when a
provider refuses.

## Decision

### Registry shape (`packages/core/attacks`)
- One module per SPEC.md §4.4 category (`direct`, `indirect`, `jailbreak`, `extraction`,
  `leakage`, `tool_misuse`, `scope_drift`), each exporting a `DEFINITIONS: tuple[
  AttackDefinition, ...]`. `registry.py` merges them into `ATTACKS: dict[str, AttackDefinition]`
  and `ATTACK_IDS: frozenset[str]`. 15 ids total: `prompt_injection.direct/indirect`, three
  `jailbreak.*` framings, three `extraction.*` tricks, `leakage.secrets`/`leakage.pii`, three
  `tool_misuse.*` techniques plus the bare `tool_misuse` (kept as an alias of
  `tool_misuse.unauthorized_call`, since it was already a valid id in the placeholder set and
  in `suites/examples/support-agent-safety.yaml`), and `scope_drift.off_topic`.
- Each `AttackDefinition` carries `severity` and `notes`: what a pass/fail looks like and a
  reminder to pair the attack with a rule judge, since detection must never depend only on an
  LLM judge (the user's brief for this prompt).
- `generate(params, seed)` is deterministic: template selection goes through one shared helper
  (`_templates.pick`) that shuffles the template order with `random.Random(seed)` and cycles
  it for `count` requests larger than the template pool, so the same seed always returns the
  same payloads and a large `count` repeats rather than raising. `count` is capped at 50,
  matching `Case.mutations`'s existing bound, since both expand one case into several variants.
- Indirect injection's `Payload` carries `documents: tuple[str, ...]` separately from `text`:
  the hidden instruction belongs in a case's `context` (delivered through `{{documents}}`, ADR
  0012), and `text` is the innocuous question the case actually asks.
- `agentprobe_core.suite.attacks.ATTACKS` now re-exports `agentprobe_core.attacks.registry.
  ATTACK_IDS` under its old name, so the schema's unknown-id validator (ADR 0010) needs no
  change and lists all 15 ids. The dependency runs one way (`suite` imports `attacks`); nothing
  in `attacks` imports `suite`.

### Obfuscation (`attacks/obfuscation.py`)
- Five transforms: `base64`, `leetspeak`, `split_word`, `homoglyph`, `hinglish`. Each is a pure
  `str -> str`, held in `OBFUSCATIONS: dict[str, Callable[[str], str]]`, applied via
  `apply_obfuscation(name, text)` or stacked via `compose_obfuscation(names, text)` — usable
  standalone or with any attack's `Payload.text`, per the brief.
- `base64`, `homoglyph` and `split_word` round-trip exactly (`base64_decode`/`unhomoglyph`/
  `unsplit_word` recover the original); `leetspeak` and `hinglish` are lossy paraphrases and
  don't. The Hinglish/Hindi set is a small curated phrase-substitution table (documented in the
  module docstring as limited — the phrases the bundled templates use, not a translator), not a
  general translation pipeline.

### Mutator (`attacks/mutator.py`)
- `mutate(attack_id, n, seed, llm)` paraphrases the attack's base payload through the shared
  `LLMClient`'s `attacker` role — the same cache, budget and mock-provider determinism as
  every other LLM call (ADR 0011), so mock mode is deterministic per seed without any special
  casing. The prompt includes the variant index, so mock mode (a pure function of the prompt)
  produces a distinct deterministic paraphrase per variant instead of the same one repeated.
- Near-duplicate paraphrases are dropped (`difflib.SequenceMatcher` ratio ≥ 0.9 against the
  base and every kept variant). Any slot left empty by a duplicate, a blocked/refused
  completion, or a raised exception is backfilled from the attack's own `generate()` templates
  (requesting `n + 1` and skipping the base), so `mutate` always returns up to `n` payloads
  without failing the run — matching the runner's existing policy of never letting a judge or
  provider failure crash a run outright (ADR 0016).

### Runtime expansion is not wired in
- `Case.attack`-only cases, `obfuscate` and `mutations` were already refused up front in
  `runner.plan_attempts` "until the attack library exists" (ADR 0010/0016 amendments). The
  library now exists, but this prompt does not wire its output into `plan_attempts`/
  `run_suite`: that would mean making `plan_attempts` (and its synchronous callers — the CLI,
  `apps/api/runs.py`, `ci.py`, `worker.py`) async for the mutator's LLM call, a change with a
  much larger blast radius than the library itself and outside this prompt's own test list
  ("every attack generates valid payloads", "mutator dedupe and fallback work", "every example
  suite parses" — none of it says cases expand at run time). `plan_attempts`'s three refusal
  messages were reworded so they stay honest (they no longer claim the library "isn't
  available"), but the refusals themselves are unchanged. Wiring expansion in is left as a
  follow-up (PROGRESS.md "Next").

## Consequences
- `suites/examples/smoke.yaml` gained an `instruction-injection` case and
  `suites/examples/rag-safety.yaml` is new, both using literal `input`/`context` (not
  attack-only expansion, since that isn't wired in yet) with an `attack:` field purely as a
  documentation label — the same pattern `support-agent-safety.yaml` already used.
  `demo-agents/vulnerabilities.json`'s `suite_case_ids` are filled for all 7 planted flaws
  (B1.8's golden-test requirement).
- A suite author who wants a specific obfuscation technique or a specific tool-misuse
  sub-technique must currently call `agentprobe_core.attacks` directly (e.g. from a script that
  generates a suite file) rather than through `attack_params`/`obfuscate` in YAML, since the
  suite-level fields aren't consumed by a live run yet.
- `pyproject.toml`'s `per-file-ignores` gained one entry:
  `packages/core/src/agentprobe_core/attacks/**` is exempt from `S311` (seeded `random.Random`,
  not cryptographic use — the existing convention for jitter/flakiness elsewhere in the repo)
  and `RUF001` (the homoglyph table's ambiguous-looking characters are the entire point).
