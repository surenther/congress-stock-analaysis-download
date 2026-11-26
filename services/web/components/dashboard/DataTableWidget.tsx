"use client";

import React, { useState } from "react";
import { DataTableWidgetSpec } from "@/types/schema";
import { ArrowUpDown, ChevronDown, ChevronUp } from "lucide-react";
import { cn, formatCellValue } from "@/lib/utils";

interface DataTableProps {
  widget: DataTableWidgetSpec;
  onRowNavigate?: (row: Record<string, any>) => void;
}

export function DataTableWidget({ widget, onRowNavigate }: DataTableProps) {
  const { title, description, data } = widget;
  const { columns, rows, empty_message } = data;

  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortOrder("asc");
    }
  };

  const sortedRows = React.useMemo(() => {
    if (!sortKey) return rows;
    return [...rows].sort((a, b) => {
      const valA = a[sortKey];
      const valB = b[sortKey];
      if (valA === valB) return 0;
      if (valA === null || valA === undefined) return 1;
      if (valB === null || valB === undefined) return -1;
      if (typeof valA === "number" && typeof valB === "number") {
        return sortOrder === "asc" ? valA - valB : valB - valA;
      }
      return sortOrder === "asc"
        ? String(valA).localeCompare(String(valB))
        : String(valB).localeCompare(String(valA));
    });
  }, [rows, sortKey, sortOrder]);

  const renderCell = (
    row: Record<string, any>,
    colKey: string,
    isBadge?: boolean,
    isMono?: boolean,
    format?: "currency" | "number",
  ) => {
    const rawVal = row[colKey];

    if (rawVal === null || rawVal === undefined || rawVal === "") {
      return <span className="font-mono text-muted-foreground">—</span>;
    }

    if (isBadge) {
      const strVal = String(rawVal);
      const isPositive = strVal.toLowerCase().includes("purchase") || strVal.toLowerCase().includes("low") || strVal.toLowerCase().includes("compliant");
      const isNegative = strVal.toLowerCase().includes("sale") || strVal.toLowerCase().includes("critical") || strVal.toLowerCase().includes("conflict");
      return (
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
            isPositive && "bg-emerald-500/10 text-emerald-500",
            isNegative && "bg-rose-500/10 text-rose-500",
            !isPositive && !isNegative && "bg-muted text-muted-foreground"
          )}
        >
          {strVal}
        </span>
      );
    }

    // Numeric values render per the column's format hint (currency vs plain
    // number); long text (treasury/fund descriptions) wraps cleanly without
    // breaking alignment.
    const isLongText = typeof rawVal === "string" && rawVal.length > 40;
    return (
      <span
        className={cn(
          isMono ? "font-mono text-xs" : "text-sm",
          "text-foreground",
          isLongText
            ? "block max-w-[22rem] whitespace-normal break-words leading-snug"
            : "whitespace-nowrap",
        )}
      >
        {formatCellValue(rawVal, format)}
      </span>
    );
  };

  return (
    <div className="flex h-full flex-col justify-between rounded-xl border border-border/50 bg-card p-5 shadow-sm">
      <div className="mb-4">
        <h3 className="text-base font-semibold tracking-tight text-foreground">{title}</h3>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border/60 text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className={cn(
                    "cursor-pointer select-none py-2.5 px-3 font-semibold hover:text-foreground transition-colors",
                    col.align === "right" && "text-right",
                    col.align === "center" && "text-center",
                    col.width && col.width
                  )}
                >
                  <div
                    className={cn(
                      "flex items-center gap-1",
                      col.align === "right" && "justify-end",
                      col.align === "center" && "justify-center"
                    )}
                  >
                    <span>{col.header}</span>
                    {sortKey === col.key ? (
                      sortOrder === "asc" ? (
                        <ChevronUp className="h-3 w-3 text-emerald-500" />
                      ) : (
                        <ChevronDown className="h-3 w-3 text-emerald-500" />
                      )
                    ) : (
                      <ArrowUpDown className="h-3 w-3 opacity-30 hover:opacity-100" />
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/30">
            {sortedRows && sortedRows.length > 0 ? (
              sortedRows.map((row, idx) => (
                <tr
                  key={idx}
                  onClick={onRowNavigate ? () => onRowNavigate(row) : undefined}
                  className={cn(
                    "transition-colors hover:bg-muted/30",
                    onRowNavigate && "cursor-pointer",
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        "py-2.5 px-3",
                        col.align === "right" && "text-right",
                        col.align === "center" && "text-center"
                      )}
                    >
                      {renderCell(row, col.key, col.badge, col.monospace, col.format)}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td
                  colSpan={columns.length}
                  className="py-8 text-center text-xs text-muted-foreground"
                >
                  {empty_message || "No records match current parameters"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
