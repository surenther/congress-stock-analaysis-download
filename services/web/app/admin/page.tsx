"use client";

import React, { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  ShieldAlert,
  ShieldCheck,
  LayoutDashboard,
  Workflow,
  CalendarClock,
  Users,
  ScrollText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { OverviewTab } from "@/components/admin/OverviewTab";
import { PipelineTab } from "@/components/admin/PipelineTab";
import { SchedulesTab } from "@/components/admin/SchedulesTab";
import { UsersTab } from "@/components/admin/UsersTab";
import { AuditTab } from "@/components/admin/AuditTab";

type TabKey = "overview" | "pipeline" | "schedules" | "users" | "audit";

const TABS: { key: TabKey; label: string; icon: React.ElementType }[] = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "pipeline", label: "Pipeline", icon: Workflow },
  { key: "schedules", label: "Schedules", icon: CalendarClock },
  { key: "users", label: "Users", icon: Users },
  { key: "audit", label: "Audit", icon: ScrollText },
];

export default function AdminPage() {
  const { user, token } = useAuth();
  const [tab, setTab] = useState<TabKey>("overview");
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const showToast = (m: string) => {
    setError(null);
    setToast(m);
    setTimeout(() => setToast(null), 4000);
  };
  const showError = (m: string) => {
    setToast(null);
    setError(m);
  };

  // Guard: Admin role required
  if (user?.role !== "admin") {
    return (
      <div className="mx-auto max-w-3xl px-4 py-24 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-rose-500/10 text-rose-500 ring-1 ring-rose-500/20">
          <ShieldAlert className="h-8 w-8" />
        </div>
        <h2 className="mt-4 text-2xl font-bold tracking-tight text-foreground">
          Admin Access Required
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          You are currently signed in with role{" "}
          <strong className="font-mono text-foreground">
            {user?.role || "user"}
          </strong>
          . The Command Center requires elevated{" "}
          <strong className="font-mono text-amber-400">admin</strong> privileges.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-7 w-7 text-emerald-500" />
          <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Admin Command Center
          </h1>
        </div>
        <p className="mt-1 text-xs text-muted-foreground sm:text-sm">
          Pipeline orchestration, cluster health, recurring schedules, RBAC user
          management, and audit trail.
        </p>
      </div>

      {/* Tab nav */}
      <div className="flex flex-wrap items-center gap-1 rounded-xl border border-border/50 bg-card p-1">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                active
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      {toast && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/60 p-4 text-xs text-emerald-300">
          {toast}
        </div>
      )}
      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-950/60 p-4 text-xs text-rose-300">
          {error}
        </div>
      )}

      {tab === "overview" && <OverviewTab token={token} onError={showError} />}
      {tab === "pipeline" && (
        <PipelineTab token={token} onError={showError} onToast={showToast} />
      )}
      {tab === "schedules" && (
        <SchedulesTab token={token} onError={showError} onToast={showToast} />
      )}
      {tab === "users" && (
        <UsersTab token={token} onError={showError} onToast={showToast} />
      )}
      {tab === "audit" && <AuditTab token={token} onError={showError} />}
    </div>
  );
}
