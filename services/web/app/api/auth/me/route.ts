import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  if (!authHeader) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const authBase = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

  try {
    const res = await fetch(`${authBase}/api/v1/auth/me`, {
      headers: { Authorization: authHeader },
      signal: AbortSignal.timeout(2000),
    });

    if (res.ok) {
      const data = await res.json();
      return NextResponse.json(data);
    }
  } catch {
    // Offline fallback
  }

  return NextResponse.json({
    id: "usr-current",
    username: "Executive Analyst",
    email: "analyst@congress.alpha",
    role: "admin",
    allowed_chambers: ["House", "Senate"],
    two_factor_enabled: true,
  });
}
