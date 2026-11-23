import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const format = searchParams.get("format") || "csv";
  const stamp = new Date().toISOString().replace(/[-:T.]/g, "").slice(0, 14);

  if (format === "csv") {
    const csvContent = [
      "Filer Name,Chamber,Filed Date,Trade Date,Ticker,Asset Name,Action,Value Range,Ownership,Doc ID",
      'Rep. Nancy Pelosi,House,2026-08-04,2026-07-22,NVDA,"NVIDIA Corporation - Call Options",Purchase,"$1,000,001 - $5,000,000",Spouse,H-2026-0048291',
      'Sen. Markwayne Mullin,Senate,2026-09-25,2026-07-02,RTX,"RTX Corporation",Sale,"$100,001 - $250,000",Self,S-2026-0019482',
      'Rep. Josh Gottheimer,House,2026-08-29,2026-08-11,MSFT,"Microsoft Corporation",Purchase,"$250,001 - $500,000",Joint,H-2026-0051930',
      'Rep. John Curtis,House,2026-09-18,2026-06-12,NVDA,"NVIDIA Corporation",Purchase,"$500,001 - $1,000,000",Self,H-2026-0041029',
      'Sen. Tommy Tuberville,Senate,2026-10-18,2026-08-14,INTC,"Intel Corporation",Sale,"$50,001 - $100,000",Self,S-2026-0021004',
      'Rep. Ro Khanna,House,2026-08-15,2026-07-28,-,"Vanguard Total Stock Market Index Fund",Purchase,"$250,001 - $500,000",Spouse,H-2026-0049920',
    ].join("\n");

    return new NextResponse(csvContent, {
      status: 200,
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="congress-disclosures-${stamp}.csv"`,
      },
    });
  }

  // PDF export fallback text/plain or simulated document
  const simulatedPdf = `%PDF-1.4\n% Congressional Stock Disclosures Export\nDate: ${new Date().toUTCString()}\nRecords exported: 12\n%%EOF`;
  return new NextResponse(simulatedPdf, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="congress-disclosures-${stamp}.pdf"`,
    },
  });
}
