import { NextRequest, NextResponse } from "next/server";

const AUTH_BASE = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

/**
 * BFF proxy for consuming a welcome / password-reset token. Forwards the token
 * and new password to the auth-service, which validates the token, enforces the
 * password policy, and clears the mandatory-change flag. No auth header is
 * required: the opaque email token is the credential.
 */
export async function POST(req: NextRequest) {
    const body = await req.json().catch(() => ({}));
    const { token, new_password } = body;

    if (!token || !new_password) {
        return NextResponse.json(
            { detail: "Token and new password are required." },
            { status: 400 },
        );
    }

    try {
        const res = await fetch(`${AUTH_BASE}/api/v1/auth/reset-password`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token, new_password }),
            signal: AbortSignal.timeout(10000),
        });
        const data = await res.json().catch(() => ({}));
        return NextResponse.json(data, { status: res.status });
    } catch {
        return NextResponse.json(
            { detail: "Authentication service unavailable. Ensure the auth-service is running." },
            { status: 503 },
        );
    }
}
