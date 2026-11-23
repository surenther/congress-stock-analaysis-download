import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const { service, port, limit, force } = await req.json();

    // Check if target container is reachable on localhost
    try {
      const res = await fetch(`http://localhost:${port}/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit, force }),
        signal: AbortSignal.timeout(2000),
      });
      if (res.ok) {
        const data = await res.json();
        return NextResponse.json(data);
      }
    } catch {
      // Standalone demo simulated job response
    }

    const jobId = `job-${Date.now().toString(36)}-${Math.floor(Math.random() * 9000 + 1000)}`;

    return NextResponse.json({
      status: "dispatched",
      job_id: jobId,
      service,
      port,
      limit,
      force,
      started_at: new Date().toISOString(),
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
