import { type NextRequest, NextResponse } from "next/server";

const PUBLIC = [/^\/$/, /^\/login$/, /^\/register$/, /^\/shared\//, /^\/dev\//];
// Headers the API trusts only from this server (ADR 0035); a browser's own copies are dropped.
const PROXY_SECRET_HEADER = "x-agentprobe-proxy-secret";
const CLIENT_IP_HEADER = "x-agentprobe-client-ip";

/**
 * Same-origin API (ADR 0009): /api/* is forwarded to the API, so the session cookies are
 * first-party and no CORS is needed. API_INTERNAL_URL is read per request, not at build time.
 *
 * With PROXY_SECRET set (production), each request also carries the secret and the browser's
 * IP, so the API's per-IP limits see the browser rather than this server. The IP is the first
 * X-Forwarded-For entry, which Vercel overwrites with the real client: only set PROXY_SECRET
 * behind a proxy that does the same.
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
    const ip = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
    if (ip) headers.set(CLIENT_IP_HEADER, ip);
  }
  return NextResponse.rewrite(target, { request: { headers } });
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
  if (PUBLIC.some((p) => p.test(pathname))) return NextResponse.next();
  if (request.cookies.has("access_token") || request.cookies.has("refresh_token")) return NextResponse.next();
  const login = new URL("/login", request.url);
  login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

export const config = {
  // The API proxy, and every page except Next's own assets and files with an extension.
  matcher: ["/api/:path*", "/((?!api/|_next/|.*\\..*).*)"],
};
