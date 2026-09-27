// @vitest-environment node
import { NextRequest } from "next/server";
import { expect, test } from "vitest";
import { proxy } from "./proxy";

const visit = (path: string, cookie?: string) =>
  proxy(new NextRequest(`http://localhost:3000${path}`, { headers: cookie ? { cookie } : {} }));

test.each(["/", "/login", "/register", "/shared/abc", "/dev/components"])("%s is public", (path) => {
  expect(visit(path).headers.get("location")).toBeNull();
});

test("a protected page without a session redirects to login, keeping where it was going", () => {
  const location = visit("/projects/p1/runs?status=fail").headers.get("location")!;
  const url = new URL(location);
  expect(url.pathname).toBe("/login");
  expect(url.searchParams.get("next")).toBe("/projects/p1/runs?status=fail");
});

test.each(["access_token=x", "refresh_token=y"])("either session cookie (%s) lets the page load", (cookie) => {
  expect(visit("/projects/p1", cookie).headers.get("location")).toBeNull();
});

test("a lookalike path is not public", () => {
  expect(visit("/login-help").headers.get("location")).toContain("/login?next=");
});
