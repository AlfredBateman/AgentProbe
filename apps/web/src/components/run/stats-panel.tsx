import Link from "next/link";
import type { ReactNode } from "react";
import { Skeleton } from "@/components/ui/feedback";
import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/status";
import type { components } from "@/lib/api/schema";
import { cx } from "@/lib/cx";
import { pct, pValue } from "@/lib/format";
import { type CaseComparisonDump, type RegressionReportDump, verdictSummary } from "@/lib/regression";
import type { CaseRow } from "@/lib/run-cases";
import { VerdictBadge } from "./labels";

type Run = components["schemas"]["RunDetailOut"];
/** null: not fetched yet; "none": no baseline on the run's branch (the API's 404). */
export type Verdict = components["schemas"]["RunVerdictOut"] | "none" | null;

const MAX_CASES = 5;

/** A pass-rate difference in percentage points: the verdict's effect size. */
export const points = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : "±"}${Math.abs(x * 100).toFixed(1)} pts`;

const fraction = (passes: number, attempts: number) => `${passes}/${attempts}`;

/**
 * The run's statistics in plain words: its own counts and pass-rate interval, then the verdict
 * against the baseline with the numbers behind it (counts, p-values, the corrected thresholds,
 * the effect size). Every figure is the API's (core's); nothing here is computed but sums.
 */
export function StatsPanel({ run, rows, verdict, projectId }: { run: Run; rows: CaseRow[]; verdict: Verdict; projectId: string }) {
  const terminal = run.status === "completed" || run.status === "failed" || run.status === "cancelled";
  const attempts = rows.flatMap((r) => r.attempts);
  const passed = attempts.filter((a) => a.status === "passed").length;
  const failed = attempts.filter((a) => a.status === "failed").length;
  const errors = attempts.filter((a) => a.status === "error").length;
  const summarized = rows.length > 0 && rows.every((r) => r.label !== null);
  const label = (l: string) => rows.filter((r) => r.label === l).length;
  const report = verdict && verdict !== "none" ? (verdict.report as RegressionReportDump | null) : null;

  return (
    <Panel aria-label="Statistics" title="Statistics" titleStyle="label" actions={report ? <VerdictBadge verdict={report.verdict} /> : undefined}>
      <h3 className="type-micro text-ink-muted">This run</h3>
      <dl className="mt-8 grid grid-cols-[auto_minmax(0,1fr)] gap-x-16 gap-y-6">
        <Row term="Pass rate">
          {run.pass_rate != null ? (
            <>
              <span className="type-display-md tabular-nums">{pct(run.pass_rate)}</span>
              <span className="mt-4 block type-data text-ink-muted">
                {run.ci_lower != null && run.ci_upper != null
                  ? `95% CI ${pct(run.ci_lower)}–${pct(run.ci_upper)}`
                  : "No interval"}
              </span>
            </>
          ) : (
            <span className="type-data text-ink-muted">{terminal ? "None recorded" : "When the run finishes"}</span>
          )}
        </Row>
        <Row term="Attempts">
          {passed} passed · <span className={failed ? "text-fail" : undefined}>{failed} failed</span> · {errors} errors{" "}
          <span className="text-ink-muted">of {run.attempts_total}</span>
        </Row>
        <Row term="Cases">
          {summarized ? (
            <>
              {label("stable-pass")} stable pass · <span className={label("stable-fail") ? "text-fail" : undefined}>{label("stable-fail")} stable fail</span> ·{" "}
              {label("flaky")} flaky
            </>
          ) : (
            <span className="text-ink-muted">Labelled when the run is summarized</span>
          )}
        </Row>
      </dl>

      <h3 className="mt-16 border-t border-hairline pt-12 type-micro text-ink-muted">Against the baseline</h3>
      <div className="mt-8">
        {!terminal ? (
          <Plain>Compared with the baseline when the run finishes.</Plain>
        ) : verdict === null ? (
          <Skeleton className="h-60" />
        ) : verdict === "none" ? (
          <Plain>
            No baseline for this suite and agent on <span className="type-code">{run.branch ?? "main"}</span>, so there is no verdict
            and no p-value. Set one with Set as baseline.
          </Plain>
        ) : verdict.is_baseline ? (
          <Plain>
            This run is the <span className="type-code">{verdict.branch}</span> baseline: later runs are compared with it.
          </Plain>
        ) : !report ? (
          <Plain>Only a completed run is compared with the baseline.</Plain>
        ) : (
          <Comparison report={report} baselineHref={`/projects/${projectId}/runs/${verdict.baseline_run_id}`} branch={verdict.branch} />
        )}
      </div>
    </Panel>
  );
}

function Comparison({
  report,
  baselineHref,
  branch,
}: {
  report: RegressionReportDump;
  baselineHref: string;
  branch: string;
}) {
  const sum = (side: "baseline" | "candidate", key: "passes" | "attempts") => report.cases.reduce((n, c) => n + c[side][key], 0);
  const suite = report.suite;

  return (
    <>
      <p className="type-body-sm text-ink">{verdictSummary(report)}</p>
      <dl className="mt-12 grid grid-cols-[auto_minmax(0,1fr)] gap-x-16 gap-y-6">
        <Row term="Baseline">
          {fraction(sum("baseline", "passes"), sum("baseline", "attempts"))} passed
          {suite && <span className="text-ink-muted"> · {pct(suite.baseline_pass_rate)}</span>}{" "}
          <Link href={baselineHref} className="type-micro text-accent underline-offset-4 hover:underline">
            <span className="type-code">{branch}</span> baseline
          </Link>
        </Row>
        <Row term="This run">
          {fraction(sum("candidate", "passes"), sum("candidate", "attempts"))} passed
          {suite && <span className="text-ink-muted"> · {pct(suite.candidate_pass_rate)}</span>}
        </Row>
        {suite && (
          <>
            <Row term="Effect size">
              <span className={suite.pass_rate_delta < 0 && report.verdict === "regression" ? "text-fail" : undefined}>
                {points(suite.pass_rate_delta)}
              </span>{" "}
              <span className="text-ink-muted">pass rate, over {suite.cases} shared cases</span>
            </Row>
            <Row term="Suite p">
              worse {pValue(suite.p_worse)} · better {pValue(suite.p_better)}{" "}
              <span className="text-ink-muted">
                vs <span className="normal-case">α</span> {report.alpha_suite} (paired sign-flip{suite.exact ? ", exact" : ", Monte Carlo"})
              </span>
            </Row>
          </>
        )}
      </dl>

    </>
  );
}

/**
 * Every shared case's test, flagged first, then by p: the counts, the difference, p and the
 * corrected threshold it had to meet. Full width: seven columns don't fit beside the board.
 */
export function CaseTests({ report, compareHref }: { report: RegressionReportDump; compareHref: string }) {
  const better = report.verdict === "improvement";
  const p = (c: CaseComparisonDump) => (better ? c.p_better : c.p_worse);
  const threshold = (c: CaseComparisonDump) => (better ? c.p_better_threshold : c.p_worse_threshold);
  const flagged = (c: CaseComparisonDump) => (better ? c.improved : c.regressed);
  const shown = report.cases.toSorted((a, b) => Number(flagged(b)) - Number(flagged(a)) || p(a) - p(b)).slice(0, MAX_CASES);
  return (
    <Panel
      aria-label="Per-case tests"
      title="Per-case tests"
      titleStyle="label"
      actions={
        <p className="type-micro text-ink-muted tabular-nums">
          {shown.length < report.cases.length ? `${shown.length} of ${report.cases.length} cases` : `${report.cases.length} cases`}
        </p>
      }
    >
      <div className="-mx-16 -mt-16 overflow-x-auto border-b border-hairline">
        <table className="w-full border-collapse type-code tabular-nums">
          <caption className="sr-only">Per-case tests, most significant first</caption>
          <thead>
            <tr>
              {["Case", "Baseline", "This run", "Δ pass rate", `p (${better ? "better" : "worse"})`, "Corrected threshold", "Result"].map((h, i) => (
                <th key={h} scope="col" className={cx("bg-surface-1 px-12 py-6 type-micro whitespace-nowrap text-ink-muted", i === 0 ? "text-left" : "text-right")}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((c) => {
              const t = threshold(c);
              const hit = flagged(c);
              return (
                <tr key={c.case_id} className="border-t border-hairline">
                  <th scope="row" className="max-w-160 truncate px-12 py-6 text-left font-normal" title={c.case_id}>
                    {c.case_id}
                  </th>
                  <td className="px-12 py-6 text-right">{fraction(c.baseline.passes, c.baseline.attempts)}</td>
                  <td className="px-12 py-6 text-right">{fraction(c.candidate.passes, c.candidate.attempts)}</td>
                  <td className="px-12 py-6 text-right whitespace-nowrap">{points(c.pass_rate_delta)}</td>
                  <td className="px-12 py-6 text-right">{pValue(p(c))}</td>
                  <td className="px-12 py-6 text-right whitespace-nowrap">{t === null ? "Not reached" : pValue(t)}</td>
                  <td className="px-12 py-6 text-right">
                    {hit ? (
                      better ? (
                        <Badge status="pass">Improved</Badge>
                      ) : (
                        <Badge status="fail">Regressed</Badge>
                      )
                    ) : (
                      <span className="type-micro text-ink-muted">Not significant</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-12 max-w-560 type-body-sm text-ink-muted">
        Each case is a one-sided Fisher exact test. The Tarone–Holm step-down over α_cases = {report.alpha_cases} gives every p a
        corrected threshold to meet, not an adjusted p-value; &ldquo;Not reached&rdquo; means the step-down stopped before that case.
        {report.cases.length > MAX_CASES && (
          <>
            {" "}
            <Link href={compareHref} className="text-accent underline-offset-4 hover:underline">
              All {report.cases.length} cases in Compare
            </Link>
            .
          </>
        )}
      </p>
    </Panel>
  );
}

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="pt-2 type-micro text-ink-muted">{term}</dt>
      <dd className="min-w-0 type-data text-ink">{children}</dd>
    </>
  );
}

function Plain({ children }: { children: ReactNode }) {
  return <p className="type-body-sm text-ink-muted">{children}</p>;
}
