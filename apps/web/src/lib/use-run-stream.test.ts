import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { type Progress, type StreamAttempt, useRunStream } from "./use-run-stream";

/** A scriptable EventSource: the test pushes events and errors into it. */
class FakeSource {
  static all: FakeSource[] = [];
  listeners = new Map<string, ((event: MessageEvent<string>) => void)[]>();
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeSource.all.push(this);
  }
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  close() {
    this.closed = true;
  }
  emit(type: string, data: object) {
    for (const listener of this.listeners.get(type) ?? []) listener(new MessageEvent(type, { data: JSON.stringify(data) }));
  }
  fail() {
    this.onerror?.();
  }
}

const running: Progress = { status: "running", done: 0, total: 4, pass_rate: null, error: null };
const attempt = (n: number): StreamAttempt => ({
  case: "greeting",
  attempt: n,
  status: "passed",
  result_id: `r${n}`,
  latency_ms: 5,
  cost_usd: null,
  score: 1,
  done: n + 1,
  total: 4,
});

function setup({ enabled = true, statuses = ["running"] as (string | null)[], resolveUrl = async () => "https://api.test/runs/r1/stream?token=t" } = {}) {
  const calls = { progress: [] as Progress[], attempts: [] as StreamAttempt[], resyncs: 0 };
  const resync = vi.fn(async () => {
    calls.resyncs += 1;
    return statuses[Math.min(calls.resyncs, statuses.length) - 1];
  });
  const hook = renderHook(() =>
    useRunStream({
      runId: "r1",
      resolveUrl,
      enabled,
      resync,
      onProgress: (p) => calls.progress.push(p),
      onAttempt: (a) => calls.attempts.push(a),
      createSource: (url) => new FakeSource(url) as unknown as EventSource,
      pollMs: 3000,
      maxFailures: 3,
      firstEventMs: 10_000,
      idleMs: 45_000,
    }),
  );
  return { hook, calls, resync };
}

const tick = (ms = 0) => act(() => vi.advanceTimersByTimeAsync(ms));
const latest = () => FakeSource.all.at(-1)!;

beforeEach(() => {
  vi.useFakeTimers();
  FakeSource.all = [];
});
afterEach(() => vi.useRealTimers());

test("a live stream: snapshot, attempts, then the final status closes it", async () => {
  const { hook, calls } = setup();
  await tick();
  expect(hook.result.current).toBe("connecting");
  await tick();
  expect(latest().url).toBe("https://api.test/runs/r1/stream?token=t");

  await act(async () => latest().emit("snapshot", { type: "snapshot", ...running }));
  expect(hook.result.current).toBe("live");
  expect(calls.progress).toEqual([{ type: "snapshot", ...running }]);
  expect(calls.resyncs).toBe(1); // picks up attempts saved before the page connected

  await act(async () => {
    latest().emit("attempt", attempt(0));
    latest().emit("attempt", attempt(1));
  });
  expect(calls.attempts.map((a) => a.result_id)).toEqual(["r0", "r1"]);

  await act(async () => latest().emit("status", { type: "status", ...running, status: "completed", done: 4 }));
  expect(hook.result.current).toBe("closed");
  expect(latest().closed).toBe(true);
  expect(calls.resyncs).toBe(2); // the final results, labels and totals
  await tick(60_000);
  expect(FakeSource.all).toHaveLength(1); // never reconnects after the end
});

test("a dropped stream resyncs, reconnects with backoff and resyncs again", async () => {
  const { hook, calls } = setup();
  await tick();
  await act(async () => latest().emit("snapshot", running));
  const first = latest();

  await act(async () => first.fail());
  expect(first.closed).toBe(true);
  expect(hook.result.current).toBe("reconnecting");
  expect(calls.resyncs).toBe(2); // fills in whatever happened while disconnected

  await tick(999);
  expect(FakeSource.all).toHaveLength(1);
  await tick(1);
  expect(FakeSource.all).toHaveLength(2);

  await act(async () => latest().emit("snapshot", { ...running, done: 3 }));
  expect(hook.result.current).toBe("live");
  expect(calls.resyncs).toBe(3);
  expect(calls.progress.at(-1)?.done).toBe(3);
});

test("a buffering proxy (no snapshot) falls back to polling until the run ends", async () => {
  const { hook, calls } = setup({ statuses: ["running", "running", "running", "running", "completed"] });
  await tick();

  await tick(10_000); // first connection: no snapshot
  expect(hook.result.current).toBe("reconnecting");
  await tick(1000);
  await tick(10_000); // second
  await tick(2000);
  await tick(10_000); // third: give up on the stream
  expect(FakeSource.all).toHaveLength(3);
  expect(FakeSource.all.every((s) => s.closed)).toBe(true);
  expect(hook.result.current).toBe("polling");
  expect(calls.resyncs).toBe(3);

  await tick(3000);
  expect(calls.resyncs).toBe(4);
  await tick(3000);
  expect(calls.resyncs).toBe(5); // "completed"
  expect(hook.result.current).toBe("closed");
  await tick(30_000);
  expect(calls.resyncs).toBe(5);
  expect(FakeSource.all).toHaveLength(3);
});

test("a silent live stream is reconnected by the idle watchdog", async () => {
  setup();
  await tick();
  await act(async () => latest().emit("snapshot", running));
  await tick(44_999);
  expect(FakeSource.all).toHaveLength(1);
  await tick(1);
  expect(FakeSource.all[0].closed).toBe(true);
  await tick(1000);
  expect(FakeSource.all).toHaveLength(2);
});

test("a run that ended while the page connected closes on its snapshot", async () => {
  const { hook, calls } = setup({ statuses: ["completed"] });
  await tick();
  await act(async () => latest().emit("snapshot", { ...running, status: "completed", done: 4 }));
  expect(hook.result.current).toBe("closed");
  expect(latest().closed).toBe(true);
  expect(calls.resyncs).toBe(1);
});

test("an ended run never connects, and unmounting closes the stream", async () => {
  const { hook } = setup({ enabled: false });
  expect(hook.result.current).toBe("closed");
  expect(FakeSource.all).toHaveLength(0);

  const live = setup();
  await tick();
  live.hook.unmount();
  expect(latest().closed).toBe(true);
  await tick(60_000);
  expect(FakeSource.all).toHaveLength(1);
});

test("each connection resolves a fresh URL, and a failed resolve counts as a failed connection", async () => {
  let n = 0;
  const resolveUrl = async () => {
    n += 1;
    if (n === 1) throw new Error("no token");
    return `https://api.test/stream?token=t${n}`;
  };
  const { hook, calls } = setup({ resolveUrl });
  await tick();
  expect(FakeSource.all).toHaveLength(0);
  expect(hook.result.current).toBe("reconnecting");
  expect(calls.resyncs).toBe(1);
  await tick(1000);
  expect(latest().url).toBe("https://api.test/stream?token=t2");
  await act(async () => latest().fail());
  await tick(2000);
  expect(latest().url).toBe("https://api.test/stream?token=t3");
});
