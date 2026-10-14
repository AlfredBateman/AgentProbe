import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "vitest";
import { LICENSE } from "./site";

const root = path.resolve(process.cwd(), "../..");
const read = (file: string) => readFileSync(path.join(root, file), "utf8");

test("the footer's license is the one package.json names, and the LICENSE file is that license", () => {
  expect(LICENSE).toBe("MIT");
  expect(JSON.parse(read("package.json")).license).toBe(LICENSE);
  const text = read("LICENSE");
  expect(text).toMatch(/^MIT License\r?\n/);
  expect(text).toMatch(/^Copyright \(c\) \d{4} \S+/m);
});

test("every published Python package declares the same license", () => {
  for (const pkg of ["packages/core", "packages/cli", "apps/api"]) {
    expect(read(`${pkg}/pyproject.toml`), pkg).toMatch(new RegExp(`^license = "${LICENSE}"\r?$`, "m"));
  }
});
