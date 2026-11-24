"use client";

import React, { useState, useRef, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
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
} from "lucide-react";
import { cn } from "@/lib/utils";

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
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: SourceCitation[];
  error?: boolean;
  isScopeError?: boolean;
}

export function ChatDrawer() {
  const { user, token, chamberScope } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});
  const [scopeToast, setScopeToast] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "initial-1",
      role: "assistant",
      content:
        "Welcome to the **Congressional Stock Intelligence AI Assistant**. Ask me anything about stock disclosures, STOCK Act compliance, recent trades, or committee conflict investigations.",
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isOpen]);

  const toggleSource = (msgId: string, idx: number) => {
    const key = `${msgId}-${idx}`;
    setExpandedSources((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim() || loading) return;

    const userText = query.trim();
    setQuery("");
    setScopeToast(null);

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      role: "user",
      content: userText,
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await fetch("/api/rag/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({
          query: userText,
          chamber: chamberScope === "Combined" ? undefined : chamberScope,
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
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/30">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-foreground">AI Intelligence Assistant</h3>
                <p className="text-[11px] text-muted-foreground">
                  Scope: <span className="font-mono text-emerald-400">{chamberScope}</span>
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

                <div className="whitespace-pre-wrap">{msg.content}</div>

                {/* Source Citations */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-3 border-t border-border/40 pt-2 space-y-1.5">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                      Cited Disclosure Sources ({msg.sources.length})
                    </span>
                    {msg.sources.map((src, idx) => {
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
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
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
