"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  Lock,
  Activity,
  Layers,
  Search,
  BookmarkCheck,
  ShieldCheck,
  ChevronDown,
  Clock,
  Sparkles,
  LogOut,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface ServiceHealth {
  name: string;
  port: number;
  healthy: boolean;
}

export function Header() {
  const pathname = usePathname();
  const {
    user,
    chamberScope,
    setChamberScope,
    isChamberLocked,
    lockedReason,
    timeHorizon,
    setTimeHorizon,
    loginAs,
    logout,
  } = useAuth();

  const [clusterHealth, setClusterHealth] = useState<ServiceHealth[]>([
    { name: "Downloader", port: 8511, healthy: true },
    { name: "Auth", port: 8512, healthy: true },
    { name: "Parser", port: 8513, healthy: true },
    { name: "Vectorizer", port: 8514, healthy: true },
    { name: "RAG", port: 8516, healthy: true },
    { name: "LiteLLM", port: 4000, healthy: true },
  ]);

  const [timeDropdownOpen, setTimeDropdownOpen] = useState(false);
  const [roleSwitchOpen, setRoleSwitchOpen] = useState(false);

  // Poll cluster health
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch("/api/health/cluster");
        if (res.ok) {
          const data = await res.json();
          if (data.services) {
            setClusterHealth(data.services);
          }
        }
      } catch {
        // Fallback to initial state
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 20000);
    return () => clearInterval(interval);
  }, []);

  const timeOptions = ["30 Days", "90 Days", "YTD", "1 Year", "All Time"];

  const navLinks = [
    { label: "Executive Analytics", href: "/dashboard", icon: Layers },
    { label: "Disclosure Grid", href: "/search", icon: Search },
    { label: "Watchlists", href: "/watchlists", icon: BookmarkCheck },
    ...(user?.role === "admin"
      ? [{ label: "Command Center", href: "/admin", icon: ShieldCheck }]
      : []),
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/60 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Brand & Main Nav */}
        <div className="flex items-center gap-6">
          <Link href="/dashboard" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500 ring-1 ring-emerald-500/30">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-1.5 font-bold tracking-tight text-foreground">
                <span>CONGRESS</span>
                <span className="text-xs font-semibold uppercase tracking-widest text-emerald-500">
                  ALPHA
                </span>
              </div>
              <p className="text-[10px] text-muted-foreground">Executive Stock Intelligence</p>
            </div>
          </Link>

          <nav className="hidden md:flex items-center gap-1 pl-4 border-l border-border/40">
            {navLinks.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                    isActive
                      ? "bg-accent text-accent-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Controls: Chamber Selector, Horizon, Cluster Health, User Pill */}
        <div className="flex items-center gap-3">
          {/* Chamber Scope Selector */}
          <div className="flex items-center rounded-lg bg-muted/40 p-1 border border-border/40">
            {(["House", "Senate", "Combined"] as const).map((scope) => {
              const isSelected = chamberScope === scope;
              const isRestricted = isChamberLocked && scope !== "House";

              return (
                <button
                  key={scope}
                  type="button"
                  disabled={isRestricted}
                  onClick={() => setChamberScope(scope)}
                  title={isRestricted ? lockedReason : `Filter to ${scope}`}
                  className={cn(
                    "relative flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                    isSelected
                      ? "bg-emerald-500 text-white font-semibold shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                    isRestricted && "cursor-not-allowed opacity-40 hover:text-muted-foreground"
                  )}
                >
                  {isRestricted && <Lock className="h-3 w-3 text-muted-foreground mr-0.5" />}
                  {scope}
                </button>
              );
            })}
          </div>

          {/* Time Horizon Selector */}
          <div className="relative">
            <button
              onClick={() => setTimeDropdownOpen(!timeDropdownOpen)}
              className="flex items-center gap-1.5 rounded-lg border border-border/50 bg-card px-2.5 py-1 text-xs font-medium text-foreground hover:bg-accent transition-colors"
            >
              <Clock className="h-3 w-3 text-muted-foreground" />
              <span>{timeHorizon}</span>
              <ChevronDown className="h-3 w-3 text-muted-foreground" />
            </button>
            {timeDropdownOpen && (
              <div className="absolute right-0 mt-1 w-32 rounded-lg border border-border bg-card p-1 shadow-lg z-50">
                {timeOptions.map((opt) => (
                  <button
                    key={opt}
                    onClick={() => {
                      setTimeHorizon(opt);
                      setTimeDropdownOpen(false);
                    }}
                    className={cn(
                      "w-full text-left rounded px-2 py-1 text-xs transition-colors",
                      timeHorizon === opt
                        ? "bg-emerald-500/10 text-emerald-500 font-semibold"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    )}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Cluster Status Dots */}
          <div className="hidden lg:flex items-center gap-1.5 rounded-lg border border-border/40 bg-card/50 px-2 py-1 text-[11px]">
            <Activity className="h-3 w-3 text-emerald-400" />
            <span className="text-muted-foreground">Cluster:</span>
            <div className="flex items-center gap-1">
              {clusterHealth.map((svc) => (
                <span
                  key={svc.name}
                  title={`${svc.name} (Port ${svc.port}): ${svc.healthy ? "Healthy" : "Offline"}`}
                  className={cn(
                    "h-2 w-2 rounded-full cursor-help",
                    svc.healthy ? "bg-emerald-500" : "bg-rose-500"
                  )}
                />
              ))}
            </div>
          </div>

          {/* User Scope Pill & Role Switcher */}
          <div className="relative">
            <button
              onClick={() => setRoleSwitchOpen(!roleSwitchOpen)}
              className="flex items-center gap-2 rounded-full border border-border/60 bg-card px-2.5 py-1 text-xs font-medium hover:border-border transition-colors"
            >
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              <span className="font-semibold text-foreground">{user?.username || "Guest"}</span>
              <span
                className={cn(
                  "rounded px-1.5 py-0.2 text-[10px] font-bold uppercase",
                  user?.role === "admin"
                    ? "bg-amber-500/10 text-amber-500 border border-amber-500/20"
                    : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                )}
              >
                {user?.role || "user"}
              </span>
              <ChevronDown className="h-3 w-3 text-muted-foreground" />
            </button>

            {roleSwitchOpen && (
              <div className="absolute right-0 mt-2 w-56 rounded-xl border border-border bg-card p-2 shadow-xl z-50">
                <div className="px-2 py-1 border-b border-border/50 text-[11px] text-muted-foreground">
                  Switch Role / CBAC Scope Demo:
                </div>
                <button
                  onClick={() => {
                    loginAs("admin", ["House", "Senate"]);
                    setRoleSwitchOpen(false);
                  }}
                  className="w-full text-left rounded-lg p-2 text-xs hover:bg-muted transition-colors mt-1"
                >
                  <div className="font-semibold text-foreground">Admin (House + Senate)</div>
                  <div className="text-[10px] text-muted-foreground">Unrestricted full cluster access</div>
                </button>
                <button
                  onClick={() => {
                    loginAs("user", ["House"]);
                    setRoleSwitchOpen(false);
                  }}
                  className="w-full text-left rounded-lg p-2 text-xs hover:bg-muted transition-colors mt-1"
                >
                  <div className="font-semibold text-foreground">Restricted User (House Only)</div>
                  <div className="text-[10px] text-rose-400">Triggers CBAC lock & 403 checks</div>
                </button>
                <div className="mt-2 pt-2 border-t border-border/40">
                  <button
                    onClick={() => {
                      setRoleSwitchOpen(false);
                      logout();
                    }}
                    className="flex w-full items-center gap-2 rounded-lg p-2 text-xs text-rose-400 hover:bg-rose-500/10 transition-colors"
                  >
                    <LogOut className="h-3.5 w-3.5" />
                    <span>Sign Out</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
