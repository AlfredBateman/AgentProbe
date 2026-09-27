import { type NextRequest, NextResponse } from "next/server";

const PUBLIC = [/^\/$/, /^\/login$/, /^\/register$/, /^\/shared\//, /^\/dev\//];

/**
 * Route protection. The session cookies are httpOnly and signed by the API, so all this can
 * check is that one exists; the API stays the authority, and a 401 that a refresh can't fix
 * sends the browser to /login anyway (lib/api/session.ts). The refresh cookie counts: an
 * expired access cookie is refreshed on the first API call.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC.some((p) => p.test(pathname))) return NextResponse.next();
  if (request.cookies.has("access_token") || request.cookies.has("refresh_token")) return NextResponse.next();
  const login = new URL("/login", request.url);
  login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

export const config = {
  // Not the API proxy, Next's own assets, or files with an extension (favicon.ico, fonts).
  matcher: ["/((?!api/|_next/|.*\\..*).*)"],
};
