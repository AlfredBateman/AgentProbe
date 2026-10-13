// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";

// DESIGN.md hard rules: no radius and no colour fade, on anything. globals.css zeroes every
// radius at runtime; this test keeps the source from asking for one in the first place.
const root = path.dirname(fileURLToPath(import.meta.url));
const files = readdirSync(root, { recursive: true, encoding: "utf8" })
  .filter((f) => /\.(ts|tsx|css)$/.test(f) && !/\.test\.tsx?$/.test(f))
  .map((f) => ({ file: f, text: readFileSync(path.join(root, f), "utf8") }));

const offenders = (pattern: RegExp) => files.filter(({ text }) => pattern.test(text)).map(({ file }) => file);

test("the source set is the whole app", () => {
  expect(files.length).toBeGreaterThan(40);
});

test("no radius utility, radius property or rounded SVG shape", () => {
  // `rounded` and every `rounded-*` (with any variant prefix) except `rounded-none`.
  expect(offenders(/(?<![\w-])rounded(?!-none(?![\w-]))(?![\w])/)).toEqual([]);
  expect(offenders(/borderRadius/)).toEqual([]);
  expect(offenders(/<circle|<ellipse|\brx=|\bry=|stroke-?[Ll]ine(?:cap|join)[=:]\s*["']?round/)).toEqual([]);
});

test("the one border-radius declaration is the global reset to 0", () => {
  const declarations = files.flatMap(({ text }) => [...text.matchAll(/border-radius\s*:\s*([^;]*);/g)].map((m) => m[1].trim()));
  expect(declarations).toEqual(["0 !important"]);
  expect(offenders(/border-radius(?!\s*:\s*0 !important)/)).toEqual([]);
});

test("no gradient anywhere in the source (hard-stop patterns are SVG tiles and masks)", () => {
  // The legacy component name is the only mention: `GradientCard` is a flat panel (ADR 0042 §5).
  const legacy = /GradientCard|gradient-card/g;
  expect(files.filter(({ text }) => /gradient/i.test(text.replace(legacy, ""))).map(({ file }) => file)).toEqual([]);
  expect(offenders(/(?<![\w-])bg-(?:linear|radial|conic)-/)).toEqual([]);
});
