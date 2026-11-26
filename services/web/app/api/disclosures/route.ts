import { NextRequest, NextResponse } from "next/server";
import { DisclosureRecord } from "@/types/disclosure";

const RAG_BASE = process.env.RAG_SERVICE_URL || "http://localhost:8516";

/**
 * BFF proxy for the disclosure data grid.
 *
 * Calls the RAG service's chamber-scoped structured search. There is no
 * hardcoded baseline: an empty dataset returns an empty page, and an
 * unreachable backend returns an error.
 */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const ticker = (searchParams.get("ticker") || "").trim().toUpperCase();
  const filerName = (searchParams.get("filer_name") || "").trim().toLowerCase();
  const action = (searchParams.get("action") || "").trim();
  const chamber = (searchParams.get("chamber") || "").trim();
  const sector = (searchParams.get("sector") || "").trim();
  const assetName = (searchParams.get("asset_name") || "").trim();
  const startDate = searchParams.get("start_date");
  const endDate = searchParams.get("end_date");
  const isLate = searchParams.get("is_late");
  const marketTrades = searchParams.get("market_trades");
  const sort = (searchParams.get("sort") || "").trim();
  const order = (searchParams.get("order") || "desc").trim();
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));
  const pageSize = Math.max(1, parseInt(searchParams.get("page_size") || "12", 10));
  const offset = (page - 1) * pageSize;

  const authHeader = req.headers.get("authorization");

  let rows: any[] = [];
  let total = 0;
  try {
    const res = await fetch(`${RAG_BASE}/api/v1/rag/search-structured`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
      body: JSON.stringify({
        top_k: pageSize,
        offset,
        sort: sort || undefined,
        order: order === "asc" ? "asc" : "desc",
        filters: {
          ticker: ticker || undefined,
          chamber: chamber && chamber !== "All" ? chamber : undefined,
          asset_category: sector || undefined,
          asset_name: assetName || undefined,
          filer_name: filerName || undefined,
          action: action && action !== "All" ? action : undefined,
          is_late: isLate === "1" ? true : undefined,
          is_market_trade: marketTrades === "1" ? true : undefined,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
        },
      }),
      signal: AbortSignal.timeout(20000),
    });

    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      return NextResponse.json(detail, { status: res.status });
    }
    const data = await res.json();
    rows = data.results || [];
    total = typeof data.total === "number" ? data.total : rows.length;
  } catch {
    return NextResponse.json(
      { detail: "Disclosure service unavailable. Ensure the RAG service is running." },
      { status: 503 },
    );
  }

  const records: DisclosureRecord[] = rows.map((row, idx) => {
    const fDate = row.filing_date;
    const tDate = row.date;
    const rType = (row.report_type || "").toUpperCase();
    let daysLate: number | null = null;
    let isLate = false;
    if (fDate && tDate) {
      const diff = Math.floor(
        (new Date(fDate).getTime() - new Date(tDate).getTime()) / 86400000,
      );
      // Valid positive calendar interval (guards against clerical date entry typos)
      if (diff >= 0) {
        daysLate = diff;
        // The 45-day STOCK Act rule strictly governs Periodic Transaction
        // Reports (report_type "PTR"); Annual/Termination/Extension filings
        // follow different deadlines. This mirrors the backend predicate in
        // services/rag/dashboard.py::_late_filing_predicate and the is_late
        // filter in services/rag/retriever.py (report_type ILIKE '%PTR%' OR NULL).
        const isPtr = !rType || rType.includes("PTR");
        isLate = isPtr && diff > 45;
      }
    }
    return {
      id: row.doc_id ? `${row.doc_id}-${idx}` : `live-${idx}`,
      filer_name: row.filer_name || "Unknown",
      chamber: row.chamber || "House",
      filed_date: fDate || "",
      trade_date: tDate || "",
      ticker: row.ticker || null,
      asset_name: row.asset_name || "",
      action: row.action || "",
      value_range: row.value_range || "",
      ownership: row.ownership || null,
      doc_id: row.doc_id || null,
      days_late: daysLate,
      is_late: isLate,
    };
  });

  // Filtering (ticker/chamber/sector/dates/filer/action/late) and pagination are
  // applied by the RAG structured search; the returned `total` is the full
  // matching count, so the grid's "of N records" is accurate.
  return NextResponse.json({ records, total, page, pageSize });
}
