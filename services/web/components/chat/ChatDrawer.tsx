"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { horizonToStartDate } from "@/lib/search-links";
import {
  MessageSquare,
  X,
  Send,
  Sparkles,
  ChevronDown,
  ChevronUp,
  FileText,
  AlertTriangle,
  Loader2,
  ExternalLink,
  ShieldAlert,
  Globe,
  Filter,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { BrandBadge } from "@/components/layout/BrandLogo";
import { MessageContent } from "./MessageContent";

interface SourceCitation {
  filer_name?: string;
  chamber?: string;
  ticker?: string;
  asset_name?: string;
  action?: string;
  date?: string; // transaction date
  filing_date?: string; // filed date
  value_range?: string;
  similarity_score?: number;
  days_late?: number | null;
  is_late?: boolean | null;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: SourceCitation[];
  error?: boolean;
  isScopeError?: boolean;
  /** Human-readable scope the answer was restricted to (null when broad). */
  scopeLabel?: string | null;
  /** The original prompt, so "Search broadly" can re-run it. */
  prompt?: string;
  /** True when the answer was produced without screen filters. */
  broad?: boolean;
}

interface GridFilters {
  ticker?: string;
  filer_name?: string;
  action?: string;
  sector?: string;
  asset_name?: string;
  start_date?: string;
  end_date?: string;
}

/** Collapse duplicate citations that point at the same filer/ticker/date/asset. */
function dedupeSources(sources?: SourceCitation[]): SourceCitation[] {
  if (!sources || sources.length === 0) return [];
  const seen = new Set<string>();
  const out: SourceCitation[] = [];
  for (const s of sources) {
    const key = [
      s.filer_name || "",
      s.ticker || "",
      s.date || s.filing_date || "",
      s.asset_name || "",
    ].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(s);
  }
  return out;
}

export function ChatDrawer() {
  const { user, token, chamberScope, timeHorizon, assetClass } = useAuth();
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});
  const [scopeToast, setScopeToast] = useState<string | null>(null);
  const [gridFilters, setGridFilters] = useState<GridFilters>({});

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "initial-1",
      role: "assistant",
      content:
        "Welcome to the **Congressional Stock Intelligence AI Assistant**. Ask me anything about stock disclosures, STOCK Act compliance, recent trades, or committee conflict investigations.",
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const isSearch = !!pathname?.startsWith("/search");
  const isWatchlists = !!pathname?.startsWith("/watchlists");
  const pageLabel = isSearch
    ? "Disclosure Grid"
    : isWatchlists
      ? "Watchlists"
      : "Executive Analytics";

  // Read the active grid filters from the URL whenever the drawer opens or the
  // route changes, so the assistant is aware of the on-screen search state.
  useEffect(() => {
    if (!isOpen || typeof window === "undefined") return;
    const sp = new URLSearchParams(window.location.search);
    setGridFilters({
      ticker: sp.get("ticker") || undefined,
      filer_name: sp.get("filer_name") || undefined,
      action: sp.get("action") || undefined,
      sector: sp.get("sector") || undefined,
      asset_name: sp.get("asset_name") || undefined,
      start_date: sp.get("start_date") || undefined,
      end_date: sp.get("end_date") || undefined,
    });
  }, [isOpen, pathname]);

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isOpen]);

  /** Human-readable scope label for the active screen context. */
  const scopeLabel = useMemo(() => {
    const parts = [
      chamberScope,
      timeHorizon,
      assetClass === "All" ? "All Assets" : `${assetClass}s`,
    ];
    if (isSearch) {
      if (gridFilters.ticker) parts.push(`Ticker: ${gridFilters.ticker}`);
      if (gridFilters.filer_name) parts.push(`Filer: ${gridFilters.filer_name}`);
      if (gridFilters.action) parts.push(`Action: ${gridFilters.action}`);
      if (gridFilters.sector) parts.push(`Sector: ${gridFilters.sector}`);
    }
    return parts.join(" • ");
  }, [chamberScope, timeHorizon, assetClass, isSearch, gridFilters]);

  /** Build the filter payload sent to the RAG service for scoped execution. */
  const buildFilters = (): Record<string, string> => {
    const f: Record<string, string> = {};
    if (chamberScope && chamberScope !== "Combined") f.chamber = chamberScope;
    if (assetClass && assetClass !== "All") f.asset_class = assetClass;
    const horizonStart = horizonToStartDate(timeHorizon);
    if (horizonStart) f.start_date = horizonStart;
    if (isSearch) {
      if (gridFilters.ticker) f.ticker = gridFilters.ticker;
      if (gridFilters.filer_name) f.filer_name = gridFilters.filer_name;
      if (gridFilters.action) f.action = gridFilters.action;
      if (gridFilters.sector) f.asset_category = gridFilters.sector;
      if (gridFilters.asset_name) f.asset_name = gridFilters.asset_name;
      if (gridFilters.start_date) f.start_date = gridFilters.start_date;
      if (gridFilters.end_date) f.end_date = gridFilters.end_date;
    }
    return f;
  };

  /** Context-derived suggested prompts (3-4) for the active screen. */
  const suggestedPrompts = useMemo(() => {
    const assetWord = assetClass === "All" ? "assets" : `${assetClass.toLowerCase()}s`;
    if (isSearch) {
      const chips = [
        "Summarize the transactions currently filtered in this table.",
        "Who traded the largest single position in these results?",
      ];
      if (gridFilters.ticker) {
        chips.push(`What is the recent trading pattern for ${gridFilters.ticker}?`);
      } else {
        chips.push("Which members were the most active in these results?");
      }
      chips.push("Are there any STOCK Act late filings in these results?");
      return chips.slice(0, 4);
    }
    if (isWatchlists) {
      return [
        "Summarize recent activity for my watched members and tickers.",
        "Which of my watched tickers had the largest trades recently?",
        "Are there any late filings among my watched members?",
      ];
    }
    // Executive Analytics
    return [
      `Which members purchased the highest volume of ${assetWord} in the last ${timeHorizon.toLowerCase()}?`,
      `Summarize net capital flows for ${assetWord} across both chambers.`,
      `Are there any STOCK Act late filings for ${assetWord} purchases in this window?`,
      `Which sectors are seeing the most ${assetWord} activity?`,
    ];
  }, [isSearch, isWatchlists, assetClass, timeHorizon, gridFilters.ticker]);

  const toggleSource = (msgId: string, idx: number) => {
    const key = `${msgId}-${idx}`;
    setExpandedSources((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const runQuery = async (userText: string, broad: boolean) => {
    setScopeToast(null);
    setLoading(true);

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      role: "user",
      content: broad ? `${userText}\n\n_(searching broadly across the entire database)_` : userText,
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const res = await fetch("/api/rag/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({
          query: userText,
          broad,
          filters: broad ? undefined : buildFilters(),
        }),
      });

      if (res.status === 403) {
        const errorData = await res.json().catch(() => ({}));
        const msg =
          errorData.message ||
          `Access Restricted: Your account permissions are limited to ${user?.allowed_chambers?.join(", ") || "House"} disclosures.`;
        setScopeToast(msg);
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: "assistant",
            content: `⚠️ **CBAC Security Guardrail:** ${msg}`,
            error: true,
            isScopeError: true,
          },
        ]);
        return;
      }

      if (!res.ok) {
        throw new Error(`Query failed with status ${res.status}`);
      }

      const data = await res.json();
      const assistantMsg: ChatMessage = {
        id: `asst-${Date.now()}`,
        role: "assistant",
        content: data.answer || data.content || "No synthesized answer returned.",
        sources: data.sources || [],
        scopeLabel: broad ? null : scopeLabel,
        prompt: userText,
        broad,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content:
            "Unable to reach the RAG synthesis microservice. Make sure services are running or verify your query parameters.",
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim() || loading) return;
    const userText = query.trim();
    setQuery("");
    await runQuery(userText, false);
  };

  const handleChip = (prompt: string) => {
    if (loading) return;
    runQuery(prompt, false);
  };

  const handleBroad = (prompt?: string) => {
    if (loading || !prompt) return;
    runQuery(prompt, true);
  };

  return (
    <>
      {/* Floating Action Button */}
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500 text-white shadow-xl hover:bg-emerald-600 transition-all hover:scale-105 focus:outline-none focus:ring-4 focus:ring-emerald-500/20"
        title="Open AI RAG Assistant"
      >
        <Sparkles className="h-6 w-6" />
        <span className="absolute -top-1 -right-1 flex h-4 w-4">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-300 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-4 w-4 bg-emerald-400"></span>
        </span>
      </button>

      {/* Scope Restriction Toast */}
      {scopeToast && (
        <div className="fixed bottom-24 right-6 z-50 flex max-w-md items-start gap-3 rounded-xl border border-rose-500/30 bg-rose-950/90 p-4 text-xs text-rose-200 shadow-2xl backdrop-blur">
          <ShieldAlert className="h-5 w-5 flex-shrink-0 text-rose-400" />
          <div className="flex-1">
            <h4 className="font-semibold text-rose-300">CBAC Policy Guardrail</h4>
            <p className="mt-0.5 leading-relaxed">{scopeToast}</p>
          </div>
          <button
            onClick={() => setScopeToast(null)}
            className="text-rose-400 hover:text-rose-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Slide-out Drawer Panel */}
      {isOpen && (
        <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col border-l border-border/80 bg-background/95 shadow-2xl backdrop-blur">
          {/* Drawer Header */}
          <div className="flex h-16 items-center justify-between border-b border-border/60 px-5">
            <div className="flex items-center gap-2.5">
              <BrandBadge size="sm" />
              <div>
                <h3 className="text-sm font-semibold text-foreground">AI Intelligence Assistant</h3>
                <p className="text-[11px] text-muted-foreground">
                  {pageLabel} · Scope:{" "}
                  <span className="font-mono text-emerald-400">{chamberScope}</span>
                </p>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Active context banner */}
          <div className="flex items-center gap-2 border-b border-border/40 bg-muted/20 px-5 py-2 text-[11px] text-muted-foreground">
            <Filter className="h-3 w-3 flex-shrink-0 text-emerald-500" />
            <span className="truncate">
              Scoped to: <span className="font-medium text-foreground">{scopeLabel}</span>
            </span>
          </div>

          {/* Chat Messages Body */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "flex flex-col rounded-xl p-3.5 text-xs leading-relaxed",
                  msg.role === "user"
                    ? "ml-8 bg-emerald-500/10 text-emerald-200 border border-emerald-500/20"
                    : msg.isScopeError
                      ? "bg-rose-950/40 text-rose-200 border border-rose-500/30"
                      : "mr-4 bg-card text-foreground border border-border/50"
                )}
              >
                <div className="flex items-center justify-between mb-1 text-[10px] uppercase font-semibold tracking-wider text-muted-foreground">
                  <span>{msg.role === "user" ? "You" : "AI Intelligence"}</span>
                </div>

                {/* Scoped-execution notification badge */}
                {msg.role === "assistant" && msg.scopeLabel && (
                  <div className="mb-2 inline-flex w-fit items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                    <Filter className="h-3 w-3" />
                    <span>Scoped to: {msg.scopeLabel}</span>
                  </div>
                )}
                {msg.role === "assistant" && msg.broad && (
                  <div className="mb-2 inline-flex w-fit items-center gap-1.5 rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[10px] font-medium text-sky-400">
                    <Globe className="h-3 w-3" />
                    <span>Broad search · entire database</span>
                  </div>
                )}

                {msg.role === "assistant" ? (
                  <MessageContent content={msg.content} />
                ) : (
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                )}

                {/* Source Citations (deduplicated) */}
                {msg.sources && msg.sources.length > 0 && (() => {
                  const sources = dedupeSources(msg.sources);
                  if (sources.length === 0) return null;
                  return (
                    <div className="mt-3 border-t border-border/40 pt-2 space-y-1.5">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                        Cited Disclosure Sources ({sources.length})
                      </span>
                      {sources.map((src, idx) => {
                        const isExpanded = expandedSources[`${msg.id}-${idx}`];
                        return (
                          <div
                            key={idx}
                            className="rounded-lg border border-border/40 bg-muted/20 p-2 text-[11px]"
                          >
                            <div
                              onClick={() => toggleSource(msg.id, idx)}
                              className="flex cursor-pointer items-center justify-between font-medium text-foreground hover:text-emerald-400 transition-colors"
                            >
                              <div className="flex items-center gap-1.5 truncate">
                                <FileText className="h-3.5 w-3.5 flex-shrink-0 text-emerald-500" />
                                <span className="font-semibold">{src.filer_name || "Official"}</span>
                                <span className="text-muted-foreground">({src.chamber || "Congress"})</span>
                                {src.ticker && (
                                  <span className="rounded bg-accent px-1 font-mono text-[10px] text-accent-foreground">
                                    {src.ticker}
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-2">
                                {src.similarity_score !== undefined && (
                                  <span className="font-mono text-[10px] text-emerald-400">
                                    {(src.similarity_score * 100).toFixed(0)}% match
                                  </span>
                                )}
                                {isExpanded ? (
                                  <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                                ) : (
                                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                                )}
                              </div>
                            </div>

                            {isExpanded && (
                              <div className="mt-2 space-y-1 border-t border-border/30 pt-2 font-mono text-[10px] text-muted-foreground">
                                <div>Asset: <span className="text-foreground">{src.asset_name || "—"}</span></div>
                                {src.action && (
                                  <div>Action: <span className="text-foreground">{src.action}</span></div>
                                )}
                                <div>Transaction Date: <span className="text-foreground">{src.date || "—"}</span></div>
                                <div>Filed Date: <span className="text-foreground">{src.filing_date || "—"}</span></div>
                                <div>Value: <span className="text-foreground">{src.value_range || "—"}</span></div>
                                {src.is_late && (
                                  <div>
                                    Status:{" "}
                                    <span className="font-semibold text-rose-400">
                                      LATE{src.days_late != null ? ` (${src.days_late} days)` : ""}
                                    </span>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                })()}

                {/* Broad-search escape hatch (only for scoped answers) */}
                {msg.role === "assistant" && msg.scopeLabel && msg.prompt && (
                  <button
                    onClick={() => handleBroad(msg.prompt)}
                    disabled={loading}
                    className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-2 text-[11px] font-medium text-sky-400 transition-colors hover:bg-sky-500/20 disabled:opacity-50"
                  >
                    <Globe className="h-3.5 w-3.5" />
                    <span>Search broadly (Query entire database without screen filters)</span>
                  </button>
                )}
              </div>
            ))}

            {/* Suggested prompt chips (fresh conversation) */}
            {messages.length <= 1 && !loading && (
              <div className="space-y-2">
                <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  <Sparkles className="h-3 w-3 text-emerald-500" />
                  Suggested for {pageLabel}
                </div>
                <div className="flex flex-col gap-1.5">
                  {suggestedPrompts.map((p) => (
                    <button
                      key={p}
                      onClick={() => handleChip(p)}
                      className="rounded-lg border border-border/50 bg-card px-3 py-2 text-left text-[11px] text-foreground transition-colors hover:border-emerald-500/40 hover:bg-emerald-500/5"
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {loading && (
              <div className="flex items-center gap-2 rounded-xl border border-border/50 bg-card p-3.5 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin text-emerald-500" />
                <span>Evaluating disclosures and synthesizing response...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Footer */}
          <form onSubmit={handleSend} className="border-t border-border/60 p-4">
            <div className="relative flex items-center">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask about Nancy Pelosi trades, NVDA purchases, late filings..."
                className="w-full rounded-xl border border-border/60 bg-card px-4 py-3 pr-12 text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
              <button
                type="submit"
                disabled={!query.trim() || loading}
                className="absolute right-2 flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500 text-white transition-opacity disabled:opacity-40 hover:bg-emerald-600"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="mt-2 flex items-center justify-between text-[10px] text-muted-foreground">
              <span>Press Enter to query RAG microservice (:8516)</span>
              <span>CBAC Enforced</span>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
