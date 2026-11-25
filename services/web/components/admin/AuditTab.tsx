"use client";

import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import { apiFetch, formatDate } from "./api";
import { AuditEntry } from "./types";
import { cn } from "@/lib/utils";

interface Props {
    token: string | null;
    onError: (m: string) => void;
}

export function AuditTab({ token, onError }: Props) {
    const [entries, setEntries] = useState<AuditEntry[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);

    const [action, setAction] = useState("");
    const [actor, setActor] = useState("");
    const [targetType, setTargetType] = useState("");
    const [since, setSince] = useState("");
    const [until, setUntil] = useState("");

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams({ limit: "100" });
            if (action) params.set("action", action);
            if (actor) params.set("actor", actor);
            if (targetType) params.set("target_type", targetType);
            if (since) params.set("since", new Date(since).toISOString());
            if (until) params.set("until", new Date(until).toISOString());
            const data = await apiFetch<{ entries: AuditEntry[]; total: number }>(
                `/api/admin/audit-log?${params.toString()}`,
                token,
            );
            setEntries(data.entries || []);
            setTotal(data.total || 0);
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, [token, action, actor, targetType, since, until, onError]);

    useEffect(() => {
        load();
    }, [load]);

    return (
        <div className="space-y-6">
            <div className="rounded-xl border border-border/50 bg-card p-6">
                <h2 className="mb-1 text-base font-semibold text-foreground">
                    Audit Log
                </h2>
                <p className="mb-4 text-xs text-muted-foreground">
                    Authentication and administrative lifecycle events.
                </p>
                <div className="flex flex-wrap items-end gap-3 text-xs">
                    <Field label="Action">
                        <input
                            value={action}
                            onChange={(e) => setAction(e.target.value)}
                            placeholder="e.g. admin.user.update"
                            className="w-48 rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                        />
                    </Field>
                    <Field label="Actor">
                        <input
                            value={actor}
                            onChange={(e) => setActor(e.target.value)}
                            placeholder="username"
                            className="w-36 rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                        />
                    </Field>
                    <Field label="Target Type">
                        <input
                            value={targetType}
                            onChange={(e) => setTargetType(e.target.value)}
                            placeholder="user"
                            className="w-28 rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                        />
                    </Field>
                    <Field label="Since">
                        <input
                            type="datetime-local"
                            value={since}
                            onChange={(e) => setSince(e.target.value)}
                            className="rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                        />
                    </Field>
                    <Field label="Until">
                        <input
                            type="datetime-local"
                            value={until}
                            onChange={(e) => setUntil(e.target.value)}
                            className="rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                        />
                    </Field>
                    <button
                        onClick={load}
                        disabled={loading}
                        className="flex items-center gap-1.5 rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition-colors border border-emerald-500/30 disabled:opacity-50"
                    >
                        <Search className="h-3.5 w-3.5" />
                        Apply
                    </button>
                    <button
                        onClick={() => {
                            setAction("");
                            setActor("");
                            setTargetType("");
                            setSince("");
                            setUntil("");
                        }}
                        className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-muted/30 px-3 py-1.5 text-xs text-foreground hover:bg-accent transition-colors"
                    >
                        <RefreshCw className="h-3.5 w-3.5" />
                        Clear
                    </button>
                </div>
            </div>

            <div className="rounded-xl border border-border/50 bg-card p-6">
                <div className="mb-4 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-foreground">
                        {total} entr{total === 1 ? "y" : "ies"}
                    </h3>
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
                                <th className="py-2.5 px-3 font-semibold">When</th>
                                <th className="py-2.5 px-3 font-semibold">Actor</th>
                                <th className="py-2.5 px-3 font-semibold">Action</th>
                                <th className="py-2.5 px-3 font-semibold">Target</th>
                                <th className="py-2.5 px-3 font-semibold">IP</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border/30">
                            {entries.map((e) => (
                                <tr key={e.id} className="hover:bg-muted/20 transition-colors">
                                    <td className="py-2.5 px-3 text-muted-foreground">
                                        {formatDate(e.created_at)}
                                    </td>
                                    <td className="py-2.5 px-3 font-medium text-foreground">
                                        {e.actor_username || "—"}
                                    </td>
                                    <td className="py-2.5 px-3">
                                        <span className="rounded bg-accent px-1.5 py-0.5 font-mono text-[10px] text-accent-foreground">
                                            {e.action}
                                        </span>
                                    </td>
                                    <td className="py-2.5 px-3 text-muted-foreground">
                                        {e.target_type
                                            ? `${e.target_type}${e.target_id ? `:${e.target_id.slice(0, 8)}` : ""}`
                                            : "—"}
                                    </td>
                                    <td className="py-2.5 px-3 font-mono text-[10px] text-muted-foreground">
                                        {e.ip || "—"}
                                    </td>
                                </tr>
                            ))}
                            {entries.length === 0 && (
                                <tr>
                                    <td
                                        colSpan={5}
                                        className="py-8 text-center text-muted-foreground"
                                    >
                                        No audit entries found.
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

function Field({
    label,
    children,
}: {
    label: string;
    children: React.ReactNode;
}) {
    return (
        <div className="flex flex-col gap-1">
            <label className="text-muted-foreground">{label}</label>
            {children}
        </div>
    );
}
