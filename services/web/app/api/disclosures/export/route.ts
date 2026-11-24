import { NextRequest, NextResponse } from "next/server";

const RAG_BASE = process.env.RAG_SERVICE_URL || "http://localhost:8516";

/**
 * BFF proxy for disclosure export. Streams the real CSV/PDF produced by the RAG
 * service's export endpoint. No hardcoded rows or simulated PDF.
 */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const format = searchParams.get("format") === "pdf" ? "pdf" : "csv";
  const authHeader = req.headers.get("authorization");

  try {
    const res = await fetch(`${RAG_BASE}/api/v1/rag/export`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
      body: JSON.stringify({
        format,
        top_k: 1000,
        filters: {
          ticker: searchParams.get("ticker") || undefined,
          chamber: searchParams.get("chamber") || undefined,
          start_date: searchParams.get("start_date") || undefined,
          end_date: searchParams.get("end_date") || undefined,
        },
      }),
      signal: AbortSignal.timeout(60000),
    });

    if (!res.ok) {
      const detail = await res.text();
      return new NextResponse(detail, { status: res.status });
    }

    const buffer = await res.arrayBuffer();
    return new NextResponse(buffer, {
      status: 200,
      headers: {
        "Content-Type":
          res.headers.get("content-type") || "application/octet-stream",
        "Content-Disposition":
          res.headers.get("content-disposition") ||
          `attachment; filename="congress-disclosures.${format}"`,
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "Export service unavailable. Ensure the RAG service is running." },
      { status: 503 },
    );
  }
}
