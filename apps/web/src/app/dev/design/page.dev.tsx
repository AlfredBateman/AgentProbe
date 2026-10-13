// Dev-only design boards for the DESIGN.md system (`*.dev.tsx` is excluded from production
// builds, see next.config.ts). Static markup; every figure on this page is a placeholder.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactNode } from "react";
import { parse } from "yaml";
import { contrast } from "@/lib/contrast";
import { cx } from "@/lib/cx";

type Tier = { fontFamily: string; fontSize: string; fontWeight: number; lineHeight: number; letterSpacing: string; wordSpacing?: string; fontStretch?: string };
type Tokens = {
  colors: Record<string, string>;
  typography: Record<string, Tier>;
  spacing: Record<string, string>;
  borders: Record<string, string>;
  zIndex: Record<string, number>;
  motion: { duration: Record<string, string>; easing: Record<string, string> };
};

// Read at render, so the boards can't drift from DESIGN.md. The dev server runs in apps/web.
function readTokens(): Tokens {
  const source = readFileSync(join(process.cwd(), "../../DESIGN.md"), "utf8");
  return parse(source.match(/^---\r?\n([\s\S]*?)\r?\n---/)![1]);
}

// The REV marks show the app's package version (the dev server runs in apps/web), never a typed number.
const REV: string = JSON.parse(readFileSync(join(process.cwd(), "package.json"), "utf8")).version;

// Class names are spelled out so Tailwind finds them.
const SPECIMENS: Record<string, { className: string; sample: string }> = {
  "display-xxl": { className: "type-display-xxl", sample: "Probe" },
  "display-xl": { className: "type-display-xl", sample: "Regression" },
  "display-lg": { className: "type-display-lg", sample: "Verdict 0123" },
  "display-md": { className: "type-display-md", sample: "Run detail" },
  headline: { className: "type-headline", sample: "Panel heading" },
  "body-lg": { className: "type-body-lg", sample: "AgentProbe runs every case many times and blocks a merge only when the drop is statistically real." },
  body: { className: "type-body", sample: "A flaky case that happened to fail this time is not a regression. Prose stays in sentence case." },
  "body-sm": { className: "type-body-sm", sample: "Help text: use five or more runs per case." },
  label: { className: "type-label", sample: "Runs per case" },
  micro: { className: "type-micro", sample: `REV ${REV} /// Unit D-01` },
  data: { className: "type-data", sample: "5/5 · 412 ms · p = 0.0040" },
  button: { className: "type-button", sample: ">>> Start run" },
  code: { className: "type-code", sample: 'tool_call(lookup_order, {"order_id": "SAMPLE-0042"})' },
};

const COLOR_ROLES: Record<string, string> = {
  canvas: "Page, panels",
  "surface-1": "Headers, hover",
  "surface-2": "Selected, dialogs",
  hairline: "1px grid lines",
  "hairline-strong": "Control borders",
  ink: "Text, pass",
  "ink-muted": "Labels, metadata",
  accent: "Brand, action, focus",
  "on-accent": "Text on lime",
  fail: "Failure only",
  "on-fail": "Text on red",
};

const BUTTON = {
  primary: "bg-accent text-on-accent hover:bg-ink",
  secondary: "border border-hairline-strong text-ink hover:border-ink",
  danger: "border border-fail text-fail hover:bg-fail hover:text-on-fail",
};

function SampleButton({ variant, children }: { variant: keyof typeof BUTTON; children: string }) {
  return (
    <button
      type="button"
      className={cx(
        "inline-flex min-h-40 shrink-0 cursor-pointer items-center px-16 type-button whitespace-nowrap active:translate-y-1 pointer-coarse:min-h-44",
        BUTTON[variant],
      )}
    >
      {children}
    </button>
  );
}

// A mark is a shape, so it reads without its colour (DESIGN.md "Status encoding").
const STATUS = {
  pass: { label: "Pass", chip: "border-hairline-strong text-ink", mark: "size-10 bg-current" },
  fail: { label: "Fail", chip: "border-fail text-fail", mark: "size-10 mark-fail" },
  flaky: { label: "Flaky", chip: "border-dashed border-ink text-ink", mark: "size-10 hatch" },
  error: { label: "Error", chip: "border-hairline-strong text-ink-muted", mark: "size-10 mark-error" },
  stable: { label: "Stable", chip: "border-hairline-strong text-ink", mark: "h-2 w-10 bg-current" },
};
type StatusName = keyof typeof STATUS;

function Chip({ status }: { status: StatusName }) {
  const s = STATUS[status];
  return (
    <span className={cx("inline-flex items-center gap-6 border px-8 py-3 type-label whitespace-nowrap", s.chip)}>
      <span aria-hidden className={cx("shrink-0", s.mark)} />
      {s.label}
    </span>
  );
}

const VERDICT = {
  regression: { label: "Regression", className: "border-fail bg-fail text-on-fail" },
  improvement: { label: "Improvement", className: "border-accent text-accent" },
  "no-change": { label: "No change", className: "border-ink text-ink" },
};
type VerdictName = keyof typeof VERDICT;

function Verdict({ kind }: { kind: VerdictName }) {
  return <span className={cx("inline-flex items-center border px-8 py-3 type-label whitespace-nowrap", VERDICT[kind].className)}>{VERDICT[kind].label}</span>;
}

function Board({ n, id, title, children }: { n: string; id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="crosshair border border-hairline-strong">
      <header className="flex flex-wrap items-center justify-between gap-8 border-b border-hairline-strong bg-surface-1 px-16 py-10 type-label text-ink-muted">
        <h2 id={`${id}-title`} className="text-ink">
          [ Board {n} / {title} ]
        </h2>
        <span>
          REV {REV} {"///"} Placeholder data
        </span>
      </header>
      {children}
    </section>
  );
}

function Strip({ children }: { children: ReactNode }) {
  return <h3 className="border-b border-hairline px-16 py-8 type-micro text-ink-muted">{children}</h3>;
}

function TypeBoard({ typography }: { typography: Tokens["typography"] }) {
  return (
    <Board n="01" id="board-type" title="Type">
      <div className="divide-y divide-hairline">
        {Object.entries(typography).map(([name, t]) => (
          <div key={name} data-tier={name} className="grid gap-12 px-16 py-16 tablet:grid-cols-[200px_1fr] tablet:gap-24">
            <div className="flex flex-col gap-4 type-micro text-ink-muted">
              <span className="type-label text-ink">{name}</span>
              <span>
                {t.fontFamily} {t.fontWeight}
                {t.fontStretch ? ` / ${t.fontStretch} width` : ""}
              </span>
              <span className="normal-case">{t.fontSize}</span>
              <span>
                LH {t.lineHeight} / TR {t.letterSpacing}
                {t.wordSpacing ? ` / WS ${t.wordSpacing}` : ""}
              </span>
            </div>
            <p className={cx("min-w-0 overflow-x-clip", SPECIMENS[name]?.className)}>{SPECIMENS[name]?.sample}</p>
          </div>
        ))}
        <div className="flex flex-wrap items-baseline gap-x-32 gap-y-12 overflow-x-clip px-16 py-24">
          <p className="type-display-xl text-accent">Filled</p>
          <p className="type-display-xl text-outline text-accent">Outline</p>
          <p className="type-display-xl text-outline">Outline</p>
        </div>
      </div>
    </Board>
  );
}

function TokenBoard({ tokens }: { tokens: Tokens }) {
  const { colors } = tokens;
  const list = (entries: Record<string, string | number>) => (
    <dl className="flex flex-col gap-8 p-16">
      {Object.entries(entries).map(([name, value]) => (
        <div key={name} className="flex items-baseline justify-between gap-12">
          <dt className="type-label">{name}</dt>
          <dd className="type-code text-ink-muted">{value}</dd>
        </div>
      ))}
    </dl>
  );
  return (
    <Board n="02" id="board-tokens" title="Tokens">
      <Strip>{"///"} Colour and contrast</Strip>
      <p className="border-b border-hairline px-16 py-8 type-body-sm text-ink-muted">
        Contrast is against canvas, or against its own fill for on-accent and on-fail.
      </p>
      <div className="grid-lines grid-cols-2 border-b border-hairline tablet:grid-cols-4 desktop:grid-cols-6">
        {Object.entries(colors).map(([name, value]) => (
          <div key={name} className="flex flex-col gap-6 p-12">
            <div className="h-56 border border-hairline-strong" style={{ backgroundColor: value }} />
            <span className="mt-4 type-label">{name}</span>
            <span className="type-code text-ink-muted">{value}</span>
            <span className="type-micro text-ink-muted">
              {contrast(value, colors[name.startsWith("on-") ? name.slice(3) : "canvas"]).toFixed(2)}:1 {"///"} {COLOR_ROLES[name]}
            </span>
          </div>
        ))}
        <div className="flex flex-col justify-between gap-6 p-12">
          <div className="h-56 border-2 border-ink" />
          <span className="mt-4 type-label">Radius</span>
          <span className="type-code text-ink-muted">0px</span>
          <span className="type-micro text-ink-muted">Everywhere {"///"} no exceptions</span>
        </div>
      </div>
      <div className="grid-lines tablet:grid-cols-2 desktop:grid-cols-4">
        <div>
          <Strip>{"///"} Borders</Strip>
          <div className="flex flex-col gap-16 p-16">
            {Object.entries(tokens.borders).map(([name, value]) => (
              <div key={name} className="flex items-center gap-12">
                <span className="w-80 type-label">
                  {name} <span className="text-ink-muted normal-case">{value}</span>
                </span>
                <span className="flex-1 bg-ink" style={{ height: value }} />
              </div>
            ))}
            <div className="grid-lines grid-cols-3 border border-hairline">
              {["Gap", "1px", "Grid"].map((cell) => (
                <span key={cell} className="p-12 type-micro text-ink-muted">
                  {cell}
                </span>
              ))}
            </div>
          </div>
        </div>
        <div>
          <Strip>{"///"} Spacing</Strip>
          <div className="flex flex-col gap-8 p-16">
            {Object.entries(tokens.spacing).map(([name, value]) => (
              <div key={name} className="flex items-center gap-12">
                <span className="w-96 shrink-0 type-label">
                  {name} <span className="text-ink-muted normal-case">{value}</span>
                </span>
                <span className="h-8 bg-ink" style={{ width: value }} />
              </div>
            ))}
          </div>
        </div>
        <div>
          <Strip>{"///"} Z-index</Strip>
          {list(tokens.zIndex)}
        </div>
        <div>
          <Strip>{"///"} Motion</Strip>
          {list({ ...tokens.motion.duration, ...tokens.motion.easing })}
        </div>
      </div>
    </Board>
  );
}

const RUNS: { id: string; suite: string; agent: string; verdict: VerdictName; rate: string; cases: string; when: string }[] = [
  { id: "sample-run-06", suite: "sample-suite-a", agent: "sample-agent-v2", verdict: "regression", rate: "86.7%", cases: "26/30", when: "T-00:04" },
  { id: "sample-run-05", suite: "sample-suite-a", agent: "sample-agent-v1", verdict: "no-change", rate: "96.0%", cases: "29/30", when: "T-01:12" },
  { id: "sample-run-04", suite: "sample-suite-b", agent: "sample-agent-v1", verdict: "improvement", rate: "97.3%", cases: "12/12", when: "T-03:40" },
  { id: "sample-run-03", suite: "sample-suite-a", agent: "sample-agent-v1", verdict: "no-change", rate: "95.3%", cases: "29/30", when: "T-09:15" },
  { id: "sample-run-02", suite: "sample-suite-b", agent: "sample-agent-v1", verdict: "regression", rate: "71.7%", cases: "8/12", when: "T-22:51" },
  { id: "sample-run-01", suite: "sample-suite-a", agent: "sample-agent-v1", verdict: "no-change", rate: "96.7%", cases: "29/30", when: "T-26:03" },
];

function ShellBoard() {
  const th = "px-12 py-8 type-micro whitespace-nowrap text-ink-muted";
  const td = "px-12 py-10 type-data whitespace-nowrap";
  return (
    <Board n="03" id="board-shell" title="App shell">
      <nav aria-label="Sample navigation" className="flex h-56 items-center gap-16 border-b border-hairline-strong px-16">
        <span className="type-headline">
          AgentProbe
          <span aria-hidden className="text-accent">
            ®
          </span>
        </span>
        <button type="button" className="hidden h-32 cursor-pointer items-center gap-8 border border-hairline-strong px-10 type-code hover:border-ink tablet:inline-flex">
          sample-project <span aria-hidden>▾</span>
        </button>
        <ul className="hidden items-center gap-20 type-label tablet:flex">
          <li>
            <a href="#board-shell" aria-current="page" className="text-accent">
              [ Runs ]
            </a>
          </li>
          {["Agents", "Suites", "Settings"].map((item) => (
            <li key={item}>
              <a href="#board-shell" className="text-ink-muted hover:text-ink">
                {item}
              </a>
            </li>
          ))}
        </ul>
        <span className="ml-auto hidden type-code text-ink-muted desktop:inline">user@example.com</span>
        <span className="ml-auto hidden tablet:inline-flex desktop:ml-0">
          <SampleButton variant="secondary">Sign out</SampleButton>
        </span>
        <span className="ml-auto tablet:hidden">
          <SampleButton variant="secondary">[ Menu ]</SampleButton>
        </span>
      </nav>
      <div className="flex flex-wrap items-end justify-between gap-16 border-b border-hairline px-16 py-20">
        <div>
          <p className="type-micro text-ink-muted">Unit D-01 {"///"} 6 runs shown</p>
          <h3 className="mt-8 type-display-md">Runs</h3>
        </div>
        <SampleButton variant="primary">{">>> Start run"}</SampleButton>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-720 border-collapse text-left">
          <caption className="sr-only">Sample runs, placeholder data</caption>
          <thead>
            <tr className="bg-surface-1">
              {["Run", "Suite", "Agent", "Verdict"].map((h) => (
                <th key={h} scope="col" className={th}>
                  {h}
                </th>
              ))}
              {["Pass rate", "Cases", "Started"].map((h) => (
                <th key={h} scope="col" className={cx(th, "text-right")}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {RUNS.map((r) => (
              <tr key={r.id} className="border-t border-hairline hover:bg-surface-1">
                <td className="px-12 py-10 type-code whitespace-nowrap">
                  <a href="#board-run" className="text-ink underline decoration-hairline-strong underline-offset-4 hover:text-accent hover:decoration-accent">
                    {r.id}
                  </a>
                </td>
                <td className="px-12 py-10 type-code whitespace-nowrap text-ink-muted">{r.suite}</td>
                <td className="px-12 py-10 type-code whitespace-nowrap text-ink-muted">{r.agent}</td>
                <td className="px-12 py-10">
                  <Verdict kind={r.verdict} />
                </td>
                <td className={cx(td, "text-right", r.verdict === "regression" && "text-fail")}>{r.rate}</td>
                <td className={cx(td, "text-right")}>{r.cases}</td>
                <td className={cx(td, "text-right text-ink-muted")}>{r.when}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex justify-between gap-16 border-t border-hairline px-16 py-8 type-micro text-ink-muted">
        <span>Sample data {"///"} not real runs</span>
        <span>Page 01 / 01</span>
      </div>
    </Board>
  );
}

const TILES = [
  { label: "Pass rate", value: "86.7%", note: "CI 80.1 to 92.0 /// illustrative" },
  { label: "Cases", value: "30", note: "26 pass / 1 fail / 2 flaky / 1 error" },
  { label: "Attempts", value: "150", note: "5 per case" },
  { label: "Regressed", value: "01", note: "p = 0.0040 /// illustrative", fail: true },
];

const STEPS = [
  { n: "01", type: "message", name: "user", ms: "n/a" },
  { n: "02", type: "tool_call", name: "lookup_order", ms: "412 ms", open: true },
  { n: "03", type: "tool_result", name: "lookup_order", ms: "38 ms" },
  { n: "04", type: "message", name: "assistant", ms: "1,204 ms" },
];
const ARGUMENTS = `{
  "order_id": "SAMPLE-0042",
  "include": ["status", "refund_window"]
}`;
const RESULT = `{
  "status": "delivered",
  "delivered_days_ago": 40
}`;

function RunBoard() {
  const row = "flex flex-wrap items-center gap-x-24 gap-y-12 border-b border-hairline px-16 py-12";
  return (
    <Board n="04" id="board-run" title="Run detail">
      <div className="flex flex-wrap items-end justify-between gap-16 border-b border-hairline px-16 py-20">
        <div className="min-w-0">
          <p className="type-code text-ink-muted">runs / sample-run-06</p>
          <h3 className="mt-8 type-display-md">Run 06</h3>
          <p className="mt-8 type-code text-ink-muted">sample-suite-a / sample-agent-v2, baseline sample-run-05</p>
        </div>
        <div className="flex flex-wrap items-center gap-8">
          <Verdict kind="regression" />
          <SampleButton variant="secondary">Compare</SampleButton>
          <SampleButton variant="danger">Cancel run</SampleButton>
        </div>
      </div>
      <dl className="grid-lines grid-cols-2 border-b border-hairline desktop:grid-cols-4">
        {TILES.map((t) => (
          <div key={t.label} className="flex flex-col gap-12 p-16">
            <dt className="type-label text-ink-muted">{t.label}</dt>
            <dd className={cx("type-display-lg tabular-nums", t.fail && "text-fail")}>{t.value}</dd>
            <dd className="type-micro text-ink-muted">{t.note}</dd>
          </div>
        ))}
      </dl>
      <div className={row}>
        <span className="w-64 type-micro text-ink-muted">Status</span>
        <div className="flex flex-wrap items-center gap-8">
          {(Object.keys(STATUS) as StatusName[]).map((s) => (
            <Chip key={s} status={s} />
          ))}
        </div>
      </div>
      <div className={row}>
        <span className="w-64 type-micro text-ink-muted">Verdict</span>
        <div className="flex flex-wrap items-center gap-8">
          {(Object.keys(VERDICT) as VerdictName[]).map((v) => (
            <Verdict key={v} kind={v} />
          ))}
        </div>
      </div>
      <div className={row}>
        <span className="w-64 type-micro text-ink-muted">Gate</span>
        <div className="flex flex-wrap items-center gap-x-24 gap-y-8 type-label">
          <span className="text-fail">{">>> Gate blocked"}</span>
          <span className="text-accent">{">>> Gate open"}</span>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-8 border-b border-hairline bg-surface-1 px-16 py-8">
        <h3 className="type-micro text-ink-muted">Trace {"///"} attempt 3 of 5</h3>
        <span className="type-code text-ink-muted">refund-outside-window</span>
      </div>
      {STEPS.map((s) => (
        <details key={s.n} open={s.open} className="group border-b border-hairline">
          <summary className="flex cursor-pointer list-none items-center gap-12 px-16 py-10 hover:bg-surface-1 [&::-webkit-details-marker]:hidden">
            <span className="type-micro text-ink-muted">{s.n}</span>
            <span className="border border-hairline-strong px-6 py-2 type-micro">{s.type}</span>
            <span className="type-code">{s.name}</span>
            <span aria-hidden className="h-px min-w-16 flex-1 bg-hairline" />
            <span className="type-data whitespace-nowrap text-ink-muted">{s.ms}</span>
            <span aria-hidden className="type-micro text-ink-muted group-open:hidden">
              [+]
            </span>
            <span aria-hidden className="hidden type-micro text-accent group-open:inline">
              [-]
            </span>
          </summary>
          <div className="grid-lines border-t border-hairline tablet:grid-cols-2">
            {[
              ["Arguments", ARGUMENTS],
              ["Result", RESULT],
            ].map(([label, code]) => (
              <div key={label} className="min-w-0 p-16">
                <p className="mb-8 type-micro text-ink-muted">{label}</p>
                <pre className="overflow-x-auto type-code">{code}</pre>
              </div>
            ))}
          </div>
        </details>
      ))}
      <p className="flex flex-wrap items-center gap-x-12 gap-y-4 px-16 py-12 text-fail">
        <span className="inline-flex items-center gap-8 type-label">
          <span aria-hidden className="size-8 shrink-0 bg-current" />
          Judge failed
        </span>
        <span className="type-code">{'not_contains: "refund approved" found in output'}</span>
      </p>
    </Board>
  );
}

// What an attempt-matrix cell looks like for each status; the legend uses the same classes.
const CELL = {
  pass: "bg-hairline-strong",
  flaky: "hatch text-ink",
  fail: "mark-fail text-fail",
  error: "mark-error text-ink-muted",
};

// A fixed pattern, not data: mostly passes, a few failures, flaky and error cells.
const CELLS = Array.from({ length: 180 }, (_, i) =>
  (i * 37 + 11) % 23 === 0 ? CELL.fail : (i * 17 + 5) % 19 === 0 ? CELL.flaky : (i * 29 + 3) % 31 === 0 ? CELL.error : CELL.pass,
);

const PANELS = [
  { title: "Point it at your agent", body: "HTTP, MCP or a Python adapter. Nothing to install inside the agent." },
  { title: "Run every case, many times", body: "Repeated attempts expose the flakiness a single pass hides." },
  { title: "Gate the PR on a real regression", body: "A statistical test decides, not a raw score delta." },
];

function HeroBoard() {
  return (
    <Board n="05" id="board-hero" title="Landing hero">
      <div className="flex items-center justify-between gap-16 border-b border-hairline px-16 py-12">
        <span className="type-headline">
          AgentProbe
          <span aria-hidden className="text-accent">
            ®
          </span>
        </span>
        <span className="hidden type-micro text-ink-muted tablet:inline">
          Regression detection for LLM agents {"///"} REV {REV}
        </span>
        <SampleButton variant="secondary">[ Sign in ]</SampleButton>
      </div>
      <div className="overflow-hidden px-16 pt-24 pb-32 tablet:px-32 tablet:pt-48 tablet:pb-48">
        {/* An @container, so display-xxl is sized against this width and cannot overflow it. Rows:
            the headline over the matrix, the matrix caption and legend (outside the headline),
            then the stats, which sit beside the second line on desktop. */}
        <div className="@container grid grid-cols-[minmax(0,1fr)]">
          <div className="relative col-start-1 row-start-1 grid py-24 tablet:py-48">
            <div aria-hidden className="scanlines col-start-1 row-start-1 w-[min(560px,72%)] place-self-center border border-hairline-strong bg-surface-1 p-12">
              <div className="grid grid-cols-[repeat(20,1fr)] gap-3">
                {CELLS.map((cell, i) => (
                  <span key={i} className={cx("aspect-square", cell)} />
                ))}
              </div>
            </div>
            <div className="relative col-start-1 row-start-1 self-center">
              <p className="type-display-xxl text-accent">Regressions</p>
              <p className="type-display-xxl">
                not <span className="text-outline text-accent">noise</span>
              </p>
            </div>
          </div>
          <div aria-hidden className="col-start-1 row-start-2 flex flex-wrap items-center justify-between gap-x-24 gap-y-8 border-t border-hairline pt-8 type-micro text-ink-muted">
            <p>
              Fig. 01 {"///"} Attempt matrix {"///"} Illustrative
            </p>
            <ul className="flex flex-wrap items-center gap-x-16 gap-y-4">
              {(["pass", "flaky", "fail", "error"] as const).map((status) => (
                <li key={status} className="inline-flex items-center gap-6">
                  <span className={cx("size-10 shrink-0", CELL[status])} />
                  {STATUS[status].label}
                </li>
              ))}
            </ul>
          </div>
          {/* Beside the second line on desktop, with leader lines back to it; below the caption otherwise. */}
          <dl className="col-start-1 row-start-3 mt-24 grid grid-cols-2 gap-16 desktop:row-start-1 desktop:mt-0 desktop:mb-64 desktop:w-[25%] desktop:grid-cols-1 desktop:self-end desktop:justify-self-end">
            {[
              ["XX.X%", "False alarms"],
              ["XX / XX", "Planted flaws caught"],
            ].map(([value, label]) => (
              <div key={label} className="flex items-center gap-12">
                <span aria-hidden className="hidden h-px min-w-24 flex-1 bg-ink-muted desktop:block" />
                <div>
                  <dd className="type-display-md">{value}</dd>
                  <dt className="mt-4 type-micro text-ink-muted">
                    {label} {"///"} placeholder
                  </dt>
                </div>
              </div>
            ))}
          </dl>
        </div>
        <div className="mt-24 flex flex-wrap items-end justify-between gap-24">
          <p className="max-w-420 type-body text-ink-muted">
            AgentProbe runs every case many times and blocks a merge only when the drop is statistically real.
          </p>
          <SampleButton variant="primary">{">>> Get started"}</SampleButton>
        </div>
      </div>
      <dl className="grid-lines border-y border-hairline tablet:grid-cols-3">
        {[
          ["Attempts per case", "XX"],
          ["Test types", "XX"],
          ["Cases in the demo suite", "XX"],
        ].map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-12 px-16 py-12">
            <dt className="type-label text-ink-muted">{label}</dt>
            <dd className="type-data">
              {value} <span className="text-ink-muted">{"///"} placeholder</span>
            </dd>
          </div>
        ))}
      </dl>
      <div className="grid-lines tablet:grid-cols-3">
        {PANELS.map((panel, i) => {
          const lime = i === 2;
          return (
            <a key={panel.title} href="#board-hero" className={cx("relative flex flex-col gap-12 p-16 tablet:p-24", lime ? "bg-accent text-on-accent" : "text-ink hover:bg-surface-1")}>
              <svg aria-hidden viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square" className="absolute top-16 right-16 size-20 tablet:top-24 tablet:right-24">
                <path d="M4 16 16 4M7 4h9v9" />
              </svg>
              <span className={cx("type-micro", !lime && "text-ink-muted")}>0{i + 1}</span>
              <h3 className="max-w-240 pr-32 type-headline">{panel.title}</h3>
              <p className={cx("max-w-320 type-body", !lime && "text-ink-muted")}>{panel.body}</p>
            </a>
          );
        })}
      </div>
    </Board>
  );
}

export default function DesignBoards() {
  const tokens = readTokens();
  return (
    <>
      <div aria-hidden className="noise" />
      <main className="mx-auto flex w-full max-w-1440 flex-col gap-48 px-16 py-32 tablet:px-32 tablet:py-48">
        <header className="flex flex-wrap items-end justify-between gap-16 border-b-2 border-ink pb-16">
          <h1 className="type-display-lg">Design boards</h1>
          <p className="type-micro text-ink-muted">
            AgentProbe® {"///"} Unit D-01 {"///"} REV {REV} {"///"} Placeholder data
          </p>
        </header>
        <TypeBoard typography={tokens.typography} />
        <TokenBoard tokens={tokens} />
        <ShellBoard />
        <RunBoard />
        <HeroBoard />
      </main>
    </>
  );
}
