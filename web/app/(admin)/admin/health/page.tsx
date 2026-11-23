"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch, proxyUrl } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface ServiceHealth {
    service: string;
    url: string;
    status: string;
    http_status: number | null;
    latency_ms: number;
    error?: string;
}

export default function AdminHealthPage() {
    const { data, isLoading } = useQuery({
        queryKey: ["cluster-health"],
        queryFn: () =>
            apiFetch<{ checked_at: string; services: ServiceHealth[] }>(
                proxyUrl("admin", "/api/v1/admin/health/cluster"),
            ),
        refetchInterval: 10000,
    });

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-semibold">Cluster Health</h1>
            <Card>
                <CardHeader>
                    <CardTitle>Microservice status</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                    {isLoading ? (
                        <p className="text-sm text-muted-foreground">Checking…</p>
                    ) : !data?.services?.length ? (
                        <p className="text-sm text-muted-foreground">
                            No services reported.
                        </p>
                    ) : (
                        (data?.services ?? []).map((svc) => (
                            <div
                                key={svc.service}
                                className="flex items-center justify-between rounded-md border p-3 text-sm"
                            >
                                <div className="flex items-center gap-3">
                                    <span
                                        className={`h-2.5 w-2.5 rounded-full ${svc.status === "healthy"
                                            ? "bg-emerald-500"
                                            : svc.status === "unhealthy"
                                                ? "bg-amber-500"
                                                : "bg-red-500"
                                            }`}
                                    />
                                    <span className="font-medium">{svc.service}</span>
                                    <span className="text-xs text-muted-foreground">{svc.url}</span>
                                </div>
                                <div className="flex items-center gap-3">
                                    <span className="text-xs text-muted-foreground">
                                        {svc.latency_ms} ms
                                    </span>
                                    <Badge
                                        variant={
                                            svc.status === "healthy"
                                                ? "success"
                                                : svc.status === "unhealthy"
                                                    ? "warning"
                                                    : "destructive"
                                        }
                                    >
                                        {svc.status}
                                    </Badge>
                                </div>
                            </div>
                        ))
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
