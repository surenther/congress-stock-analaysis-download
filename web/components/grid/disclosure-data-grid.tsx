"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { apiFetch, proxyUrl } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";

interface Row {
    doc_id: string;
    filer_name: string;
    chamber: string;
    filing_date: string;
    transaction_date: string;
    ticker: string;
    asset_name: string;
    action: string;
    value_range: string;
    sector: string;
}

interface Filters {
    ticker: string;
    member: string;
    action: string;
    start_date: string;
    end_date: string;
    min_value: string;
    max_value: string;
}

const EMPTY: Filters = {
    ticker: "",
    member: "",
    action: "",
    start_date: "",
    end_date: "",
    min_value: "",
    max_value: "",
};

function buildQuery(filters: Filters, limit: number, offset: number): string {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
        if (v) params.set(k, v);
    });
    params.set("limit", String(limit));
    params.set("offset", String(offset));
    return params.toString();
}

export function DisclosureDataGrid({ chamber }: { chamber: string }) {
    const [filters, setFilters] = useState<Filters>(EMPTY);
    const [applied, setApplied] = useState<Filters>(EMPTY);
    const [page, setPage] = useState(0);
    const limit = 25;

    const chamberParam = chamber === "combined" ? {} : { chamber };
    const query = buildQuery({ ...applied, ...chamberParam } as Filters, limit, page * limit);

    const { data, isLoading } = useQuery({
        queryKey: ["disclosures", chamber, applied, page],
        queryFn: () =>
            apiFetch<{ total: number; results: Row[] }>(
                proxyUrl("analytics", `/api/v1/analytics/disclosures?${query}`),
            ),
    });

    const total = data?.total ?? 0;
    const pages = Math.max(1, Math.ceil(total / limit));

    function exportAs(format: "csv" | "pdf") {
        const exportQuery = buildQuery(
            { ...applied, ...chamberParam } as Filters,
            1000,
            0,
        );
        window.open(
            proxyUrl("analytics", `/api/v1/analytics/export?format=${format}&${exportQuery}`),
            "_blank",
        );
    }

    return (
        <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle>Disclosure Records</CardTitle>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => exportAs("csv")}>
                        <Download className="h-4 w-4" /> CSV
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => exportAs("pdf")}>
                        <Download className="h-4 w-4" /> PDF
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                    <div className="space-y-1">
                        <Label htmlFor="ticker">Ticker</Label>
                        <Input
                            id="ticker"
                            value={filters.ticker}
                            onChange={(e) => setFilters({ ...filters, ticker: e.target.value })}
                        />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="member">Member</Label>
                        <Input
                            id="member"
                            value={filters.member}
                            onChange={(e) => setFilters({ ...filters, member: e.target.value })}
                        />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="action">Action</Label>
                        <Input
                            id="action"
                            placeholder="Purchase / Sale"
                            value={filters.action}
                            onChange={(e) => setFilters({ ...filters, action: e.target.value })}
                        />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="start">Start date</Label>
                        <Input
                            id="start"
                            type="date"
                            value={filters.start_date}
                            onChange={(e) =>
                                setFilters({ ...filters, start_date: e.target.value })
                            }
                        />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="end">End date</Label>
                        <Input
                            id="end"
                            type="date"
                            value={filters.end_date}
                            onChange={(e) =>
                                setFilters({ ...filters, end_date: e.target.value })
                            }
                        />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="min">Min value</Label>
                        <Input
                            id="min"
                            type="number"
                            value={filters.min_value}
                            onChange={(e) =>
                                setFilters({ ...filters, min_value: e.target.value })
                            }
                        />
                    </div>
                    <div className="space-y-1">
                        <Label htmlFor="max">Max value</Label>
                        <Input
                            id="max"
                            type="number"
                            value={filters.max_value}
                            onChange={(e) =>
                                setFilters({ ...filters, max_value: e.target.value })
                            }
                        />
                    </div>
                    <div className="flex items-end">
                        <Button
                            className="w-full"
                            onClick={() => {
                                setApplied(filters);
                                setPage(0);
                            }}
                        >
                            Apply filters
                        </Button>
                    </div>
                </div>

                {isLoading ? (
                    <p className="text-sm text-muted-foreground">Loading…</p>
                ) : (
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Filer</TableHead>
                                <TableHead>Chamber</TableHead>
                                <TableHead>Filed</TableHead>
                                <TableHead>Ticker</TableHead>
                                <TableHead>Action</TableHead>
                                <TableHead>Value</TableHead>
                                <TableHead>Sector</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {(data?.results ?? []).map((row, i) => (
                                <TableRow key={`${row.doc_id}-${i}`}>
                                    <TableCell className="font-medium">{row.filer_name}</TableCell>
                                    <TableCell>{row.chamber}</TableCell>
                                    <TableCell>{row.filing_date}</TableCell>
                                    <TableCell>{row.ticker}</TableCell>
                                    <TableCell>{row.action}</TableCell>
                                    <TableCell>{row.value_range}</TableCell>
                                    <TableCell>{row.sector}</TableCell>
                                </TableRow>
                            ))}
                            {!data?.results?.length && (
                                <TableRow>
                                    <TableCell colSpan={7} className="text-muted-foreground">
                                        No records match the filters.
                                    </TableCell>
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                )}

                <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">
                        {total.toLocaleString()} records
                    </span>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={page === 0}
                            onClick={() => setPage((p) => Math.max(0, p - 1))}
                        >
                            Previous
                        </Button>
                        <span>
                            Page {page + 1} of {pages}
                        </span>
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={page + 1 >= pages}
                            onClick={() => setPage((p) => p + 1)}
                        >
                            Next
                        </Button>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
