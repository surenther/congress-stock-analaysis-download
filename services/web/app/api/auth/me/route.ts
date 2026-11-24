import { NextRequest, NextResponse } from "next/server";

const AUTH_BASE = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

/**
 * BFF proxy for the current user profile. Forwards the bearer token to the
 * auth-service. No fabricated user fallback.
 */
export async function GET(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  if (!authHeader) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  try {
    const res = await fetch(`${AUTH_BASE}/api/v1/auth/me`, {
      headers: { Authorization: authHeader },
      signal: AbortSignal.timeout(10000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: "Authentication service unavailable." },
      { status: 503 },
    );
  }
}
