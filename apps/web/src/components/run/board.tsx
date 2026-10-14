"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Panel } from "@/components/ui/panel";
import { StatusDot } from "@/components/ui/status";
import { cx } from "@/lib/cx";
import { duration, usd } from "@/lib/format";
import { useFlash } from "@/lib/motion/hooks";
import { CELL_MARK, CELL_TEXT, type Cell, segments, tally } from "@/lib/run-board";
import type { Attempt } from "@/lib/run-cases";
import type { Connection } from "@/lib/use-run-stream";

const CONNECTION: Record<Connection, string> = {
  connecting: "Connecting…",
  live: "Live",
  reconnecting: "Reconnecting…",
  polling: "Live updates unavailable; refreshing every few seconds",
  closed: "Finished",
};

const SEGMENTS = 40;

function useNow() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

/** The live strip: a segmented bar of attempts, the readouts beside it, and the stream's state. */
export function ProgressStrip({
  status,
  done,
  total,
  startedAt,
  attempts,
  connection,
}: {
  status: string;
  done: number;
  total: number;
  startedAt: string | null;
  attempts: Attempt[];
  connection: Connection;
}) {
  const now = useNow();
  const started = startedAt ? Date.parse(startedAt) : null;
  const elapsed = started ? now - started : 0;
  const eta = started && done > 0 && done < total ? (elapsed / done) * (total - done) : null;
  const costs = attempts.map((a) => a.cost).filter((c): c is number => c !== null);
  const count = (s: string) => attempts.filter((a) => a.status === s).length;
  const filled = segments(done, total, SEGMENTS);
  const width = String(total).length;

  return (
    <section aria-labelledby="live-title" className="mt-24 border border-hairline-strong bg-canvas">
      <header className="flex flex-wrap items-center justify-between gap-x-12 gap-y-4 border-b border-hairline px-16 py-8">
        <h2 id="live-title" className="inline-flex items-center gap-8 type-label">
          <StatusDot status={status === "queued" ? "queued" : "running"} decorative />
          {status === "queued" ? "Queued" : "Running"}
        </h2>
        <p aria-live="polite" className="type-micro text-ink-muted">
          {CONNECTION[connection]}
        </p>
      </header>
      <div className="flex flex-col gap-12 p-16">
        <div className="flex flex-wrap items-center gap-x-16 gap-y-8">
          <div
            role="progressbar"
            aria-label="Attempts finished"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={done}
            aria-valuetext={`${done} of ${total} attempts`}
            className="flex h-16 min-w-200 flex-1 gap-2"
          >
            {Array.from({ length: SEGMENTS }, (_, i) => (
              <span key={i} className={cx("flex-1", i < filled ? "bg-ink" : "border border-hairline")} />
            ))}
          </div>
          <p className="type-data whitespace-pre text-ink tabular-nums">
            {String(done).padStart(width, "0")}/{total} <span className="text-ink-muted">ATT</span>{" "}
            {total ? `${Math.floor((done / total) * 100)}%` : "0%"}
          </p>
        </div>
        <dl className="grid grid-cols-2 gap-x-16 gap-y-8 tablet:grid-cols-3 desktop:grid-cols-6">
          <Readout term="Passed">{count("passed")}</Readout>
          <Readout term="Failed" fail={count("failed") > 0}>
            {count("failed")}
          </Readout>
          <Readout term="Errors">{count("error")}</Readout>
          <Readout term="Elapsed">{started ? duration(elapsed) : "—"}</Readout>
          <Readout term="Remaining">{eta === null ? "—" : `~${duration(eta)}`}</Readout>
          <Readout term="Cost so far">{costs.length ? usd(costs.reduce((a, b) => a + b, 0)) : "—"}</Readout>
        </dl>
      </div>
    </section>
  );
}

function Readout({ term, fail, children }: { term: string; fail?: boolean; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4">
      <dt className="type-micro text-ink-muted">{term}</dt>
      <dd className={cx("type-data tabular-nums", fail ? "text-fail" : "text-ink")}>{children}</dd>
    </div>
  );
}

const SLOT = { passed: "pass", failed: "fail", error: "error" } as const;

/** The case grid: every case of the run, in the suite's order, as one cell that changes state. */
export function CaseBoard({ cells, projectId, runId }: { cells: Cell[]; projectId: string; runId: string }) {
  const counts = tally(cells).filter(([, n]) => n > 0);
  return (
    <Panel
      aria-label="Cases at a glance"
      title="Case board"
      titleStyle="label"
      actions={
        <p className="type-micro text-ink-muted tabular-nums">
          {cells.length} {cells.length === 1 ? "case" : "cases"}
        </p>
      }
    >
      {cells.length === 0 ? (
        <p className="type-body-sm text-ink-muted">No cases yet.</p>
      ) : (
        <ol aria-label="Case board" className="grid grid-cols-[repeat(auto-fill,minmax(148px,1fr))] border-t border-l border-hairline">
          {cells.map((cell) => (
            <CaseCell key={cell.case} cell={cell} href={cell.resultId ? `/projects/${projectId}/runs/${runId}/results/${cell.resultId}` : null} />
          ))}
        </ol>
      )}
      <ul aria-label="Cases by state" className="mt-12 flex flex-wrap gap-x-16 gap-y-6">
        {counts.map(([state, n]) => (
          <li key={state} className={cx("inline-flex items-center gap-6 type-micro", state === "fail" ? "text-fail" : "text-ink-muted")}>
            <StatusDot status={CELL_MARK[state]} decorative />
            {CELL_TEXT[state]} <span className="tabular-nums">{n}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function CaseCell({ cell, href }: { cell: Cell; href: string | null }) {
  const flash = useRef<HTMLSpanElement>(null);
  useFlash(flash, cell.state);
  const fail = cell.state === "fail";
  const muted = cell.state === "queued" || cell.state === "not-run" || cell.state === "error";
  const label = `${cell.case}: ${CELL_TEXT[cell.state]}${cell.done ? `, ${cell.passes} of ${cell.done} attempts passed` : ""}`;
  const body = (
    <>
      <span className="flex items-center justify-between gap-8">
        <span className={cx("inline-flex items-center gap-6 type-micro", fail ? "text-fail" : muted ? "text-ink-muted" : "text-ink")}>
          <StatusDot status={CELL_MARK[cell.state]} decorative />
          {CELL_TEXT[cell.state]}
        </span>
        <span className="type-micro text-ink-muted tabular-nums">
          {cell.passes}/{cell.done}
        </span>
      </span>
      {/* The case id is the author's: verbatim, never uppercased. */}
      <span className="truncate type-code text-ink" title={cell.case}>
        {cell.case}
      </span>
      <span aria-hidden className="flex flex-wrap gap-3">
        {cell.slots.map((s, i) => (
          <StatusDot key={i} status={s ? (SLOT[s as keyof typeof SLOT] ?? "error") : "queued"} decorative className={s ? undefined : "text-hairline-strong"} />
        ))}
      </span>
    </>
  );
  return (
    <li data-case={cell.case} data-state={cell.state} className={cx("relative min-w-0 border-r border-b border-hairline", fail ? "text-fail" : "text-ink")}>
      {href ? (
        <Link href={href} aria-label={label} className="flex h-full flex-col gap-8 p-10 -outline-offset-2 hover:bg-surface-1">
          {body}
        </Link>
      ) : (
        <div role="group" aria-label={label} className="flex h-full flex-col gap-8 p-10">
          {body}
        </div>
      )}
      {/* The state-change flash: hidden by its clip, shown and stepped away by useFlash. */}
      <span ref={flash} data-flash aria-hidden className="pointer-events-none absolute inset-0 border-2 border-current [clip-path:inset(0_0_100%_0)]" />
    </li>
  );
}
