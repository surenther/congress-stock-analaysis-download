"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  ShieldAlert,
  Play,
  RotateCw,
  CheckCircle2,
  KeyRound,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface ApiUser {
  id: string;
  username: string;
  email: string | null;
  roles: string[];
  allowed_chambers: string[];
  is_active: boolean;
  mfa_enabled: boolean;
}

interface ApiJob {
  service: string;
  job_id: string;
  status: string;
  chamber: string | null;
  total_documents: number | null;
  processed_documents: number | null;
  created_at: string | null;
  error_message: string | null;
}

const PIPELINE_SERVICES = [
  { key: "downloader", label: "Downloader Service", port: 8511 },
  { key: "parser", label: "PDF/OCR Parser", port: 8513 },
  { key: "vectorizer", label: "LangChain Vectorizer", port: 8514 },
];

export default function AdminPage() {
  const { user, token } = useAuth();

  const [limit, setLimit] = useState(50);
  const [force, setForce] = useState(false);
  const [users, setUsers] = useState<ApiUser[]>([]);
  const [jobs, setJobs] = useState<ApiJob[]>([]);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const authHeaders = useCallback(
    (): Record<string, string> =>
      token ? { Authorization: `Bearer ${token}` } : {},
    [token],
  );

  const loadUsers = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/users", { headers: authHeaders() });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load users");
      setUsers(data);
    } catch (e: any) {
      setError(e.message);
    }
  }, [authHeaders]);

  const loadJobs = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/jobs?limit=25", {
        headers: authHeaders(),
      });
      if (!res.ok) return;
      const data = await res.json();
      setJobs(data.jobs || []);
    } catch {
      /* ignore transient polling errors */
    }
  }, [authHeaders]);

  useEffect(() => {
    if (user?.role !== "admin") return;
    loadUsers();
    loadJobs();
    const interval = setInterval(loadJobs, 10000);
    return () => clearInterval(interval);
  }, [user?.role, loadUsers, loadJobs]);

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

  const latestJob = (service: string): ApiJob | undefined =>
    jobs.find((j) => j.service === service);

  const triggerPipeline = async (key: string) => {
    setError(null);
    setBusy((p) => ({ ...p, [key]: true }));
    try {
      const res = await fetch("/api/admin/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ service: key, limit, force }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Trigger failed");
      const jobId =
        data.result?.job_id || data.result?.jobId || data.job_id || "dispatched";
      setToast(`Triggered ${key} (job ${jobId})`);
      loadJobs();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy((p) => ({ ...p, [key]: false }));
    }
  };

  const handlePasswordReset = async (id: string, username: string) => {
    setError(null);
    try {
      const res = await fetch(`/api/admin/users/${id}/reset-password`, {
        method: "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Reset failed");
      setToast(`Password reset link dispatched for ${username}`);
      setTimeout(() => setToast(null), 4000);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const toggleActive = async (u: ApiUser) => {
    setError(null);
    try {
      const res = await fetch(`/api/admin/users/${u.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ is_active: !u.is_active }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Update failed");
      loadUsers();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const toggleChamberScope = async (u: ApiUser) => {
    setError(null);
    const current = u.allowed_chambers;
    const next =
      current.length === 2
        ? ["House"]
        : current[0] === "House"
          ? ["Senate"]
          : ["House", "Senate"];
    try {
      const res = await fetch(`/api/admin/users/${u.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ allowed_chambers: next }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Update failed");
      loadUsers();
    } catch (e: any) {
      setError(e.message);
    }
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
          {PIPELINE_SERVICES.map((svc) => {
            const job = latestJob(svc.key);
            const status = busy[svc.key]
              ? "running"
              : job
                ? job.status.toLowerCase()
                : "idle";
            return (
              <div
                key={svc.key}
                className="rounded-xl border border-border/40 bg-background/50 p-4 space-y-3"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">{svc.label}</h3>
                    <p className="font-mono text-[11px] text-muted-foreground">Port :{svc.port}</p>
                  </div>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-bold uppercase",
                      status === "completed" && "bg-emerald-500/10 text-emerald-400",
                      status === "running" && "bg-amber-500/10 text-amber-400 animate-pulse",
                      status === "failed" && "bg-rose-500/10 text-rose-400",
                      status === "idle" && "bg-muted text-muted-foreground",
                    )}
                  >
                    {status}
                  </span>
                </div>

                {job && (
                  <div className="font-mono text-[11px] text-muted-foreground bg-card p-2 rounded border border-border/30">
                    {job.processed_documents ?? 0} / {job.total_documents ?? "—"} processed
                    {job.error_message ? ` · ${job.error_message}` : ""}
                  </div>
                )}

                <button
                  onClick={() => triggerPipeline(svc.key)}
                  disabled={busy[svc.key]}
                  className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-emerald-500/10 py-2 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition-colors border border-emerald-500/30 disabled:opacity-50"
                >
                  {busy[svc.key] ? (
                    <RotateCw className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Play className="h-3.5 w-3.5" />
                  )}
                  <span>Trigger Job</span>
                </button>
              </div>
            );
          })}
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
                <th className="py-2.5 px-3 font-semibold">Status</th>
                <th className="py-2.5 px-3 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {users.map((u) => {
                const role = u.roles.includes("admin") ? "admin" : "user";
                return (
                  <tr key={u.id} className="hover:bg-muted/20 transition-colors">
                    <td className="py-3 px-3">
                      <div className="font-semibold text-foreground">{u.username}</div>
                      <div className="text-[11px] text-muted-foreground">{u.email || "—"}</div>
                    </td>
                    <td className="py-3 px-3">
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5 text-[10px] font-bold uppercase",
                          role === "admin"
                            ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                            : "bg-blue-500/10 text-blue-400 border border-blue-500/20",
                        )}
                      >
                        {role}
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
                          onClick={() => toggleChamberScope(u)}
                          className="ml-2 text-[10px] text-emerald-400 hover:underline"
                        >
                          (cycle scope)
                        </button>
                      </div>
                    </td>
                    <td className="py-3 px-3 text-center">
                      {u.mfa_enabled ? (
                        <span className="inline-flex items-center gap-1 text-emerald-400 font-medium">
                          <CheckCircle2 className="h-3 w-3" /> Enabled
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-muted-foreground">
                          Disabled
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-3">
                      <button
                        onClick={() => toggleActive(u)}
                        className={cn(
                          "rounded px-1.5 py-0.5 text-[10px] font-bold uppercase",
                          u.is_active
                            ? "bg-emerald-500/10 text-emerald-400"
                            : "bg-rose-500/10 text-rose-400",
                        )}
                      >
                        {u.is_active ? "active" : "inactive"}
                      </button>
                    </td>
                    <td className="py-3 px-3 text-right">
                      <button
                        onClick={() => handlePasswordReset(u.id, u.username)}
                        className="flex items-center gap-1 rounded border border-border/60 bg-muted/30 px-2 py-1 text-[11px] text-foreground hover:bg-accent transition-colors ml-auto"
                      >
                        <KeyRound className="h-3 w-3 text-muted-foreground" />
                        <span>Reset Password</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
              {users.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-muted-foreground">
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
