import { NextRequest, NextResponse } from "next/server";
import { serviceBaseUrl } from "@/lib/backend";

/** BFF: request a password-reset email. */
export async function POST(req: NextRequest) {
    const body = await req.json().catch(() => ({}));
    const resp = await fetch(
        `${serviceBaseUrl("auth")}/api/v1/auth/forgot-password`,
        {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        },
    );
    const data = await resp.json().catch(() => ({}));
    return NextResponse.json(data, { status: resp.status });
}
