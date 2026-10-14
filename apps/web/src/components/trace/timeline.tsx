import { AttemptBadge, JudgmentBadge } from "@/components/run/labels";
import { Panel } from "@/components/ui/panel";
import { CopyButton, jsonText, PlainText, visibleText } from "@/components/ui/code";
import type { components } from "@/lib/api/schema";
import { cx } from "@/lib/cx";
import { ms, score } from "@/lib/format";

export type Trace = components["schemas"]["TraceOut"];
export type Step = Trace["steps"][number];
type Judgment = components["schemas"]["TraceJudgmentOut"];

/** Judges that call an LLM; every other judge is a deterministic rule (agentprobe_core.runner.uses_llm). */
const LLM_JUDGES = new Set(["llm_rubric", "consistency"]);

/** What a step says, without when it said it: two attempts differ on content, not timing. */
function content(step: Step): string {
  return JSON.stringify({ ...step, timestamp: undefined, duration_ms: undefined });
}

/** Indices of `a`'s steps that have no identical counterpart at the same index in `b`. */
export function differingSteps(a: Step[], b: Step[]): Set<number> {
  return new Set(a.flatMap((step, i) => (i < b.length && content(step) === content(b[i]) ? [] : [i])));
}

/** The step's kind (interface words) and its subject (data: a role or a tool name, verbatim). */
function title(step: Step): { kind: string; subject: string | null } {
  switch (step.type) {
    case "message":
      return { kind: "Message", subject: step.role };
    case "tool_call":
      return { kind: "Tool call", subject: step.tool };
    case "tool_result":
      return { kind: "Tool result", subject: step.tool };
    case "error":
      return { kind: "Error", subject: null };
  }
}

function body(step: Step): { label: string; text: string } {
  switch (step.type) {
    case "message":
      return { label: "Content", text: step.content };
    case "tool_call":
      return { label: "Arguments", text: jsonText(step.arguments ?? {}) };
    case "tool_result":
      return { label: "Result", text: jsonText(step.result ?? null) };
    case "error":
      return { label: "Message", text: step.message };
  }
}

const GLYPH: Record<Step["type"], string> = { message: "M", tool_call: "T", tool_result: "R", error: "!" };

type Props = {
  trace: Trace;
  /** All steps collapsed to one line (each still opens on its own) or all open. */
  compact: boolean;
  /** "wide": verdicts in a column beside their step (≥1199px). "narrow": always below it (compare mode). */
  layout?: "wide" | "narrow";
  /** Steps to mark as different from the attempt this one is compared with. */
  differs?: Set<number>;
  /** Prefix for element ids, so two timelines on one page don't collide. */
  idPrefix?: string;
};

export function Timeline({ trace, compact, layout = "wide", differs, idPrefix = "step" }: Props) {
  const byStep = new Map<number, Judgment[]>();
  for (const j of trace.judgments) if (j.step !== null) byStep.set(j.step, [...(byStep.get(j.step) ?? []), j]);
  const whole = trace.judgments.filter((j) => j.step === null);
  const start = trace.steps[0]?.timestamp ? Date.parse(trace.steps[0].timestamp) : null;

  return (
    <>
      {trace.steps.length === 0 ? (
        <p className="border border-hairline p-16 type-body-sm text-ink-muted">No trace: the agent never answered.</p>
      ) : (
        <ol aria-label="Trace steps" className="flex flex-col">
          {trace.steps.map((step, i) => {
            const verdicts = byStep.get(i) ?? [];
            const different = differs?.has(i);
            const offset = start !== null && step.timestamp ? Date.parse(step.timestamp) - start : null;
            const { label, text } = body(step);
            const { kind, subject } = title(step);
            return (
              // content-visibility: the browser skips layout and paint for steps off screen, while
              // every step stays in the DOM for find-in-page, tab order and screen readers (ADR 0031).
              <li
                key={i}
                id={`${idPrefix}-${i}`}
                className="relative grid scroll-mt-72 pb-8 pl-40 [contain-intrinsic-size:auto_56px] [content-visibility:auto]"
              >
                <span aria-hidden className="absolute top-32 bottom-0 left-12 w-px bg-hairline-strong" />
                <span
                  aria-hidden
                  className={cx(
                    "absolute top-4 left-0 flex size-24 items-center justify-center border border-hairline-strong type-micro",
                    step.type === "error" ? "border-fail bg-canvas text-fail" : "bg-canvas text-ink",
                  )}
                >
                  {GLYPH[step.type]}
                </span>
                <div
                  className={cx(
                    "grid gap-12",
                    layout === "wide" && verdicts.length > 0 && "desktop:grid-cols-[minmax(0,1fr)_minmax(0,320px)]",
                  )}
                >
                  <details
                    open={!compact}
                    className={cx("group min-w-0 border", different ? "border-ink-muted bg-surface-2" : "border-hairline bg-canvas")}
                  >
                    <summary className="flex min-h-40 cursor-pointer list-none flex-wrap items-center gap-x-12 gap-y-4 px-12 py-8 -outline-offset-2 [&::-webkit-details-marker]:hidden">
                      <span aria-hidden className="type-micro text-ink-muted tabular-nums">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className="sr-only">Step {i + 1}:</span>
                      <span className={cx("type-label", step.type === "error" ? "text-fail" : "text-ink")}>{kind}</span>
                      {subject !== null && <span className="min-w-0 truncate type-code text-ink">{visibleText(subject)}</span>}
                      {different && <span className="border border-ink-muted px-6 type-micro text-ink">Differs</span>}
                      {step.type === "error" && <JudgmentBadge status="error" />}
                      <span className="ml-auto type-micro text-ink-muted tabular-nums">
                        {!!offset && `+${ms(offset)} · `}
                        {step.duration_ms != null ? ms(step.duration_ms) : "no timing"}
                      </span>
                      {/* One line of the content while collapsed, as plain text. */}
                      <span className="w-full truncate type-code text-ink-muted group-open:hidden">{visibleText(text)}</span>
                    </summary>
                    <div className="border-t border-hairline px-12 pt-4 pb-12">
                      <div className="mb-4 flex items-center justify-between gap-8">
                        <p className="type-micro text-ink-muted">{label}</p>
                        <CopyButton text={text} name={`step ${i + 1}`} />
                      </div>
                      <PlainText text={text} />
                    </div>
                  </details>
                  {verdicts.length > 0 && <Verdicts judgments={verdicts} label={`Verdicts on step ${i + 1}`} />}
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {whole.length > 0 && (
        <section className="mt-8 pl-40" aria-label="Verdicts on the whole attempt">
          <h3 className="mb-8 type-micro text-ink-muted">Whole attempt</h3>
          <Verdicts judgments={whole} label="Verdicts on the whole attempt" />
        </section>
      )}
    </>
  );
}

/** Rule verdicts are solid-bordered, LLM verdicts dashed; both say which they are in text. */
function Verdicts({ judgments, label }: { judgments: Judgment[]; label: string }) {
  return (
    <ul aria-label={label} className="flex min-w-0 flex-col gap-8">
      {judgments.map((j, i) => {
        const llm = LLM_JUDGES.has(j.judge);
        return (
          <li
            key={i}
            className={cx("border p-12", llm ? "border-dashed border-ink-muted" : "border-hairline bg-canvas")}
          >
            <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
              <JudgmentBadge status={j.status} />
              <span className="type-code text-ink">{j.judge}</span>
              <span className="type-micro text-ink-muted">{llm ? "LLM judge" : "Rule"}</span>
              <span className="ml-auto type-micro text-ink-muted tabular-nums">Score {score(j.score)}</span>
            </div>
            {j.reason && <PlainText text={j.reason} mono={false} limit={600} className="mt-6 text-ink-muted" />}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Every verdict on the attempt in one list: which judges passed, each one's score, the step it
 * concerns (a link to it) and its reason. Reasons quote agent output: plain text only.
 */
export function VerdictPanel({ trace, idPrefix = "step" }: { trace: Trace; idPrefix?: string }) {
  const passed = trace.judgments.filter((j) => j.status === "pass").length;
  return (
    <Panel aria-label="Judge verdicts" title="Judge verdicts" titleStyle="label" actions={<AttemptBadge status={trace.status} />}>
      <p className="type-data text-ink tabular-nums">
        {trace.judgments.length === 0 ? "No judges ran" : `${passed} of ${trace.judgments.length} passed`}
      </p>
      {trace.judgments.length > 0 && (
        <ol aria-label="Judge verdicts" className="-mx-16 mt-12 -mb-16">
          {trace.judgments.map((j, i) => (
            <li key={i} className={cx("border-t px-16 py-10", j.status === "fail" ? "border-fail" : "border-hairline")}>
              <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
                <JudgmentBadge status={j.status} />
                <span className="min-w-0 truncate type-code text-ink">{j.judge}</span>
                <span className="type-micro text-ink-muted">{LLM_JUDGES.has(j.judge) ? "LLM judge" : "Rule"}</span>
                <span className="ml-auto type-micro text-ink-muted tabular-nums">Score {score(j.score)}</span>
              </div>
              <p className="mt-4 type-micro">
                {j.step === null ? (
                  <span className="text-ink-muted">Whole attempt</span>
                ) : (
                  <a href={`#${idPrefix}-${j.step}`} className="text-accent underline-offset-4 hover:underline">
                    Step {j.step + 1}
                  </a>
                )}
              </p>
              {j.reason && <PlainText text={j.reason} mono={false} limit={240} className="mt-4 text-ink-muted" />}
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}
