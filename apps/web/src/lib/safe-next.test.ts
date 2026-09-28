import { expect, test } from "vitest";
import { safeNext } from "./safe-next";

test("a same-origin relative path is kept", () => {
  expect(safeNext("/projects/p1/runs?status=fail")).toBe("/projects/p1/runs?status=fail");
});

// null/empty, no leading slash, absolute URLs, protocol-relative, and backslashes (some
// browsers/proxies normalize "\" to "/", so "/\evil.com" can behave like "//evil.com").
test.each([
  null,
  "",
  "evil.com",
  "http://evil.com",
  "https://evil.com/x",
  "//evil.com",
  "///evil.com",
  "/\\evil.com",
  "\\\\evil.com",
  "/ok/\\../evil",
])("%s falls back to the default", (input: string | null) => {
  expect(safeNext(input)).toBe("/projects");
});

test("a custom fallback is used when the input is unsafe", () => {
  expect(safeNext("//evil.com", "/login")).toBe("/login");
});
