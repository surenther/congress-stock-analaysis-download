import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  const authBase = process.env.AUTH_SERVICE_URL || "http://localhost:8512";

  if (authHeader) {
    try {
      await fetch(`${authBase}/api/v1/auth/logout`, {
        method: "POST",
        headers: { Authorization: authHeader },
        signal: AbortSignal.timeout(1000),
      });
    } catch {}
  }

  return NextResponse.json({ status: "ok", message: "Logged out successfully" });
}
