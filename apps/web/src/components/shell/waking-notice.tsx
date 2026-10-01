"use client";

import { useSyncExternalStore } from "react";
import { wakeNotice } from "@/lib/api/wake";

/** Shown while a sleeping API wakes (ADR 0036): a wait, not an error. */
export function WakingNotice() {
  const show = useSyncExternalStore(wakeNotice.subscribe, wakeNotice.get, () => false);
  return (
    // Always mounted, so screen readers announce the notice when it appears.
    <div role="status" aria-live="polite" className="pointer-events-none fixed right-16 bottom-16 left-16 z-50 tablet:right-auto">
      {show && (
        <div className="flex w-full items-start gap-12 rounded-lg bg-surface-2 px-15 py-12 text-body-sm shadow-float tablet:max-w-360">
          <span aria-hidden className="mt-6 size-8 shrink-0 animate-pulse rounded-full bg-ink-muted motion-reduce:animate-none" />
          <span>
            <span className="block text-ink">Waking the server, about a minute</span>
            <span className="block text-ink-muted">The free hosting tier sleeps when idle. Your request goes through once it&rsquo;s up.</span>
          </span>
        </div>
      )}
    </div>
  );
}
