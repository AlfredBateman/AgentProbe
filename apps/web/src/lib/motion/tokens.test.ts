// @vitest-environment node
import { expect, test } from "vitest";
import { readTokens } from "../../../scripts/gen-theme.mjs";
import { DURATION, EASE, MECH_BEZIER } from "./core";

const { motion } = readTokens() as { motion: { duration: Record<string, string>; easing: Record<string, string> } };

test("durations equal DESIGN.md's, in seconds", () => {
  expect(Object.keys(DURATION).sort()).toEqual(Object.keys(motion.duration).sort());
  for (const [name, ms] of Object.entries(motion.duration)) expect(DURATION[name as keyof typeof DURATION] * 1000, name).toBeCloseTo(parseFloat(ms));
});

test("easings equal DESIGN.md's", () => {
  expect(Object.keys(EASE).sort()).toEqual(Object.keys(motion.easing).sort());
  expect(motion.easing.mech.match(/-?[\d.]+/g)?.join(",")).toBe(MECH_BEZIER);
  expect(motion.easing.step).toMatch(/^steps\(6\b/);
  expect(EASE.step).toBe("steps(6)");
  expect(motion.easing.linear).toBe("linear");
});
