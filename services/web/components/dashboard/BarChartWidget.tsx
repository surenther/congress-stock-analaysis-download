"use client";

import React from "react";
import { BarChartWidgetSpec } from "@/types/schema";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

interface BarChartProps {
  widget: BarChartWidgetSpec;
  /** Receives the clicked row plus the dataKey of the series (bar) clicked. */
  onPointClick?: (item: any, seriesKey?: string) => void;
}

const DEFAULT_COLORS = ["#10b981", "#f43f5e", "#6366f1", "#0ea5e9", "#eab308"];

export function BarChartWidget({ widget, onPointClick }: BarChartProps) {
  const { title, description, data } = widget;
  const { items, series, xAxisKey, orientation } = data;
  const isHorizontal = orientation === "horizontal";

  const currencyTick = (val: number) => {
    if (val >= 1000000) return `$${(val / 1000000).toFixed(1)}M`;
    if (val >= 1000) return `$${(val / 1000).toFixed(0)}K`;
    return `${val}`;
  };

  return (
    <div className="flex h-full flex-col justify-between rounded-xl border border-border/50 bg-card p-5 shadow-sm">
      <div className="mb-4">
        <h3 className="text-base font-semibold tracking-tight text-foreground">{title}</h3>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>

      <div className="h-[280px] w-full">
        {items && items.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={items}
              layout={isHorizontal ? "vertical" : "horizontal"}
              margin={
                isHorizontal
                  ? { top: 10, right: 20, left: 10, bottom: 0 }
                  : { top: 10, right: 10, left: -20, bottom: 0 }
              }
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#27272a"
                vertical={isHorizontal}
                horizontal={!isHorizontal}
              />
              {isHorizontal ? (
                <>
                  <XAxis
                    type="number"
                    stroke="#71717a"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={currencyTick}
                  />
                  <YAxis
                    type="category"
                    dataKey={xAxisKey}
                    stroke="#71717a"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    width={64}
                  />
                </>
              ) : (
                <>
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
                    tickFormatter={currencyTick}
                  />
                </>
              )}
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
              {series.map((s, idx) => (
                <Bar
                  key={s.dataKey}
                  dataKey={s.dataKey}
                  name={s.name}
                  fill={s.color || DEFAULT_COLORS[idx % DEFAULT_COLORS.length]}
                  stackId={s.stackId}
                  radius={
                    s.stackId
                      ? [0, 0, 0, 0]
                      : isHorizontal
                        ? [0, 4, 4, 0]
                        : [4, 4, 0, 0]
                  }
                  cursor={onPointClick ? "pointer" : undefined}
                  onClick={
                    onPointClick
                      ? (d: any) => onPointClick(d?.payload ?? d, s.dataKey)
                      : undefined
                  }
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            No chart data available for selected scope
          </div>
        )}
      </div>
    </div>
  );
}
