import { NextRequest, NextResponse } from "next/server";

const ADMIN_BASE = process.env.ADMIN_SERVICE_URL || "http://localhost:8515";

/**
 * BFF proxy: a single user's merged activity history + summary (admin only).
 * Forwards query params (``limit`` / ``offset``) to the admin service.
 */
export async function GET(
    req: NextRequest,
    { params }: { params: { id: string } },
) {
    const authHeader = req.headers.get("authorization");
    const { search } = new URL(req.url);
    try {
        const res = await fetch(
            `${ADMIN_BASE}/api/v1/admin/users/${params.id}/activity${search}`,
            {
                headers: authHeader ? { Authorization: authHeader } : {},
                signal: AbortSignal.timeout(10000),
            },
        );
        const data = await res.json().catch(() => ({}));
        return NextResponse.json(data, { status: res.status });
    } catch {
        return NextResponse.json(
            { detail: "Admin service unavailable." },
            { status: 503 },
        );
    }
}