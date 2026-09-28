"use client";

import { useEffect, useRef, useState } from "react";

/** The run fields every SSE event carries (apps/api runstore.run_event). */
export type Progress = { status: string; done: number; total: number; pass_rate: number | null; error: string | null };
/** One saved attempt, as `GET /runs/{id}/stream` announces it (apps/api queue.record_attempt). */
export type StreamAttempt = {
  case: string;
  attempt: number;
  status: "passed" | "failed" | "error";
  result_id: string;
  latency_ms: number | null;
  cost_usd: number | null;
  score: number | null;
  done: number;
  total: number;
};
export type Connection = "connecting" | "live" | "reconnecting" | "polling" | "closed";

export const TERMINAL = new Set(["completed", "failed", "cancelled"]);

type Options = {
  /** Identifies the stream: a new key reconnects. */
  runId: string;
  /** The URL to open, resolved again for every connection (a stream token is short-lived). */
  resolveUrl: () => Promise<string>;
  /** Connect at all: false for a run that has already ended. */
  enabled: boolean;
  /**
   * Refetches the authoritative state (the run and its saved attempts) and returns the run's
   * status, or null if the fetch failed. It runs after every (re)connect, on every poll and
   * when the run ends, so it must merge attempts into what the stream already delivered,
   * never replace them: an attempt announced during the fetch would otherwise vanish.
   */
  resync: () => Promise<string | null>;
  onProgress: (progress: Progress) => void;
  onAttempt: (attempt: StreamAttempt) => void;
  createSource?: (url: string) => EventSource;
  pollMs?: number;
  /** Consecutive failed connections before falling back to polling. */
  maxFailures?: number;
  /** No snapshot this long after connecting: the stream is buffered or dead. */
  firstEventMs?: number;
  /** No event this long on a live stream: reconnect (costs one snapshot and one resync). */
  idleMs?: number;
};

/**
 * Follows a run's SSE stream. EventSource's own reconnect is not used: every error closes the
 * source, resyncs through the API client (which also refreshes an expired session, which
 * EventSource can't) and reconnects with backoff. After `maxFailures` connections in a row
 * that never delivered a snapshot, it polls `resync` instead until the run ends.
 */
export function useRunStream(options: Options): Connection {
  const ref = useRef(options);
  useEffect(() => {
    ref.current = options;
  });
  const { runId, enabled } = options;
  const [connection, setConnection] = useState<Connection>("connecting");

  useEffect(() => {
    if (!enabled) return;
    const {
      createSource = (u: string) => new EventSource(u),
      pollMs = 3000,
      maxFailures = 3,
      firstEventMs = 10_000,
      idleMs = 45_000,
    } = ref.current;
    let source: EventSource | null = null;
    let stopped = false;
    let failures = 0;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let watchdog: ReturnType<typeof setTimeout> | undefined;
    let pollTimer: ReturnType<typeof setInterval> | undefined;

    function teardown() {
      stopped = true;
      source?.close();
      clearTimeout(retryTimer);
      clearTimeout(watchdog);
      clearInterval(pollTimer);
    }

    /** Stops for good once the run has ended; true if it has. */
    function ended(status: string | null): boolean {
      if (status === null || !TERMINAL.has(status)) return false;
      teardown();
      setConnection("closed");
      return true;
    }

    async function resync(): Promise<boolean> {
      return ended(await ref.current.resync());
    }

    function arm(ms: number) {
      clearTimeout(watchdog);
      watchdog = setTimeout(() => void fail(), ms);
    }

    async function fail() {
      source?.close();
      source = null;
      clearTimeout(watchdog);
      if (stopped) return;
      failures += 1;
      const polling = failures >= maxFailures;
      setConnection(polling ? "polling" : "reconnecting");
      if ((await resync()) || stopped) return;
      if (polling) {
        pollTimer = setInterval(() => void resync(), pollMs);
      } else {
        retryTimer = setTimeout(() => void connect(), Math.min(1000 * 2 ** (failures - 1), 8000));
      }
    }

    async function connect() {
      if (stopped) return;
      let url: string;
      try {
        url = await ref.current.resolveUrl();
      } catch {
        return void fail();
      }
      if (stopped) return;
      const es = createSource(url);
      source = es;
      arm(firstEventMs);
      es.addEventListener("snapshot", (event) => {
        failures = 0;
        arm(idleMs);
        setConnection("live");
        const progress = JSON.parse((event as MessageEvent<string>).data) as Progress;
        ref.current.onProgress(progress);
        void resync(); // attempts saved before (or between) connections aren't replayed
      });
      es.addEventListener("attempt", (event) => {
        arm(idleMs);
        const attempt = JSON.parse((event as MessageEvent<string>).data) as StreamAttempt;
        ref.current.onAttempt(attempt);
      });
      es.addEventListener("status", (event) => {
        arm(idleMs);
        const progress = JSON.parse((event as MessageEvent<string>).data) as Progress;
        ref.current.onProgress(progress);
        if (TERMINAL.has(progress.status)) {
          teardown();
          setConnection("closed");
          void ref.current.resync(); // the final results, labels and totals
        }
      });
      es.onerror = () => {
        if (source === es) void fail();
      };
    }

    void connect();
    return teardown;
  }, [runId, enabled]);

  return enabled ? connection : "closed";
}
