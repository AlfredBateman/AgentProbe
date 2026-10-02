// @vitest-environment node
import { NextRequest } from "next/server";
import { expect, test, vi } from "vitest";
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

const callApi = (path: string, headers: Record<string, string> = {}) =>
  proxy(new NextRequest(`http://localhost:3000${path}`, { headers: { "x-real-ip": "203.0.113.5", ...headers } }));
const forwarded = (response: Response, name: string) => response.headers.get(`x-middleware-request-${name}`);

test("/api/* goes to the local API when API_INTERNAL_URL is unset", () => {
  vi.stubEnv("API_INTERNAL_URL", undefined);
  expect(callApi("/api/health").headers.get("x-middleware-rewrite")).toBe("http://localhost:8000/health");
  vi.unstubAllEnvs();
});

test("/api/* is forwarded to API_INTERNAL_URL, path and query kept, /api stripped", () => {
  vi.stubEnv("API_INTERNAL_URL", "https://api.example");
  const response = callApi("/api/runs/r1/export?format=html");
  expect(response.headers.get("x-middleware-rewrite")).toBe("https://api.example/runs/r1/export?format=html");
  vi.unstubAllEnvs();
});

test("with PROXY_SECRET, the API gets the secret and the client IP from x-real-ip, never from X-Forwarded-For", () => {
  vi.stubEnv("PROXY_SECRET", "s".repeat(40));
  // A browser's own X-Forwarded-For and client-IP header: in production the former sometimes
  // reached the API leftmost (ADR 0036).
  const response = callApi("/api/auth/login", {
    "x-agentprobe-proxy-secret": "forged",
    "x-agentprobe-client-ip": "198.51.100.1",
    "x-forwarded-for": "198.51.100.2, 203.0.113.5",
  });
  expect(forwarded(response, "x-agentprobe-proxy-secret")).toBe("s".repeat(40));
  expect(forwarded(response, "x-agentprobe-client-ip")).toBe("203.0.113.5");
  vi.unstubAllEnvs();
});

test("with PROXY_SECRET and no x-real-ip, a browser's client-IP header still never reaches the API", () => {
  vi.stubEnv("PROXY_SECRET", "s".repeat(40));
  const response = proxy(
    new NextRequest("http://localhost:3000/api/auth/login", {
      headers: { "x-agentprobe-client-ip": "198.51.100.1", "x-forwarded-for": "198.51.100.2" },
    }),
  );
  expect(forwarded(response, "x-agentprobe-proxy-secret")).toBe("s".repeat(40));
  // The middleware lists every header it overrides; a deleted one is absent from the list.
  expect(response.headers.get("x-middleware-override-headers")?.split(",")).not.toContain("x-agentprobe-client-ip");
  vi.unstubAllEnvs();
});

test("without PROXY_SECRET, a browser's forged secret and client IP never reach the API", () => {
  vi.stubEnv("PROXY_SECRET", "");
  const response = callApi("/api/auth/login", { "x-agentprobe-proxy-secret": "forged", "x-agentprobe-client-ip": "198.51.100.1" });
  expect(forwarded(response, "x-agentprobe-proxy-secret")).toBeNull();
  expect(forwarded(response, "x-agentprobe-client-ip")).toBeNull();
  expect(forwarded(response, "host")).toBeNull();
  vi.unstubAllEnvs();
});
