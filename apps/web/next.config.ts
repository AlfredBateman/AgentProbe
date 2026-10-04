import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

export default function config(phase: string): NextConfig {
  return {
    // `next dev` would otherwise write AGENTS.md/CLAUDE.md agent-instruction files here.
    agentRules: false,
    // Docker only (apps/web/Dockerfile sets NEXT_OUTPUT): a self-contained server for a small
    // image. Off elsewhere: standalone copies node_modules as symlinks, which Windows restricts.
    output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
    // `*.dev.tsx` pages (the /dev/components showcase) exist only under `next dev`, so a
    // production build never contains them.
    pageExtensions: phase === PHASE_DEVELOPMENT_SERVER ? ["dev.tsx", "tsx", "ts"] : ["tsx", "ts"],
    // /api/* is forwarded to the API by src/proxy.ts (ADR 0035), not a rewrite here.
    // Security headers for every page and asset; the API sets its own on /api/*. The CSP
    // carries a per-request nonce, so src/proxy.ts sets it.
    async headers() {
      return [
        {
          source: "/((?!api/).*)",
          headers: [
            { key: "X-Content-Type-Options", value: "nosniff" },
            { key: "X-Frame-Options", value: "DENY" },
            // Same-origin only: a share link's token is in its path.
            { key: "Referrer-Policy", value: "same-origin" },
            { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
            { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
          ],
        },
      ];
    },
  };
}
