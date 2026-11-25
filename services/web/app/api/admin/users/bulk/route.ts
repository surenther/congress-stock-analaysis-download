import { NextRequest, NextResponse } from "next/server";

const AUTH_BASE = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

/** BFF proxy: apply one action to many users (admin only). */
export async function POST(req: NextRequest) {
    const authHeader = req.headers.get("authorization");
    const body = await req.json().catch(() => ({}));
    try {
        const res = await fetch(`${AUTH_BASE}/api/v1/admin/users/bulk`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(authHeader ? { Authorization: authHeader } : {}),
            },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(30000),
        });
        const data = await res.json().catch(() => ({}));
        return NextResponse.json(data, { status: res.status });
    } catch {
        return NextResponse.json(
            { detail: "Auth service unavailable." },
            { status: 503 },
        );
    }
}
