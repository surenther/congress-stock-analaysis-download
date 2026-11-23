"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth-context";
import { DisclosureRecord, Chamber } from "@/types/disclosure";
import {
  Search,
  Download,
  Filter,
  FileSpreadsheet,
  FileText,
  Lock,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Building2,
  Calendar,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function SearchPage() {
  const { chamberScope, isChamberLocked } = useAuth();

  const [ticker, setTicker] = useState("");
  const [filerName, setFilerName] = useState("");
  const [action, setAction] = useState<string>("All");
  const [selectedChamber, setSelectedChamber] = useState<string>(
    chamberScope === "Combined" ? "All" : chamberScope
  );
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 12;

  const { data, isLoading, refetch } = useQuery<{
    records: DisclosureRecord[];
    total: number;
  }>({
    queryKey: [
      "disclosures-search",
      ticker,
      filerName,
      action,
      selectedChamber,
      startDate,
      endDate,
      page,
    ],
    queryFn: async () => {
      const params = new URLSearchParams({
        ticker,
        filer_name: filerName,
        action: action === "All" ? "" : action,
        chamber: isChamberLocked ? "House" : selectedChamber === "All" ? "" : selectedChamber,
        start_date: startDate,
        end_date: endDate,
        page: String(page),
        page_size: String(pageSize),
      });
      const res = await fetch(`/api/disclosures?${params.toString()}`);
      if (!res.ok) throw new Error("Search failed");
      return res.json();
    },
  });

  const handleExport = (format: "csv" | "pdf") => {
    const params = new URLSearchParams({
      ticker,
      filer_name: filerName,
      action: action === "All" ? "" : action,
      chamber: isChamberLocked ? "House" : selectedChamber === "All" ? "" : selectedChamber,
      format,
    });
    window.open(`/api/disclosures/export?${params.toString()}`, "_blank");
  };

  const totalPages = Math.ceil((data?.total || 0) / pageSize) || 1;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Title & Export Actions */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Disclosure Records Grid
          </h1>
          <p className="mt-1 text-xs text-muted-foreground sm:text-sm">
            High-performance structured search across official House and Senate financial disclosures.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => handleExport("csv")}
            className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors"
          >
            <FileSpreadsheet className="h-3.5 w-3.5 text-emerald-400" />
            <span>Export CSV</span>
          </button>
          <button
            onClick={() => handleExport("pdf")}
            className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors"
          >
            <FileText className="h-3.5 w-3.5 text-rose-400" />
            <span>Export PDF</span>
          </button>
        </div>
      </div>

      {/* Multi-Variable Search Controls Bar */}
      <div className="mb-6 rounded-xl border border-border/50 bg-card p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
          {/* Ticker Input */}
          <div>
            <label className="text-[11px] font-semibold uppercase text-muted-foreground">
              Ticker
            </label>
            <div className="relative mt-1">
              <input
                type="text"
                placeholder="NVDA, MSFT..."
                value={ticker}
                onChange={(e) => {
                  setTicker(e.target.value.toUpperCase());
                  setPage(1);
                }}
                className="w-full rounded-lg border border-border/60 bg-background px-3 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Filer Name */}
          <div>
            <label className="text-[11px] font-semibold uppercase text-muted-foreground">
              Filer Name
            </label>
            <div className="relative mt-1">
              <input
                type="text"
                placeholder="Pelosi, Curtis..."
                value={filerName}
                onChange={(e) => {
                  setFilerName(e.target.value);
                  setPage(1);
                }}
                className="w-full rounded-lg border border-border/60 bg-background px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Action Filter */}
          <div>
            <label className="text-[11px] font-semibold uppercase text-muted-foreground">
              Action
            </label>
            <select
              value={action}
              onChange={(e) => {
                setAction(e.target.value);
                setPage(1);
              }}
              className="mt-1 w-full rounded-lg border border-border/60 bg-background px-3 py-1.5 text-xs text-foreground focus:border-emerald-500 focus:outline-none"
            >
              <option value="All">All Actions</option>
              <option value="Purchase">Purchase</option>
              <option value="Sale">Sale</option>
              <option value="Exchange">Exchange</option>
            </select>
          </div>

          {/* Chamber Scope */}
          <div>
            <div className="flex items-center gap-1">
              <label className="text-[11px] font-semibold uppercase text-muted-foreground">
                Chamber
              </label>
              {isChamberLocked && <Lock className="h-3 w-3 text-muted-foreground" />}
            </div>
            <select
              value={isChamberLocked ? "House" : selectedChamber}
              disabled={isChamberLocked}
              onChange={(e) => {
                setSelectedChamber(e.target.value);
                setPage(1);
              }}
              className="mt-1 w-full rounded-lg border border-border/60 bg-background px-3 py-1.5 text-xs text-foreground focus:border-emerald-500 focus:outline-none disabled:opacity-50"
            >
              <option value="All">All Chambers</option>
              <option value="House">House of Reps</option>
              <option value="Senate">U.S. Senate</option>
            </select>
          </div>

          {/* Start Date */}
          <div>
            <label className="text-[11px] font-semibold uppercase text-muted-foreground">
              From Date
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                setPage(1);
              }}
              className="mt-1 w-full rounded-lg border border-border/60 bg-background px-3 py-1.5 text-xs text-foreground focus:border-emerald-500 focus:outline-none"
            >
            </input>
          </div>

          {/* End Date */}
          <div>
            <label className="text-[11px] font-semibold uppercase text-muted-foreground">
              To Date
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => {
                setEndDate(e.target.value);
                setPage(1);
              }}
              className="mt-1 w-full rounded-lg border border-border/60 bg-background px-3 py-1.5 text-xs text-foreground focus:border-emerald-500 focus:outline-none"
            >
            </input>
          </div>
        </div>
      </div>

      {/* High-Performance Table */}
      <div className="rounded-xl border border-border/50 bg-card shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border/60 bg-muted/20 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="py-3 px-4 font-semibold">Filer Name</th>
                <th className="py-3 px-3 font-semibold">Chamber</th>
                <th className="py-3 px-3 font-semibold">Filed Date</th>
                <th className="py-3 px-3 font-semibold">Trade Date</th>
                <th className="py-3 px-3 font-semibold">Ticker</th>
                <th className="py-3 px-4 font-semibold">Asset Name</th>
                <th className="py-3 px-3 font-semibold text-center">Action</th>
                <th className="py-3 px-4 font-semibold text-right">Value Range</th>
                <th className="py-3 px-3 font-semibold text-center">Ownership</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {isLoading ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-xs text-muted-foreground">
                    Querying congressional filing registry...
                  </td>
                </tr>
              ) : data?.records && data.records.length > 0 ? (
                data.records.map((rec) => {
                  const isBuy = rec.action.toLowerCase().includes("purchase");
                  const isSell = rec.action.toLowerCase().includes("sale");

                  return (
                    <tr key={rec.id} className="transition-colors hover:bg-muted/30">
                      {/* Filer Name */}
                      <td className="py-3 px-4 font-medium text-foreground">
                        <div className="flex items-center gap-2">
                          <span>{rec.filer_name}</span>
                          {rec.is_late && (
                            <span
                              title={`Filed ${rec.days_late || 45}+ days after trade`}
                              className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-bold text-rose-400"
                            >
                              LATE
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Chamber */}
                      <td className="py-3 px-3">
                        <span
                          className={cn(
                            "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                            rec.chamber === "House"
                              ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                              : "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                          )}
                        >
                          {rec.chamber}
                        </span>
                      </td>

                      {/* Filed Date */}
                      <td className="py-3 px-3 font-mono text-xs text-muted-foreground">
                        {rec.filed_date || <span className="text-muted-foreground font-mono">—</span>}
                      </td>

                      {/* Trade Date */}
                      <td className="py-3 px-3 font-mono text-xs text-foreground">
                        {rec.trade_date || <span className="text-muted-foreground font-mono">—</span>}
                      </td>

                      {/* Ticker: Display ticker or muted fallback badge */}
                      <td className="py-3 px-3">
                        {rec.ticker ? (
                          <span className="rounded bg-accent px-1.5 py-0.5 font-mono text-xs font-semibold text-accent-foreground">
                            {rec.ticker}
                          </span>
                        ) : (
                          <span className="text-muted-foreground font-mono text-xs">—</span>
                        )}
                      </td>

                      {/* Asset Name: Always display asset_name when ticker is blank or null */}
                      <td className="py-3 px-4 max-w-xs truncate text-foreground font-medium">
                        {rec.asset_name || <span className="text-muted-foreground italic">Unlisted / Fund</span>}
                      </td>

                      {/* Action */}
                      <td className="py-3 px-3 text-center">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold",
                            isBuy && "bg-emerald-500/10 text-emerald-400",
                            isSell && "bg-rose-500/10 text-rose-400",
                            !isBuy && !isSell && "bg-muted text-muted-foreground"
                          )}
                        >
                          {isBuy && <TrendingUp className="h-3 w-3" />}
                          {isSell && <TrendingDown className="h-3 w-3" />}
                          {rec.action}
                        </span>
                      </td>

                      {/* Value Range */}
                      <td className="py-3 px-4 text-right font-mono text-xs font-medium text-foreground">
                        {rec.value_range || <span className="text-muted-foreground font-mono">—</span>}
                      </td>

                      {/* Ownership */}
                      <td className="py-3 px-3 text-center text-xs text-muted-foreground">
                        {rec.ownership || <span className="text-muted-foreground font-mono">—</span>}
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-xs text-muted-foreground">
                    No disclosure records match the given criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="flex items-center justify-between border-t border-border/50 px-4 py-3 text-xs text-muted-foreground">
          <div>
            Showing <span className="font-semibold text-foreground">{data?.records?.length || 0}</span> of{" "}
            <span className="font-semibold text-foreground">{data?.total || 0}</span> records
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="flex items-center gap-1 rounded-md border border-border/50 px-2.5 py-1 text-xs hover:bg-muted disabled:opacity-40 transition-colors"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              <span>Previous</span>
            </button>
            <span className="font-mono text-foreground font-medium">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="flex items-center gap-1 rounded-md border border-border/50 px-2.5 py-1 text-xs hover:bg-muted disabled:opacity-40 transition-colors"
            >
              <span>Next</span>
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
