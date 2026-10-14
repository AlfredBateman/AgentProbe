import Link from "next/link";
import { PlainText } from "@/components/ui/code";
import { cx } from "@/lib/cx";
import { ms, score, usd } from "@/lib/format";
import { AttemptBadge, JudgmentBadge } from "./labels";

export type AttemptItem = {
  key: string;
  /** The case id, when the list spans several cases. Verbatim. */
  title?: string;
  /** 0-based, as stored; shown 1-based. */
  attempt: number;
  status: string;
  score: number | null;
  latencyMs?: number | null;
  cost?: number | null;
  errorKind?: string | null;
  /** The agent's reply: untrusted, shown as text only. */
  output?: string | null;
  judgments: { judge: string; status: string; reason: string | null }[];
  /** The full trace, for a signed-in viewer. A public snapshot has none. */
  traceHref?: string;
};

/**
 * One case's attempts, each with its outcome, readouts, the agent's output and every judge's
 * reason. Output and reasons quote an agent that may have been attacked: plain text only, with
 * control characters made visible. A failed attempt carries a red edge and its word.
 */
export function AttemptList({ items, label }: { items: AttemptItem[]; label: string }) {
  return (
    <ol aria-label={label} className="flex flex-col gap-12 whitespace-normal">
      {items.map((a) => (
        <li key={a.key} className={cx("border border-l-2 border-hairline bg-canvas", a.status === "failed" ? "border-l-fail" : "border-l-hairline-strong")}>
          <div className="flex flex-wrap items-center gap-x-12 gap-y-6 border-b border-hairline px-12 py-8">
            {a.title && <span className="type-code break-words text-ink">{a.title}</span>}
            <span className="type-label text-ink">Attempt {a.attempt + 1}</span>
            <AttemptBadge status={a.status} />
            <dl className="flex flex-wrap items-baseline gap-x-12 gap-y-4 tabular-nums">
              <Readout term="Score">{score(a.score)}</Readout>
              {a.latencyMs !== undefined && <Readout term="Latency">{ms(a.latencyMs)}</Readout>}
              {a.cost !== undefined && <Readout term="Cost">{usd(a.cost)}</Readout>}
              {a.errorKind && <Readout term="Error">{a.errorKind}</Readout>}
            </dl>
            {a.traceHref && (
              <Link href={a.traceHref} className="tap ml-auto type-label text-accent underline-offset-4 hover:underline">
                View trace
              </Link>
            )}
          </div>
          <div className="flex flex-col gap-12 px-12 py-12">
            {a.output && (
              <div>
                <p className="mb-4 type-micro text-ink-muted">Output</p>
                <PlainText text={a.output} limit={600} />
              </div>
            )}
            {a.judgments.length > 0 && (
              <ul aria-label="Judgments" className="flex flex-col gap-8">
                {a.judgments.map((j, i) => (
                  <li key={i} className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-8 gap-y-4">
                    <JudgmentBadge status={j.status} />
                    <div className="min-w-0">
                      <p className="type-code break-words text-ink">{j.judge}</p>
                      {j.reason && <PlainText text={j.reason} mono={false} limit={300} className="mt-2 [&_samp]:text-ink-muted" />}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Readout({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-4">
      <dt className="type-micro text-ink-muted">{term}</dt>
      <dd className="type-data text-ink">{children}</dd>
    </div>
  );
}
