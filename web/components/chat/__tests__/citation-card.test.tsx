import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CitationCard } from "../citation-card";

describe("CitationCard", () => {
    it("renders the grounded citation metadata", () => {
        render(
            <CitationCard
                citation={{
                    doc_id: "10073198",
                    filer_name: "Laurie Buckhout",
                    chamber: "House",
                    filing_date: "2026-01-24",
                    ticker: "NVDA",
                    value_range: "$15,001 - $50,000",
                }}
            />,
        );
        expect(screen.getByText("Laurie Buckhout")).toBeInTheDocument();
        expect(screen.getByText(/House/)).toBeInTheDocument();
        expect(screen.getByText(/NVDA/)).toBeInTheDocument();
        expect(screen.getByText(/10073198/)).toBeInTheDocument();
    });
});
