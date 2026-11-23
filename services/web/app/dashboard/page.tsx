"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth-context";
import { DashboardLayoutSpec } from "@/types/schema";
import { WidgetRenderer } from "@/components/dashboard/WidgetRenderer";
import {
  Sparkles,
  RefreshCw,
  AlertCircle,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";

export default function DashboardPage() {
  const { chamberScope, timeHorizon } = useAuth();

  const { data, isLoading, error, refetch, isFetching } = useQuery<DashboardLayoutSpec>({
    queryKey: ["dashboard-analytics", chamberScope, timeHorizon],
    queryFn: async () => {
      const res = await fetch("/api/rag/dashboard/analytics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chamber: chamberScope, timeHorizon }),
      });
      if (!res.ok) {
        throw new Error("Failed to load schema-driven dashboard spec");
      }
      return res.json();
    },
  });

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Executive Portal Header Banner */}
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              Executive Analytics Portal
            </h1>
            <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-500 ring-1 ring-emerald-500/30">
              Live Feed
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground sm:text-sm">
            Schema-driven congressional stock intelligence, STOCK Act compliance audit, and legislative conflict tracking.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin text-emerald-500" : ""}`} />
            <span>Refresh Analytics</span>
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="mb-6 flex items-center gap-3 rounded-xl border border-destructive/50 bg-destructive/10 p-4 text-xs text-destructive">
          <AlertCircle className="h-5 w-5 flex-shrink-0" />
          <div>
            <div className="font-semibold">Unable to fetch dashboard schema</div>
            <div className="text-muted-foreground">{String(error)}</div>
          </div>
        </div>
      )}

      {/* Loading Skeleton */}
      {isLoading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-28 animate-pulse rounded-xl border border-border/40 bg-card/60 p-5"
              />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <div className="h-80 animate-pulse rounded-xl border border-border/40 bg-card/60 lg:col-span-8" />
            <div className="h-80 animate-pulse rounded-xl border border-border/40 bg-card/60 lg:col-span-4" />
          </div>
        </div>
      ) : data?.widgets && data.widgets.length > 0 ? (
        <div className="space-y-6">
          {/* Top KPI Cards Grid */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {data.widgets
              .filter((w) => w.widget_type === "metric_card")
              .map((w) => (
                <WidgetRenderer key={w.id} widget={w} />
              ))}
          </div>

          {/* Dynamic Visualizations & Data Tables Grid */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            {data.widgets
              .filter((w) => w.widget_type !== "metric_card")
              .map((w) => (
                <WidgetRenderer key={w.id} widget={w} />
              ))}
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-border/50 bg-card p-12 text-center text-sm text-muted-foreground">
          No layout specification returned for the selected scope.
        </div>
      )}
    </div>
  );
}
