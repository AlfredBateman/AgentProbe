# 0015: Regex judge hardening

Status: accepted (2026-09-24). Supersedes the `regex` bullet of [ADR 0013](0013-judges.md). Amended 2026-09-26 with a fourth guard, a group-nesting bound (see [Nesting](#nesting-amended-2026-09-26)).

## Context
Suite YAML is user-supplied, and the hosted worker runs it, so a `regex` judge's pattern is hostile input. ADR 0013 guarded stdlib `re` with a 4,096-character cap on the agent's output. A cap doesn't bound backtracking, though: `^(a|aa)+$` against forty `a`s and a `!` explores about 10^8 paths, far below the cap. Stdlib `re` has no timeout, so a malicious pattern could hang a worker.

Measuring the fix turned up a second vector. The `regex` package unrolls counted repeats **while compiling**, and its timeout only covers matching:

| Pattern | Compile time | Memory |
|---|---|---|
| `(?:a{1000}){1000}` | 0.27 s | about 250 MB |
| `(?:(?:a{1000}){1000}){1000}` (29 characters) | effectively never finishes | about 250 GB |

Any fixed minimum count gets unrolled: `{n}`, `{n,}`, `[ab]{n}`, `(a|b){n}`. An optional range such as `{1,n}` does not.

## Decision
Three guards, all in `judges/rules.py`:

1. **Matching uses the `regex` package (2026.9.10) with a timeout of 0.25 s.** Its documentation says the timeout (in seconds) "applies to the entire operation". A timeout raises `TimeoutError`, which becomes `status="error"` with a reason naming the timeout. It is never a pass or a fail.
   - The `regex` engine's own repeat guards defuse some classic patterns, but not all:
     - `^(a|aa)+$` is still exponential.
     - `(a+)+$` becomes polynomial but not safe: unbounded, it takes 0.2 s at 500 characters, 12 s at 2,000, and over 30 s at 5,000.
   - Both are tests, and both end as `error` in about 0.25 s.
2. **Patterns are parsed with the stdlib parser (`re._parser`) before compiling**, and refused when their counted repeats would expand past 10,000 elements.
   - The stdlib parser never unrolls anything.
   - The estimate multiplies each repeat's body by its count. It uses the upper count when there is one, so it never undercounts, and the lower count for open-ended repeats. Nesting multiplies.
   - The 29-character bomb is refused in microseconds with "expands to 1,000,000,000 elements".
   - Everyday patterns are far below the limit. A UUID pattern expands to 36 elements, an IPv4 pattern (`(?:\d{1,3}\.){3}\d{1,3}`) to 15.
   - The limit mirrors RE2's own repetition limit.
   - Parsing also keeps the accepted syntax at Python `re`, as before. Deeper nesting than the parser handles, or a repeat count above the engine's maximum, is an error.
3. **The output cap rises from 4,096 to 100,000 characters.** The cap existed only as a stand-in for a timeout, and it hid matches late in long outputs. It now just bounds memory.

**Considered: RE2 (`google-re2` 1.1.20251105).** It installs and works on Python 3.12 on Windows. It has linear-time matching, and its compile-time limits (repetition ≤ 1,000, `max_mem`) would have covered both vectors by design. It was rejected for three reasons:
- It drops lookarounds and backreferences.
- It has no verbose mode, which the judge's `x` flag needs.
- It logs parse errors to stderr through glog by default.

All three are behavior users of a Python tool already rely on or would trip over. `regex` keeps Python `re` semantics.

### Nesting (amended 2026-09-26)
A fourth guard, checked before anything parses the pattern: refuse more than `MAX_REGEX_NESTING = 50` nested groups.

The expansion bound above uses the stdlib parser, which recurses once per group. `"(" * 5000 + "a" + ")" * 5000` therefore raises `RecursionError`, which the judge already caught and turned into an error verdict — the test for it has been there since this ADR. What the test did not cover: the half-built parse tree is itself thousands deep, so **freeing** it can exhaust the stack again, and that second `RecursionError` cannot propagate from a deallocation. CPython reports it through `sys.unraisablehook`, attributed to whatever the process happens to be doing next.

That is how it showed up: a CI run failed in an unrelated test with "multiple unraisable exception warnings", on Linux only, and only once other tests had changed the garbage collector's timing. It had been latent since this ADR.

Counting parentheses first (linear, skipping escapes and character classes) means the deep tree is never built, so the hazard is gone rather than caught. It also matters outside tests: the same pattern in a real suite would have scattered unraisable errors through the API or worker process. Legitimate patterns nest a handful of levels; a test pins that a pattern at exactly the limit still compiles and matches, and that escaped parens and parens inside a class don't count towards the depth.

## Consequences
- `packages/core` depends directly on `regex==2026.9.10`. It was already in the lock through tiktoken. `types-regex==2026.9.10.20260911` is a workspace dev dependency for mypy.
- `re._parser` and `re._constants` are private stdlib modules with no typeshed stubs. They are imported with a scoped `type: ignore[import-not-found]`. They have been stable since `sre_parse`, the project pins Python 3.12, and the expansion tests catch any change.
- Divergence between the two parsers is the residual risk: a pattern the stdlib parser reads differently from `regex`, so that the estimate undercounts. The 10,000-element limit leaves room for that. Even a 100× undercount (10^6 elements) compiles in about 0.3 s using about 250 MB. That is survivable, where the bomb was not.
- The judge blocks the event loop for at most the timeout per attempt. A suite that times out on every attempt still costs 0.25 s per attempt. A run-level time budget (B1.7/B2.3) should bound the total, for example by failing a pattern fast after its first timeout in a run.
