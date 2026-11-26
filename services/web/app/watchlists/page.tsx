"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  Plus,
  Trash2,
  TrendingUp,
  TrendingDown,
  Bell,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { validateWatchlistValue } from "@/lib/watchlist-validation";

interface WatchlistItem {
  id: string;
  type: "ticker" | "member";
  value: string;
  created_at: string | null;
}

interface FeedRow {
  doc_id: string;
  filer_name: string;
  chamber: string;
  filing_date: string | null;
  transaction_date: string | null;
  ticker: string | null;
  asset_name: string | null;
  action: string | null;
  value_range: string | null;
}

export default function WatchlistsPage() {
  const { token } = useAuth();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [feed, setFeed] = useState<FeedRow[]>([]);
  const [newItemType, setNewItemType] = useState<"ticker" | "member">("ticker");
  const [newItemName, setNewItemName] = useState("");
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Live validation so free-form values are rejected before submission.
  const validation = useMemo(
    () => validateWatchlistValue(newItemType, newItemName),
    [newItemType, newItemName],
  );
  const showError = touched && newItemName.trim() !== "" && !validation.valid;

  const authHeaders = useCallback(
    (): Record<string, string> =>
      token ? { Authorization: `Bearer ${token}` } : {},
    [token],
  );

  const load = useCallback(async () => {
    try {
      const [wRes, fRes] = await Promise.all([
        fetch("/api/watchlists", { headers: authHeaders() }),
        fetch("/api/watchlists/feed", { headers: authHeaders() }),
      ]);
      if (wRes.ok) setItems((await wRes.json()).items || []);
      if (fRes.ok) setFeed((await fRes.json()).results || []);
    } catch (e: any) {
      setError(e.message);
    }
  }, [authHeaders]);

  useEffect(() => {
    load();
  }, [load]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    const check = validateWatchlistValue(newItemType, newItemName);
    if (!check.valid) {
      setError(check.error || "Invalid value.");
      return;
    }
    setError(null);
    try {
      const res = await fetch("/api/watchlists", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ type: newItemType, value: check.normalized }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Failed to add");
      setNewItemName("");
      setTouched(false);
      load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleRemove = async (id: string) => {
    setError(null);
    try {
      const res = await fetch(`/api/watchlists/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!res.ok && res.status !== 204) {
        throw new Error((await res.json()).detail || "Failed to remove");
      }
      load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const statsFor = (item: WatchlistItem) => {
    const rows = feed.filter((r) =>
      item.type === "ticker"
        ? r.ticker === item.value
        : r.filer_name === item.value,
    );
    const last = rows[0];
    const action = (last?.action || "").toLowerCase();
    const sentiment = action.includes("purchase")
      ? "Bullish"
      : action.includes("sale")
        ? "Bearish"
        : "Neutral";
    return {
      count: rows.length,
      lastTrade: last?.filing_date || last?.transaction_date || "—",
      sentiment,
    };
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Surveillance Watchlists
          </h1>
          <p className="mt-1 text-xs text-muted-foreground sm:text-sm">
            Pin high-conviction tickers or congressional members for priority alerts and dedicated timeline activity.
          </p>
        </div>

        {/* Quick Add Form */}
        <form onSubmit={handleAdd} className="flex flex-col items-stretch gap-1.5 sm:items-end">
          <div className="flex items-center gap-2">
            <select
              value={newItemType}
              onChange={(e) => {
                setNewItemType(e.target.value as any);
                setNewItemName("");
                setTouched(false);
              }}
              className="rounded-lg border border-border/60 bg-card px-2.5 py-1.5 text-xs text-foreground focus:border-emerald-500 focus:outline-none"
            >
              <option value="ticker">Ticker</option>
              <option value="member">Member</option>
            </select>
            <input
              type="text"
              placeholder={newItemType === "ticker" ? "e.g. AAPL" : "e.g. Josh Gottheimer"}
              value={newItemName}
              maxLength={newItemType === "ticker" ? 8 : 60}
              autoCapitalize={newItemType === "ticker" ? "characters" : "words"}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={showError}
              onChange={(e) => {
                const v = e.target.value;
                setNewItemName(newItemType === "ticker" ? v.toUpperCase() : v);
                setTouched(true);
              }}
              className={cn(
                "w-40 sm:w-48 rounded-lg border bg-card px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none",
                showError
                  ? "border-rose-500/60 focus:border-rose-500"
                  : "border-border/60 focus:border-emerald-500",
              )}
            />
            <button
              type="submit"
              disabled={!validation.valid}
              title={validation.valid ? "Pin to watchlist" : validation.error}
              className="flex items-center gap-1 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-600 transition-colors disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Pin</span>
            </button>
          </div>
          {showError ? (
            <p className="text-[11px] text-rose-400">{validation.error}</p>
          ) : (
            <p className="text-[11px] text-muted-foreground">
              {newItemType === "ticker"
                ? "1–5 letters, e.g. AAPL or BRK.B"
                : "Full name, e.g. Josh Gottheimer"}
            </p>
          )}
        </form>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-950/60 p-3.5 text-xs text-rose-300">
          {error}
        </div>
      )}

      {/* Pinned Cards Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 mb-10">
        {items.map((item) => {
          const stats = statsFor(item);
          return (
            <div
              key={item.id}
              className="group relative rounded-xl border border-border/50 bg-card p-5 shadow-sm transition-all hover:border-border"
            >
              <div className="flex items-start justify-between">
                <div>
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] font-bold uppercase",
                      item.type === "ticker"
                        ? "bg-accent text-accent-foreground font-mono"
                        : "bg-blue-500/10 text-blue-400",
                    )}
                  >
                    {item.type}
                  </span>
                  <h3 className="mt-2 text-lg font-bold tracking-tight text-foreground">
                    {item.value}
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    {item.type === "ticker" ? "Monitored Ticker" : "Monitored Member"}
                  </p>
                </div>

                <button
                  onClick={() => handleRemove(item.id)}
                  className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-rose-400 transition-opacity p-1"
                  title="Remove from Watchlist"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-border/40 pt-3 text-xs">
                <span className="text-muted-foreground">
                  Trades: <strong className="text-foreground">{stats.count}</strong>
                </span>
                <div
                  className={cn(
                    "flex items-center gap-1 text-[11px] font-semibold",
                    stats.sentiment === "Bearish"
                      ? "text-rose-400"
                      : stats.sentiment === "Bullish"
                        ? "text-emerald-400"
                        : "text-muted-foreground",
                  )}
                >
                  {stats.sentiment === "Bearish" ? (
                    <TrendingDown className="h-3 w-3" />
                  ) : (
                    <TrendingUp className="h-3 w-3" />
                  )}
                  <span>{stats.sentiment}</span>
                </div>
                <span className="font-mono text-[11px] text-muted-foreground">
                  {stats.lastTrade}
                </span>
              </div>
            </div>
          );
        })}
        {items.length === 0 && (
          <div className="col-span-full rounded-xl border border-border/50 bg-card p-8 text-center text-xs text-muted-foreground">
            No watchlist entries yet. Pin a ticker or member above.
          </div>
        )}
      </div>

      {/* Monitoring Feed Timeline */}
      <div className="rounded-xl border border-border/50 bg-card p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bell className="h-4 w-4 text-emerald-500" />
            <h3 className="text-base font-semibold text-foreground">Dedicated Watchlist Activity Feed</h3>
          </div>
          <span className="text-xs text-muted-foreground">Real-time alerts</span>
        </div>

        <div className="divide-y divide-border/30">
          {feed.map((row, idx) => (
            <div
              key={`${row.doc_id}-${idx}`}
              className="py-3.5 flex items-start justify-between text-xs"
            >
              <div>
                <span className="font-semibold text-foreground">{row.filer_name}</span>{" "}
                {row.action?.toLowerCase().includes("sale") ? "sold" : "traded"}{" "}
                <strong className="font-mono text-emerald-400">
                  {row.ticker || row.asset_name || "—"}
                </strong>{" "}
                ({row.value_range || "—"}).
                <div className="text-[11px] text-muted-foreground mt-0.5">
                  {row.chamber} · Filed {row.filing_date || "—"}
                </div>
              </div>
              <span className="font-mono text-muted-foreground text-[11px]">
                {row.transaction_date || "—"}
              </span>
            </div>
          ))}
          {feed.length === 0 && (
            <div className="py-6 text-center text-xs text-muted-foreground">
              No recent activity for your watchlist.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
