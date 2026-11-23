"use client";

import React, { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  ShieldAlert,
  Play,
  RotateCw,
  Users,
  CheckCircle2,
  AlertTriangle,
  KeyRound,
  ShieldCheck,
  Server,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface PipelineJob {
  service: string;
  port: number;
  lastJobId?: string;
  status: "idle" | "running" | "completed" | "failed";
  progress?: string;
}

export default function AdminPage() {
  const { user } = useAuth();

  // Pipeline orchestration state
  const [limit, setLimit] = useState(50);
  const [force, setForce] = useState(false);

  const [pipelineJobs, setPipelineJobs] = useState<Record<string, PipelineJob>>({
    downloader: { service: "Downloader Service", port: 8511, status: "idle" },
    parser: { service: "PDF/OCR Parser", port: 8513, status: "idle" },
    vectorizer: { service: "LangChain Vectorizer", port: 8514, status: "idle" },
  });

  // User management table state
  const [users, setUsers] = useState([
    {
      id: "usr-1",
      username: "admin-exec",
      email: "oversight.admin@congress.gov",
      role: "admin",
      allowed_chambers: ["House", "Senate"],
      two_factor: true,
      last_active: "Just now",
    },
    {
      id: "usr-2",
      username: "fellow-house",
      email: "fellow.house@congress.gov",
      role: "user",
      allowed_chambers: ["House"],
      two_factor: true,
      last_active: "2 hours ago",
    },
    {
      id: "usr-3",
      username: "senate-auditor",
      email: "auditor.senate@congress.gov",
      role: "user",
      allowed_chambers: ["Senate"],
      two_factor: false,
      last_active: "1 day ago",
    },
  ]);

  const [resetToast, setResetToast] = useState<string | null>(null);

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
          You are currently signed in with role <strong className="font-mono text-foreground">{user?.role || "user"}</strong>.
          The Command Center requires elevated <strong className="font-mono text-amber-400">admin</strong> privileges.
        </p>
        <p className="mt-4 text-xs text-muted-foreground">
          You can use the role switcher in the top right header pill to demo the Admin view.
        </p>
      </div>
    );
  }

  const triggerPipeline = async (key: string, port: number) => {
    setPipelineJobs((prev) => ({
      ...prev,
      [key]: { ...prev[key], status: "running", progress: "Triggering container endpoint..." },
    }));

    try {
      const res = await fetch("/api/admin/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service: key, port, limit, force }),
      });

      const data = await res.json();
      setPipelineJobs((prev) => ({
        ...prev,
        [key]: {
          ...prev[key],
          status: "completed",
          lastJobId: data.job_id || `job-${Math.floor(Math.random() * 90000 + 10000)}`,
          progress: `Completed (${limit} items processed, force=${force})`,
        },
      }));
    } catch {
      setPipelineJobs((prev) => ({
        ...prev,
        [key]: { ...prev[key], status: "failed", progress: "Failed to connect to container port" },
      }));
    }
  };

  const handlePasswordReset = (username: string) => {
    setResetToast(`Password reset link dispatched for ${username}`);
    setTimeout(() => setResetToast(null), 4000);
  };

  const toggleChamberScope = (userId: string) => {
    setUsers((prev) =>
      prev.map((u) => {
        if (u.id === userId) {
          const current = u.allowed_chambers;
          const next =
            current.length === 2
              ? ["House"]
              : current[0] === "House"
              ? ["Senate"]
              : ["House", "Senate"];
          return { ...u, allowed_chambers: next };
        }
        return u;
      })
    );
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-7 w-7 text-emerald-500" />
          <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Admin Command Center
          </h1>
        </div>
        <p className="mt-1 text-xs text-muted-foreground sm:text-sm">
          Pipeline orchestration controls, cluster job status polling, and RBAC user access management.
        </p>
      </div>

      {resetToast && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/60 p-4 text-xs text-emerald-300">
          {resetToast}
        </div>
      )}

      {/* Section 1: Pipeline Orchestration Controls */}
      <div className="rounded-xl border border-border/50 bg-card p-6 shadow-sm">
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">Pipeline Orchestration Controls</h2>
            <p className="text-xs text-muted-foreground">
              Manually trigger and poll Downloader (:8511), Parser (:8513), and Vectorizer (:8514).
            </p>
          </div>

          {/* Trigger Parameters */}
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="text-muted-foreground">Limit:</span>
              <input
                type="number"
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="w-16 rounded-md border border-border/60 bg-background px-2 py-1 text-xs font-mono text-foreground focus:outline-none focus:border-emerald-500"
              />
            </div>
            <label className="flex items-center gap-1.5 cursor-pointer text-foreground">
              <input
                type="checkbox"
                checked={force}
                onChange={(e) => setForce(e.target.checked)}
                className="rounded border-border text-emerald-500 focus:ring-emerald-500"
              />
              <span>Force Re-process</span>
            </label>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {Object.entries(pipelineJobs).map(([key, job]) => (
            <div
              key={key}
              className="rounded-xl border border-border/40 bg-background/50 p-4 space-y-3"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">{job.service}</h3>
                  <p className="font-mono text-[11px] text-muted-foreground">Port :{job.port}</p>
                </div>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-bold uppercase",
                    job.status === "completed" && "bg-emerald-500/10 text-emerald-400",
                    job.status === "running" && "bg-amber-500/10 text-amber-400 animate-pulse",
                    job.status === "failed" && "bg-rose-500/10 text-rose-400",
                    job.status === "idle" && "bg-muted text-muted-foreground"
                  )}
                >
                  {job.status}
                </span>
              </div>

              {job.progress && (
                <div className="font-mono text-[11px] text-muted-foreground bg-card p-2 rounded border border-border/30">
                  {job.progress}
                </div>
              )}

              <button
                onClick={() => triggerPipeline(key, job.port)}
                disabled={job.status === "running"}
                className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-emerald-500/10 py-2 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition-colors border border-emerald-500/30 disabled:opacity-50"
              >
                {job.status === "running" ? (
                  <RotateCw className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Play className="h-3.5 w-3.5" />
                )}
                <span>Trigger Job</span>
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Section 2: User Access & Chamber Scope Management */}
      <div className="rounded-xl border border-border/50 bg-card p-6 shadow-sm">
        <div className="mb-4">
          <h2 className="text-base font-semibold text-foreground">User Management & CBAC Access Scope</h2>
          <p className="text-xs text-muted-foreground">
            Configure chamber boundaries, two-factor authentication requirements, and security credentials.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-border/60 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="py-2.5 px-3 font-semibold">User</th>
                <th className="py-2.5 px-3 font-semibold">Role</th>
                <th className="py-2.5 px-3 font-semibold">Allowed Chambers</th>
                <th className="py-2.5 px-3 font-semibold text-center">2FA Status</th>
                <th className="py-2.5 px-3 font-semibold">Last Active</th>
                <th className="py-2.5 px-3 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-muted/20 transition-colors">
                  <td className="py-3 px-3">
                    <div className="font-semibold text-foreground">{u.username}</div>
                    <div className="text-[11px] text-muted-foreground">{u.email}</div>
                  </td>
                  <td className="py-3 px-3">
                    <span
                      className={cn(
                        "rounded px-1.5 py-0.5 text-[10px] font-bold uppercase",
                        u.role === "admin"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                          : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                      )}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="py-3 px-3">
                    <div className="flex items-center gap-1.5">
                      {u.allowed_chambers.map((ch) => (
                        <span
                          key={ch}
                          className="rounded bg-accent px-1.5 py-0.5 font-mono text-[10px] text-accent-foreground"
                        >
                          {ch}
                        </span>
                      ))}
                      <button
                        onClick={() => toggleChamberScope(u.id)}
                        className="ml-2 text-[10px] text-emerald-400 hover:underline"
                      >
                        (cycle scope)
                      </button>
                    </div>
                  </td>
                  <td className="py-3 px-3 text-center">
                    {u.two_factor ? (
                      <span className="inline-flex items-center gap-1 text-emerald-400 font-medium">
                        <CheckCircle2 className="h-3 w-3" /> Enabled
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-muted-foreground">
                        Disabled
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-3 text-muted-foreground">{u.last_active}</td>
                  <td className="py-3 px-3 text-right">
                    <button
                      onClick={() => handlePasswordReset(u.username)}
                      className="flex items-center gap-1 rounded border border-border/60 bg-muted/30 px-2 py-1 text-[11px] text-foreground hover:bg-accent transition-colors ml-auto"
                    >
                      <KeyRound className="h-3 w-3 text-muted-foreground" />
                      <span>Reset Password</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
