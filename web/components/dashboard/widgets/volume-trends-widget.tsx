"use client";

import { useQuery } from "@tanstack/react-query";
import {
    Bar,
    BarChart,
    CartesianGrid,
    Legend,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";
import { apiFetch, proxyUrl } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Point {
    period: string;
    action: string;
    trade_count: number;
    total_value: number;
}

export function VolumeTrendsWidget({
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
        queryKey: ["volume-trends", chamber],
        queryFn: () =>
            apiFetch<{ results: Point[] }>(
                proxyUrl(
                    "analytics",
                    `/api/v1/analytics/volume-trends?${chamberParam}granularity=month`,
                ),
            ),
    });

    // Pivot rows into { period, Purchase, Sale } for a grouped bar chart.
    const byPeriod = new Map<string, Record<string, number | string>>();
    for (const row of data?.results ?? []) {
        const key = String(row.period);
        const entry = byPeriod.get(key) ?? { period: key };
        entry[row.action] = row.trade_count;
        byPeriod.set(key, entry);
    }
    const chartData = Array.from(byPeriod.values());

    return (
        <Card>
            <CardHeader>
                <CardTitle>{title}</CardTitle>
                {description && (
                    <p className="text-sm text-muted-foreground">{description}</p>
                )}
            </CardHeader>
            <CardContent className="h-72">
                {isLoading ? (
                    <p className="text-sm text-muted-foreground">Loading…</p>
                ) : (
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="period" fontSize={12} />
                            <YAxis fontSize={12} />
                            <Tooltip />
                            <Legend />
                            <Bar dataKey="Purchase" fill="#2563eb" />
                            <Bar dataKey="Sale" fill="#dc2626" />
                        </BarChart>
                    </ResponsiveContainer>
                )}
            </CardContent>
        </Card>
    );
}
