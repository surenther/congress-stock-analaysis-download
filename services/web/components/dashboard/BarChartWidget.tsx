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
                stroke="hsl(var(--border))"
                vertical={isHorizontal}
                horizontal={!isHorizontal}
              />
              {isHorizontal ? (
                <>
                  <XAxis
                    type="number"
                    stroke="hsl(var(--muted-foreground))"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={currencyTick}
                  />
                  <YAxis
                    type="category"
                    dataKey={xAxisKey}
                    stroke="hsl(var(--muted-foreground))"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    width={132}
                    interval={0}
                    tick={(props: any) => {
                      // Readable asset titles / ticker badges instead of
                      // truncated uppercase prefixes. The full asset name is
                      // available in the hover tooltip.
                      const { x, y, payload } = props;
                      const row = items?.[payload?.index] ?? {};
                      const full = row.asset_name || row.ticker || payload?.value;
                      return (
                        <g transform={`translate(${x},${y})`}>
                          <title>{full}</title>
                          <text
                            x={-8}
                            y={0}
                            dy={4}
                            textAnchor="end"
                            fill="hsl(var(--muted-foreground))"
                            fontSize={11}
                          >
                            {payload?.value}
                          </text>
                        </g>
                      );
                    }}
                  />
                </>
              ) : (
                <>
                  <XAxis
                    dataKey={xAxisKey}
                    stroke="hsl(var(--muted-foreground))"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    stroke="hsl(var(--muted-foreground))"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={currencyTick}
                  />
                </>
              )}
              <Tooltip
                cursor={{ fill: "hsl(var(--muted) / 0.5)" }}
                content={({ active, payload, label }: any) => {
                  if (!active || !payload || payload.length === 0) return null;
                  const row = payload[0]?.payload ?? {};
                  // Prefer the full asset name (Top Traded Assets) over the
                  // abbreviated axis label.
                  const heading = row.asset_name || row.ticker || label;
                  return (
                    <div className="rounded-lg border border-border/60 bg-popover px-3 py-2 text-xs text-popover-foreground shadow-lg">
                      <div className="mb-1 font-medium text-popover-foreground">{heading}</div>
                      {payload.map((p: any) => (
                        <div
                          key={p.dataKey}
                          className="flex items-center justify-between gap-4"
                        >
                          <span className="flex items-center gap-1.5 text-muted-foreground">
                            <span
                              className="h-2 w-2 rounded-full"
                              style={{ backgroundColor: p.color }}
                            />
                            {p.name}
                          </span>
                          <span className="font-mono text-foreground">
                            ${Number(p.value || 0).toLocaleString()}
                          </span>
                        </div>
                      ))}
                    </div>
                  );
                }}
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
