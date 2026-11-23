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
    committee: string;
    sector: string;
    trade_count: number;
    total_value: number;
}

export function CommitteeSectorWidget({
    chamber,
    title,
    description,
}: {
    chamber: string;
    title: string;
    description?: string;
}) {
    const chamberParam = chamber === "combined" ? "" : `?chamber=${chamber}`;
    const { data, isLoading } = useQuery({
        queryKey: ["committee-sector", chamber],
        queryFn: () =>
            apiFetch<{ results: Row[] }>(
                proxyUrl(
                    "analytics",
                    `/api/v1/analytics/committee-sector${chamberParam}`,
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
                                <TableHead>Committee</TableHead>
                                <TableHead>Sector</TableHead>
                                <TableHead className="text-right">Trades</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {(data?.results ?? []).map((row, i) => (
                                <TableRow key={`${row.committee}-${row.sector}-${i}`}>
                                    <TableCell className="font-medium">{row.committee}</TableCell>
                                    <TableCell>{row.sector}</TableCell>
                                    <TableCell className="text-right">{row.trade_count}</TableCell>
                                </TableRow>
                            ))}
                            {!data?.results?.length && (
                                <TableRow>
                                    <TableCell colSpan={3} className="text-muted-foreground">
                                        No committee/sector data available.
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
