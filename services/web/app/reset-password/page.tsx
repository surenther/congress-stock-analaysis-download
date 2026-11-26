"use client";

import React, { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
    ShieldCheck,
    Lock,
    ArrowRight,
    AlertCircle,
    Loader2,
    CheckCircle2,
} from "lucide-react";
import { BrandBadge } from "@/components/layout/BrandLogo";

const MIN_PASSWORD_LENGTH = 12;

/** Mirror of the auth-service password policy for instant client feedback. */
function validatePassword(password: string): string | null {
    if (password.length < MIN_PASSWORD_LENGTH) {
        return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
    }
    if (!/[a-z]/.test(password)) return "Password must contain a lowercase letter.";
    if (!/[A-Z]/.test(password)) return "Password must contain an uppercase letter.";
    if (!/[0-9]/.test(password)) return "Password must contain a digit.";
    return null;
}

function ResetPasswordForm() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const token = searchParams.get("token") || "";
    const purpose = searchParams.get("purpose") || "reset";
    const username = searchParams.get("username") || "";
    const isWelcome = purpose === "welcome";

    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [done, setDone] = useState(false);

    const policyError = useMemo(
        () => (password ? validatePassword(password) : null),
        [password],
    );
    const mismatch = confirm.length > 0 && confirm !== password;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        if (!token) {
            setError("This link is missing its reset token. Please request a new email.");
            return;
        }
        const policy = validatePassword(password);
        if (policy) {
            setError(policy);
            return;
        }
        if (password !== confirm) {
            setError("Passwords do not match.");
            return;
        }

        setLoading(true);
        try {
            const res = await fetch("/api/auth/reset-password", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token, new_password: password }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(data.detail || "Could not set your password.");
            }
            setDone(true);
            // Give the user a moment to read the confirmation, then send them to login
            // with the username prefilled so they don't have to retype it.
            const loginUrl = username
                ? `/login?reset=success&username=${encodeURIComponent(username)}`
                : "/login?reset=success";
            setTimeout(() => router.push(loginUrl), 1800);
        } catch (err: any) {
            setError(err.message || "Could not set your password.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
            <div className="w-full max-w-md space-y-6">
                <div className="text-center">
                    <BrandBadge size="lg" className="mx-auto" />
                    <h2 className="mt-4 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
                        {isWelcome ? "Activate your account" : "Set a new password"}
                    </h2>
                    <p className="mt-1 text-xs text-muted-foreground sm:text-sm">
                        {isWelcome
                            ? "Choose a password to activate your account. You'll set up two-factor authentication on first sign-in."
                            : "Choose a new password for your account."}
                    </p>
                    {username && (
                        <p className="mt-2 text-xs text-muted-foreground">
                            Account:{" "}
                            <span className="font-semibold text-foreground">{username}</span>
                        </p>
                    )}
                </div>

                {error && (
                    <div className="flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-950/60 p-3.5 text-xs text-rose-300">
                        <AlertCircle className="h-4 w-4 flex-shrink-0 text-rose-400" />
                        <div className="flex-1">{error}</div>
                    </div>
                )}

                <div className="rounded-2xl border border-border/60 bg-card p-6 shadow-xl sm:p-8">
                    {done ? (
                        <div className="space-y-4 text-center">
                            <div className="flex justify-center">
                                <CheckCircle2 className="h-12 w-12 text-emerald-400" />
                            </div>
                            <h3 className="text-sm font-bold text-foreground">
                                Password set successfully
                            </h3>
                            <p className="text-xs text-muted-foreground">
                                Redirecting you to sign in…
                            </p>
                            <button
                                type="button"
                                onClick={() =>
                                    router.push(
                                        username
                                            ? `/login?reset=success&username=${encodeURIComponent(username)}`
                                            : "/login?reset=success",
                                    )
                                }
                                className="w-full rounded-xl bg-emerald-500 py-2.5 text-xs font-semibold text-white hover:bg-emerald-600 transition-colors"
                            >
                                Continue to sign in
                            </button>
                        </div>
                    ) : (
                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                                    New password
                                </label>
                                <div className="relative mt-1">
                                    <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-muted-foreground">
                                        <Lock className="h-4 w-4" />
                                    </span>
                                    <input
                                        type="password"
                                        required
                                        autoFocus
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        placeholder="••••••••••••"
                                        className="w-full rounded-xl border border-border/60 bg-background py-2.5 pl-10 pr-4 text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                    />
                                </div>
                                <p className="mt-1 text-[11px] text-muted-foreground">
                                    At least {MIN_PASSWORD_LENGTH} characters, with upper & lower
                                    case letters and a digit.
                                </p>
                            </div>

                            <div>
                                <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                                    Confirm password
                                </label>
                                <div className="relative mt-1">
                                    <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-muted-foreground">
                                        <Lock className="h-4 w-4" />
                                    </span>
                                    <input
                                        type="password"
                                        required
                                        value={confirm}
                                        onChange={(e) => setConfirm(e.target.value)}
                                        placeholder="••••••••••••"
                                        className="w-full rounded-xl border border-border/60 bg-background py-2.5 pl-10 pr-4 text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                                    />
                                </div>
                                {mismatch && (
                                    <p className="mt-1 text-[11px] text-rose-400">
                                        Passwords do not match.
                                    </p>
                                )}
                            </div>

                            <button
                                type="submit"
                                disabled={loading || !!policyError || mismatch || !password || !confirm}
                                className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 py-3 text-xs font-semibold text-white shadow-lg transition-all hover:bg-emerald-600 disabled:opacity-50"
                            >
                                {loading ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                    <>
                                        <span>Set password</span>
                                        <ArrowRight className="h-3.5 w-3.5" />
                                    </>
                                )}
                            </button>
                        </form>
                    )}
                </div>

                <div className="flex items-center justify-center gap-2 text-[11px] text-muted-foreground">
                    <ShieldCheck className="h-3 w-3" />
                    <span>Protected by Chamber-Based Access Control (CBAC) & TOTP 2FA</span>
                </div>
            </div>
        </div>
    );
}

export default function ResetPasswordPage() {
    return (
        <Suspense
            fallback={
                <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center">
                    <Loader2 className="h-5 w-5 animate-spin text-emerald-500" />
                </div>
            }
        >
            <ResetPasswordForm />
        </Suspense>
    );
}
