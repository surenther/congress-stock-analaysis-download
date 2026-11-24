import { NextRequest, NextResponse } from "next/server";

const RAG_BASE = process.env.RAG_SERVICE_URL || "http://localhost:8516";

/**
 * BFF proxy for the LLM-driven dashboard spec.
 *
 * Forwards to the RAG service, which gathers real chamber-scoped aggregates and
 * asks the LLM to author the schema-driven layout. No hardcoded fallback: if the
 * backend is unavailable the caller receives an error.
 */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const authHeader = req.headers.get("authorization");

  try {
    const res = await fetch(`${RAG_BASE}/api/v1/rag/dashboard/analytics`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
      body: JSON.stringify({
        chamber: body.chamber,
        horizon: body.timeHorizon || body.horizon,
      }),
      // The LLM synthesis can take a while.
      signal: AbortSignal.timeout(120000),
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      {
        detail:
          "Dashboard service unavailable. Ensure the RAG service and LiteLLM proxy are running.",
      },
      { status: 503 },
    );
  }
}
