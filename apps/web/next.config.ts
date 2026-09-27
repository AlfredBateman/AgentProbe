import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

export default function config(phase: string): NextConfig {
  return {
    // `next dev` would otherwise write AGENTS.md/CLAUDE.md here; agent instructions live in the root CLAUDE.md.
    agentRules: false,
    // `*.dev.tsx` pages (the /dev/components showcase) exist only under `next dev`, so a
    // production build never contains them.
    pageExtensions: phase === PHASE_DEVELOPMENT_SERVER ? ["dev.tsx", "tsx", "ts"] : ["tsx", "ts"],
    // Same-origin API (ADR 0009): the browser only ever talks to /api, so the session cookies
    // are first-party and no CORS is needed.
    async rewrites() {
      return [{ source: "/api/:path*", destination: `${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/:path*` }];
    },
  };
}
