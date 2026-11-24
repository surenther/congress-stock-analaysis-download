import { NextRequest, NextResponse } from "next/server";

const RAG_BASE = process.env.RAG_SERVICE_URL || "http://localhost:8516";

/** BFF proxy: list and add watchlist entries. */
export async function GET(req: NextRequest) {
    const authHeader = req.headers.get("authorization");
    try {
        const res = await fetch(`${RAG_BASE}/api/v1/watchlists`, {
            headers: authHeader ? { Authorization: authHeader } : {},
            signal: AbortSignal.timeout(10000),
        });
        const data = await res.json().catch(() => ({}));
        return NextResponse.json(data, { status: res.status });
    } catch {
        return NextResponse.json(
            { detail: "Watchlist service unavailable." },
            { status: 503 },
        );
    }
}

export async function POST(req: NextRequest) {
    const authHeader = req.headers.get("authorization");
    const body = await req.json().catch(() => ({}));
    try {
        const res = await fetch(`${RAG_BASE}/api/v1/watchlists`, {
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
            { detail: "Watchlist service unavailable." },
            { status: 503 },
        );
    }
}
