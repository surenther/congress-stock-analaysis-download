import { NextRequest, NextResponse } from "next/server";

const ADMIN_BASE = process.env.ADMIN_SERVICE_URL || "http://localhost:8515";

/** BFF proxy: delete a recurring pipeline schedule (admin only). */
export async function DELETE(
    req: NextRequest,
    { params }: { params: { id: string } },
) {
    const authHeader = req.headers.get("authorization");
    try {
        const res = await fetch(
            `${ADMIN_BASE}/api/v1/admin/pipeline/schedule/${params.id}`,
            {
                method: "DELETE",
                headers: authHeader ? { Authorization: authHeader } : {},
                signal: AbortSignal.timeout(10000),
            },
        );
        if (res.status === 204) {
            return new NextResponse(null, { status: 204 });
        }
        const data = await res.json().catch(() => ({}));
        return NextResponse.json(data, { status: res.status });
    } catch {
        return NextResponse.json(
            { detail: "Admin service unavailable." },
            { status: 503 },
        );
    }
}
