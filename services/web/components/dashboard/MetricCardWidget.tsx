"use client";

import React from "react";
import { MetricCardWidgetSpec } from "@/types/schema";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  widget: MetricCardWidgetSpec;
}

export function MetricCardWidget({ widget }: MetricCardProps) {
  const { data, title } = widget;
  const direction = data.trend_direction || (data.trend_percentage && data.trend_percentage > 0 ? "up" : data.trend_percentage && data.trend_percentage < 0 ? "down" : "neutral");

  return (
    <div className="relative h-full overflow-hidden rounded-xl border border-border/50 bg-card p-4 shadow-sm transition-all hover:border-emerald-500/40">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {data.category || title}
        </span>
        {data.trend_percentage !== undefined && (
          <div
            className={cn(
              "flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
              direction === "up" && "bg-emerald-500/10 text-emerald-500",
              direction === "down" && "bg-rose-500/10 text-rose-500",
              direction === "neutral" && "bg-muted text-muted-foreground"
            )}
          >
            {direction === "up" && <TrendingUp className="h-3 w-3" />}
            {direction === "down" && <TrendingDown className="h-3 w-3" />}
            {direction === "neutral" && <Minus className="h-3 w-3" />}
            <span>
              {direction === "up" ? "+" : ""}
              {data.trend_percentage.toFixed(1)}%
            </span>
          </div>
        )}
      </div>

      <div className="mt-2 flex items-baseline gap-1">
        {data.prefix && <span className="text-base text-muted-foreground">{data.prefix}</span>}
        <span className="text-xl font-bold tracking-tight text-foreground lg:text-2xl">
          {data.value ?? "—"}
        </span>
        {data.suffix && <span className="text-xs text-muted-foreground">{data.suffix}</span>}
      </div>

      {(data.trend_label || data.subtext) && (
        <div className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">
          {data.trend_label || data.subtext}
        </div>
      )}
    </div>
  );
}
