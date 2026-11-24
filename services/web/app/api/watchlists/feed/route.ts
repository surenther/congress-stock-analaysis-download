import { NextRequest, NextResponse } from "next/server";

const RAG_BASE = process.env.RAG_SERVICE_URL || "http://localhost:8516";

/** BFF proxy: personalized watchlist activity feed. */
export async function GET(req: NextRequest) {
    const authHeader = req.headers.get("authorization");
    try {
        const res = await fetch(`${RAG_BASE}/api/v1/watchlists/feed`, {
            headers: authHeader ? { Authorization: authHeader } : {},
            signal: AbortSignal.timeout(15000),
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
