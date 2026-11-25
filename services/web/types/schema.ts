export type WidgetType =
  | "metric_card"
  | "bar_chart"
  | "line_chart"
  | "pie_chart"
  | "data_table";

export interface BaseWidgetSpec {
  id: string;
  widget_type: WidgetType;
  title: string;
  description?: string;
  span?: 1 | 2 | 3 | 4 | 12; // grid span
}

export interface MetricCardWidgetSpec extends BaseWidgetSpec {
  widget_type: "metric_card";
  data: {
    category?: string;
    value: string | number;
    prefix?: string;
    suffix?: string;
    trend_percentage?: number;
    trend_direction?: "up" | "down" | "neutral";
    trend_label?: string;
    subtext?: string;
  };
}

export interface BarChartSeries {
  dataKey: string;
  name: string;
  color?: string;
  stackId?: string;
}

export interface BarChartWidgetSpec extends BaseWidgetSpec {
  widget_type: "bar_chart";
  data: {
    xAxisKey: string;
    series: BarChartSeries[];
    items: Array<Record<string, any>>;
    /** "horizontal" renders horizontal bars (categories on the Y axis). */
    orientation?: "vertical" | "horizontal";
  };
}

export interface LineChartSeries {
  dataKey: string;
  name: string;
  color?: string;
  area?: boolean;
}

export interface LineChartWidgetSpec extends BaseWidgetSpec {
  widget_type: "line_chart";
  data: {
    xAxisKey: string;
    series: LineChartSeries[];
    items: Array<Record<string, any>>;
  };
}

export interface PieChartWidgetSpec extends BaseWidgetSpec {
  widget_type: "pie_chart";
  data: {
    nameKey: string;
    valueKey: string;
    items: Array<{
      name?: string;
      value?: number;
      color?: string;
      percentage?: number;
      [key: string]: any;
    }>;
  };
}

export interface TableColumnSpec {
  key: string;
  header: string;
  align?: "left" | "center" | "right";
  badge?: boolean;
  monospace?: boolean;
  width?: string;
}

export interface DataTableWidgetSpec extends BaseWidgetSpec {
  widget_type: "data_table";
  data: {
    columns: TableColumnSpec[];
    rows: Array<Record<string, any>>;
    total_count?: number;
    empty_message?: string;
  };
}

export type WidgetSpec =
  | MetricCardWidgetSpec
  | BarChartWidgetSpec
  | LineChartWidgetSpec
  | PieChartWidgetSpec
  | DataTableWidgetSpec;

export interface DashboardLayoutSpec {
  status: "success" | "error";
  chamber_scope: string[];
  time_horizon?: string;
  generated_at: string;
  system_health?: {
    overall: "healthy" | "degraded" | "unhealthy";
    services: Record<string, string>;
  };
  metrics: {
    total_volume?: number;
    active_members?: number;
    buy_sell_ratio?: number;
    late_filings_count?: number;
  };
  widgets: WidgetSpec[];
}
