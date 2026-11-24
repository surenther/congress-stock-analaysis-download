import { NextRequest, NextResponse } from "next/server";

const AUTH_BASE = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

/**
 * BFF proxy for TOTP verification. Forwards to the auth-service, which issues
 * the access + refresh tokens. No mock token fallback.
 */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const { mfa_token, code } = body;

  if (!mfa_token || !code) {
    return NextResponse.json(
      { detail: "mfa_token and 6-digit TOTP code are required." },
      { status: 400 },
    );
  }

  try {
    const res = await fetch(`${AUTH_BASE}/api/v1/auth/mfa/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mfa_token, code }),
      signal: AbortSignal.timeout(10000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: "Authentication service unavailable. Ensure the auth-service is running." },
      { status: 503 },
    );
  }
}
