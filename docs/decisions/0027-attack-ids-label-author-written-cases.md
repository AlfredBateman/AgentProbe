# 0027: Attack ids label author-written cases; no payload generation

Status: accepted (2026-09-27, user decision). Supersedes [ADR 0021](0021-attack-library-and-mutator.md).
Amends PLAN.md §2 #10, C1 and C2.

## Context
ADR 0021 built three pieces:
- per-category payload generators (`generate(attack_id, params, seed)`);
- composable obfuscation transforms, with decode-only helpers for their tests;
- an LLM mutator (`mutate`) on its own `attacker` LLM role.

None of them was ever on a runtime path:
- `plan_attempts` refused any case that set `mutations`, `obfuscate` or `attack_params`, and any
  `attack` case without a literal `input`.
- Nothing outside the attack package and its own tests called `generate()`, `mutate()` or an
  obfuscation.
- Every `attack:` case in `suites/examples/` has a literal `input:` or `call:`, so the golden
  tests (B1.8, C4) that load them never depended on generation. This was checked before the cut.

[POSITIONING.md](../POSITIONING.md) fixes what AgentProbe is for: statistically-corrected,
flakiness-aware regression detection in a CI gate. The attack *categories* serve that. They
classify cases, and "caught X of Y planted flaws" is evidence for the judging half of the pitch.
A variety of generated payloads doesn't serve it. Generation is a red-team breadth feature,
which is the axis POSITIONING.md §2 says a single-author project loses on. Generated variants
also work against the statistics: a regression test compares the same case across runs, and a
case whose input the tool invents is a moving target.

## Decision
- **Out of scope:** generated attack-payload variety, meaning template generators, obfuscation
  transforms and LLM mutation. AgentProbe regression-tests author-written, category-classified
  attack cases.
- **Kept:** the id-to-category registry, `ATTACKS: dict[str, str]` in
  `agentprobe_core/suite/attacks.py`, with the same 15 ids and 6 categories. The schema
  validates `Case.attack` against it, and the suite editor (E-phase) can offer it for
  autocomplete.
- **Removed:**
  - the `agentprobe_core.attacks` package (generators, `Payload`/`AttackDefinition`,
    obfuscation and its decode helpers, the mutator) and its tests;
  - the `attacker` LLM role, whose only caller was the mutator (`Role`, `config/llm.yaml`,
    `LLM_MODEL_ATTACKER`);
  - the ruff per-file ignore for the package.
- **`mutations`, `obfuscate` and `attack_params` are removed from the suite schema.** They are
  not kept behind a refusal-only path for features that won't be built. `Case` is
  `extra="forbid"`, so a suite that still sets one fails to parse with pydantic's "Extra inputs
  are not permitted" at that field's path.
- **`attack` is a label only.** A case needs `input` or `call`, checked when the suite is
  parsed. Before, an `attack`-only case parsed and was then refused by `plan_attempts`. So
  `plan_attempts` no longer raises, `POST /suites/{id}/runs` no longer catches its
  `ValueError`, and `execute_attempt`'s "no input and no call" error branch is gone.

## Consequences
- A suite file using a removed field, or an `attack`-only case, stops parsing at upload or
  `agentprobe run`. The server re-parses stored YAML when a run is created, so a stored suite
  like that now gets a 422 "Suite validation failed". None of the example suites used them.
  The only tests that did were the refusal tests, which now assert the parse-time error.
- SPEC.md §4.4's "parameterized generators", Obfuscation row and mutator paragraph, and the
  "Attack mutator" should-have in §14, are out of scope under this ADR. SPEC.md stays as the original scope
  statement, as with ADR 0001's deviations.
- `demo-agents/vulnerabilities.json` and the golden tests are unchanged. They already relied
  only on categories and literal inputs.
- Revisit only if the positioning changes. A generator would then be a new feature that writes
  literal cases into a suite file, keeping every run of a case identical, rather than expanding
  cases at run time.
