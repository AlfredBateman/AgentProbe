import http from "node:http";
import type { AddressInfo } from "node:net";

/**
 * A pass-through proxy in front of a demo agent that can hold its calls, so a spec can keep a
 * run live for as long as it needs to watch it. Without it the run races the page: on CI (local
 * Postgres, mock agent) a 20-attempt run finishes in about 0.3 s, before the run page's first
 * fetch, and the page then (correctly) never opens a stream.
 *
 * Held calls are released in arrival order. Keep a hold well under the adapter's 30 s attempt
 * timeout, or the attempt errors as unreachable.
 */
export async function gatedAgent(target: string) {
  const held: (() => void)[] = [];
  let open = true;
  const server = http.createServer(async (req, res) => {
    const chunks: Buffer[] = [];
    for await (const chunk of req) chunks.push(chunk as Buffer);
    if (!open) await new Promise<void>((release) => held.push(release));
    try {
      const upstream = await fetch(target, {
        method: "POST",
        headers: { "content-type": req.headers["content-type"] ?? "application/json" },
        body: Buffer.concat(chunks),
      });
      res.writeHead(upstream.status, { "content-type": upstream.headers.get("content-type") ?? "application/json" });
      res.end(Buffer.from(await upstream.arrayBuffer()));
    } catch {
      res.writeHead(502).end();
    }
  });
  await new Promise<void>((listening) => server.listen(0, "127.0.0.1", listening));

  return {
    url: `http://127.0.0.1:${(server.address() as AddressInfo).port}`,
    /** Calls waiting at the gate. */
    held: () => held.length,
    hold: () => {
      open = false;
    },
    releaseOne: () => held.shift()?.(),
    open: () => {
      open = true;
      for (const release of held.splice(0)) release();
    },
    close: () =>
      new Promise<void>((closed) => {
        server.close(() => closed());
        server.closeAllConnections(); // the API's client keeps its connections alive
      }),
  };
}
