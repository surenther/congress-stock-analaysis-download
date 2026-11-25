import { NextRequest, NextResponse } from "next/server";

const ADMIN_BASE = process.env.ADMIN_SERVICE_URL || "http://localhost:8515";

/** BFF proxy: recent audit-log entries with optional filters (admin only). */
export async function GET(req: NextRequest) {
    const authHeader = req.headers.get("authorization");
    const { search } = new URL(req.url);
    try {
        const res = await fetch(`${ADMIN_BASE}/api/v1/admin/audit-log${search}`, {
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
