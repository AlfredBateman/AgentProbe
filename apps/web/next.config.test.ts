// @vitest-environment node
import { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD } from "next/constants";
import { afterEach, expect, test, vi } from "vitest";
import config from "./next.config";

afterEach(() => vi.unstubAllEnvs());

test("dev-only pages exist under next dev and never in a production build", () => {
  expect(config(PHASE_DEVELOPMENT_SERVER).pageExtensions).toContain("dev.tsx");
  expect(config(PHASE_PRODUCTION_BUILD).pageExtensions).not.toContain("dev.tsx");
});

test("/api has no rewrite here: src/proxy.ts forwards it, with the proxy secret (ADR 0035)", () => {
  expect(config(PHASE_PRODUCTION_BUILD).rewrites).toBeUndefined();
});
