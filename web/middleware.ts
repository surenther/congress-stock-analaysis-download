import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "congress_session";

// Routes that do not require an authenticated session.
const PUBLIC_PREFIXES = [
    "/login",
    "/mfa",
    "/setup-2fa",
    "/change-password",
    "/forgot-password",
    "/reset-password",
    "/api/auth",
    "/api/health",
];

function isPublic(pathname: string): boolean {
    return PUBLIC_PREFIXES.some(
        (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
    );
}

/**
 * Route guard. The session cookie is opaque (encrypted) so the middleware only
 * checks for its presence; fine-grained role/scope checks happen server-side in
 * the page components and the BFF.
 */
export function middleware(req: NextRequest) {
    const { pathname } = req.nextUrl;
    const hasSession = Boolean(req.cookies.get(SESSION_COOKIE)?.value);

    if (isPublic(pathname)) {
        if (hasSession && (pathname === "/login" || pathname === "/")) {
            return NextResponse.redirect(new URL("/dashboard", req.url));
        }
        return NextResponse.next();
    }

    if (!hasSession) {
        const url = new URL("/login", req.url);
        url.searchParams.set("next", pathname);
        return NextResponse.redirect(url);
    }

    return NextResponse.next();
}

export const config = {
    matcher: ["/((?!_next/static|_next/image|favicon.ico|api/health).*)"],
};
