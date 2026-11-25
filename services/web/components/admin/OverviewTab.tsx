"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, Server, CheckCircle2, XCircle } from "lucide-react";
import { apiFetch, timeAgo } from "./api";
import { ApiJob, ClusterService, JobSummary } from "./types";
import { StatusBadge } from "./StatusBadge";
import { cn } from "@/lib/utils";

interface Props {
    token: string | null;
    onError: (m: string) => void;
}

const STATUS_ORDER = [
    "COMPLETED",
    "IN_PROGRESS",
    "PENDING",
    "FAILED",
    "CANCELLED",
];

export function OverviewTab({ token, onError }: Props) {
    const [summary, setSummary] = useState<JobSummary | null>(null);
    const [cluster, setCluster] = useState<ClusterService[]>([]);
    const [recent, setRecent] = useState<ApiJob[]>([]);
    const [loading, setLoading] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [s, c, j] = await Promise.all([
                apiFetch<JobSummary>("/api/admin/jobs/summary", token),
                apiFetch<{ services: ClusterService[] }>(
                    "/api/health/cluster",
                    token,
                ).catch(() => ({ services: [] as ClusterService[] })),
                apiFetch<{ jobs: ApiJob[] }>("/api/admin/jobs?limit=8", token),
            ]);
            setSummary(s);
            setCluster(c.services || []);
            setRecent(j.jobs || []);
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, [token, onError]);

    useEffect(() => {
        load();
        const interval = setInterval(load, 20000);
        return () => clearInterval(interval);
    }, [load]);

    const byService = summary?.by_service || {};
    const byStatus = summary?.by_status || {};

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-foreground">
                    Cluster Overview
                </h2>
                <button
                    onClick={load}
                    disabled={loading}
                    className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-muted/30 px-2.5 py-1 text-xs text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                >
                    <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
                    Refresh
                </button>
            </div>

            {/* Summary tiles */}
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <Tile label="Total Jobs" value={summary?.total ?? "—"} accent="emerald" />
                {(["downloader", "parser", "vectorizer"] as const).map((svc) => (
                    <Tile
                        key={svc}
                        label={svc}
                        value={byService[svc] ?? 0}
                        accent="blue"
                    />
                ))}
            </div>

            {/* Status breakdown */}
            <div className="rounded-xl border border-border/50 bg-card p-5">
                <h3 className="mb-3 text-sm font-semibold text-foreground">
                    Jobs by Status
                </h3>
                <div className="flex flex-wrap gap-3">
                    {STATUS_ORDER.map((st) => (
                        <div
                            key={st}
                            className="flex items-center gap-2 rounded-lg border border-border/40 bg-background/50 px-3 py-2"
                        >
                            <StatusBadge status={st} />
                            <span className="font-mono text-sm text-foreground">
                                {byStatus[st] ?? 0}
                            </span>
                        </div>
                    ))}
                </div>
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                {/* Cluster health */}
                <div className="rounded-xl border border-border/50 bg-card p-5">
                    <div className="mb-3 flex items-center gap-2">
                        <Activity className="h-4 w-4 text-emerald-400" />
                        <h3 className="text-sm font-semibold text-foreground">
                            Service Health
                        </h3>
                    </div>
                    <div className="space-y-2">
                        {cluster.length === 0 && (
                            <p className="text-xs text-muted-foreground">
                                No health data available.
                            </p>
                        )}
                        {cluster.map((svc) => (
                            <div
                                key={svc.name}
                                className="flex items-center justify-between rounded-lg border border-border/40 bg-background/50 px-3 py-2"
                            >
                                <div className="flex items-center gap-2">
                                    <Server className="h-3.5 w-3.5 text-muted-foreground" />
                                    <span className="text-xs font-medium text-foreground">
                                        {svc.name}
                                    </span>
                                    <span className="font-mono text-[10px] text-muted-foreground">
                                        :{svc.port}
                                    </span>
                                </div>
                                <div className="flex items-center gap-2">
                                    {svc.latency_ms !== undefined && (
                                        <span className="font-mono text-[10px] text-muted-foreground">
                                            {svc.latency_ms}ms
                                        </span>
                                    )}
                                    {svc.healthy ? (
                                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-400">
                                            <CheckCircle2 className="h-3 w-3" /> Healthy
                                        </span>
                                    ) : (
                                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-rose-400">
                                            <XCircle className="h-3 w-3" /> Offline
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Recent jobs */}
                <div className="rounded-xl border border-border/50 bg-card p-5">
                    <h3 className="mb-3 text-sm font-semibold text-foreground">
                        Recent Jobs
                    </h3>
                    <div className="space-y-2">
                        {recent.length === 0 && (
                            <p className="text-xs text-muted-foreground">No jobs yet.</p>
                        )}
                        {recent.map((job) => (
                            <div
                                key={`${job.service}-${job.job_id}`}
                                className="flex items-center justify-between rounded-lg border border-border/40 bg-background/50 px-3 py-2"
                            >
                                <div className="min-w-0">
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs font-medium text-foreground">
                                            {job.service}
                                        </span>
                                        <StatusBadge status={job.status} />
                                    </div>
                                    <div className="truncate font-mono text-[10px] text-muted-foreground">
                                        {job.job_id}
                                    </div>
                                </div>
                                <span className="shrink-0 text-[10px] text-muted-foreground">
                                    {timeAgo(job.created_at)}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}

function Tile({
    label,
    value,
    accent,
}: {
    label: string;
    value: number | string;
    accent: "emerald" | "blue";
}) {
    return (
        <div className="rounded-xl border border-border/50 bg-card p-4">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
                {label}
            </p>
            <p
                className={cn(
                    "mt-1 text-2xl font-bold",
                    accent === "emerald" ? "text-emerald-400" : "text-blue-400",
                )}
            >
                {value}
            </p>
        </div>
    );
}
