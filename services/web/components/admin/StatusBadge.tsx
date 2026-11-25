import React from "react";
import { cn } from "@/lib/utils";

/** Colored pill for a job/item status. */
export function StatusBadge({ status }: { status: string }) {
    const s = (status || "").toLowerCase();
    return (
        <span
            className={cn(
                "inline-block rounded-full px-2 py-0.5 text-[10px] font-bold uppercase",
                s === "completed" && "bg-emerald-500/10 text-emerald-400",
                (s === "running" || s === "in_progress") &&
                "bg-amber-500/10 text-amber-400 animate-pulse",
                s === "pending" && "bg-blue-500/10 text-blue-400",
                s === "failed" && "bg-rose-500/10 text-rose-400",
                s === "cancelled" && "bg-zinc-500/10 text-zinc-400",
                s === "success" && "bg-emerald-500/10 text-emerald-400",
                s === "skipped" && "bg-zinc-500/10 text-zinc-400",
                s === "idle" && "bg-muted text-muted-foreground",
            )}
        >
            {status}
        </span>
    );
}
