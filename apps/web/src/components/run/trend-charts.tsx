"use client";

import type { ReactNode } from "react";
import { Area, CartesianGrid, ComposedChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BASELINE, chartTheme, CURRENT, SERIES } from "@/components/ui/chart-theme";
import { ms, pct, usd } from "@/lib/format";
import { isEmpty, type TrendPoint } from "@/lib/trends";

// Rules (ADR 0028 §2, the dataviz method): one y-axis per chart, a single series in ink, the
// baseline dashed ink-muted, the CI as a faint band of the series' own ink, accent-blue never.
// The runs table below the charts is their table view: every plotted value is also there.

const shortDate = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const shortTime = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });
const fullDate = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const HEIGHT = 220; // plot plus the x-axis band, so the axis labels are never cropped

type Props = { points: TrendPoint[] };

function Frame({ title, legend, empty, children }: { title: string; legend?: ReactNode; empty?: string | false; children: ReactNode }) {
  return (
    <figure className="min-w-0 rounded-xl bg-surface-1 p-20">
      <figcaption className="mb-12 flex flex-wrap items-baseline justify-between gap-x-15 gap-y-4">
        <span className="font-display text-dash-heading text-ink">{title}</span>
        {legend && !empty && <span className="flex flex-wrap gap-x-12 gap-y-4 text-data-label text-ink-muted">{legend}</span>}
      </figcaption>
      {empty ? (
        <p className="flex items-center justify-center text-body-sm text-ink-muted" style={{ height: HEIGHT }}>
          {empty}
        </p>
      ) : (
        <div style={{ height: HEIGHT }}>{children}</div>
      )}
    </figure>
  );
}

/** A legend key: a 2px line (dashed for a baseline) or a band swatch, then its text in ink-muted. */
function Key({ color, kind = "line", children }: { color: string; kind?: "line" | "dashed" | "band"; children: ReactNode }) {
  const swatch =
    kind === "band" ? (
      <span aria-hidden className="inline-block h-10 w-16 rounded-xs opacity-20" style={{ background: color }} />
    ) : (
      <span aria-hidden className="inline-block w-16 border-t-2" style={{ borderColor: color, borderStyle: kind === "dashed" ? "dashed" : "solid" }} />
    );
  return (
    <span className="inline-flex items-center gap-6">
      {swatch}
      {children}
    </span>
  );
}

const DAY_MS = 86_400_000;

const xAxis = (points: TrendPoint[]) => (
  <XAxis
    dataKey="at"
    {...chartTheme.xAxis}
    // Runs inside one day are told apart by time; a longer history by date.
    tickFormatter={(at: string) => (spanMs(points) < DAY_MS ? shortTime : shortDate).format(new Date(at))}
    padding={{ left: 12, right: 24 }}
    minTickGap={24}
    // One tick per run, even two on the same day: the x-axis is runs in order, not a time scale.
    allowDuplicatedCategory
    interval={points.length > 12 ? "preserveStartEnd" : 0}
  />
);

const spanMs = (points: TrendPoint[]) => (points.length ? Date.parse(points.at(-1)!.at) - Date.parse(points[0].at) : 0);

const tooltipLabel =(at: unknown) => (typeof at === "string" ? fullDate.format(new Date(at)) : "");

export function PassRateChart({ points, baseline }: Props & { baseline: { rate: number; branch: string } | null }) {
  return (
    <Frame
      title="Pass rate"
      empty={isEmpty(points, "pass") && "No completed runs of this suite yet"}
      legend={
        <>
          <Key color={CURRENT}>Pass rate</Key>
          <Key color={CURRENT} kind="band">
            95% CI
          </Key>
          {baseline && (
            <Key color={BASELINE} kind="dashed">
              Baseline ({baseline.branch}) {pct(baseline.rate)}
            </Key>
          )}
        </>
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...chartTheme.grid} />
          {xAxis(points)}
          <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v: number) => pct(v, 0)} {...chartTheme.yAxis} />
          <Tooltip
            {...chartTheme.tooltip}
            labelFormatter={tooltipLabel}
            formatter={(value, name) =>
              Array.isArray(value) ? [`${pct(Number(value[0]))}–${pct(Number(value[1]))}`, name] : [pct(Number(value)), name]
            }
          />
          <Area name="95% CI" dataKey="band" stroke="none" fill={CURRENT} fillOpacity={0.12} isAnimationActive={false} activeDot={false} />
          {baseline && <ReferenceLine y={baseline.rate} stroke={BASELINE} strokeDasharray="4 4" strokeWidth={1.5} ifOverflow="extendDomain" />}
          <Line name="Pass rate" dataKey="pass" stroke={CURRENT} connectNulls {...chartTheme.line} dot={points.length === 1 ? { r: 4 } : false} />
        </ComposedChart>
      </ResponsiveContainer>
    </Frame>
  );
}

export function CostChart({ points }: Props) {
  return (
    <Frame
      title="Cost per run"
      // All zero is "nothing spent" (mock judging), not a trend worth a flat line on a made-up axis.
      empty={
        points.every((p) => !p.cost && !p.judge) && "No cost recorded: the agent reports no price, and mock judging is free"
      }
      legend={
        <>
          <Key color={SERIES[0]}>Agent</Key>
          <Key color={SERIES[1]}>Judging</Key>
        </>
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...chartTheme.grid} />
          {xAxis(points)}
          <YAxis tickFormatter={(v: number) => usd(v)} {...chartTheme.yAxis} width={56} />
          <Tooltip {...chartTheme.tooltip} labelFormatter={tooltipLabel} formatter={(value, name) => [usd(Number(value)), name]} />
          <Line name="Agent" dataKey="cost" stroke={SERIES[0]} connectNulls {...chartTheme.line} dot={points.length === 1 ? { r: 4 } : false} />
          <Line name="Judging" dataKey="judge" stroke={SERIES[1]} connectNulls {...chartTheme.line} dot={points.length === 1 ? { r: 4 } : false} />
        </LineChart>
      </ResponsiveContainer>
    </Frame>
  );
}

export function LatencyChart({ points }: Props) {
  return (
    <Frame title="Mean latency" empty={isEmpty(points, "latency") && "No latency recorded for these runs"}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...chartTheme.grid} />
          {xAxis(points)}
          <YAxis tickFormatter={(v: number) => ms(v)} {...chartTheme.yAxis} width={56} />
          <Tooltip {...chartTheme.tooltip} labelFormatter={tooltipLabel} formatter={(value, name) => [ms(Number(value)), name]} />
          <Line name="Mean latency" dataKey="latency" stroke={CURRENT} connectNulls {...chartTheme.line} dot={points.length === 1 ? { r: 4 } : false} />
        </LineChart>
      </ResponsiveContainer>
    </Frame>
  );
}
