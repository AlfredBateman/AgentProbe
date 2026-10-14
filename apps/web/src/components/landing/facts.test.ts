// @vitest-environment node
import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { generate, OUTPUT } from "../../../scripts/gen-landing-facts.mjs";

test("facts.json is up to date with docs/metrics.md and README.md (run `pnpm --filter web gen:facts`)", () => {
  expect(readFileSync(OUTPUT, "utf8").replace(/\r\n/g, "\n")).toBe(generate());
});

test("a figure missing from its document stops the generator instead of leaving a blank", () => {
  expect(() => generate("# Measured metrics\n", "# AgentProbe\n")).toThrow(/not found/);
});

test("no fact is empty", () => {
  const values = Object.values(JSON.parse(generate()) as Record<string, string | Record<string, string>>).flatMap((v) => (typeof v === "string" ? [v] : Object.values(v)));
  expect(values.length).toBeGreaterThan(15);
  for (const value of values) expect(value).toMatch(/\S/);
});
