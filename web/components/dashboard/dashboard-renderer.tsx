"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch, proxyUrl } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TopAssetsWidget } from "./widgets/top-assets-widget";
import { VolumeTrendsWidget } from "./widgets/volume-trends-widget";
import { LateFilingsWidget } from "./widgets/late-filings-widget";
import { CommitteeSectorWidget } from "./widgets/committee-sector-widget";

interface Widget {
    id: string;
    type: string;
    title: string;
    description?: string;
    span: number;
    config: Record<string, unknown>;
}

interface Dashboard {
    scope: string[];
    generated_at: string;
    widgets: Widget[];
}

const REGISTRY: Record<
    string,
    React.ComponentType<{ chamber: string; title: string; description?: string }>
> = {
    top_assets: TopAssetsWidget,
    volume_trends: VolumeTrendsWidget,
    late_filings: LateFilingsWidget,
    committee_sector: CommitteeSectorWidget,
};

/**
 * Schema-driven dashboard renderer (FR-2.1). Mounts a widget component for
 * each descriptor returned by the analytics service.
 */
export function DashboardRenderer({ chamber }: { chamber: string }) {
    const { data, isLoading, error } = useQuery({
        queryKey: ["dashboard"],
        queryFn: () =>
            apiFetch<Dashboard>(proxyUrl("analytics", "/api/v1/analytics/dashboard")),
    });

    if (isLoading) {
        return <p className="text-sm text-muted-foreground">Loading dashboard…</p>;
    }
    if (error) {
        return (
            <p className="text-sm text-destructive">
                Failed to load dashboard: {(error as Error).message}
            </p>
        );
    }

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-semibold capitalize">
                    {chamber} Analytics
                </h1>
                <span className="text-xs text-muted-foreground">
                    Scope: {data?.scope.join(", ")}
                </span>
            </div>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                {data?.widgets.map((widget) => {
                    const Component = REGISTRY[widget.type];
                    if (!Component) {
                        return (
                            <Card key={widget.id}>
                                <CardHeader>
                                    <CardTitle>{widget.title}</CardTitle>
                                </CardHeader>
                                <CardContent className="text-sm text-muted-foreground">
                                    Unknown widget type: {widget.type}
                                </CardContent>
                            </Card>
                        );
                    }
                    return (
                        <div
                            key={widget.id}
                            className={widget.span >= 2 ? "lg:col-span-2" : ""}
                        >
                            <Component
                                chamber={chamber}
                                title={widget.title}
                                description={widget.description}
                            />
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
