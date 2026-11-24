import { NextRequest, NextResponse } from "next/server";

const ADMIN_BASE = process.env.ADMIN_SERVICE_URL || "http://localhost:8515";

function portFromUrl(url: string): number {
  try {
    return Number(new URL(url).port) || 0;
  } catch {
    return 0;
  }
}

/**
 * BFF proxy for cluster health. Forwards to the admin-service aggregation
 * endpoint (admin-only). Returns the real per-service status and latency; no
 * fabricated "healthy" values.
 */
export async function GET(req: NextRequest) {
  const authHeader = req.headers.get("authorization");

  try {
    const res = await fetch(`${ADMIN_BASE}/api/v1/admin/health/cluster`, {
      headers: authHeader ? { Authorization: authHeader } : {},
      signal: AbortSignal.timeout(10000),
    });

    if (res.status === 401 || res.status === 403) {
      // Non-admin callers cannot read cluster health; return an empty set.
      return NextResponse.json({ services: [] });
    }
    if (!res.ok) {
      return NextResponse.json(
        { detail: "Health aggregation unavailable." },
        { status: res.status },
      );
    }

    const data = await res.json();
    const services = (data.services || []).map((s: any) => ({
      name: s.service,
      port: portFromUrl(s.url),
      healthy: s.status === "healthy",
      latency_ms: s.latency_ms,
    }));
    return NextResponse.json({
      status: "ok",
      timestamp: data.checked_at,
      services,
    });
  } catch {
    return NextResponse.json(
      { detail: "Admin service unavailable." },
      { status: 503 },
    );
  }
}
