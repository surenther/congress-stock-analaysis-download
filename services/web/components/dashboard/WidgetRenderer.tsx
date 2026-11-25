"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { WidgetSpec } from "@/types/schema";
import { useAuth } from "@/lib/auth-context";
import { buildSearchHref } from "@/lib/search-links";
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
  const router = useRouter();
  const { chamberScope } = useAuth();
  const chamber =
    chamberScope && chamberScope !== "Combined" ? chamberScope : undefined;

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

  const navigate = (href?: string) => {
    if (href) router.push(href);
  };

  const fmtDate = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
      d.getDate(),
    ).padStart(2, "0")}`;

  /** Drill-down target for a table row, keyed by widget id. */
  const rowHref = (row: Record<string, any>): string | undefined => {
    switch (widget.id) {
      case "table-top-assets":
        return buildSearchHref({ ticker: row?.ticker, chamber });
      case "table-late-filings":
        return buildSearchHref({
          filer_name: row?.filer_name,
          is_late: "1",
          chamber,
        });
      case "table-committee-conflicts":
        return buildSearchHref({
          ticker: row?.ticker,
          filer_name: row?.member,
          chamber,
        });
      default:
        return undefined;
    }
  };

  /** Drill-down target for a chart point/slice, keyed by widget id. */
  const pointHref = (item: any, seriesKey?: string): string | undefined => {
    switch (widget.id) {
      case "chart-monthly-volume": {
        const month = item?.month;
        if (!month || !/^\d{4}-\d{2}$/.test(month)) return undefined;
        const [y, m] = month.split("-").map(Number);
        const lastDay = new Date(y, m, 0); // day 0 of next month = last day here
        // Narrow by the clicked series: the "purchases" bar -> Purchase action,
        // the "sales" bar -> Sale action.
        const action =
          seriesKey === "purchases"
            ? "Purchase"
            : seriesKey === "sales"
              ? "Sale"
              : undefined;
        return buildSearchHref({
          start_date: `${month}-01`,
          end_date: fmtDate(lastDay),
          action,
          chamber,
        });
      }
      case "chart-volume-timeline": {
        const period = item?.period; // YYYY-MM-DD (week start)
        if (!period) return undefined;
        const start = new Date(`${period}T00:00:00`);
        if (isNaN(start.getTime())) return undefined;
        const end = new Date(start);
        end.setDate(end.getDate() + 6);
        // The tech_flow series is a derived aggregate (tech OR semiconductor),
        // so it is not mapped to a single asset_category; the drill-down filters
        // by the clicked week's date range.
        return buildSearchHref({
          start_date: period,
          end_date: fmtDate(end),
          chamber,
        });
      }
      case "chart-sector-donut":
        return buildSearchHref({ sector: item?.sector, chamber });
      default:
        return undefined;
    }
  };

  const renderComponent = () => {
    switch (widget.widget_type) {
      case "metric_card":
        return <MetricCardWidget widget={widget} />;
      case "bar_chart":
        return (
          <BarChartWidget
            widget={widget}
            onPointClick={(item, seriesKey) => navigate(pointHref(item, seriesKey))}
          />
        );
      case "line_chart":
        return (
          <LineChartWidget
            widget={widget}
            onPointClick={(item, seriesKey) => navigate(pointHref(item, seriesKey))}
          />
        );
      case "pie_chart":
        return (
          <PieChartWidget
            widget={widget}
            onSliceClick={(item) => navigate(pointHref(item))}
          />
        );
      case "data_table":
        return (
          <DataTableWidget
            widget={widget}
            onRowNavigate={(row) => navigate(rowHref(row))}
          />
        );
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
