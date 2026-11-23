import { NextResponse } from "next/server";
import { serviceBaseUrl } from "@/lib/backend";
import { getSession, SESSION_COOKIE } from "@/lib/session";

/** BFF: revoke the refresh token and clear the session cookie. */
export async function POST() {
    const session = await getSession();
    if (session?.refreshToken) {
        await fetch(`${serviceBaseUrl("auth")}/api/v1/auth/logout`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: session.refreshToken }),
        }).catch(() => undefined);
    }
    const res = NextResponse.json({ ok: true });
    res.cookies.set(SESSION_COOKIE, "", { path: "/", maxAge: 0 });
    return res;
}
