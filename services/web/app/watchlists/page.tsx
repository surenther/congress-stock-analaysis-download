"use client";

import React, { useState } from "react";
import {
  BookmarkCheck,
  Plus,
  Trash2,
  TrendingUp,
  TrendingDown,
  Bell,
  Star,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface PinnedItem {
  id: string;
  type: "ticker" | "member";
  name: string;
  subtitle: string;
  trades_count: number;
  last_trade: string;
  sentiment: "Bullish" | "Bearish" | "Neutral";
}

export default function WatchlistsPage() {
  const [watchlist, setWatchlist] = useState<PinnedItem[]>([
    {
      id: "pin-1",
      type: "ticker",
      name: "NVDA",
      subtitle: "NVIDIA Corporation",
      trades_count: 48,
      last_trade: "2026-08-04",
      sentiment: "Bullish",
    },
    {
      id: "pin-2",
      type: "ticker",
      name: "MSFT",
      subtitle: "Microsoft Corporation",
      trades_count: 36,
      last_trade: "2026-08-29",
      sentiment: "Bullish",
    },
    {
      id: "pin-3",
      type: "member",
      name: "Rep. Nancy Pelosi",
      subtitle: "House · CA-11",
      trades_count: 14,
      last_trade: "2026-08-04",
      sentiment: "Bullish",
    },
    {
      id: "pin-4",
      type: "member",
      name: "Sen. Markwayne Mullin",
      subtitle: "Senate · OK",
      trades_count: 9,
      last_trade: "2026-09-25",
      sentiment: "Bearish",
    },
    {
      id: "pin-5",
      type: "ticker",
      name: "LMT",
      subtitle: "Lockheed Martin Corp.",
      trades_count: 18,
      last_trade: "2026-08-01",
      sentiment: "Bullish",
    },
  ]);

  const [newItemType, setNewItemType] = useState<"ticker" | "member">("ticker");
  const [newItemName, setNewItemName] = useState("");

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newItemName.trim()) return;

    const newItem: PinnedItem = {
      id: `pin-${Date.now()}`,
      type: newItemType,
      name: newItemType === "ticker" ? newItemName.trim().toUpperCase() : newItemName.trim(),
      subtitle: newItemType === "ticker" ? "Monitored Equity Target" : "Congressional Representative",
      trades_count: 1,
      last_trade: new Date().toISOString().split("T")[0],
      sentiment: "Bullish",
    };
    setWatchlist([newItem, ...watchlist]);
    setNewItemName("");
  };

  const handleRemove = (id: string) => {
    setWatchlist(watchlist.filter((w) => w.id !== id));
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
        <form onSubmit={handleAdd} className="flex items-center gap-2">
          <select
            value={newItemType}
            onChange={(e) => setNewItemType(e.target.value as any)}
            className="rounded-lg border border-border/60 bg-card px-2.5 py-1.5 text-xs text-foreground focus:border-emerald-500 focus:outline-none"
          >
            <option value="ticker">Ticker</option>
            <option value="member">Member</option>
          </select>
          <input
            type="text"
            placeholder={newItemType === "ticker" ? "e.g. AAPL" : "e.g. Josh Gottheimer"}
            value={newItemName}
            onChange={(e) => setNewItemName(e.target.value)}
            className="w-40 sm:w-48 rounded-lg border border-border/60 bg-card px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald-500 focus:outline-none"
          />
          <button
            type="submit"
            className="flex items-center gap-1 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-600 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Pin</span>
          </button>
        </form>
      </div>

      {/* Pinned Cards Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 mb-10">
        {watchlist.map((item) => (
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
                      : "bg-blue-500/10 text-blue-400"
                  )}
                >
                  {item.type}
                </span>
                <h3 className="mt-2 text-lg font-bold tracking-tight text-foreground">
                  {item.name}
                </h3>
                <p className="text-xs text-muted-foreground">{item.subtitle}</p>
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
                Trades: <strong className="text-foreground">{item.trades_count}</strong>
              </span>
              <div className="flex items-center gap-1 text-[11px] font-semibold text-emerald-400">
                <TrendingUp className="h-3 w-3" />
                <span>{item.sentiment}</span>
              </div>
              <span className="font-mono text-[11px] text-muted-foreground">
                {item.last_trade}
              </span>
            </div>
          </div>
        ))}
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
          <div className="py-3.5 flex items-start justify-between text-xs">
            <div>
              <span className="font-semibold text-foreground">Rep. Nancy Pelosi</span> filed a periodic transaction for{" "}
              <strong className="font-mono text-emerald-400">NVDA</strong> (50 Call Options, value $1M - $5M).
              <div className="text-[11px] text-muted-foreground mt-0.5">Filing disclosed in compliance with STOCK Act (13 days).</div>
            </div>
            <span className="font-mono text-muted-foreground text-[11px]">2 hours ago</span>
          </div>
          <div className="py-3.5 flex items-start justify-between text-xs">
            <div>
              <span className="font-semibold text-foreground">Sen. Markwayne Mullin</span> sold equity shares of{" "}
              <strong className="font-mono text-rose-400">RTX</strong> ($100K - $250K).
              <div className="text-[11px] text-rose-400 mt-0.5">⚠️ Flagged as late disclosure (85 days to disclose).</div>
            </div>
            <span className="font-mono text-muted-foreground text-[11px]">Yesterday</span>
          </div>
          <div className="py-3.5 flex items-start justify-between text-xs">
            <div>
              <strong className="font-mono text-emerald-400">MSFT</strong> traded by Rep. Josh Gottheimer in joint investment account ($250K - $500K).
              <div className="text-[11px] text-muted-foreground mt-0.5">Total of 36 congressional trades recorded for MSFT this quarter.</div>
            </div>
            <span className="font-mono text-muted-foreground text-[11px]">3 days ago</span>
          </div>
        </div>
      </div>
    </div>
  );
}
