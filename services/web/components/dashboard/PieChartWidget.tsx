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

interface PieChartProps {
  widget: PieChartWidgetSpec;
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

export function PieChartWidget({ widget }: PieChartProps) {
  const { title, description, data } = widget;
  const { items, nameKey, valueKey } = data;

  const total = items?.reduce((sum, item) => sum + (Number(item[valueKey]) || 0), 0) || 0;

  return (
    <div className="flex h-full flex-col justify-between rounded-xl border border-border/50 bg-card p-5 shadow-sm">
      <div className="mb-2">
        <h3 className="text-base font-semibold tracking-tight text-foreground">{title}</h3>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>

      <div className="flex flex-col items-center sm:flex-row sm:items-center sm:justify-around">
        <div className="h-[210px] w-[210px]">
          {items && items.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={items}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={3}
                  dataKey={valueKey}
                  nameKey={nameKey}
                >
                  {items.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.color || PIE_COLORS[index % PIE_COLORS.length]}
                      stroke="#09090b"
                      strokeWidth={2}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#09090b",
                    borderColor: "#27272a",
                    borderRadius: "8px",
                    fontSize: "12px",
                    color: "#f4f4f5",
                  }}
                  formatter={(val: any) =>
                    typeof val === "number" ? [`$${val.toLocaleString()}`, ""] : [val, ""]
                  }
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
              No distribution data
            </div>
          )}
        </div>

        {/* Inline Legend with Percentages */}
        <div className="mt-4 flex flex-1 flex-col gap-2 sm:mt-0 sm:pl-4">
          {items.map((item, idx) => {
            const val = Number(item[valueKey]) || 0;
            const pct = item.percentage ?? (total > 0 ? (val / total) * 100 : 0);
            const color = item.color || PIE_COLORS[idx % PIE_COLORS.length];
            return (
              <div key={idx} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 overflow-hidden">
                  <span
                    className="h-2.5 w-2.5 flex-shrink-0 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="truncate text-foreground font-medium">{item[nameKey]}</span>
                </div>
                <div className="flex items-center gap-2 pl-2">
                  <span className="font-mono text-muted-foreground">
                    {pct.toFixed(1)}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
