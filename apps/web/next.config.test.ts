// @vitest-environment node
import { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD } from "next/constants";
import { afterEach, expect, test, vi } from "vitest";
import config from "./next.config";

afterEach(() => vi.unstubAllEnvs());

test("dev-only pages exist under next dev and never in a production build", () => {
  expect(config(PHASE_DEVELOPMENT_SERVER).pageExtensions).toContain("dev.tsx");
  expect(config(PHASE_PRODUCTION_BUILD).pageExtensions).not.toContain("dev.tsx");
});

test("/api is rewritten to the API, from API_INTERNAL_URL when set", async () => {
  const rewrites = () => config(PHASE_PRODUCTION_BUILD).rewrites!() as Promise<unknown>;
  expect(await rewrites()).toEqual([{ source: "/api/:path*", destination: "http://localhost:8000/:path*" }]);
  vi.stubEnv("API_INTERNAL_URL", "https://api.example.test");
  expect(await rewrites()).toEqual([{ source: "/api/:path*", destination: "https://api.example.test/:path*" }]);
});
