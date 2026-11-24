import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { username, password } = body;

    if (!username || !password) {
      return NextResponse.json(
        { detail: "Username and password are required." },
        { status: 400 }
      );
    }

    const authBase = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

    try {
      const res = await fetch(`${authBase}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        signal: AbortSignal.timeout(3000),
      });

      const data = await res.json();
      if (!res.ok) {
        return NextResponse.json(
          { detail: data.detail || "Invalid credentials." },
          { status: res.status }
        );
      }

      return NextResponse.json(data);
    } catch {
      // Standalone development fallback when auth-service container is not running
      // Simulate standard 2FA flow:
      if (password === "invalid" || password === "wrong") {
        return NextResponse.json(
          { detail: "Invalid username or password." },
          { status: 401 }
        );
      }

      // Default demo flow requires 2FA TOTP verification
      const mfaToken = `mfa-temp-token-${username}-${Date.now()}`;
      return NextResponse.json({
        mfa_required: true,
        mfa_token: mfaToken,
        username,
        is_demo: true,
      });
    }
  } catch (err: any) {
    return NextResponse.json({ detail: err.message }, { status: 500 });
  }
}
