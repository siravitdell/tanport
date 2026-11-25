import { type NextRequest, NextResponse } from "next/server";

/** Must match SESSION_COOKIE in backend/app/api/deps.py. */
const SESSION_COOKIE = "tanport_session";

/**
 * Optimistic check only: no session cookie → /login. Whether the session is still valid is
 * decided by the API (AuthProvider calls /api/auth/me and handles 401).
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  return NextResponse.redirect(new URL("/login", request.url));
}

export const config = {
  // Pages only: not the API (forwarded to FastAPI), Next internals, static files or /login.
  matcher: ["/((?!api/|_next/|login$|favicon\\.ico$|.*\\.[a-zA-Z0-9]+$).*)"],
};
