"use client";

import React from "react";
import { LineChartWidgetSpec } from "@/types/schema";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

interface LineChartProps {
  widget: LineChartWidgetSpec;
  /** Receives the clicked row plus the dataKey of the series (area) clicked. */
  onPointClick?: (item: any, seriesKey?: string) => void;
}

const DEFAULT_LINE_COLORS = ["#0ea5e9", "#10b981", "#8b5cf6", "#f59e0b"];

export function LineChartWidget({ widget, onPointClick }: LineChartProps) {
  const { title, description, data } = widget;
  const { items, series, xAxisKey } = data;

  return (
    <div className="flex h-full flex-col justify-between rounded-xl border border-border/50 bg-card p-5 shadow-sm">
      <div className="mb-4">
        <h3 className="text-base font-semibold tracking-tight text-foreground">{title}</h3>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>

      <div className="h-[280px] w-full">
        {items && items.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={items} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                {series.map((s, idx) => {
                  const color = s.color || DEFAULT_LINE_COLORS[idx % DEFAULT_LINE_COLORS.length];
                  return (
                    <linearGradient
                      key={`grad-${s.dataKey}`}
                      id={`grad-${s.dataKey}`}
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop offset="5%" stopColor={color} stopOpacity={0.4} />
                      <stop offset="95%" stopColor={color} stopOpacity={0.0} />
                    </linearGradient>
                  );
                })}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis
                dataKey={xAxisKey}
                stroke="#71717a"
                fontSize={11}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                stroke="#71717a"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                tickFormatter={(val) => {
                  if (val >= 1000000) return `$${(val / 1000000).toFixed(1)}M`;
                  if (val >= 1000) return `$${(val / 1000).toFixed(0)}K`;
                  return `${val}`;
                }}
              />
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
              <Legend
                wrapperStyle={{ fontSize: "11px", paddingTop: "8px" }}
                iconType="circle"
              />
              {series.map((s, idx) => {
                const color = s.color || DEFAULT_LINE_COLORS[idx % DEFAULT_LINE_COLORS.length];
                return (
                  <Area
                    key={s.dataKey}
                    type="monotone"
                    dataKey={s.dataKey}
                    name={s.name}
                    stroke={color}
                    strokeWidth={2}
                    fillOpacity={1}
                    fill={`url(#grad-${s.dataKey})`}
                    cursor={onPointClick ? "pointer" : undefined}
                    onClick={
                      onPointClick
                        ? (d: any) => onPointClick(d?.payload ?? d, s.dataKey)
                        : undefined
                    }
                  />
                );
              })}
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            No trend data available for selected scope
          </div>
        )}
      </div>
    </div>
  );
}
