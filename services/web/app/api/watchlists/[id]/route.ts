import { NextRequest, NextResponse } from "next/server";

const RAG_BASE = process.env.RAG_SERVICE_URL || "http://localhost:8516";

/** BFF proxy: remove a watchlist entry. */
export async function DELETE(
    req: NextRequest,
    { params }: { params: { id: string } },
) {
    const authHeader = req.headers.get("authorization");
    try {
        const res = await fetch(`${RAG_BASE}/api/v1/watchlists/${params.id}`, {
            method: "DELETE",
            headers: authHeader ? { Authorization: authHeader } : {},
            signal: AbortSignal.timeout(10000),
        });
        if (res.status === 204) {
            return new NextResponse(null, { status: 204 });
        }
        const data = await res.json().catch(() => ({}));
        return NextResponse.json(data, { status: res.status });
    } catch {
        return NextResponse.json(
            { detail: "Watchlist service unavailable." },
            { status: 503 },
        );
    }
}
