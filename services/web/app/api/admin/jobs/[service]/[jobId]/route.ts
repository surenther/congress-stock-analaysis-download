import { NextRequest, NextResponse } from "next/server";

const ADMIN_BASE = process.env.ADMIN_SERVICE_URL || "http://localhost:8515";

/** BFF proxy: single normalized job detail (admin only). */
export async function GET(
    req: NextRequest,
    { params }: { params: { service: string; jobId: string } },
) {
    const authHeader = req.headers.get("authorization");
    try {
        const res = await fetch(
            `${ADMIN_BASE}/api/v1/jobs/${params.service}/${params.jobId}`,
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
