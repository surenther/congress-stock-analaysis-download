import { NextRequest, NextResponse } from "next/server";
import { DisclosureRecord } from "@/types/disclosure";

// Mock disclosure database records adhering strictly to schema rules
const MOCK_DISCLOSURES: DisclosureRecord[] = [
  {
    id: "dis-001",
    filer_name: "Rep. Nancy Pelosi",
    chamber: "House",
    filed_date: "2026-08-04",
    trade_date: "2026-07-22",
    ticker: "NVDA",
    asset_name: "NVIDIA Corporation - Call Options",
    action: "Purchase",
    value_range: "$1,000,001 - $5,000,000",
    ownership: "Spouse",
    doc_id: "H-2026-0048291",
    days_late: 13,
    is_late: false,
  },
  {
    id: "dis-002",
    filer_name: "Sen. Markwayne Mullin",
    chamber: "Senate",
    filed_date: "2026-09-25",
    trade_date: "2026-07-02",
    ticker: "RTX",
    asset_name: "RTX Corporation",
    action: "Sale",
    value_range: "$100,001 - $250,000",
    ownership: "Self",
    doc_id: "S-2026-0019482",
    days_late: 85,
    is_late: true,
  },
  {
    id: "dis-003",
    filer_name: "Rep. Josh Gottheimer",
    chamber: "House",
    filed_date: "2026-08-29",
    trade_date: "2026-08-11",
    ticker: "MSFT",
    asset_name: "Microsoft Corporation",
    action: "Purchase",
    value_range: "$250,001 - $500,000",
    ownership: "Joint",
    doc_id: "H-2026-0051930",
    days_late: 18,
    is_late: false,
  },
  {
    id: "dis-004",
    filer_name: "Rep. John Curtis",
    chamber: "House",
    filed_date: "2026-09-18",
    trade_date: "2026-06-12",
    ticker: "NVDA",
    asset_name: "NVIDIA Corporation",
    action: "Purchase",
    value_range: "$500,001 - $1,000,000",
    ownership: "Self",
    doc_id: "H-2026-0041029",
    days_late: 98,
    is_late: true,
  },
  {
    id: "dis-005",
    filer_name: "Sen. Tommy Tuberville",
    chamber: "Senate",
    filed_date: "2026-10-18",
    trade_date: "2026-08-14",
    ticker: "INTC",
    asset_name: "Intel Corporation",
    action: "Sale",
    value_range: "$50,001 - $100,000",
    ownership: "Self",
    doc_id: "S-2026-0021004",
    days_late: 65,
    is_late: true,
  },
  {
    id: "dis-006",
    filer_name: "Rep. Marjorie Taylor Greene",
    chamber: "House",
    filed_date: "2026-10-10",
    trade_date: "2026-08-01",
    ticker: "LMT",
    asset_name: "Lockheed Martin Corp.",
    action: "Purchase",
    value_range: "$15,001 - $50,000",
    ownership: "Self",
    doc_id: "H-2026-0055102",
    days_late: 70,
    is_late: true,
  },
  {
    id: "dis-007",
    filer_name: "Sen. Maria Cantwell",
    chamber: "Senate",
    filed_date: "2026-09-10",
    trade_date: "2026-08-20",
    ticker: "AMZN",
    asset_name: "Amazon.com, Inc.",
    action: "Purchase",
    value_range: "$100,001 - $250,000",
    ownership: "Spouse",
    doc_id: "S-2026-0020115",
    days_late: 21,
    is_late: false,
  },
  {
    id: "dis-008",
    filer_name: "Rep. French Hill",
    chamber: "House",
    filed_date: "2026-09-02",
    trade_date: "2026-08-15",
    ticker: "JPM",
    asset_name: "JPMorgan Chase & Co.",
    action: "Purchase",
    value_range: "$50,001 - $100,000",
    ownership: "Self",
    doc_id: "H-2026-0053911",
    days_late: 18,
    is_late: false,
  },
  {
    id: "dis-009",
    filer_name: "Sen. Jack Reed",
    chamber: "Senate",
    filed_date: "2026-08-25",
    trade_date: "2026-08-05",
    ticker: "GD",
    asset_name: "General Dynamics Corp.",
    action: "Purchase",
    value_range: "$15,001 - $50,000",
    ownership: "Joint",
    doc_id: "S-2026-0019912",
    days_late: 20,
    is_late: false,
  },
  {
    id: "dis-010",
    filer_name: "Rep. Ro Khanna",
    chamber: "House",
    filed_date: "2026-08-15",
    trade_date: "2026-07-28",
    ticker: null,
    asset_name: "Vanguard Total Stock Market Index Fund",
    action: "Purchase",
    value_range: "$250,001 - $500,000",
    ownership: "Spouse",
    doc_id: "H-2026-0049920",
    days_late: 18,
    is_late: false,
  },
  {
    id: "dis-011",
    filer_name: "Rep. Ro Khanna",
    chamber: "House",
    filed_date: "2026-08-15",
    trade_date: "2026-07-28",
    ticker: null,
    asset_name: "Fidelity Government Money Market Fund",
    action: "Sale",
    value_range: "$100,001 - $250,000",
    ownership: "Spouse",
    doc_id: "H-2026-0049921",
    days_late: 18,
    is_late: false,
  },
  {
    id: "dis-012",
    filer_name: "Sen. Mitch McConnell",
    chamber: "Senate",
    filed_date: "2026-07-30",
    trade_date: "2026-07-10",
    ticker: "WMT",
    asset_name: "Walmart Inc.",
    action: "Purchase",
    value_range: "$50,001 - $100,000",
    ownership: "Spouse",
    doc_id: "S-2026-0018890",
    days_late: 20,
    is_late: false,
  },
];

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const ticker = (searchParams.get("ticker") || "").trim().toUpperCase();
  const filerName = (searchParams.get("filer_name") || "").trim().toLowerCase();
  const action = (searchParams.get("action") || "").trim();
  const chamber = (searchParams.get("chamber") || "").trim();
  const startDate = searchParams.get("start_date");
  const endDate = searchParams.get("end_date");
  const page = parseInt(searchParams.get("page") || "1", 10);
  const pageSize = parseInt(searchParams.get("page_size") || "12", 10);

  // Filter records
  let filtered = MOCK_DISCLOSURES.filter((rec) => {
    if (ticker && (!rec.ticker || !rec.ticker.toUpperCase().includes(ticker))) {
      return false;
    }
    if (filerName && !rec.filer_name.toLowerCase().includes(filerName)) {
      return false;
    }
    if (action && action !== "All" && !rec.action.toLowerCase().includes(action.toLowerCase())) {
      return false;
    }
    if (chamber && chamber !== "All" && rec.chamber.toLowerCase() !== chamber.toLowerCase()) {
      return false;
    }
    if (startDate && rec.trade_date < startDate) {
      return false;
    }
    if (endDate && rec.trade_date > endDate) {
      return false;
    }
    return true;
  });

  const total = filtered.length;
  const startIdx = (page - 1) * pageSize;
  const paginated = filtered.slice(startIdx, startIdx + pageSize);

  return NextResponse.json({
    records: paginated,
    total,
    page,
    pageSize,
  });
}
