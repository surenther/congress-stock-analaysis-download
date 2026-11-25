"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
    Play,
    RotateCw,
    RefreshCw,
    X,
    RotateCcw,
    Ban,
    FileText,
} from "lucide-react";
import { apiFetch, formatDate, timeAgo } from "./api";
import { ApiJob, JobItem, PIPELINE_SERVICES, JOB_STATUSES } from "./types";
import { StatusBadge } from "./StatusBadge";
import { cn } from "@/lib/utils";

interface Props {
    token: string | null;
    onError: (m: string) => void;
    onToast: (m: string) => void;
}

export function PipelineTab({ token, onError, onToast }: Props) {
    const [limit, setLimit] = useState(50);
    const [force, setForce] = useState(false);
    const [chamber, setChamber] = useState("all");
    const [jobs, setJobs] = useState<ApiJob[]>([]);
    const [busy, setBusy] = useState<Record<string, boolean>>({});
    const [loadingJobs, setLoadingJobs] = useState(false);
    const [filterService, setFilterService] = useState("");
    const [filterStatus, setFilterStatus] = useState("");

    const [selected, setSelected] = useState<ApiJob | null>(null);
    const [items, setItems] = useState<JobItem[]>([]);
    const [itemsLoading, setItemsLoading] = useState(false);
    const [actionBusy, setActionBusy] = useState(false);

    const loadJobs = useCallback(async () => {
        setLoadingJobs(true);
        try {
            const params = new URLSearchParams({ limit: "50" });
            if (filterService) params.set("service", filterService);
            if (filterStatus) params.set("status", filterStatus);
            const data = await apiFetch<{ jobs: ApiJob[] }>(
                `/api/admin/jobs?${params.toString()}`,
                token,
            );
            setJobs(data.jobs || []);
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setLoadingJobs(false);
        }
    }, [token, filterService, filterStatus, onError]);

    useEffect(() => {
        loadJobs();
        const interval = setInterval(loadJobs, 10000);
        return () => clearInterval(interval);
    }, [loadJobs]);

    const triggerPipeline = async (key: string) => {
        setBusy((p) => ({ ...p, [key]: true }));
        try {
            const data = await apiFetch<{ result?: { job_id?: string } }>(
                "/api/admin/pipeline",
                token,
                {
                    method: "POST",
                    body: JSON.stringify({ service: key, limit, force, chamber }),
                },
            );
            const jobId = data.result?.job_id || "dispatched";
            onToast(`Triggered ${key} (job ${jobId})`);
            loadJobs();
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setBusy((p) => ({ ...p, [key]: false }));
        }
    };

    const openJob = async (job: ApiJob) => {
        setSelected(job);
        setItems([]);
        setItemsLoading(true);
        try {
            const data = await apiFetch<{ items: JobItem[] }>(
                `/api/admin/jobs/${job.service}/${job.job_id}/items?limit=200`,
                token,
            );
            setItems(data.items || []);
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setItemsLoading(false);
        }
    };

    const retryJob = async (job: ApiJob) => {
        setActionBusy(true);
        try {
            const data = await apiFetch<{ retried?: number; message?: string }>(
                `/api/admin/jobs/${job.service}/${job.job_id}/retry`,
                token,
                { method: "POST" },
            );
            onToast(
                data.message || `Retried ${data.retried ?? 0} failed item(s) for ${job.service}`,
            );
            loadJobs();
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setActionBusy(false);
        }
    };

    const cancelJob = async (job: ApiJob) => {
        setActionBusy(true);
        try {
            const data = await apiFetch<{ message?: string }>(
                `/api/admin/jobs/${job.service}/${job.job_id}/cancel`,
                token,
                { method: "POST" },
            );
            onToast(data.message || `Cancellation requested for ${job.service}`);
            loadJobs();
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setActionBusy(false);
        }
    };

    const isActive = (s: string) =>
        s === "PENDING" || s === "IN_PROGRESS";

    return (
        <div className="space-y-6">
            {/* Trigger controls */}
            <div className="rounded-xl border border-border/50 bg-card p-6">
                <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <h2 className="text-base font-semibold text-foreground">
                            Pipeline Orchestration
                        </h2>
                        <p className="text-xs text-muted-foreground">
                            Manually trigger Downloader (:8511), Parser (:8513), and Vectorizer
                            (:8514).
                        </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-4 text-xs">
                        <div className="flex items-center gap-1.5">
                            <span className="text-muted-foreground">Chamber:</span>
                            <select
                                value={chamber}
                                onChange={(e) => setChamber(e.target.value)}
                                className="rounded-md border border-border/60 bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                            >
                                <option value="all">all</option>
                                <option value="house">house</option>
                                <option value="senate">senate</option>
                            </select>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <span className="text-muted-foreground">Limit:</span>
                            <input
                                type="number"
                                value={limit}
                                onChange={(e) => setLimit(Number(e.target.value))}
                                className="w-16 rounded-md border border-border/60 bg-background px-2 py-1 text-xs font-mono text-foreground focus:outline-none focus:border-emerald-500"
                            />
                        </div>
                        <label className="flex items-center gap-1.5 cursor-pointer text-foreground">
                            <input
                                type="checkbox"
                                checked={force}
                                onChange={(e) => setForce(e.target.checked)}
                                className="rounded border-border text-emerald-500 focus:ring-emerald-500"
                            />
                            <span>Force Re-process</span>
                        </label>
                    </div>
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    {PIPELINE_SERVICES.map((svc) => {
                        const latest = jobs.find((j) => j.service === svc.key);
                        const status = busy[svc.key]
                            ? "running"
                            : latest
                                ? latest.status.toLowerCase()
                                : "idle";
                        return (
                            <div
                                key={svc.key}
                                className="rounded-xl border border-border/40 bg-background/50 p-4 space-y-3"
                            >
                                <div className="flex items-center justify-between">
                                    <div>
                                        <h3 className="text-sm font-semibold text-foreground">
                                            {svc.label}
                                        </h3>
                                        <p className="font-mono text-[11px] text-muted-foreground">
                                            Port :{svc.port}
                                        </p>
                                    </div>
                                    <StatusBadge status={status} />
                                </div>
                                {latest && (
                                    <div className="font-mono text-[11px] text-muted-foreground bg-card p-2 rounded border border-border/30">
                                        {latest.processed_documents ?? 0} /{" "}
                                        {latest.total_documents ?? "—"} processed
                                    </div>
                                )}
                                <button
                                    onClick={() => triggerPipeline(svc.key)}
                                    disabled={busy[svc.key]}
                                    className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-emerald-500/10 py-2 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition-colors border border-emerald-500/30 disabled:opacity-50"
                                >
                                    {busy[svc.key] ? (
                                        <RotateCw className="h-3.5 w-3.5 animate-spin" />
                                    ) : (
                                        <Play className="h-3.5 w-3.5" />
                                    )}
                                    <span>Trigger Job</span>
                                </button>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Job table */}
            <div className="rounded-xl border border-border/50 bg-card p-6">
                <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <h2 className="text-base font-semibold text-foreground">
                        Job History
                    </h2>
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                        <select
                            value={filterService}
                            onChange={(e) => setFilterService(e.target.value)}
                            className="rounded-md border border-border/60 bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                        >
                            <option value="">All services</option>
                            {PIPELINE_SERVICES.map((s) => (
                                <option key={s.key} value={s.key}>
                                    {s.key}
                                </option>
                            ))}
                        </select>
                        <select
                            value={filterStatus}
                            onChange={(e) => setFilterStatus(e.target.value)}
                            className="rounded-md border border-border/60 bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                        >
                            <option value="">All statuses</option>
                            {JOB_STATUSES.map((s) => (
                                <option key={s} value={s}>
                                    {s}
                                </option>
                            ))}
                        </select>
                        <button
                            onClick={loadJobs}
                            disabled={loadingJobs}
                            className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-muted/30 px-2.5 py-1 text-xs text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                        >
                            <RefreshCw
                                className={cn("h-3.5 w-3.5", loadingJobs && "animate-spin")}
                            />
                            Refresh
                        </button>
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                        <thead className="border-b border-border/60 text-[11px] uppercase tracking-wider text-muted-foreground">
                            <tr>
                                <th className="py-2.5 px-3 font-semibold">Service</th>
                                <th className="py-2.5 px-3 font-semibold">Status</th>
                                <th className="py-2.5 px-3 font-semibold">Chamber</th>
                                <th className="py-2.5 px-3 font-semibold">Progress</th>
                                <th className="py-2.5 px-3 font-semibold">Created</th>
                                <th className="py-2.5 px-3 font-semibold text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border/30">
                            {jobs.map((job) => (
                                <tr
                                    key={`${job.service}-${job.job_id}`}
                                    className="hover:bg-muted/20 transition-colors"
                                >
                                    <td className="py-3 px-3">
                                        <div className="font-semibold text-foreground">
                                            {job.service}
                                        </div>
                                        <div className="font-mono text-[10px] text-muted-foreground">
                                            {job.job_id.slice(0, 8)}
                                        </div>
                                    </td>
                                    <td className="py-3 px-3">
                                        <StatusBadge status={job.status} />
                                    </td>
                                    <td className="py-3 px-3 text-muted-foreground">
                                        {job.chamber || "—"}
                                    </td>
                                    <td className="py-3 px-3 font-mono text-muted-foreground">
                                        {job.processed_documents ?? 0} / {job.total_documents ?? "—"}
                                    </td>
                                    <td className="py-3 px-3 text-muted-foreground">
                                        {timeAgo(job.created_at)}
                                    </td>
                                    <td className="py-3 px-3">
                                        <div className="flex items-center justify-end gap-1.5">
                                            <button
                                                onClick={() => openJob(job)}
                                                className="flex items-center gap-1 rounded border border-border/60 bg-muted/30 px-2 py-1 text-[11px] text-foreground hover:bg-accent transition-colors"
                                            >
                                                <FileText className="h-3 w-3 text-muted-foreground" />
                                                Details
                                            </button>
                                            {isActive(job.status) && (
                                                <button
                                                    onClick={() => cancelJob(job)}
                                                    disabled={actionBusy}
                                                    className="flex items-center gap-1 rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[11px] text-rose-400 hover:bg-rose-500/20 transition-colors disabled:opacity-50"
                                                >
                                                    <Ban className="h-3 w-3" />
                                                    Cancel
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                            {jobs.length === 0 && (
                                <tr>
                                    <td
                                        colSpan={6}
                                        className="py-8 text-center text-muted-foreground"
                                    >
                                        No jobs found.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Detail drawer */}
            {selected && (
                <div className="fixed inset-0 z-50 flex justify-end">
                    <div
                        className="absolute inset-0 bg-black/50"
                        onClick={() => setSelected(null)}
                    />
                    <div className="relative z-10 h-full w-full max-w-xl overflow-y-auto border-l border-border bg-card p-6 shadow-2xl">
                        <div className="mb-4 flex items-start justify-between">
                            <div>
                                <h3 className="text-base font-semibold text-foreground">
                                    {selected.service} job
                                </h3>
                                <p className="font-mono text-[11px] text-muted-foreground">
                                    {selected.job_id}
                                </p>
                            </div>
                            <button
                                onClick={() => setSelected(null)}
                                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>

                        <div className="mb-4 grid grid-cols-2 gap-3 text-xs">
                            <Detail label="Status">
                                <StatusBadge status={selected.status} />
                            </Detail>
                            <Detail label="Chamber">{selected.chamber || "—"}</Detail>
                            <Detail label="Progress">
                                {selected.processed_documents ?? 0} /{" "}
                                {selected.total_documents ?? "—"}
                            </Detail>
                            <Detail label="Cost">
                                {selected.total_cost != null
                                    ? `$${selected.total_cost.toFixed(4)}`
                                    : "—"}
                            </Detail>
                            <Detail label="Created">{formatDate(selected.created_at)}</Detail>
                            <Detail label="Updated">{formatDate(selected.updated_at)}</Detail>
                        </div>

                        {selected.error_message && (
                            <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-950/40 p-3 text-[11px] text-amber-300">
                                {selected.error_message}
                            </div>
                        )}

                        <div className="mb-3 flex items-center gap-2">
                            <button
                                onClick={() => retryJob(selected)}
                                disabled={actionBusy}
                                className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition-colors disabled:opacity-50"
                            >
                                <RotateCcw className="h-3.5 w-3.5" />
                                Retry Failed
                            </button>
                            {isActive(selected.status) && (
                                <button
                                    onClick={() => cancelJob(selected)}
                                    disabled={actionBusy}
                                    className="flex items-center gap-1.5 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-400 hover:bg-rose-500/20 transition-colors disabled:opacity-50"
                                >
                                    <Ban className="h-3.5 w-3.5" />
                                    Cancel Job
                                </button>
                            )}
                        </div>

                        <h4 className="mb-2 text-sm font-semibold text-foreground">
                            Per-document outcomes
                        </h4>
                        {itemsLoading ? (
                            <p className="text-xs text-muted-foreground">Loading…</p>
                        ) : items.length === 0 ? (
                            <p className="text-xs text-muted-foreground">No items recorded.</p>
                        ) : (
                            <div className="space-y-1.5">
                                {items.map((item, idx) => (
                                    <div
                                        key={`${item.doc_id}-${idx}`}
                                        className="rounded-lg border border-border/40 bg-background/50 p-2.5"
                                    >
                                        <div className="flex items-center justify-between gap-2">
                                            <span className="truncate font-mono text-[11px] text-foreground">
                                                {item.doc_id || item.file_path || "—"}
                                            </span>
                                            <StatusBadge status={item.status} />
                                        </div>
                                        {item.detail && (
                                            <p className="mt-1 text-[10px] text-muted-foreground">
                                                {item.detail}
                                            </p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

function Detail({
    label,
    children,
}: {
    label: string;
    children: React.ReactNode;
}) {
    return (
        <div className="rounded-lg border border-border/40 bg-background/50 p-2.5">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                {label}
            </p>
            <div className="mt-0.5 text-foreground">{children}</div>
        </div>
    );
}
