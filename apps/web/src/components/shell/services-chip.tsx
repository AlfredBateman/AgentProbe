"use client";

import { useEffect, useSyncExternalStore } from "react";
import { Badge, type Status } from "@/components/ui/status";
import { awakeFetch, type WakeState, wakeStatus } from "@/lib/api/wake";

const CHIP: Record<WakeState, [Status, string]> = {
  checking: ["queued", "Checking"],
  waking: ["running", "Waking"],
  awake: ["pass", "Awake"],
  down: ["error", "Unreachable"],
};

/**
 * "Services awake?": the API, as the app's own requests have found it (lib/api/wake.ts). It
 * sends nothing of its own. The free tier sleeps when idle (ADR 0036); the demo agents' host is
 * pinged awake in the background, but an opaque ping cannot tell a 200 from a 502, so only the
 * API is reported. The chip keeps one width, so its text changing moves nothing.
 *
 * `probe`: for a page that makes no API call of its own (register, the error pages), where the
 * chip would otherwise say "Checking" for good. It asks once, through the same `awakeFetch` the
 * landing page's chip uses, which also starts a sleeping API waking.
 */
export function ServicesChip({ className, probe = false }: { className?: string; probe?: boolean }) {
  const state = useSyncExternalStore(wakeStatus.subscribe, wakeStatus.get, () => "checking" as const);
  useEffect(() => {
    if (!probe || wakeStatus.get() !== "checking") return;
    // The answer reaches the chip through the store; a failure shows as "Unreachable" there.
    awakeFetch(new Request(new URL("/api/health", window.location.origin), { cache: "no-store" })).catch(() => {});
  }, [probe]);
  const [status, text] = CHIP[state];
  return (
    <span
      role="status"
      className={className}
      title="API status, from the app's own requests. The demo agents' host is woken in the background."
    >
      <span className="mr-8 type-micro text-ink-muted">API</span>
      <Badge status={status} className="min-w-128 justify-start">
        {text}
      </Badge>
    </span>
  );
}
