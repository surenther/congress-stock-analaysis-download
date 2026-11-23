import { NextRequest, NextResponse } from "next/server";
import { serviceBaseUrl } from "@/lib/backend";
import {
    encryptSession,
    SESSION_COOKIE,
    sessionCookieOptions,
} from "@/lib/session";

/**
 * BFF login. Proxies to the auth service. When the auth service issues tokens
 * (2FA already satisfied), the tokens are stored in an encrypted httpOnly
 * cookie and the user profile is returned. Otherwise the next-step payload
 * (mfa_required / must_setup_2fa / must_change_password) is passed through.
 */
export async function POST(req: NextRequest) {
    const body = await req.json().catch(() => ({}));
    const resp = await fetch(`${serviceBaseUrl("auth")}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
        return NextResponse.json(data, { status: resp.status });
    }

    if (data.access_token) {
        const meResp = await fetch(`${serviceBaseUrl("auth")}/api/v1/auth/me`, {
            headers: { Authorization: `Bearer ${data.access_token}` },
        });
        const me = meResp.ok ? await meResp.json() : {};
        const session = encryptSession({
            accessToken: data.access_token,
            refreshToken: data.refresh_token ?? "",
            username: me.username ?? body.username ?? "",
            roles: me.roles ?? [],
            allowedChambers: me.allowed_chambers ?? [],
        });
        const res = NextResponse.json({ ok: true, me });
        res.cookies.set(SESSION_COOKIE, session, sessionCookieOptions());
        return res;
    }

    return NextResponse.json(data);
}
