import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { ScrollRegion } from "./scroll-region";

// Charts in the telemetry style (DESIGN.md "Charts", ADR 0050): HTML and CSS laid out in
// percentages, so every label is real mono type at any width. 1px strokes, flat fills, no
// colour fade, no legend (rows are labelled directly), and a table view under each figure.
//
// Colour: lime marks the candidate, the run under examination; ink marks a baseline; red marks
// failure and nothing else. A series is never told by colour alone: every row has its word, and
// every attempt has its own shape.

export type Tone = "baseline" | "candidate" | "fail";

const TEXT: Record<Tone, string> = { baseline: "text-ink", candidate: "text-accent", fail: "text-fail" };

/** A figure: a label strip, the plot (drawn in once), and the same numbers as a table. */
export function ChartFigure({
  title,
  note,
  table,
  className,
  children,
}: {
  title: string;
  note?: ReactNode;
  /** The table view: `ChartTable`. A figure without one is not accessible, so it is required. */
  table: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    // A column, so figures side by side in a grid row share a height and their table views line up.
    <figure className={cx("flex min-w-0 flex-col border border-hairline bg-canvas", className)}>
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-12 gap-y-4 border-b border-hairline px-16 py-8">
        <span className="type-label text-ink">{title}</span>
        {note && <span className="type-micro text-ink-muted">{note}</span>}
      </figcaption>
      <div className="draw-in flex flex-1 flex-col justify-center p-16">{children}</div>
      <details className="border-t border-hairline">
        <summary className="flex min-h-40 cursor-pointer items-center px-16 type-micro text-ink-muted hover:text-ink pointer-coarse:min-h-44">Table view</summary>
        <div className="px-16 pb-16">
          <ScrollRegion label={`${title}, table view`}>{table}</ScrollRegion>
        </div>
      </details>
    </figure>
  );
}

/** The table behind a figure: every plotted value, as text. Cells are code type, so ids stay verbatim. */
export function ChartTable({ caption, head, rows }: { caption: string; head: string[]; rows: ReactNode[][] }) {
  return (
    <table className="w-full border-collapse type-code tabular-nums">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr>
          {head.map((h, i) => (
            <th key={h} scope="col" className={cx("bg-surface-1 px-12 py-6 type-micro whitespace-nowrap text-ink-muted", i === 0 ? "text-left" : "text-right")}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, r) => (
          <tr key={r} className="border-t border-hairline">
            {row.map((cell, i) => (
              <td key={i} className={cx("px-12 py-6", i === 0 ? "text-left" : "text-right")}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const TICKS = [0, 25, 50, 75, 100] as const;
const LABEL_COLUMN = "grid grid-cols-[minmax(72px,96px)_minmax(0,1fr)] items-center gap-12";

export type WhiskerRow = {
  label: string;
  tone: Exclude<Tone, "fail">;
  /** A rate in 0..1, or null when the run has none. */
  value: number | null;
  /** The 95% interval, as the API reports it. */
  lower: number | null;
  upper: number | null;
};

/**
 * Rates on a 0 to 100% ruler: a square at the value, a whisker across its 95% interval. The
 * scale is always the full 0..100, never cropped to the data. Rows are labelled in place.
 */
export function RateWhiskers({ rows }: { rows: WhiskerRow[] }) {
  return (
    <div aria-hidden>
      <ul className="flex flex-col gap-16">
        {rows.map((row) => (
          <li key={row.label} className={cx(LABEL_COLUMN, TEXT[row.tone])}>
            <span className="inline-flex items-center gap-6 type-micro text-ink">
              <span className="size-8 shrink-0 bg-current" />
              {row.label}
            </span>
            <div className="relative h-24">
              <span className="absolute inset-x-0 top-1/2 h-px bg-hairline-strong" />
              {TICKS.map((t) => (
                <span key={t} className="absolute top-1/2 h-8 w-px -translate-y-1/2 bg-hairline-strong" style={{ left: `${t}%` }} />
              ))}
              {row.lower !== null && row.upper !== null && (
                <>
                  <span className="absolute top-1/2 h-px bg-current" style={{ left: `${row.lower * 100}%`, width: `${(row.upper - row.lower) * 100}%` }} />
                  {[row.lower, row.upper].map((edge, i) => (
                    <span key={i} className="absolute top-1/2 h-12 w-px -translate-x-1/2 -translate-y-1/2 bg-current" style={{ left: `${edge * 100}%` }} />
                  ))}
                </>
              )}
              {row.value !== null && (
                <span className="absolute top-1/2 size-10 -translate-x-1/2 -translate-y-1/2 bg-current" style={{ left: `${row.value * 100}%` }} />
              )}
            </div>
          </li>
        ))}
      </ul>
      <div className={cx(LABEL_COLUMN, "mt-8")}>
        <span />
        <div className="relative h-16 type-micro text-ink-muted">
          {TICKS.filter((t) => t % 50 === 0).map((t) => (
            <span key={t} className={cx("absolute", t === 0 ? "left-0" : t === 100 ? "right-0" : "-translate-x-1/2")} style={t === 50 ? { left: "50%" } : undefined}>
              {t}%
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * One mark per attempt: a filled square for a pass (lime for the candidate, ink for a baseline),
 * the knocked-out cross for a failure (red), the hollow `!` for an error. Errors are a subset of
 * the non-passes, as in core's summary. The counts beside it are the figure's text.
 */
export function AttemptStrip({ passes, attempts, errors = 0, tone }: { passes: number; attempts: number; errors?: number; tone: Exclude<Tone, "fail"> }) {
  const failed = attempts - passes - errors;
  return (
    <span aria-hidden className="inline-flex flex-wrap gap-2">
      {Array.from({ length: attempts }, (_, i) =>
        i < passes ? (
          <span key={i} className={cx("size-10 bg-current", TEXT[tone])} />
        ) : i < passes + failed ? (
          <span key={i} className="size-10 mark-fail text-fail" />
        ) : (
          <span key={i} className="size-10 mark-error text-ink-muted" />
        ),
      )}
    </span>
  );
}

export type BarRow = {
  key: string;
  label: ReactNode;
  value: number;
  tone: Tone | "flaky";
  /** Shown after the value: a unit or a share. */
  note?: string;
};

/**
 * Horizontal bars on one scale (`max`, default the largest value), the value and its label
 * written on the row. A flaky bar is hatched, so it still reads without its colour.
 */
export function Bars({ rows, max }: { rows: BarRow[]; max?: number }) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="flex flex-col gap-12">
      {rows.map((row) => (
        <li key={row.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-12 gap-y-4 tablet:grid-cols-[minmax(120px,240px)_minmax(0,1fr)_auto]">
          {/* Code type: a label here is a case id or a cluster's name, never recased. The interface's own words go in with `uppercase`. */}
          <span className="min-w-0 truncate type-code text-ink tablet:col-start-1">{row.label}</span>
          <span className="type-data text-ink tabular-nums tablet:col-start-3">
            {row.value}
            {row.note && <span className="text-ink-muted"> {row.note}</span>}
          </span>
          <span aria-hidden className="col-span-2 flex h-12 items-center border-l border-hairline-strong tablet:col-span-1 tablet:col-start-2 tablet:row-start-1">
            <span
              className={cx("block h-full", row.tone === "flaky" ? "hatch text-ink" : row.tone === "fail" ? "bg-fail" : row.tone === "candidate" ? "bg-accent" : "bg-ink")}
              style={{ width: `${(row.value / top) * 100}%`, minWidth: row.value > 0 ? 2 : 0 }}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}

export type TrendPoint = { id: string; rate: number | null; role?: "baseline" | "candidate" };

/**
 * A suite's pass rate over its completed runs, oldest to newest, on a 0 to 100% scale: a 1px
 * line, a small square per run, the baseline and the candidate larger and named in place. The
 * line is the only SVG; its markers and words are HTML so they never scale with it.
 */
export function RunTrend({ points }: { points: TrendPoint[] }) {
  const rated = points.filter((p): p is TrendPoint & { rate: number } => p.rate !== null);
  const x = (i: number) => (points.length === 1 ? 50 : (i / (points.length - 1)) * 100);
  const line = points.flatMap((p, i) => (p.rate === null ? [] : [`${x(i)},${100 - p.rate * 100}`])).join(" ");
  return (
    <div aria-hidden className="grid grid-cols-[40px_minmax(0,1fr)] gap-x-8">
      <div className="relative h-160 type-micro text-ink-muted">
        {[100, 50, 0].map((t) => (
          <span key={t} className="absolute right-0 -translate-y-1/2" style={{ top: `${100 - t}%` }}>
            {t}%
          </span>
        ))}
      </div>
      <div className="relative h-160 border-b border-l border-hairline-strong">
        {[0, 50, 100].map((t) => (
          <span key={t} className="absolute inset-x-0 h-px bg-hairline" style={{ top: `${100 - t}%` }} />
        ))}
        <div className="absolute inset-x-12 inset-y-0">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible">
            {rated.length > 1 && <polyline points={line} fill="none" strokeWidth={1} vectorEffect="non-scaling-stroke" className="stroke-ink-muted" />}
          </svg>
          {points.map((p, i) =>
            p.rate === null ? null : (
              <span
                key={p.id}
                className={cx(
                  "absolute -translate-x-1/2 -translate-y-1/2",
                  p.role === "candidate" ? "size-10 bg-accent" : p.role === "baseline" ? "size-10 bg-ink" : "size-4 bg-ink-muted",
                )}
                style={{ left: `${x(i)}%`, top: `${100 - p.rate * 100}%` }}
              >
                {p.role && (
                  <span
                    className={cx(
                      "absolute type-micro whitespace-nowrap",
                      // Words hang inward from the plot's edges, so a label never leaves the figure.
                      x(i) > 66 ? "right-0" : x(i) < 33 ? "left-0" : "left-1/2 -translate-x-1/2",
                      p.role === "candidate" ? "bottom-full mb-4 text-accent" : "top-full mt-4 text-ink",
                    )}
                  >
                    {p.role === "candidate" ? "Candidate" : "Baseline"}
                  </span>
                )}
              </span>
            ),
          )}
        </div>
      </div>
      <span />
      <p className="mt-24 type-micro text-ink-muted">Runs, oldest to newest</p>
    </div>
  );
}
