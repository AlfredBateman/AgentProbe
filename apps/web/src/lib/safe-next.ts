/**
 * Validates a post-login redirect target (the `next` query param). It must stay on this
 * origin: a same-origin relative path only. Rejects protocol-relative `//host` (the browser
 * treats it as a different origin) and any backslash (some browsers/proxies normalize `\` to
 * `/`, so `/\evil.com` can behave like `//evil.com`).
 */
export function safeNext(next: string | null | undefined, fallback = "/projects"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) {
    return fallback;
  }
  return next;
}
