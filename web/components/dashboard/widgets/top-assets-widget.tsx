"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch, proxyUrl } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";

interface Row {
    ticker: string;
    asset_name: string;
    action: string;
    trade_count: number;
    total_value: number;
}

export function TopAssetsWidget({
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
        queryKey: ["top-assets", chamber],
        queryFn: () =>
            apiFetch<{ results: Row[] }>(
                proxyUrl(
                    "analytics",
                    `/api/v1/analytics/top-assets?${chamberParam}limit=10`,
                ),
            ),
    });

    return (
        <Card>
            <CardHeader>
                <CardTitle>{title}</CardTitle>
                {description && (
                    <p className="text-sm text-muted-foreground">{description}</p>
                )}
            </CardHeader>
            <CardContent>
                {isLoading ? (
                    <p className="text-sm text-muted-foreground">Loading…</p>
                ) : (
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Ticker</TableHead>
                                <TableHead>Asset</TableHead>
                                <TableHead>Action</TableHead>
                                <TableHead className="text-right">Trades</TableHead>
                                <TableHead className="text-right">Est. Value</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {(data?.results ?? []).map((row, i) => (
                                <TableRow key={`${row.ticker}-${row.action}-${i}`}>
                                    <TableCell className="font-medium">
                                        {row.ticker ? (
                                            row.ticker
                                        ) : (
                                            <span className="text-muted-foreground">—</span>
                                        )}
                                    </TableCell>
                                    <TableCell className="max-w-[200px] truncate">
                                        {row.asset_name ? (
                                            row.asset_name
                                        ) : (
                                            <span className="text-muted-foreground">—</span>
                                        )}
                                    </TableCell>
                                    <TableCell>{row.action}</TableCell>
                                    <TableCell className="text-right">{row.trade_count}</TableCell>
                                    <TableCell className="text-right">
                                        ${Math.round(row.total_value).toLocaleString()}
                                    </TableCell>
                                </TableRow>
                            ))}
                            {!data?.results?.length && (
                                <TableRow>
                                    <TableCell colSpan={5} className="text-muted-foreground">
                                        No data in scope.
                                    </TableCell>
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                )}
            </CardContent>
        </Card>
    );
}
