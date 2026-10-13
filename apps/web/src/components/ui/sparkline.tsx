import { cx } from "@/lib/cx";

const PAD = 3; // keeps the end marker and the stroke inside the viewBox

/** SVG points for a series: x spread evenly, y scaled to the series' own range (a flat series sits mid-height). */
export function sparklinePoints(values: readonly number[], width: number, height: number): [number, number][] {
  const v = values.filter(Number.isFinite);
  const min = Math.min(...v);
  const range = Math.max(...v) - min;
  const innerW = width - 2 * PAD;
  const innerH = height - 2 * PAD;
  return v.map((value, i) => [
    PAD + (v.length === 1 ? innerW / 2 : (i / (v.length - 1)) * innerW),
    PAD + (range === 0 ? innerH / 2 : innerH - ((value - min) / range) * innerH),
  ]);
}

type Props = { values: readonly number[]; width?: number; height?: number; className?: string } & (
  | { label: string; decorative?: never }
  | { label?: never; decorative: true }
);

/**
 * A tiny line of a series, drawn in the current color with a square marker on the last value.
 * Give it a `label` that says what it shows ("Pass rate, last 6 runs: 89%"); the shape alone is not text.
 */
export function Sparkline({ values, width = 96, height = 24, className, label, decorative }: Props) {
  const points = sparklinePoints(values, width, height);
  const last = points.at(-1);
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      fill="none"
      className={cx("inline-block shrink-0 text-ink", className)}
      {...(decorative ? { "aria-hidden": true } : { role: "img", "aria-label": label })}
    >
      {last ? (
        <>
          {points.length > 1 && (
            <polyline
              points={points.map(([x, y]) => `${x},${y}`).join(" ")}
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinejoin="miter"
              strokeLinecap="butt"
              vectorEffect="non-scaling-stroke"
            />
          )}
          <rect x={last[0] - 2} y={last[1] - 2} width={4} height={4} fill="currentColor" />
        </>
      ) : (
        // No data: a dashed baseline, so an empty sparkline is visibly empty and not missing.
        <line x1={PAD} x2={width - PAD} y1={height / 2} y2={height / 2} stroke="currentColor" strokeDasharray="2 3" opacity={0.5} />
      )}
    </svg>
  );
}
