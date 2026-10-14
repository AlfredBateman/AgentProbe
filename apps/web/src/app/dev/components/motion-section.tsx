"use client";

// The motion layer (src/lib/motion) in the catalogue: each effect with a Replay button, and a
// switch that forces reduced motion so the final-state path can be seen without changing the OS
// setting. Fake data only.
import gsap from "gsap";
import { type ReactNode, useRef, useState, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Label, Switch } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { Stat, StatGrid } from "@/components/ui/stat";
import { REDUCE_ATTR } from "@/lib/motion/core";
import { useCountUp, useReveal, useStagger } from "@/lib/motion/hooks";
import { PageTransition } from "@/lib/motion/page-transition";
import { useSplitHeading } from "@/lib/motion/split-heading";

const OS_REDUCES = "(prefers-reduced-motion: reduce)";
const watchOs = (notify: () => void) => {
  const query = matchMedia(OS_REDUCES);
  query.addEventListener("change", notify);
  return () => query.removeEventListener("change", notify);
};

function Revealed({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useReveal(ref);
  return (
    <div ref={ref} className="border border-hairline-strong p-16">
      {children}
    </div>
  );
}

function Counted({ value, format }: { value: number; format: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const text = useCountUp(ref, value, format);
  return <span ref={ref}>{text}</span>;
}

function Staggered({ selector, children }: { selector?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useStagger(ref, selector);
  return <div ref={ref}>{children}</div>;
}

function SplitHeading({ children }: { children: string }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useSplitHeading(ref);
  return (
    <h3 ref={ref} className="max-w-480 type-display-lg">
      {children}
    </h3>
  );
}

type Row = { id: string; passes: number; latency: number };
const rows: Row[] = [
  { id: "refund-inside-window", passes: 5, latency: 412 },
  { id: "refund-outside-window", passes: 0, latency: 388 },
  { id: "order-status", passes: 4, latency: 1204 },
  { id: "prompt-leak", passes: 5, latency: 297 },
  { id: "scope-drift", passes: 3, latency: 655 },
];
const columns: Column<Row>[] = [
  { key: "case", header: "Case", value: (r) => r.id },
  { key: "passes", header: "Passes", align: "right", value: (r) => r.passes, render: (r) => `${r.passes}/5` },
  { key: "latency", header: "Mean latency", align: "right", value: (r) => r.latency, render: (r) => `${r.latency.toLocaleString("en-US")} ms` },
];

const percent = (n: number) => `${n.toFixed(1)}%`;
const whole = (n: number) => String(Math.round(n));
const dollars = (n: number) => `$${n.toFixed(4)}`;
const millis = (n: number) => `${Math.round(n).toLocaleString("en-US")} ms`;

/** One effect: a titled panel whose Replay button remounts its demo. */
function Effect({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  const [run, setRun] = useState(0);
  return (
    <Panel
      title={title}
      titleStyle="label"
      actions={
        <Button variant="secondary" onClick={() => setRun(run + 1)}>
          Replay
        </Button>
      }
    >
      <p className="mb-16 max-w-640 type-micro text-ink-muted">{note}</p>
      <div key={run}>{children}</div>
    </Panel>
  );
}

export function MotionSection() {
  const [forced, setForced] = useState(false);
  const osReduces = useSyncExternalStore(watchOs, () => matchMedia(OS_REDUCES).matches, () => false);
  const [all, setAll] = useState(0);

  function force(on: boolean) {
    setForced(on);
    document.documentElement.toggleAttribute(REDUCE_ATTR, on);
    // Reverts every live effect to its final state and re-runs it under the new setting.
    gsap.matchMediaRefresh();
  }

  return (
    <div className="flex flex-col gap-24" key={all}>
      <div className="flex flex-wrap items-center gap-x-24 gap-y-12 border border-hairline p-16">
        <span className="flex items-center gap-12">
          <Switch id="force-reduce" checked={forced} onChange={(e) => force(e.target.checked)} />
          <Label htmlFor="force-reduce">Force reduced motion</Label>
        </span>
        <span className="type-micro text-ink-muted">
          OS setting: {osReduces ? "reduce" : "no preference"} {"///"} effective: {osReduces || forced ? "reduced (final states at once)" : "motion on"}
        </span>
        <Button variant="secondary" onClick={() => setAll(all + 1)}>
          Replay all
        </Button>
      </div>

      <Effect title="Reveal" note="useReveal: a clip wipe, 200 ms, once, when it first scrolls into view. No fade. Clip-path is cleared afterwards.">
        <Revealed>
          <p className="type-body">Fourteen of forty attempts failed, all in two cases. Both are listed below.</p>
        </Revealed>
      </Effect>

      <Effect title="Count up" note="useCountUp: 0 to value in 800 ms, once. React keeps owning the text, so a later change just shows the new number.">
        <StatGrid>
          <Stat label="Pass rate" value={<Counted value={97.5} format={percent} />} note="CI 87.1 to 100" />
          <Stat label="Attempts" value={<Counted value={40} format={whole} />} />
          <Stat label="Cost" value={<Counted value={0.0042} format={dollars} />} />
          <Stat label="Mean latency" value={<Counted value={1204} format={millis} />} tone="fail" />
        </StatGrid>
      </Effect>

      <Effect title="Stagger: list" note="useStagger: direct children reveal in turn, at most 40 rows, over at most 400 ms.">
        <Staggered>
          {rows.map((r) => (
            <div key={r.id} className="flex items-center justify-between border-b border-hairline py-8">
              <span className="type-body-sm">{r.id}</span>
              <span className="type-micro tabular-nums text-ink-muted">{r.passes}/5</span>
            </div>
          ))}
        </Staggered>
      </Effect>

      <Effect title="Stagger: table rows" note={'useStagger(ref, "tbody tr"): the same on a DataTable body. Sorting afterwards does not replay it.'}>
        <Staggered selector="tbody tr">
          <DataTable columns={columns} rows={rows} rowKey={(r) => r.id} caption="Cases in this run" />
        </Staggered>
      </Effect>

      <Effect title="Split heading" note="useSplitHeading: SplitText lines slide up out of a mask, 400 ms. The split is reverted when it ends, so the heading's markup is the original again.">
        <SplitHeading>Regressions caught before they merge</SplitHeading>
      </Effect>

      <Effect
        title="Page transition"
        note="PageTransition, for app/template.tsx: a clip wipe on each navigation. A tab's first mount (the server-rendered page) is skipped, so Replay remounts it the way a navigation does."
      >
        <PageTransition>
          <div className="border border-hairline-strong p-16">
            <p className="type-headline">Project overview</p>
            <p className="type-body-sm text-ink-muted">Route content. Streamed Suspense children arrive after the wipe and simply appear.</p>
          </div>
        </PageTransition>
      </Effect>
    </div>
  );
}
