import { NextRequest, NextResponse } from "next/server";

const ADMIN_BASE = process.env.ADMIN_SERVICE_URL || "http://localhost:8515";

/**
 * BFF proxy for pipeline orchestration. Forwards to the admin-service, which
 * proxies the trigger to the target pipeline service. No simulated job ids.
 */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const { service, force, chamber, limit } = body;
  const authHeader = req.headers.get("authorization");

  if (!service) {
    return NextResponse.json({ detail: "service is required" }, { status: 400 });
  }

  const upstreamBody: Record<string, unknown> = { force: Boolean(force) };
  if (chamber) upstreamBody.chamber = chamber;
  if (limit !== undefined && limit !== null) upstreamBody.limit = Number(limit);

  try {
    const res = await fetch(
      `${ADMIN_BASE}/api/v1/admin/pipeline/${service}/trigger`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(authHeader ? { Authorization: authHeader } : {}),
        },
        body: JSON.stringify(upstreamBody),
        signal: AbortSignal.timeout(30000),
      },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: "Admin service unavailable. Ensure the admin-service is running." },
      { status: 503 },
    );
  }
}
