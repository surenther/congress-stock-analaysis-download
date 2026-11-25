import { NextRequest, NextResponse } from "next/server";

const ADMIN_BASE = process.env.ADMIN_SERVICE_URL || "http://localhost:8515";

/** BFF proxy: list recurring pipeline schedules (admin only). */
export async function GET(req: NextRequest) {
    const authHeader = req.headers.get("authorization");
    try {
        const res = await fetch(`${ADMIN_BASE}/api/v1/admin/pipeline/schedule`, {
            headers: authHeader ? { Authorization: authHeader } : {},
            signal: AbortSignal.timeout(10000),
        });
        const data = await res.json().catch(() => ({}));
        return NextResponse.json(data, { status: res.status });
    } catch {
        return NextResponse.json(
            { detail: "Admin service unavailable." },
            { status: 503 },
        );
    }
}

/** BFF proxy: create a recurring pipeline schedule (admin only). */
export async function POST(req: NextRequest) {
    const authHeader = req.headers.get("authorization");
    const body = await req.json().catch(() => ({}));
    try {
        const res = await fetch(`${ADMIN_BASE}/api/v1/admin/pipeline/schedule`, {
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
            { detail: "Admin service unavailable." },
            { status: 503 },
        );
    }
}
