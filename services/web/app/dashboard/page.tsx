"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth-context";
import { DashboardLayoutSpec, WidgetSpec } from "@/types/schema";
import { WidgetRenderer } from "@/components/dashboard/WidgetRenderer";
import {
  Sparkles,
  RefreshCw,
  AlertCircle,
  ShieldCheck,
  TrendingUp,
  Loader2,
} from "lucide-react";

/**
 * A widget is only worth rendering if it actually carries data. Empty widgets
 * (e.g. an LLM-authored card with no rows/points in scope) are hidden entirely.
 */
function widgetHasData(w: WidgetSpec): boolean {
  const d: any = (w as any).data;
  if (!d) return false;
  if (w.widget_type === "metric_card") {
    return d.value !== undefined && d.value !== null && d.value !== "";
  }
  if (w.widget_type === "data_table") {
    return Array.isArray(d.rows) && d.rows.length > 0;
  }
  // bar_chart / line_chart / pie_chart
  return Array.isArray(d.items) && d.items.length > 0;
}

export default function DashboardPage() {
  const { chamberScope, timeHorizon, token } = useAuth();

  const { data, isLoading, error, refetch, isFetching } = useQuery<DashboardLayoutSpec>({
    queryKey: ["dashboard-analytics", chamberScope, timeHorizon, token],
    queryFn: async () => {
      const res = await fetch("/api/rag/dashboard/analytics", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ chamber: chamberScope, timeHorizon }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(
          detail?.detail || "Failed to load schema-driven dashboard spec",
        );
      }
      return res.json();
    },
    enabled: !!token,
  });

  // Only keep widgets that actually have data in scope.
  const visibleWidgets = (data?.widgets ?? []).filter(widgetHasData);
  const metricWidgets = visibleWidgets.filter((w) => w.widget_type === "metric_card");
  const otherWidgets = visibleWidgets.filter((w) => w.widget_type !== "metric_card");

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
            {isFetching ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-500" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            <span>{isFetching ? "Analyzing…" : "Refresh Analytics"}</span>
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

      {/* Background refresh indicator */}
      {isFetching && !isLoading && (
        <div className="mb-4 flex items-center gap-2 text-xs font-medium text-emerald-500">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span>Updating analysis from live disclosures…</span>
        </div>
      )}

      {/* Loading state (LLM synthesis in progress) */}
      {isLoading ? (
        <div className="space-y-6">
          <div className="flex items-center gap-2 text-sm font-medium text-emerald-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>AI is composing your dashboard from live disclosures…</span>
          </div>
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
      ) : metricWidgets.length > 0 || otherWidgets.length > 0 ? (
        <div className="space-y-6">
          {/* Top KPI Cards Grid */}
          {metricWidgets.length > 0 && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {metricWidgets.map((w) => (
                <WidgetRenderer key={w.id} widget={w} />
              ))}
            </div>
          )}

          {/* Dynamic Visualizations & Data Tables Grid */}
          {otherWidgets.length > 0 && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              {otherWidgets.map((w) => (
                <WidgetRenderer key={w.id} widget={w} />
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-border/50 bg-card p-12 text-center text-sm text-muted-foreground">
          No data available for the selected scope yet.
        </div>
      )}
    </div>
  );
}
