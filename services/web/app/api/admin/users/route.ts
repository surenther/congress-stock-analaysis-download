import { NextRequest, NextResponse } from "next/server";

const AUTH_BASE = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

/** BFF proxy: list and create users (admin only). */
export async function GET(req: NextRequest) {
    const authHeader = req.headers.get("authorization");
    try {
        const res = await fetch(`${AUTH_BASE}/api/v1/admin/users`, {
            headers: authHeader ? { Authorization: authHeader } : {},
            signal: AbortSignal.timeout(10000),
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

export async function POST(req: NextRequest) {
    const authHeader = req.headers.get("authorization");
    const body = await req.json().catch(() => ({}));
    try {
        const res = await fetch(`${AUTH_BASE}/api/v1/admin/users`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(authHeader ? { Authorization: authHeader } : {}),
            },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(10000),
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
