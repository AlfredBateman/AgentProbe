# 0024: Failure clustering

Status: accepted (2026-09-27). Implements PLAN.md C4, closing SPEC.md §4.8 and §8's
`GET /runs/{id}/findings` and `/ci/report`'s `top_findings`.

## Context
SPEC.md §4.8: "Failing outputs are embedded (pgvector) and clustered so 40 failures become
'5 root causes'. An LLM summarizes each cluster with a suggested fix." The `findings` table
and its `embedding vector(EMBEDDING_DIM)` column already existed (migration 0001, ADR 0007);
nothing had ever written to it. POSITIONING.md marks C4 as the first thing to cut if time runs
short, since it presents already-detected failures rather than detecting anything new — so the
brief is to do the minimum genuinely useful version, not build a clustering platform.

## Decision

### Clustering method: single-linkage agglomerative, stdlib only, fixed distance threshold
`agentprobe_core.findings.agglomerative_cluster` repeatedly merges the two clusters whose
closest pair of members is nearest (single-linkage), stopping once the nearest pair is more
than `DEFAULT_DISTANCE_THRESHOLD` (0.25 cosine distance, i.e. similarity ≥ 0.75) apart. Chosen
over k-means or a library (scikit-learn, scipy): the number of distinct root causes in a run
isn't known ahead of time, so a threshold-based method that doesn't need a chosen `k` fits the
problem better, and `packages/core` has no numpy/scipy dependency anywhere else (ADR 0006's
statistics are pure Python for the same reason) — adding one for this alone would be a new
category of dependency for a single feature. A run's failing outputs number in the tens to low
hundreds, where the O(n³) worst case (an O(n²) pairwise scan repeated up to n times) costs
nothing measurable; a `ponytail:`-style note in the module says to swap in a real library if
that stops being true. Ties are broken by scan order (lowest cluster indices first), so the
same embeddings always cluster the same way. Every size is handled without a special case: no
failing outputs → no findings; one → one cluster of one; identical outputs → one cluster,
since their cosine distance is exactly 0, always within any positive threshold.

The threshold was picked against the mock embedding's actual behavior (word/trigram feature
hashing, `agentprobe_core.llm.mock.fake_embedding`) rather than a textbook default, and
confirmed on the vulnerable demo bot's real failures (`scripts/measure_clustering.py`,
docs/metrics.md): its five distinct planted flaws land in five separate clusters, and each
flaw's repeated attempts (deterministic mock responses) collapse into one. There is no
suite-level config for it (unlike the statistics thresholds, which SPEC.md and ADR 0006
require to be configurable) — clustering doesn't gate a build the way a regression verdict
does, so getting it slightly wrong costs a slightly-off findings list, not a false CI failure.

### What gets clustered: `run_results` with `status = 'failed'` and a non-null output
Not `error` attempts: an error means AgentProbe never got a judged answer (a timeout, an
unreachable agent, a judge crash), so there's no "failure" in the SPEC.md §4.8 sense to
explain — clustering those would mix infrastructure noise in with behavioral findings. A
`failed` attempt always has a judge verdict and, in every adapter this codebase has, an
`output` string; the query still guards on `output IS NOT NULL` rather than assuming it.

### Summarizer prompt: two labelled lines, not JSON
The summarizer role is asked for exactly two lines, `Summary: ...` and `Fix: ...`, parsed by
prefix rather than through `llm.complete`'s `json_schema` (the way `llm_rubric` gets its
verdict, ADR 0013). Reason: the mock provider's generic JSON-schema fallback
(`schema_instance`) returns the literal string `"mock"` for every string field regardless of
input, so every cluster's mock finding would read identically — worse than no test coverage,
since it would look like real behavior while asserting nothing. Free text, by contrast, uses
the mock provider's existing hash-based default (`f"mock {role} response {hash}"`, keyed on
the actual prompt), which already varies by cluster content and is exactly as deterministic.
`_parse` falls back to the whole response as the summary and a generic suggested fix when the
requested format isn't found (mock's default text, or a live model that doesn't comply) — still
deterministic, just less specific, and the label is the summary truncated to 60 characters. No
change to `agentprobe_core.llm.mock` was needed or made.

### Storage: the existing `findings` table, no migration
`Finding.embedding` stores the cluster's centroid (the mean of its members' embedding
vectors) — not one representative member's vector — so a finding's position reflects the whole
group. `cluster_run` (`apps/api/findings.py`) is idempotent: it deletes and re-inserts a run's
findings rather than diffing, the same pattern `save_summary` uses for `judgments`. This
matters because a job can be redelivered on the Redis backend (ADR 0017) and `/ci/report` could
in principle be called again for the same run.

### Where it runs: a post-run job on both queue backends, and inline in `/ci/report`
A live run (inline or Redis) triggers `queue.cluster_findings` exactly where `save_summary`
returns `"completed"` — both in `queue.finalize` (the Redis backend's `finalize_run` job, and
the inline backend's cancelled/failed path) and in `execute_inline`'s own completed fast path,
so a run that finished normally is clustered exactly once regardless of backend. `/ci/report`
is different: ADR 0018 already made it "one request doing one piece of work end to end", so
clustering there runs synchronously, inside the same request, wrapped in `db.begin_nested()`
(a SAVEPOINT) so a clustering failure can't poison the request's own transaction and lose the
run it was supposed to attach findings to.

**A clustering failure never fails the run.** `queue.cluster_findings` catches every exception
and logs it (`logger("agentprobe.runs")`); `/ci/report` does the same around its nested
transaction (`logger("agentprobe.ci")`). Nothing writes the failure to a database column: SPEC's
"the error is recorded" is satisfied by AgentProbe's existing structured JSON logging
(`apps/api/logs.py`), the same way an inline queue crash is already only logged
(`InlineQueue._run`), not stored — there is no established convention in this codebase for
storing background-job failures on the row they concern, only for logging them.

### `apps/api/findings.py` layout
One file, mirroring `baselines.py`/`share.py`/`ci.py`: the `GET /runs/{id}/findings` router,
the read query (`_read_failed_outputs`), the single-transaction orchestration (`cluster_run`,
taking a plain `AsyncSession` so `/ci/report` can share its own transaction) and the
queue-facing wrapper (`cluster_and_save`, taking `runstore.Sessions` and committing its own).
The clustering algorithm and the summarizer call themselves live in `agentprobe_core.findings`
(pure, DB-free, same `packages/core` boundary as everything else) as `agglomerative_cluster`
and `cluster_failures`; `apps/api` never reimplements them.

## Consequences
- `/ci/report`'s `top_findings` (previously always `[]`) returns the largest clusters (by
  member count, capped at 5) as `{label, summary, suggested_fix, member_count}`.
  `GET /runs/{id}/findings` returns every cluster, largest first, with `member_result_ids` so
  the dashboard can link back to the results that produced it.
- Clustering costs one embedding call and one summarizer call per cluster, on a fresh
  `LLMClient` built independently of the suite's own judges (`runstore.make_llm_client`,
  extracted from `Plan.llm()`, which still wraps its `LLMConfigError` as `Unrecoverable` for
  the run itself). A suite with no LLM-based judges at all still gets clustering, since the
  client is no longer gated on `uses_llm(suite)`.
- The distance threshold is empirical against the mock embedding's specific hashing (ADR
  0011). A live embedding model may cluster differently at the same threshold; there is
  nowhere to configure it per suite yet. Revisit if live findings turn out too coarse or too
  fine once RUN_LIVE=1 runs exist to look at (docs/metrics.md's live section is unmeasured, the
  same status as detection and false-alarm metrics before their own live runs).
- `docs/metrics.md` gained a measured "N failures → K root causes" number
  (`scripts/measure_clustering.py`), the same kind of honest, reproducible number the other two
  metrics sections already are.
