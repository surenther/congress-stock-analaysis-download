"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Plus, Trash2, RefreshCw, Clock } from "lucide-react";
import { apiFetch, formatDate } from "./api";
import { Schedule, PIPELINE_SERVICES } from "./types";
import { cn } from "@/lib/utils";

interface Props {
    token: string | null;
    onError: (m: string) => void;
    onToast: (m: string) => void;
}

export function SchedulesTab({ token, onError, onToast }: Props) {
    const [schedules, setSchedules] = useState<Schedule[]>([]);
    const [loading, setLoading] = useState(false);
    const [service, setService] = useState("downloader");
    const [chamber, setChamber] = useState("");
    const [interval, setIntervalMinutes] = useState(60);
    const [creating, setCreating] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const data = await apiFetch<{ schedules: Schedule[] }>(
                "/api/admin/schedules",
                token,
            );
            setSchedules(data.schedules || []);
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, [token, onError]);

    useEffect(() => {
        load();
    }, [load]);

    const create = async () => {
        setCreating(true);
        try {
            await apiFetch("/api/admin/schedules", token, {
                method: "POST",
                body: JSON.stringify({
                    service,
                    chamber: chamber || null,
                    interval_minutes: interval,
                }),
            });
            onToast(`Created ${service} schedule every ${interval} min`);
            load();
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setCreating(false);
        }
    };

    const remove = async (id: string) => {
        try {
            await apiFetch(`/api/admin/schedules/${id}`, token, { method: "DELETE" });
            onToast("Schedule deleted");
            load();
        } catch (e) {
            onError((e as Error).message);
        }
    };

    return (
        <div className="space-y-6">
            {/* Create form */}
            <div className="rounded-xl border border-border/50 bg-card p-6">
                <h2 className="mb-1 text-base font-semibold text-foreground">
                    Recurring Schedules
                </h2>
                <p className="mb-4 text-xs text-muted-foreground">
                    Automatically trigger a pipeline service on a fixed interval.
                </p>
                <div className="flex flex-wrap items-end gap-3 text-xs">
                    <div className="flex flex-col gap-1">
                        <label className="text-muted-foreground">Service</label>
                        <select
                            value={service}
                            onChange={(e) => setService(e.target.value)}
                            className="rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                        >
                            {PIPELINE_SERVICES.map((s) => (
                                <option key={s.key} value={s.key}>
                                    {s.key}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="flex flex-col gap-1">
                        <label className="text-muted-foreground">Chamber</label>
                        <select
                            value={chamber}
                            onChange={(e) => setChamber(e.target.value)}
                            className="rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                        >
                            <option value="">(none)</option>
                            <option value="house">house</option>
                            <option value="senate">senate</option>
                            <option value="all">all</option>
                        </select>
                    </div>
                    <div className="flex flex-col gap-1">
                        <label className="text-muted-foreground">Interval (min)</label>
                        <input
                            type="number"
                            min={1}
                            value={interval}
                            onChange={(e) => setIntervalMinutes(Number(e.target.value))}
                            className="w-24 rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs font-mono text-foreground focus:outline-none focus:border-emerald-500"
                        />
                    </div>
                    <button
                        onClick={create}
                        disabled={creating}
                        className="flex items-center gap-1.5 rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition-colors border border-emerald-500/30 disabled:opacity-50"
                    >
                        <Plus className="h-3.5 w-3.5" />
                        Create Schedule
                    </button>
                </div>
            </div>

            {/* List */}
            <div className="rounded-xl border border-border/50 bg-card p-6">
                <div className="mb-4 flex items-center justify-between">
                    <h2 className="text-base font-semibold text-foreground">
                        Active Schedules
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
                <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                        <thead className="border-b border-border/60 text-[11px] uppercase tracking-wider text-muted-foreground">
                            <tr>
                                <th className="py-2.5 px-3 font-semibold">Service</th>
                                <th className="py-2.5 px-3 font-semibold">Chamber</th>
                                <th className="py-2.5 px-3 font-semibold">Interval</th>
                                <th className="py-2.5 px-3 font-semibold">Next Run</th>
                                <th className="py-2.5 px-3 font-semibold">Last Run</th>
                                <th className="py-2.5 px-3 font-semibold text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border/30">
                            {schedules.map((s) => (
                                <tr key={s.id} className="hover:bg-muted/20 transition-colors">
                                    <td className="py-3 px-3 font-semibold text-foreground">
                                        {s.service}
                                    </td>
                                    <td className="py-3 px-3 text-muted-foreground">
                                        {s.chamber || "—"}
                                    </td>
                                    <td className="py-3 px-3">
                                        <span className="inline-flex items-center gap-1 font-mono text-muted-foreground">
                                            <Clock className="h-3 w-3" />
                                            {s.interval_minutes}m
                                        </span>
                                    </td>
                                    <td className="py-3 px-3 text-muted-foreground">
                                        {formatDate(s.next_run_at)}
                                    </td>
                                    <td className="py-3 px-3 text-muted-foreground">
                                        {formatDate(s.last_run_at)}
                                    </td>
                                    <td className="py-3 px-3 text-right">
                                        <button
                                            onClick={() => remove(s.id)}
                                            className="ml-auto flex items-center gap-1 rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[11px] text-rose-400 hover:bg-rose-500/20 transition-colors"
                                        >
                                            <Trash2 className="h-3 w-3" />
                                            Delete
                                        </button>
                                    </td>
                                </tr>
                            ))}
                            {schedules.length === 0 && (
                                <tr>
                                    <td
                                        colSpan={6}
                                        className="py-8 text-center text-muted-foreground"
                                    >
                                        No schedules configured.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
