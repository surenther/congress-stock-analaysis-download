import { NextRequest, NextResponse } from "next/server";

const AUTH_BASE = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

/**
 * BFF proxy for password login. Forwards to the auth-service, which returns the
 * next required step (2FA / password change / setup) or a token pair. No demo
 * fallback: an unreachable auth-service returns an error.
 */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const { username, password } = body;

  if (!username || !password) {
    return NextResponse.json(
      { detail: "Username and password are required." },
      { status: 400 },
    );
  }

  try {
    const res = await fetch(`${AUTH_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
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
