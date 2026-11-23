"use client";

import { FileText } from "lucide-react";

export interface Citation {
    doc_id?: string;
    document_id?: string;
    filer_name?: string;
    chamber?: string;
    filing_date?: string;
    ticker?: string;
    asset_name?: string;
    action?: string;
    date?: string;
    value_range?: string;
    similarity_score?: number;
}

/** Grounded source metadata card (FR-3.3). */
export function CitationCard({ citation }: { citation: Citation }) {
    return (
        <div className="rounded-md border p-2 text-xs">
            <div className="flex items-center gap-2 font-medium">
                <FileText className="h-3.5 w-3.5" />
                {citation.filer_name ?? "Unknown filer"}
            </div>
            <div className="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5 text-muted-foreground">
                <span>Chamber: {citation.chamber ?? "—"}</span>
                <span>Filed: {citation.filing_date ?? "—"}</span>
                <span>Ticker: {citation.ticker ?? "—"}</span>
                <span>Value: {citation.value_range ?? "—"}</span>
                <span className="col-span-2">
                    Doc ID: {citation.document_id ?? citation.doc_id ?? "—"}
                </span>
            </div>
        </div>
    );
}
