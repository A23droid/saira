import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// `/` and `/login` are the only public routes — everything else under the
// app shell requires a session.
const PUBLIC_PATHS = ["/", "/login"];

/**
 * This only checks for the *presence* of the `refresh_token` cookie, not
 * whether it (or the short-lived access token) is still valid — that's a
 * fast, dependency-free first line of defense against an obviously
 * logged-out visitor hitting a protected URL directly or via a stale
 * bookmark. The authoritative check happens client-side in
 * `AuthProvider`/`RequireAuth`, which calls `/auth/me` (with the API
 * client's automatic refresh-on-401) and redirects if that fails too —
 * that's what actually validates the session against the backend.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (PUBLIC_PATHS.includes(pathname)) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has("refresh_token");
  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
