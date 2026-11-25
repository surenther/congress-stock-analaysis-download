import { NextRequest, NextResponse } from "next/server";

const AUTH_BASE = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

/** BFF proxy: clear a user's TOTP enrollment so they can re-enroll (admin only). */
export async function POST(
    req: NextRequest,
    { params }: { params: { id: string } },
) {
    const authHeader = req.headers.get("authorization");
    try {
        const res = await fetch(
            `${AUTH_BASE}/api/v1/admin/users/${params.id}/reset-2fa`,
            {
                method: "POST",
                headers: authHeader ? { Authorization: authHeader } : {},
                signal: AbortSignal.timeout(10000),
            },
        );
        const data = await res.json().catch(() => ({}));
        return NextResponse.json(data, { status: res.status });
    } catch {
        return NextResponse.json(
            { detail: "Auth service unavailable." },
            { status: 503 },
        );
    }
}
