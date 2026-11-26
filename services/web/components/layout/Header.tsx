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
  Menu,
  X,
} from "lucide-react";
import { BrandBadge } from "@/components/layout/BrandLogo";
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
    token,
    chamberScope,
    setChamberScope,
    isChamberLocked,
    lockedReason,
    timeHorizon,
    setTimeHorizon,
    assetClass,
    setAssetClass,
    logout,
  } = useAuth();

  const [clusterHealth, setClusterHealth] = useState<ServiceHealth[]>([]);

  const [timeDropdownOpen, setTimeDropdownOpen] = useState(false);
  const [roleSwitchOpen, setRoleSwitchOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Close the mobile menu whenever the route changes.
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  // Poll cluster health
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch("/api/health/cluster", {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const data = await res.json();
          setClusterHealth(data.services || []);
        }
      } catch {
        setClusterHealth([]);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 20000);
    return () => clearInterval(interval);
  }, [token]);

  const timeOptions = ["30 Days", "90 Days", "YTD", "1 Year", "All Time"];
  const assetClasses = ["Stock", "Bond", "Other", "All"] as const;

  const navLinks = [
    { label: "Executive Analytics", href: "/dashboard", icon: Layers },
    { label: "Disclosure Grid", href: "/search", icon: Search },
    { label: "Watchlists", href: "/watchlists", icon: BookmarkCheck },
    ...(user?.role === "admin"
      ? [{ label: "Command Center", href: "/admin", icon: ShieldCheck }]
      : []),
  ];

  const chamberScopes = ["House", "Senate", "Combined"] as const;

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/60 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        {/* Brand (left) */}
        <Link href="/dashboard" className="flex shrink-0 items-center gap-2.5">
          <BrandBadge size="md" />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 font-bold tracking-tight text-foreground">
              <span>CONGRESS</span>
              <span className="text-xs font-semibold uppercase tracking-widest text-emerald-500">
                ALPHA
              </span>
            </div>
            <p className="hidden text-[10px] text-muted-foreground sm:block">
              Executive Stock Intelligence
            </p>
          </div>
        </Link>

        {/* Nav + Controls (right-aligned) */}
        <div className="flex min-w-0 items-center gap-3">
          <nav className="hidden xl:flex items-center gap-0.5">
            {navLinks.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
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

          {/* Desktop Controls: Chamber Selector, Horizon, Cluster Health, User Pill */}
          <div className="hidden xl:flex shrink-0 items-center gap-3">
            {/* Chamber Scope Selector */}
            <div className="flex items-center rounded-lg bg-muted/40 p-1 border border-border/40">
              {chamberScopes.map((scope) => {
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

            {/* Asset Class Selector */}
            <div className="flex items-center rounded-lg bg-muted/40 p-1 border border-border/40">
              {assetClasses.map((ac) => {
                const isSelected = assetClass === ac;
                return (
                  <button
                    key={ac}
                    type="button"
                    onClick={() => setAssetClass(ac)}
                    title={`Filter analytics to ${ac} assets`}
                    className={cn(
                      "rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                      isSelected
                        ? "bg-emerald-500 text-white font-semibold shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {ac}
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
            <div className="hidden 2xl:flex items-center gap-1.5 rounded-lg border border-border/40 bg-card/50 px-2 py-1 text-[11px]">
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
                <span className="font-semibold text-foreground">{user?.username}</span>
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
                    Signed in as{" "}
                    <span className="font-semibold text-foreground">
                      {user?.username}
                    </span>
                  </div>
                  <div className="px-2 py-1.5 text-[10px] text-muted-foreground">
                    Scope: {(user?.allowed_chambers || []).join(", ") || "—"}
                  </div>
                  <div className="mt-1 pt-2 border-t border-border/40">
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

          {/* Mobile menu toggle */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen((v) => !v)}
            aria-label="Toggle navigation menu"
            aria-expanded={mobileMenuOpen}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-card text-foreground transition-colors hover:bg-accent xl:hidden"
          >
            {mobileMenuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* Mobile menu panel */}
      {mobileMenuOpen && (
        <div className="border-t border-border/60 bg-background xl:hidden">
          <div className="mx-auto max-w-7xl space-y-4 px-4 py-4 sm:px-6">
            {/* Nav links */}
            <nav className="flex flex-col gap-1">
              {navLinks.map((item) => {
                const Icon = item.icon;
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                );
              })}
            </nav>

            {/* Chamber scope */}
            <div>
              <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase text-muted-foreground">
                Chamber
                {isChamberLocked && <Lock className="h-3 w-3" />}
              </div>
              <div className="flex items-center rounded-lg bg-muted/40 p-1 border border-border/40">
                {chamberScopes.map((scope) => {
                  const isSelected = chamberScope === scope;
                  const isRestricted = isChamberLocked && scope !== "House";
                  return (
                    <button
                      key={scope}
                      type="button"
                      disabled={isRestricted}
                      onClick={() => setChamberScope(scope)}
                      className={cn(
                        "flex flex-1 items-center justify-center gap-1 rounded-md px-2.5 py-1.5 text-xs font-medium transition-all",
                        isSelected
                          ? "bg-emerald-500 text-white font-semibold shadow-sm"
                          : "text-muted-foreground hover:text-foreground",
                        isRestricted && "cursor-not-allowed opacity-40"
                      )}
                    >
                      {isRestricted && <Lock className="h-3 w-3 mr-0.5" />}
                      {scope}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Asset class */}
            <div>
              <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase text-muted-foreground">
                <Layers className="h-3 w-3" /> Asset Class
              </div>
              <div className="flex items-center rounded-lg bg-muted/40 p-1 border border-border/40">
                {assetClasses.map((ac) => {
                  const isSelected = assetClass === ac;
                  return (
                    <button
                      key={ac}
                      type="button"
                      onClick={() => setAssetClass(ac)}
                      className={cn(
                        "flex flex-1 items-center justify-center rounded-md px-2.5 py-1.5 text-xs font-medium transition-all",
                        isSelected
                          ? "bg-emerald-500 text-white font-semibold shadow-sm"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {ac}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Time horizon */}
            <div>
              <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase text-muted-foreground">
                <Clock className="h-3 w-3" /> Time Horizon
              </div>
              <div className="flex flex-wrap gap-1.5">
                {timeOptions.map((opt) => (
                  <button
                    key={opt}
                    onClick={() => setTimeHorizon(opt)}
                    className={cn(
                      "rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors",
                      timeHorizon === opt
                        ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500"
                        : "border-border/50 text-muted-foreground hover:bg-muted"
                    )}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>

            {/* User + sign out */}
            <div className="flex items-center justify-between gap-3 border-t border-border/40 pt-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-foreground">
                  {user?.username}
                </div>
                <div className="truncate text-[11px] text-muted-foreground">
                  {user?.role || "user"} ·{" "}
                  {(user?.allowed_chambers || []).join(", ") || "—"}
                </div>
              </div>
              <button
                onClick={logout}
                className="flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-rose-400 hover:bg-rose-500/10 transition-colors"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign Out
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
