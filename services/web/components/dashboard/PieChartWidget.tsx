"use client";

import React from "react";
import { PieChartWidgetSpec } from "@/types/schema";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { cn } from "@/lib/utils";

interface PieChartProps {
  widget: PieChartWidgetSpec;
  onSliceClick?: (item: any) => void;
}

const PIE_COLORS = [
  "#10b981", // Emerald
  "#0ea5e9", // Sky
  "#8b5cf6", // Violet
  "#f59e0b", // Amber
  "#ec4899", // Pink
  "#06b6d4", // Cyan
  "#64748b", // Slate
];

export function PieChartWidget({ widget, onSliceClick }: PieChartProps) {
  const { title, description, data } = widget;
  const { items, nameKey, valueKey } = data;

  const safeItems = items ?? [];
  const total =
    safeItems.reduce((sum, item) => sum + (Number(item[valueKey]) || 0), 0) || 0;

  return (
    <div className="flex h-full flex-col rounded-xl border border-border/50 bg-card p-5 shadow-sm">
      <div className="mb-3">
        <h3 className="text-base font-semibold tracking-tight text-foreground">{title}</h3>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-5 sm:flex-row sm:items-center sm:justify-start sm:gap-6">
        {/* Donut — fixed square box so it always renders centered */}
        <div className="relative h-[190px] w-[190px] shrink-0">
          {safeItems.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={safeItems}
                  cx="50%"
                  cy="50%"
                  innerRadius={52}
                  outerRadius={82}
                  paddingAngle={3}
                  dataKey={valueKey}
                  nameKey={nameKey}
                  isAnimationActive={false}
                  cursor={onSliceClick ? "pointer" : undefined}
                  onClick={
                    onSliceClick
                      ? (d: any) => onSliceClick(d?.payload ?? d)
                      : undefined
                  }
                >
                  {safeItems.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.color || PIE_COLORS[index % PIE_COLORS.length]}
                      stroke="#09090b"
                      strokeWidth={2}
                    />
                  ))}
                </Pie>
                <Tooltip
                  cursor={false}
                  wrapperStyle={{ zIndex: 20, outline: "none" }}
                  content={({ active, payload }: any) => {
                    if (!active || !payload || payload.length === 0) return null;
                    const p = payload[0];
                    const name = p?.name ?? p?.payload?.[nameKey] ?? "—";
                    const value = Number(p?.value) || 0;
                    const pct = total > 0 ? (value / total) * 100 : 0;
                    return (
                      <div className="rounded-lg border border-border/60 bg-[#09090b] px-3 py-2 text-xs shadow-lg">
                        <div className="font-medium text-[#f4f4f5]">{name}</div>
                        <div className="font-mono text-emerald-400">
                          ${value.toLocaleString()}
                        </div>
                        <div className="text-muted-foreground">{pct.toFixed(1)}%</div>
                      </div>
                    );
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
              No distribution data
            </div>
          )}
        </div>

        {/* Legend with percentages — 2 columns when the card is full-width */}
        <div className="grid w-full min-w-0 flex-1 grid-cols-1 content-center gap-x-6 gap-y-2 sm:grid-cols-2">
          {safeItems.map((item, idx) => {
            const val = Number(item[valueKey]) || 0;
            const pct = item.percentage ?? (total > 0 ? (val / total) * 100 : 0);
            const color = item.color || PIE_COLORS[idx % PIE_COLORS.length];
            return (
              <div
                key={idx}
                onClick={onSliceClick ? () => onSliceClick(item) : undefined}
                className={cn(
                  "flex items-center justify-between gap-3 rounded px-1 py-0.5 text-xs",
                  onSliceClick && "cursor-pointer hover:bg-muted/40",
                )}
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 flex-shrink-0 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="truncate font-medium text-foreground">
                    {item[nameKey]}
                  </span>
                </div>
                <span className="flex-shrink-0 font-mono text-muted-foreground">
                  {pct.toFixed(1)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
