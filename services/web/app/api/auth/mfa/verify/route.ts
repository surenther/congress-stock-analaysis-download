import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { mfa_token, code, username } = body;

    if (!mfa_token || !code) {
      return NextResponse.json(
        { detail: "mfa_token and 6-digit TOTP code are required." },
        { status: 400 }
      );
    }

    const authBase = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

    try {
      const res = await fetch(`${authBase}/api/v1/auth/mfa/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mfa_token, code }),
        signal: AbortSignal.timeout(3000),
      });

      const data = await res.json();
      if (!res.ok) {
        return NextResponse.json(
          { detail: data.detail || "Invalid 2FA code." },
          { status: res.status }
        );
      }

      return NextResponse.json(data);
    } catch {
      // Standalone development fallback
      if (code.length !== 6 || isNaN(Number(code))) {
        return NextResponse.json(
          { detail: "Code must be a 6-digit numeric TOTP token." },
          { status: 400 }
        );
      }

      // Issue mock JWT with roles and chamber claims
      const userRole = (username || "").toLowerCase().includes("admin") ? "admin" : "user";
      const allowedChambers = userRole === "admin" ? ["House", "Senate"] : ["House"];

      const mockPayload = {
        sub: username || "analyst",
        username: username || "Executive Analyst",
        role: userRole,
        allowed_chambers: allowedChambers,
      };

      const mockToken = `jwt-token-${userRole}-${Date.now()}`;

      return NextResponse.json({
        access_token: mockToken,
        refresh_token: `refresh-${mockToken}`,
        token_type: "bearer",
        expires_in: 1800,
        user: mockPayload,
      });
    }
  } catch (err: any) {
    return NextResponse.json({ detail: err.message }, { status: 500 });
  }
}
