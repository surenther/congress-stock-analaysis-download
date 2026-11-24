import { NextRequest, NextResponse } from "next/server";

const AUTH_BASE = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

/** BFF proxy: begin TOTP enrollment (returns otpauth URI + QR PNG + secret). */
export async function POST(req: NextRequest) {
    const body = await req.json().catch(() => ({}));
    try {
        const res = await fetch(`${AUTH_BASE}/api/v1/auth/mfa/setup`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mfa_token: body.mfa_token }),
            signal: AbortSignal.timeout(10000),
        });
        const data = await res.json().catch(() => ({}));
        return NextResponse.json(data, { status: res.status });
    } catch {
        return NextResponse.json(
            { detail: "Authentication service unavailable." },
            { status: 503 },
        );
    }
}
