"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
    KeyRound,
    ShieldOff,
    UserPlus,
    RefreshCw,
    X,
    CheckCircle2,
    Power,
    Pencil,
} from "lucide-react";
import { apiFetch } from "./api";
import { ApiUser, BulkActionResult } from "./types";
import { cn } from "@/lib/utils";

interface Props {
    token: string | null;
    onError: (m: string) => void;
    onToast: (m: string) => void;
}

export function UsersTab({ token, onError, onToast }: Props) {
    const [users, setUsers] = useState<ApiUser[]>([]);
    const [loading, setLoading] = useState(false);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [busy, setBusy] = useState(false);

    const [createOpen, setCreateOpen] = useState(false);
    const [newUsername, setNewUsername] = useState("");
    const [newEmail, setNewEmail] = useState("");
    const [newIsAdmin, setNewIsAdmin] = useState(false);
    const [newChambers, setNewChambers] = useState<string[]>([
        "House",
        "Senate",
    ]);

    const [editUser, setEditUser] = useState<ApiUser | null>(null);
    const [editEmail, setEditEmail] = useState("");
    const [editIsAdmin, setEditIsAdmin] = useState(false);
    const [editChambers, setEditChambers] = useState<string[]>([]);
    const [editActive, setEditActive] = useState(true);
    const [editSendWelcome, setEditSendWelcome] = useState(false);

    const loadUsers = useCallback(async () => {
        setLoading(true);
        try {
            const data = await apiFetch<ApiUser[]>("/api/admin/users", token);
            setUsers(data);
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, [token, onError]);

    useEffect(() => {
        loadUsers();
    }, [loadUsers]);

    const toggleSelect = (id: string) => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const toggleSelectAll = () => {
        setSelected((prev) =>
            prev.size === users.length ? new Set() : new Set(users.map((u) => u.id)),
        );
    };

    const toggleActive = async (u: ApiUser) => {
        try {
            await apiFetch(`/api/admin/users/${u.id}`, token, {
                method: "PATCH",
                body: JSON.stringify({ is_active: !u.is_active }),
            });
            loadUsers();
        } catch (e) {
            onError((e as Error).message);
        }
    };

    const resetPassword = async (u: ApiUser) => {
        try {
            await apiFetch(`/api/admin/users/${u.id}/reset-password`, token, {
                method: "POST",
            });
            onToast(`Password reset link dispatched for ${u.username}`);
        } catch (e) {
            onError((e as Error).message);
        }
    };

    const reset2fa = async (u: ApiUser) => {
        try {
            await apiFetch(`/api/admin/users/${u.id}/reset-2fa`, token, {
                method: "POST",
            });
            onToast(`2FA cleared for ${u.username}`);
            loadUsers();
        } catch (e) {
            onError((e as Error).message);
        }
    };

    const createUser = async () => {
        setBusy(true);
        try {
            await apiFetch("/api/admin/users", token, {
                method: "POST",
                body: JSON.stringify({
                    username: newUsername,
                    email: newEmail || null,
                    roles: newIsAdmin ? ["admin"] : ["user"],
                    allowed_chambers: newChambers,
                    send_welcome: true,
                }),
            });
            onToast(`User ${newUsername} created`);
            setCreateOpen(false);
            setNewUsername("");
            setNewEmail("");
            setNewIsAdmin(false);
            setNewChambers(["House", "Senate"]);
            loadUsers();
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    const openEdit = (u: ApiUser) => {
        setEditUser(u);
        setEditEmail(u.email || "");
        setEditIsAdmin(u.roles.includes("admin"));
        setEditChambers(u.allowed_chambers);
        setEditActive(u.is_active);
        setEditSendWelcome(false);
    };

    const saveEdit = async () => {
        if (!editUser) return;
        setBusy(true);
        try {
            await apiFetch(`/api/admin/users/${editUser.id}`, token, {
                method: "PATCH",
                body: JSON.stringify({
                    email: editEmail || undefined,
                    roles: editIsAdmin ? ["admin"] : ["user"],
                    allowed_chambers: editChambers,
                    is_active: editActive,
                    send_welcome: editSendWelcome,
                }),
            });
            onToast(`User ${editUser.username} updated`);
            setEditUser(null);
            loadUsers();
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    const bulkAction = async (
        action: "activate" | "deactivate" | "reset-2fa" | "set-chambers",
        chambers?: string[],
    ) => {
        if (selected.size === 0) return;
        setBusy(true);
        try {
            const data = await apiFetch<BulkActionResult>("/api/admin/users/bulk", token, {
                method: "POST",
                body: JSON.stringify({
                    user_ids: Array.from(selected),
                    action,
                    allowed_chambers: chambers,
                }),
            });
            onToast(
                `Bulk ${action}: ${data.succeeded} succeeded, ${data.failed} failed`,
            );
            setSelected(new Set());
            loadUsers();
        } catch (e) {
            onError((e as Error).message);
        } finally {
            setBusy(false);
        }
    };

    const toggleChamber = (list: string[], ch: string) =>
        list.includes(ch) ? list.filter((c) => c !== ch) : [...list, ch];

    return (
        <div className="space-y-6">
            <div className="rounded-xl border border-border/50 bg-card p-6">
                <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <h2 className="text-base font-semibold text-foreground">
                            User Management & CBAC Access Scope
                        </h2>
                        <p className="text-xs text-muted-foreground">
                            Configure chamber boundaries, two-factor authentication, and
                            security credentials.
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={loadUsers}
                            disabled={loading}
                            className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-muted/30 px-2.5 py-1 text-xs text-foreground hover:bg-accent transition-colors disabled:opacity-50"
                        >
                            <RefreshCw
                                className={cn("h-3.5 w-3.5", loading && "animate-spin")}
                            />
                            Refresh
                        </button>
                        <button
                            onClick={() => setCreateOpen(true)}
                            className="flex items-center gap-1.5 rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition-colors border border-emerald-500/30"
                        >
                            <UserPlus className="h-3.5 w-3.5" />
                            Create User
                        </button>
                    </div>
                </div>

                {/* Bulk action bar */}
                {selected.size > 0 && (
                    <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-950/30 p-3 text-xs">
                        <span className="font-semibold text-emerald-300">
                            {selected.size} selected
                        </span>
                        <button
                            onClick={() => bulkAction("activate")}
                            disabled={busy}
                            className="rounded border border-border/60 bg-muted/30 px-2 py-1 text-foreground hover:bg-accent disabled:opacity-50"
                        >
                            Activate
                        </button>
                        <button
                            onClick={() => bulkAction("deactivate")}
                            disabled={busy}
                            className="rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-rose-400 hover:bg-rose-500/20 disabled:opacity-50"
                        >
                            Deactivate
                        </button>
                        <button
                            onClick={() => bulkAction("reset-2fa")}
                            disabled={busy}
                            className="rounded border border-border/60 bg-muted/30 px-2 py-1 text-foreground hover:bg-accent disabled:opacity-50"
                        >
                            Reset 2FA
                        </button>
                        <button
                            onClick={() => bulkAction("set-chambers", ["House", "Senate"])}
                            disabled={busy}
                            className="rounded border border-border/60 bg-muted/30 px-2 py-1 text-foreground hover:bg-accent disabled:opacity-50"
                        >
                            Grant Both Chambers
                        </button>
                        <button
                            onClick={() => setSelected(new Set())}
                            className="ml-auto text-muted-foreground hover:text-foreground"
                        >
                            Clear
                        </button>
                    </div>
                )}

                <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                        <thead className="border-b border-border/60 text-[11px] uppercase tracking-wider text-muted-foreground">
                            <tr>
                                <th className="py-2.5 px-3">
                                    <input
                                        type="checkbox"
                                        checked={
                                            users.length > 0 && selected.size === users.length
                                        }
                                        onChange={toggleSelectAll}
                                        className="rounded border-border text-emerald-500 focus:ring-emerald-500"
                                    />
                                </th>
                                <th className="py-2.5 px-3 font-semibold">User</th>
                                <th className="py-2.5 px-3 font-semibold">Role</th>
                                <th className="py-2.5 px-3 font-semibold">Allowed Chambers</th>
                                <th className="py-2.5 px-3 font-semibold text-center">2FA</th>
                                <th className="py-2.5 px-3 font-semibold">Status</th>
                                <th className="py-2.5 px-3 font-semibold text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border/30">
                            {users.map((u) => {
                                const role = u.roles.includes("admin") ? "admin" : "user";
                                return (
                                    <tr
                                        key={u.id}
                                        className="hover:bg-muted/20 transition-colors"
                                    >
                                        <td className="py-3 px-3">
                                            <input
                                                type="checkbox"
                                                checked={selected.has(u.id)}
                                                onChange={() => toggleSelect(u.id)}
                                                className="rounded border-border text-emerald-500 focus:ring-emerald-500"
                                            />
                                        </td>
                                        <td className="py-3 px-3">
                                            <div className="font-semibold text-foreground">
                                                {u.username}
                                            </div>
                                            <div className="text-[11px] text-muted-foreground">
                                                {u.email || "—"}
                                            </div>
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
                                            <div className="flex flex-wrap items-center gap-1.5">
                                                {u.allowed_chambers.map((ch) => (
                                                    <span
                                                        key={ch}
                                                        className="rounded bg-accent px-1.5 py-0.5 font-mono text-[10px] text-accent-foreground"
                                                    >
                                                        {ch}
                                                    </span>
                                                ))}
                                            </div>
                                        </td>
                                        <td className="py-3 px-3 text-center">
                                            {u.mfa_enabled ? (
                                                <span className="inline-flex items-center gap-1 text-emerald-400 font-medium">
                                                    <CheckCircle2 className="h-3 w-3" /> Enabled
                                                </span>
                                            ) : (
                                                <span className="text-muted-foreground">Disabled</span>
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
                                        <td className="py-3 px-3">
                                            <div className="flex items-center justify-end gap-1.5">
                                                <button
                                                    onClick={() => openEdit(u)}
                                                    title="Edit user"
                                                    className="flex items-center gap-1 rounded border border-border/60 bg-muted/30 px-2 py-1 text-[11px] text-foreground hover:bg-accent transition-colors"
                                                >
                                                    <Pencil className="h-3 w-3 text-muted-foreground" />
                                                    Edit
                                                </button>
                                                <button
                                                    onClick={() => resetPassword(u)}
                                                    title="Reset password"
                                                    className="flex items-center gap-1 rounded border border-border/60 bg-muted/30 px-2 py-1 text-[11px] text-foreground hover:bg-accent transition-colors"
                                                >
                                                    <KeyRound className="h-3 w-3 text-muted-foreground" />
                                                    Password
                                                </button>
                                                <button
                                                    onClick={() => reset2fa(u)}
                                                    title="Reset 2FA"
                                                    className="flex items-center gap-1 rounded border border-border/60 bg-muted/30 px-2 py-1 text-[11px] text-foreground hover:bg-accent transition-colors"
                                                >
                                                    <ShieldOff className="h-3 w-3 text-muted-foreground" />
                                                    2FA
                                                </button>
                                                <button
                                                    onClick={() => toggleActive(u)}
                                                    title={u.is_active ? "Deactivate" : "Activate"}
                                                    className="flex items-center gap-1 rounded border border-border/60 bg-muted/30 px-2 py-1 text-[11px] text-foreground hover:bg-accent transition-colors"
                                                >
                                                    <Power className="h-3 w-3 text-muted-foreground" />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                            {users.length === 0 && (
                                <tr>
                                    <td
                                        colSpan={7}
                                        className="py-8 text-center text-muted-foreground"
                                    >
                                        No users found.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Create user modal */}
            {createOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div
                        className="absolute inset-0 bg-black/50"
                        onClick={() => setCreateOpen(false)}
                    />
                    <div className="relative z-10 w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl">
                        <div className="mb-4 flex items-center justify-between">
                            <h3 className="text-base font-semibold text-foreground">
                                Create User
                            </h3>
                            <button
                                onClick={() => setCreateOpen(false)}
                                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                        <div className="space-y-3 text-xs">
                            <div className="flex flex-col gap-1">
                                <label className="text-muted-foreground">Username</label>
                                <input
                                    value={newUsername}
                                    onChange={(e) => setNewUsername(e.target.value)}
                                    className="rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                                />
                            </div>
                            <div className="flex flex-col gap-1">
                                <label className="text-muted-foreground">Email</label>
                                <input
                                    type="email"
                                    value={newEmail}
                                    onChange={(e) => setNewEmail(e.target.value)}
                                    className="rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                                />
                            </div>
                            <label className="flex items-center gap-2 text-foreground">
                                <input
                                    type="checkbox"
                                    checked={newIsAdmin}
                                    onChange={(e) => setNewIsAdmin(e.target.checked)}
                                    className="rounded border-border text-emerald-500 focus:ring-emerald-500"
                                />
                                Grant admin role
                            </label>
                            <div className="flex flex-col gap-1">
                                <label className="text-muted-foreground">
                                    Allowed Chambers
                                </label>
                                <div className="flex gap-3">
                                    {["House", "Senate"].map((ch) => (
                                        <label
                                            key={ch}
                                            className="flex items-center gap-1.5 text-foreground"
                                        >
                                            <input
                                                type="checkbox"
                                                checked={newChambers.includes(ch)}
                                                onChange={() =>
                                                    setNewChambers((prev) => toggleChamber(prev, ch))
                                                }
                                                className="rounded border-border text-emerald-500 focus:ring-emerald-500"
                                            />
                                            {ch}
                                        </label>
                                    ))}
                                </div>
                            </div>
                        </div>
                        <div className="mt-5 flex justify-end gap-2">
                            <button
                                onClick={() => setCreateOpen(false)}
                                className="rounded-lg border border-border/60 bg-muted/30 px-3 py-1.5 text-xs text-foreground hover:bg-accent transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={createUser}
                                disabled={busy || !newUsername || newChambers.length === 0}
                                className="rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition-colors border border-emerald-500/30 disabled:opacity-50"
                            >
                                Create
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Edit user modal */}
            {editUser && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div
                        className="absolute inset-0 bg-black/50"
                        onClick={() => setEditUser(null)}
                    />
                    <div className="relative z-10 w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl">
                        <div className="mb-4 flex items-center justify-between">
                            <div>
                                <h3 className="text-base font-semibold text-foreground">
                                    Edit User
                                </h3>
                                <p className="text-[11px] text-muted-foreground">
                                    {editUser.username}
                                </p>
                            </div>
                            <button
                                onClick={() => setEditUser(null)}
                                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                        <div className="space-y-3 text-xs">
                            <div className="flex flex-col gap-1">
                                <label className="text-muted-foreground">Email</label>
                                <input
                                    type="email"
                                    value={editEmail}
                                    onChange={(e) => setEditEmail(e.target.value)}
                                    placeholder="name@example.com"
                                    className="rounded-md border border-border/60 bg-background px-2 py-1.5 text-xs text-foreground focus:outline-none focus:border-emerald-500"
                                />
                            </div>
                            <label className="flex items-center gap-2 text-foreground">
                                <input
                                    type="checkbox"
                                    checked={editIsAdmin}
                                    onChange={(e) => setEditIsAdmin(e.target.checked)}
                                    className="rounded border-border text-emerald-500 focus:ring-emerald-500"
                                />
                                Grant admin role
                            </label>
                            <div className="flex flex-col gap-1">
                                <label className="text-muted-foreground">
                                    Allowed Chambers
                                </label>
                                <div className="flex gap-3">
                                    {["House", "Senate"].map((ch) => (
                                        <label
                                            key={ch}
                                            className="flex items-center gap-1.5 text-foreground"
                                        >
                                            <input
                                                type="checkbox"
                                                checked={editChambers.includes(ch)}
                                                onChange={() =>
                                                    setEditChambers((prev) => toggleChamber(prev, ch))
                                                }
                                                className="rounded border-border text-emerald-500 focus:ring-emerald-500"
                                            />
                                            {ch}
                                        </label>
                                    ))}
                                </div>
                            </div>
                            <label className="flex items-center gap-2 text-foreground">
                                <input
                                    type="checkbox"
                                    checked={editActive}
                                    onChange={(e) => setEditActive(e.target.checked)}
                                    className="rounded border-border text-emerald-500 focus:ring-emerald-500"
                                />
                                Account active
                            </label>
                            <label className="flex items-center gap-2 text-foreground">
                                <input
                                    type="checkbox"
                                    checked={editSendWelcome}
                                    onChange={(e) => setEditSendWelcome(e.target.checked)}
                                    className="rounded border-border text-emerald-500 focus:ring-emerald-500"
                                />
                                Send welcome / set-password email
                            </label>
                        </div>
                        <div className="mt-5 flex justify-end gap-2">
                            <button
                                onClick={() => setEditUser(null)}
                                className="rounded-lg border border-border/60 bg-muted/30 px-3 py-1.5 text-xs text-foreground hover:bg-accent transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={saveEdit}
                                disabled={busy || editChambers.length === 0}
                                className="rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition-colors border border-emerald-500/30 disabled:opacity-50"
                            >
                                Save
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
