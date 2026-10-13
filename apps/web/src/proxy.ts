import { type NextRequest, NextResponse } from "next/server";
import { NUDGE_URLS } from "@/lib/api/public-url";

const PUBLIC = [/^\/$/, /^\/login$/, /^\/register$/, /^\/shared\//, /^\/dev\//];
// The API trusts CLIENT_IP_HEADER only on requests carrying this secret (ADR 0036); a
// browser's own copies of both are dropped.
const PROXY_SECRET_HEADER = "x-agentprobe-proxy-secret";
const CLIENT_IP_HEADER = "x-agentprobe-client-ip";

/**
 * Same-origin API (ADR 0009): /api/* is forwarded to the API, so the session cookies are
 * first-party and no CORS is needed. API_INTERNAL_URL is read per request, not at build time.
 *
 * With PROXY_SECRET set (production), each request also carries the secret and the browser's
 * IP in CLIENT_IP_HEADER, so the API's per-IP limits see the browser rather than this server.
 * The IP is Vercel's x-real-ip, which its edge sets from the connection. X-Forwarded-For is not
 * used: in production a browser's own X-Forwarded-For sometimes came out leftmost (ADR 0036).
 * Only set PROXY_SECRET behind a proxy that sets x-real-ip.
 */
function forwardToApi(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const target = new URL(pathname.slice("/api".length) + search, process.env.API_INTERNAL_URL ?? "http://localhost:8000");
  const headers = new Headers(request.headers);
  headers.delete("host"); // the proxy sets the API's own host
  headers.delete(PROXY_SECRET_HEADER);
  headers.delete(CLIENT_IP_HEADER);
  const secret = process.env.PROXY_SECRET;
  if (secret) {
    headers.set(PROXY_SECRET_HEADER, secret);
    const ip = request.headers.get("x-real-ip")?.trim();
    if (ip) headers.set(CLIENT_IP_HEADER, ip); // else the API keys on this server's address
  }
  return NextResponse.rewrite(target, { request: { headers } });
}

/**
 * The page's Content-Security-Policy. Scripts run only with this response's nonce, which Next
 * puts on its own scripts (it reads the nonce from the request's CSP header), and whatever
 * those load ('strict-dynamic'): an injected <script> or inline handler never runs. Styles
 * allow inline, because React renders style attributes, which a nonce can't cover. The only
 * other origins are the API's own, for live run progress (ADR 0031), and the services the
 * browser pings awake (lib/api/wake.ts). `next dev` needs eval.
 */
export function contentSecurityPolicy(nonce: string, dev = process.env.NODE_ENV === "development") {
  const others = [...new Set(NUDGE_URLS.map((u) => new URL(u).origin))].map((o) => ` ${o}`).join("");
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self'${others}`,
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

function page(request: NextRequest) {
  const csp = contentSecurityPolicy(btoa(crypto.randomUUID()));
  const headers = new Headers(request.headers);
  headers.set("content-security-policy", csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("content-security-policy", csp);
  return response;
}

/**
 * Route protection. The session cookies are httpOnly and signed by the API, so all this can
 * check is that one exists; the API stays the authority, and a 401 that a refresh can't fix
 * sends the browser to /login anyway (lib/api/session.ts). The refresh cookie counts: an
 * expired access cookie is refreshed on the first API call.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (pathname === "/api" || pathname.startsWith("/api/")) return forwardToApi(request);
  if (PUBLIC.some((p) => p.test(pathname))) return page(request);
  if (request.cookies.has("access_token") || request.cookies.has("refresh_token")) return page(request);
  const login = new URL("/login", request.url);
  login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

export const config = {
  // The API proxy, and every page except Next's own assets and files with an extension.
  matcher: ["/api/:path*", "/((?!api/|_next/|.*\\..*).*)"],
};
