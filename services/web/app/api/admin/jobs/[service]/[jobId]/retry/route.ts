import { NextRequest, NextResponse } from "next/server";

const ADMIN_BASE = process.env.ADMIN_SERVICE_URL || "http://localhost:8515";

/** BFF proxy: re-trigger the failed documents of a job (admin only). */
export async function POST(
    req: NextRequest,
    { params }: { params: { service: string; jobId: string } },
) {
    const authHeader = req.headers.get("authorization");
    try {
        const res = await fetch(
            `${ADMIN_BASE}/api/v1/admin/pipeline/jobs/${params.service}/${params.jobId}/retry`,
            {
                method: "POST",
                headers: authHeader ? { Authorization: authHeader } : {},
                signal: AbortSignal.timeout(30000),
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
