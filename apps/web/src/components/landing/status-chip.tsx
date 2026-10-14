"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { Badge, type Status } from "@/components/ui/status";
import { awakeFetch, wakeNotice } from "@/lib/api/wake";

type State = "checking" | "waking" | "online" | "unreachable";

const CHIP: Record<State, [Status, string]> = {
  checking: ["queued", "API checking"],
  waking: ["running", "API waking"],
  online: ["pass", "API online"],
  unreachable: ["error", "API unreachable"],
};

/**
 * Whether the API answers, asked once per visit. On the free tier it sleeps when idle (ADR 0036),
 * so asking also starts it waking before a visitor opens the demo. The chip keeps one width, so
 * its text changing moves nothing.
 */
export function StatusChip() {
  const [answer, setAnswer] = useState<"online" | "unreachable" | null>(null);
  const waking = useSyncExternalStore(wakeNotice.subscribe, wakeNotice.get, () => false);

  useEffect(() => {
    awakeFetch(new Request(new URL("/api/health", window.location.origin), { cache: "no-store" })).then(
      (r) => setAnswer(r.ok ? "online" : "unreachable"),
      () => setAnswer("unreachable"),
    );
  }, []);

  const [status, text] = CHIP[answer ?? (waking ? "waking" : "checking")];
  return (
    <span role="status">
      <Badge status={status} className="min-w-152">
        {text}
      </Badge>
    </span>
  );
}
