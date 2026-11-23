"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { apiFetch, proxyUrl } from "@/lib/api-client";
import { orPlaceholder } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface Row {
    doc_id: string;
    item_index?: number;
    filer_name: string;
    chamber: string;
    filing_date: string;
    transaction_date: string;
    days_to_file: number;
    ticker: string | null;
    asset_name: string | null;
    action: string;
    value_range: string;
}

export function LateFilingsWidget({
    chamber,
    title,
    description,
}: {
    chamber: string;
    title: string;
    description?: string;
}) {
    const chamberParam = chamber === "combined" ? "" : `chamber=${chamber}&`;
    const { data, isLoading } = useQuery({
        queryKey: ["late-filings", chamber],
        queryFn: () =>
            apiFetch<{ total: number; results: Row[] }>(
                proxyUrl(
                    "analytics",
                    `/api/v1/analytics/late-filings?${chamberParam}limit=10`,
                ),
            ),
    });

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-500" />
                    {title}
                </CardTitle>
                {description && (
                    <p className="text-sm text-muted-foreground">{description}</p>
                )}
            </CardHeader>
            <CardContent className="space-y-2">
                {isLoading ? (
                    <p className="text-sm text-muted-foreground">Loading…</p>
                ) : (
                    <>
                        <p className="text-sm text-muted-foreground">
                            {data?.total ?? 0} filings beyond the 45-day window
                        </p>
                        {(data?.results ?? []).map((row, index) => (
                            <div
                                key={`${row.doc_id}-${row.item_index ?? index}`}
                                className="flex items-center justify-between rounded-md border p-2 text-sm"
                            >
                                <div>
                                    <div className="font-medium">
                                        {row.filer_name} —{" "}
                                        {orPlaceholder(row.ticker || row.asset_name)} (
                                        {orPlaceholder(row.action)})
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        {orPlaceholder(row.value_range)}
                                    </div>
                                </div>
                                <Badge variant="warning">+{row.days_to_file}d</Badge>
                            </div>
                        ))}
                        {!data?.results?.length && (
                            <p className="text-sm text-muted-foreground">
                                No late filings in scope.
                            </p>
                        )}
                    </>
                )}
            </CardContent>
        </Card>
    );
}
