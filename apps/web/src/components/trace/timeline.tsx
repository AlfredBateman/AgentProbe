import { JudgmentBadge } from "@/components/run/labels";
import { jsonText, PlainText } from "@/components/ui/code";
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

function title(step: Step): string {
  switch (step.type) {
    case "message":
      return `Message · ${step.role}`;
    case "tool_call":
      return `Tool call · ${step.tool}`;
    case "tool_result":
      return `Tool result · ${step.tool}`;
    case "error":
      return "Error";
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
        <p className="rounded-lg bg-surface-1 p-15 text-body-sm text-ink-muted">No trace: the agent never answered.</p>
      ) : (
        <ol aria-label="Trace steps" className="flex flex-col">
          {trace.steps.map((step, i) => {
            const verdicts = byStep.get(i) ?? [];
            const different = differs?.has(i);
            const offset = start !== null && step.timestamp ? Date.parse(step.timestamp) - start : null;
            const { label, text } = body(step);
            return (
              // content-visibility: the browser skips layout and paint for steps off screen, while
              // every step stays in the DOM for find-in-page, tab order and screen readers (ADR 0031).
              <li
                key={i}
                id={`${idPrefix}-${i}`}
                className="relative grid gap-x-15 pb-12 [contain-intrinsic-size:auto_88px] [content-visibility:auto] pl-44"
              >
                <span aria-hidden className="absolute top-40 bottom-0 left-15 w-1 bg-hairline" />
                <span
                  aria-hidden
                  className={cx(
                    "absolute top-8 left-0 flex size-32 items-center justify-center rounded-full font-mono text-code",
                    step.type === "error" ? "bg-surface-2 text-fail" : "bg-surface-2 text-ink",
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
                    className={cx("group min-w-0 rounded-lg", different ? "bg-surface-2" : "bg-surface-1")}
                  >
                    <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-12 gap-y-4 rounded-lg px-15 py-10 outline-none focus-visible:shadow-focus [&::-webkit-details-marker]:hidden">
                      <span className="text-data text-ink-muted tabular-nums">{i + 1}</span>
                      <span className="font-medium text-body-sm text-ink">{title(step)}</span>
                      {different && <span className="rounded-sm border border-ink-muted px-6 text-data-label text-ink">Differs</span>}
                      {step.type === "error" && <JudgmentBadge status="error" />}
                      <span className="ml-auto text-data text-ink-muted tabular-nums">
                        {!!offset && `+${ms(offset)} · `}
                        {step.duration_ms != null ? ms(step.duration_ms) : "no timing"}
                      </span>
                      {/* One line of the content while collapsed, as plain text. */}
                      <span className="w-full truncate font-mono text-code text-ink-muted group-open:hidden">{text}</span>
                    </summary>
                    <div className="border-t border-hairline-soft px-15 py-12">
                      <p className="mb-6 text-data-label text-ink-muted">{label}</p>
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
        <section className="mt-8 pl-44" aria-label="Verdicts on the whole attempt">
          <h3 className="mb-8 text-data-label text-ink-muted">Whole attempt</h3>
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
            className={cx("rounded-lg border p-12", llm ? "border-dashed border-ink-muted" : "border-hairline bg-canvas")}
          >
            <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
              <JudgmentBadge status={j.status} />
              <span className="font-mono text-code text-ink">{j.judge}</span>
              <span className="text-data-label text-ink-muted">{llm ? "LLM judge" : "Rule"}</span>
              <span className="ml-auto text-data text-ink-muted tabular-nums">Score {score(j.score)}</span>
            </div>
            {j.reason && <PlainText text={j.reason} mono={false} limit={600} className="mt-6 text-ink-muted" />}
          </li>
        );
      })}
    </ul>
  );
}
