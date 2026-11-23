"use client";

import React from "react";
import { WidgetSpec } from "@/types/schema";
import { MetricCardWidget } from "./MetricCardWidget";
import { BarChartWidget } from "./BarChartWidget";
import { LineChartWidget } from "./LineChartWidget";
import { PieChartWidget } from "./PieChartWidget";
import { DataTableWidget } from "./DataTableWidget";
import { cn } from "@/lib/utils";

interface WidgetRendererProps {
  widget: WidgetSpec;
  className?: string;
}

export function WidgetRenderer({ widget, className }: WidgetRendererProps) {
  // Determine responsive grid col span
  const getSpanClass = (span?: number) => {
    switch (span) {
      case 1:
        return "col-span-12 md:col-span-6 lg:col-span-4";
      case 2:
        return "col-span-12 md:col-span-6 lg:col-span-6";
      case 3:
        return "col-span-12 lg:col-span-8";
      case 4:
      case 12:
        return "col-span-12";
      default:
        return "col-span-12 lg:col-span-6";
    }
  };

  const renderComponent = () => {
    switch (widget.widget_type) {
      case "metric_card":
        return <MetricCardWidget widget={widget} />;
      case "bar_chart":
        return <BarChartWidget widget={widget} />;
      case "line_chart":
        return <LineChartWidget widget={widget} />;
      case "pie_chart":
        return <PieChartWidget widget={widget} />;
      case "data_table":
        return <DataTableWidget widget={widget} />;
      default:
        return (
          <div className="rounded-xl border border-border/50 bg-card p-4 text-xs text-muted-foreground">
            Unknown widget type: {(widget as any).widget_type}
          </div>
        );
    }
  };

  return (
    <div className={cn(getSpanClass(widget.span), className)}>
      {renderComponent()}
    </div>
  );
}
