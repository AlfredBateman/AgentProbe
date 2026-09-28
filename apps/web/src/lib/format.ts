// Display formatting for run data. Unknown values (null) render as an em dash, never as 0.
const DASH = "—";

export const pct = (x: number | null | undefined, digits = 1) => (x == null ? DASH : `${(x * 100).toFixed(digits)}%`);

export function usd(x: number | null | undefined): string {
  if (x == null) return DASH;
  if (x === 0) return "$0";
  return x < 0.01 ? `$${x.toFixed(4)}` : `$${x.toFixed(2)}`;
}

export function ms(x: number | null | undefined): string {
  if (x == null) return DASH;
  return x < 1000 ? `${Math.round(x)} ms` : `${(x / 1000).toFixed(x < 10_000 ? 2 : 1)} s`;
}

export const count = (x: number | null | undefined) => (x == null ? DASH : x.toLocaleString());

export const score = (x: number | null | undefined) => (x == null ? DASH : x.toFixed(2));

/** A wall-clock duration, e.g. "42s", "3m 05s", "1h 02m". */
export function duration(totalMs: number): string {
  const s = Math.max(0, Math.round(totalMs / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
export const date = (iso: string | null | undefined) => (iso ? dateFormat.format(new Date(iso)) : DASH);
