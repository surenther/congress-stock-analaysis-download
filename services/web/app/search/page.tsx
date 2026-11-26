"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
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
  ChevronUp,
  ChevronDown,
  ArrowUpDown,
  TrendingUp,
  TrendingDown,
  Building2,
  Calendar,
  ArrowLeft,
} from "lucide-react";
import { cn } from "@/lib/utils";

/** A clickable table header that toggles server-side sorting for its column. */
function SortableTh({
  label,
  columnKey,
  align,
  activeKey,
  activeOrder,
  onSort,
}: {
  label: string;
  columnKey: string;
  align?: "left" | "center" | "right";
  activeKey: string | null;
  activeOrder: "asc" | "desc";
  onSort: (key: string) => void;
}) {
  const active = activeKey === columnKey;
  return (
    <th
      className={cn(
        "py-3 px-3 font-semibold",
        align === "right" && "text-right",
        align === "center" && "text-center",
      )}
    >
      <button
        type="button"
        onClick={() => onSort(columnKey)}
        title={`Sort by ${label}`}
        className={cn(
          "inline-flex items-center gap-1 transition-colors hover:text-foreground",
          align === "right" && "flex-row-reverse",
          align === "center" && "justify-center",
          active && "text-foreground",
        )}
      >
        <span>{label}</span>
        {active ? (
          activeOrder === "asc" ? (
            <ChevronUp className="h-3 w-3 text-emerald-500" />
          ) : (
            <ChevronDown className="h-3 w-3 text-emerald-500" />
          )
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-30" />
        )}
      </button>
    </th>
  );
}

/** Small removable chip used by the Active Filters banner. */
function FilterChip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/20 px-2 py-0.5">
      {label}
      <button
        onClick={onClear}
        className="font-bold hover:text-amber-200"
        aria-label={`Clear ${label}`}
      >
        ×
      </button>
    </span>
  );
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <div className="h-8 w-64 animate-pulse rounded bg-muted/40" />
        </div>
      }
    >
      <SearchPageInner />
    </Suspense>
  );
}

function SearchPageInner() {
  const { chamberScope, isChamberLocked, token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();

  const [ticker, setTicker] = useState("");
  const [filerName, setFilerName] = useState("");
  const [action, setAction] = useState<string>("All");
  const [selectedChamber, setSelectedChamber] = useState<string>(
    chamberScope === "Combined" ? "All" : chamberScope
  );
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [isLate, setIsLate] = useState(false);
  const [marketTrades, setMarketTrades] = useState(false);
  const [sector, setSector] = useState("");
  const [assetName, setAssetName] = useState("");
  const [fromDashboard, setFromDashboard] = useState(false);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const pageSize = 12;
  const skipSyncRef = React.useRef(false);

  // Toggle server-side sorting for a column. A new column starts descending;
  // clicking the active column flips the direction. Sorting resets to page 1.
  const toggleSort = (key: string) => {
    if (sortKey === key) {
      setSortOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortOrder("desc");
    }
    setPage(1);
  };

  // Hydrate filters from the URL whenever it changes. This runs on mount and on
  // every navigation, so a dashboard drill-down applies its filters while a
  // direct click on "Disclosure Grid" (no query string) clears them.
  useEffect(() => {
    const sp = new URLSearchParams(searchKey);
    setTicker(sp.get("ticker")?.toUpperCase() ?? "");
    setFilerName(sp.get("filer_name") ?? "");
    setAction(sp.get("action") ?? "All");
    setSelectedChamber(
      sp.get("chamber") ?? (chamberScope === "Combined" ? "All" : chamberScope),
    );
    setStartDate(sp.get("start_date") ?? "");
    setEndDate(sp.get("end_date") ?? "");
    setSector(sp.get("sector") ?? "");
    setAssetName(sp.get("asset_name") ?? "");
    setIsLate(sp.get("is_late") === "1");
    setMarketTrades(sp.get("market_trades") === "1");
    setFromDashboard(sp.get("from") === "dashboard");
    setSortKey(sp.get("sort") || null);
    setSortOrder(sp.get("order") === "asc" ? "asc" : "desc");
    setPage(1);
    // The state above already reflects the URL, so skip the next URL sync.
    skipSyncRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchKey]);

  // Keep the URL in sync with the active filters so a refresh or a shared link
  // preserves the current view. The run immediately after hydration is skipped
  // because the state already matches the URL.
  useEffect(() => {
    if (skipSyncRef.current) {
      skipSyncRef.current = false;
      return;
    }
    const sp = new URLSearchParams();
    if (ticker) sp.set("ticker", ticker);
    if (filerName) sp.set("filer_name", filerName);
    if (action && action !== "All") sp.set("action", action);
    const effectiveChamber = isChamberLocked ? "House" : selectedChamber;
    if (effectiveChamber && effectiveChamber !== "All") {
      sp.set("chamber", effectiveChamber);
    }
    if (startDate) sp.set("start_date", startDate);
    if (endDate) sp.set("end_date", endDate);
    if (sector) sp.set("sector", sector);
    if (assetName) sp.set("asset_name", assetName);
    if (isLate) sp.set("is_late", "1");
    if (marketTrades) sp.set("market_trades", "1");
    if (fromDashboard) sp.set("from", "dashboard");
    if (sortKey) {
      sp.set("sort", sortKey);
      sp.set("order", sortOrder);
    }
    const nextKey = sp.toString();
    if (nextKey === searchKey) return;
    window.history.replaceState(null, "", nextKey ? `/search?${nextKey}` : "/search");
  }, [
    ticker,
    filerName,
    action,
    selectedChamber,
    startDate,
    endDate,
    sector,
    assetName,
    isLate,
    marketTrades,
    fromDashboard,
    sortKey,
    sortOrder,
    isChamberLocked,
    searchKey,
  ]);

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
      isLate,
      marketTrades,
      sector,
      assetName,
      sortKey,
      sortOrder,
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
        is_late: isLate ? "1" : "",
        market_trades: marketTrades ? "1" : "",
        sector,
        asset_name: assetName,
        sort: sortKey || "",
        order: sortOrder,
        page: String(page),
        page_size: String(pageSize),
      });
      const res = await fetch(`/api/disclosures?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail?.detail || "Search failed");
      }
      return res.json();
    },
    enabled: !!token,
  });

  const handleExport = async (format: "csv" | "pdf") => {
    const params = new URLSearchParams({
      ticker,
      filer_name: filerName,
      action: action === "All" ? "" : action,
      chamber: isChamberLocked ? "House" : selectedChamber === "All" ? "" : selectedChamber,
      is_late: isLate ? "1" : "",
      market_trades: marketTrades ? "1" : "",
      sector,
      asset_name: assetName,
      start_date: startDate,
      end_date: endDate,
      format,
    });
    try {
      const res = await fetch(`/api/disclosures/export?${params.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        throw new Error("Export failed");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `congress-disclosures.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      // Export is best-effort; surface nothing destructive if it fails.
    }
  };

  const totalPages = Math.ceil((data?.total || 0) / pageSize) || 1;

  const hasActiveFilters =
    !!ticker ||
    !!filerName ||
    action !== "All" ||
    (!isChamberLocked && selectedChamber !== "All") ||
    !!startDate ||
    !!endDate ||
    !!sector ||
    !!assetName ||
    isLate ||
    marketTrades;

  const clearAllFilters = () => {
    setTicker("");
    setFilerName("");
    setAction("All");
    if (!isChamberLocked) setSelectedChamber("All");
    setStartDate("");
    setEndDate("");
    setSector("");
    setAssetName("");
    setIsLate(false);
    setMarketTrades(false);
    setPage(1);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Back to dashboard — only shown when arriving from a drill-down */}
      {fromDashboard && (
        <button
          onClick={() => router.push("/dashboard")}
          className="mb-4 inline-flex items-center gap-1.5 rounded-lg border border-border/60 bg-card px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Back to Dashboard</span>
        </button>
      )}

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

        <div className="flex flex-wrap items-center gap-2">
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

      {/* Active filters (from dashboard drill-downs or manual selection) */}
      {hasActiveFilters && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
          <span className="font-medium">Active filters:</span>
          {ticker && (
            <FilterChip
              label={`Ticker: ${ticker}`}
              onClear={() => {
                setTicker("");
                setPage(1);
              }}
            />
          )}
          {filerName && (
            <FilterChip
              label={`Filer: ${filerName}`}
              onClear={() => {
                setFilerName("");
                setPage(1);
              }}
            />
          )}
          {action !== "All" && (
            <FilterChip
              label={`Action: ${action}`}
              onClear={() => {
                setAction("All");
                setPage(1);
              }}
            />
          )}
          {!isChamberLocked && selectedChamber !== "All" && (
            <FilterChip
              label={`Chamber: ${selectedChamber}`}
              onClear={() => {
                setSelectedChamber("All");
                setPage(1);
              }}
            />
          )}
          {startDate && (
            <FilterChip
              label={`From: ${startDate}`}
              onClear={() => {
                setStartDate("");
                setPage(1);
              }}
            />
          )}
          {endDate && (
            <FilterChip
              label={`To: ${endDate}`}
              onClear={() => {
                setEndDate("");
                setPage(1);
              }}
            />
          )}
          {sector && (
            <FilterChip
              label={`Sector: ${sector}`}
              onClear={() => {
                setSector("");
                setPage(1);
              }}
            />
          )}
          {assetName && (
            <FilterChip
              label={`Asset: ${assetName}`}
              onClear={() => {
                setAssetName("");
                setPage(1);
              }}
            />
          )}
          {isLate && (
            <FilterChip
              label="Late filings (over 45 days)"
              onClear={() => {
                setIsLate(false);
                setPage(1);
              }}
            />
          )}
          {marketTrades && (
            <FilterChip
              label="Market trades only"
              onClear={() => {
                setMarketTrades(false);
                setPage(1);
              }}
            />
          )}
          <button onClick={clearAllFilters} className="ml-auto font-semibold hover:underline">
            Clear all
          </button>
        </div>
      )}

      {/* High-Performance Table */}
      <div className="rounded-xl border border-border/50 bg-card shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border/60 bg-muted/20 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <SortableTh label="Filer Name" columnKey="filer_name" activeKey={sortKey} activeOrder={sortOrder} onSort={toggleSort} />
                <SortableTh label="Chamber" columnKey="chamber" activeKey={sortKey} activeOrder={sortOrder} onSort={toggleSort} />
                <SortableTh label="Filed Date" columnKey="filed_date" activeKey={sortKey} activeOrder={sortOrder} onSort={toggleSort} />
                <SortableTh label="Trade Date" columnKey="trade_date" activeKey={sortKey} activeOrder={sortOrder} onSort={toggleSort} />
                <SortableTh label="Ticker" columnKey="ticker" activeKey={sortKey} activeOrder={sortOrder} onSort={toggleSort} />
                <SortableTh label="Asset Name" columnKey="asset_name" activeKey={sortKey} activeOrder={sortOrder} onSort={toggleSort} />
                <SortableTh label="Action" columnKey="action" align="center" activeKey={sortKey} activeOrder={sortOrder} onSort={toggleSort} />
                <SortableTh label="Value Range" columnKey="value_range" align="right" activeKey={sortKey} activeOrder={sortOrder} onSort={toggleSort} />
                <SortableTh label="Ownership" columnKey="ownership" align="center" activeKey={sortKey} activeOrder={sortOrder} onSort={toggleSort} />
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
                              title={`Filed ${rec.days_late} days after trade (exceeds STOCK Act 45-day deadline)`}
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
        <div className="flex flex-col gap-2 border-t border-border/50 px-4 py-3 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
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
