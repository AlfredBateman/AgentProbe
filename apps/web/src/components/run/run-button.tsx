"use client";

import { type ComponentProps, useId, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { type WakeState, wakeStatus } from "@/lib/api/wake";

/** Why a run can't start right now, from what the app's own requests have shown of the API. */
const API_REASON: Partial<Record<WakeState, string>> = {
  waking: "The API is waking up, which takes about 30 to 40 seconds. Run unlocks when it answers.",
  down: "The API isn't answering. Reload the page to try again.",
};

type Props = Omit<ComponentProps<"button">, "disabled" | "children" | "type"> & {
  variant?: "primary" | "secondary";
  /** The button's text; "Run" by default. */
  label?: string;
  /** Another reason the run can't start (nothing to run, say); shown like the API's. */
  blocked?: string | null;
  /** Fill the width of the container (a grid of actions). */
  block?: boolean;
  /** Show the reason as text beside the button. Off in a table row, where it stays screen-reader only. */
  note?: boolean;
};

/**
 * The "Run" button. Disabled, with its reason in words, while the API is asleep (ADR 0036), is
 * unreachable, or the caller says the run can't start. "Checking" stays enabled: the request
 * itself is what finds out, and the API client waits for a sleeping API before sending a
 * mutation, so a click is never lost.
 */
export function RunButton({ variant = "primary", label = "Run", blocked, note = true, block, ...props }: Props) {
  const api = useSyncExternalStore(wakeStatus.subscribe, wakeStatus.get, () => "checking" as const);
  const reasonId = useId();
  const reason = API_REASON[api] ?? blocked ?? null;
  return (
    <span className={block ? "flex w-full flex-col gap-4" : "inline-flex flex-col items-end gap-4"}>
      <Button
        variant={variant}
        className={block ? "w-full" : undefined}
        {...props}
        disabled={reason !== null}
        aria-describedby={reason ? reasonId : undefined}
      >
        {api === "waking" ? "Waking…" : label}
      </Button>
      {/* Always mounted, so a screen reader announces the reason when it appears. */}
      <span id={reasonId} role="status" className={note ? "max-w-280 text-right type-body-sm text-ink-muted" : "sr-only"}>
        {reason}
      </span>
    </span>
  );
}
