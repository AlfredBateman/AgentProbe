// @vitest-environment node
import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { contrast } from "@/lib/contrast";
import { generate, OUTPUT, readTokens } from "../../scripts/gen-theme.mjs";

const { colors, aliases } = readTokens() as { colors: Record<string, string>; aliases: { colors: Record<string, string> } };
const hex = (name: string) => colors[aliases.colors[name] ?? name];
const surfaces = ["canvas", "surface-1", "surface-2"];
const onSurfaces = (names: string[]) => names.flatMap((n) => surfaces.map((s) => [n, s]));

test("theme.css is up to date with DESIGN.md (run `pnpm --filter web gen:theme`)", () => {
  expect(readFileSync(OUTPUT, "utf8").replace(/\r\n/g, "\n")).toBe(generate());
});

// WCAG AA body text on every surface (ADR 0042 records the measured ratios).
test.each(onSurfaces(["ink", "ink-muted", "accent", "fail", "pass", "flaky", "neutral"]))("%s on %s is at least 4.5:1", (fg, bg) => {
  expect(contrast(hex(fg), hex(bg))).toBeGreaterThanOrEqual(4.5);
});

test.each([
  ["on-accent", "accent"],
  ["on-fail", "fail"],
])("%s on a %s fill is at least 4.5:1", (fg, bg) => {
  expect(contrast(hex(fg), hex(bg))).toBeGreaterThanOrEqual(4.5);
});

// Non-text marks and control borders: WCAG 1.4.11 asks 3:1 against the surface they sit on.
test.each(onSurfaces(["hairline-strong", "chart-1", "chart-2", "chart-3", "chart-4"]))("%s on %s is at least 3:1", (fg, bg) => {
  expect(contrast(hex(fg), hex(bg))).toBeGreaterThanOrEqual(3);
});
