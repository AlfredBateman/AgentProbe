// @vitest-environment node
import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { GRADIENT_STOPS } from "@/components/ui/gradient-card";
import { contrast } from "@/lib/contrast";
import { generate, OUTPUT, readTokens } from "../../scripts/gen-theme.mjs";

const { colors } = readTokens() as { colors: Record<string, string> };
const surfaces = ["canvas", "surface-1", "surface-2"];

test("theme.css is up to date with DESIGN.md (run `pnpm --filter web gen:theme`)", () => {
  expect(readFileSync(OUTPUT, "utf8").replace(/\r\n/g, "\n")).toBe(generate());
});

// WCAG AA body text on every surface (ADR 0028 records the measured ratios).
const text = ["ink", "ink-muted", "accent-blue", "semantic-success", "semantic-danger", "semantic-warning", "semantic-neutral"];
test.each(text.flatMap((t) => surfaces.map((s) => [t, s])))("%s on %s is at least 4.5:1", (fg, bg) => {
  expect(contrast(colors[fg], colors[bg])).toBeGreaterThanOrEqual(4.5);
});

// Non-text marks: WCAG 1.4.11 asks 3:1 against the surface they sit on.
test.each(["chart-1", "chart-2", "chart-3", "chart-4"].flatMap((c) => surfaces.map((s) => [c, s])))(
  "%s on %s is at least 3:1",
  (fg, bg) => {
    expect(contrast(colors[fg], colors[bg])).toBeGreaterThanOrEqual(3);
  },
);

test.each(GRADIENT_STOPS)("white text on gradient stop %s is at least 4.5:1", (stop) => {
  expect(contrast(colors.ink, stop)).toBeGreaterThanOrEqual(4.5);
});
