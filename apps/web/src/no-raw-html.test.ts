// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";

// Agent output, attack payloads and tool results are untrusted: nothing in the app
// may inject HTML, and nothing may turn text into markup.
test("no source file injects raw HTML", () => {
  const root = path.dirname(fileURLToPath(import.meta.url));
  const files = readdirSync(root, { recursive: true, encoding: "utf8" }).filter(
    (f) => /\.(ts|tsx)$/.test(f) && !/\.test\.tsx?$/.test(f),
  );
  expect(files.length).toBeGreaterThan(20);
  const offenders = files.filter((f) =>
    /dangerouslySetInnerHTML|\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML|from ["'](react-markdown|marked|markdown-it)["']/.test(
      readFileSync(path.join(root, f), "utf8"),
    ),
  );
  expect(offenders).toEqual([]);
});
