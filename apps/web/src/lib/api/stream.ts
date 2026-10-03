import { api } from "./client";
import { PUBLIC_API_URL } from "./public-url";

// Next's /api rewrite gzips responses, and a gzipped event stream is held until it ends: every
// event arrived at once, when the run finished (measured, ADR 0031). So the browser opens a
// run's stream on the API itself, with a 60 s stream token minted through the rewrite (ADR 0009
// §5). Without a public API URL it falls back to the rewrite, where the stream hook's watchdog
// soon switches to polling.

/** A fresh URL for each connection: a token is only good for 60 s. */
export async function streamUrl(runId: string, apiUrl = PUBLIC_API_URL): Promise<string> {
  if (!apiUrl) return `/api/runs/${runId}/stream`;
  const { data } = await api.POST("/runs/{run_id}/stream-token", { params: { path: { run_id: runId } } });
  if (!data) throw new Error("couldn't get a stream token");
  return `${apiUrl.replace(/\/+$/, "")}/runs/${encodeURIComponent(runId)}/stream?token=${encodeURIComponent(data.token)}`;
}
