import { NextRequest, NextResponse } from "next/server";

const RAG_BASE = process.env.RAG_SERVICE_URL || "http://localhost:8516";

/**
 * BFF proxy for the RAG assistant. Forwards to the RAG service, which enforces
 * CBAC and synthesizes a grounded answer. No hardcoded answers or sources.
 */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const authHeader = req.headers.get("authorization");
  const prompt = body.query || body.prompt;

  if (!prompt) {
    return NextResponse.json({ detail: "query is required" }, { status: 400 });
  }

  try {
    const res = await fetch(`${RAG_BASE}/api/v1/rag/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
      body: JSON.stringify({
        prompt,
        top_k: body.top_k || 8,
        filters:
          body.chamber && body.chamber !== "Combined"
            ? { chamber: body.chamber }
            : undefined,
      }),
      signal: AbortSignal.timeout(120000),
    });

    const data = await res.json().catch(() => ({}));

    if (res.status === 403) {
      // Flatten the structured CHAMBER_SCOPE_VIOLATION detail for the UI banner.
      const detail = data.detail || data;
      return NextResponse.json(detail, { status: 403 });
    }

    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: "RAG service unavailable. Ensure the RAG service is running." },
      { status: 503 },
    );
  }
}
