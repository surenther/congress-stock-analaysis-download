import { NextRequest, NextResponse } from "next/server";
import { isServiceName, serviceBaseUrl } from "@/lib/backend";
import {
    encryptSession,
    getSession,
    SESSION_COOKIE,
    sessionCookieOptions,
    type SessionData,
} from "@/lib/session";

/**
 * Generic authenticated BFF proxy.
 *
 * URL shape: /api/proxy/{service}/{...backendPath}
 * The session's access token is attached as a Bearer header. On a 401 the
 * refresh token is used to rotate the session once, then the request is retried.
 */

async function refreshSession(session: SessionData): Promise<SessionData | null> {
    if (!session.refreshToken) return null;
    const resp = await fetch(`${serviceBaseUrl("auth")}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: session.refreshToken }),
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    const meResp = await fetch(`${serviceBaseUrl("auth")}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
    });
    const me = meResp.ok ? await meResp.json() : {};
    return {
        accessToken: data.access_token,
        refreshToken: data.refresh_token ?? session.refreshToken,
        username: me.username ?? session.username,
        roles: me.roles ?? session.roles,
        allowedChambers: me.allowed_chambers ?? session.allowedChambers,
    };
}

async function handle(
    req: NextRequest,
    { params }: { params: Promise<{ path: string[] }> },
) {
    const { path } = await params;
    const [service, ...rest] = path;
    if (!service || !isServiceName(service)) {
        return NextResponse.json({ detail: "Unknown service" }, { status: 404 });
    }
    const session = await getSession();
    if (!session) {
        return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }

    const target = `${serviceBaseUrl(service)}/${rest.join("/")}${req.nextUrl.search}`;
    const method = req.method.toUpperCase();
    const bodyText = ["GET", "HEAD"].includes(method) ? undefined : await req.text();

    const doFetch = (token: string) =>
        fetch(target, {
            method,
            headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
            },
            body: bodyText,
            cache: "no-store",
        });

    let resp = await doFetch(session.accessToken);
    let newSession: SessionData | null = null;

    if (resp.status === 401) {
        newSession = await refreshSession(session);
        if (newSession) {
            resp = await doFetch(newSession.accessToken);
        }
    }

    const text = await resp.text();
    const res = new NextResponse(text, {
        status: resp.status,
        headers: {
            "Content-Type": resp.headers.get("content-type") ?? "application/json",
        },
    });
    if (newSession) {
        res.cookies.set(SESSION_COOKIE, encryptSession(newSession), sessionCookieOptions());
    }
    return res;
}

export const GET = handle;
export const POST = handle;
export const PATCH = handle;
export const PUT = handle;
export const DELETE = handle;
