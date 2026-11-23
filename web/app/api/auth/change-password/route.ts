import { NextRequest, NextResponse } from "next/server";
import { serviceBaseUrl } from "@/lib/backend";

/**
 * BFF: change password. Accepts either the mfa_token (first-login flow) or the
 * session access token (self-service).
 */
export async function POST(req: NextRequest) {
    const body = await req.json().catch(() => ({}));
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (body.mfa_token) {
        headers.Authorization = `Bearer ${body.mfa_token}`;
    }
    const resp = await fetch(
        `${serviceBaseUrl("auth")}/api/v1/auth/change-password`,
        {
            method: "POST",
            headers,
            body: JSON.stringify({
                current_password: body.current_password,
                new_password: body.new_password,
            }),
        },
    );
    const data = await resp.json().catch(() => ({}));
    return NextResponse.json(data, { status: resp.status });
}
