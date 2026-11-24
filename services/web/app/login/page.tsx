"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  ShieldCheck,
  Lock,
  User,
  KeyRound,
  ArrowRight,
  Sparkles,
  AlertCircle,
  Loader2,
  CheckCircle2,
  Smartphone,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function LoginPage() {
  const router = useRouter();
  const { loginWithCredentials, verifyMfaCode } = useAuth();

  // Step: "credentials" | "mfa" | "mfa_setup"
  const [step, setStep] = useState<"credentials" | "mfa" | "mfa_setup">("credentials");

  // Credentials state
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  // 2FA state
  const [mfaToken, setMfaToken] = useState("");
  const [totpCode, setTotpCode] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCredentialsSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;

    setError(null);
    setLoading(true);

    try {
      const res = await loginWithCredentials(username.trim(), password);

      if (res.access_token) {
        // Direct login without 2FA
        router.push("/dashboard");
        return;
      }

      if (res.mfa_required) {
        setMfaToken(res.mfa_token || "");
        setStep("mfa");
        return;
      }

      if (res.must_setup_2fa) {
        setMfaToken(res.mfa_token || "");
        setStep("mfa_setup");
        return;
      }
    } catch (err: any) {
      setError(err.message || "Invalid username or password.");
    } finally {
      setLoading(false);
    }
  };

  const handleMfaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!totpCode.trim() || totpCode.trim().length < 6) {
      setError("Please enter the full 6-digit verification code.");
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const success = await verifyMfaCode(mfaToken, totpCode.trim(), username);
      if (success) {
        router.push("/dashboard");
      } else {
        setError("Invalid or expired 2FA verification code.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to verify 2FA code.");
    } finally {
      setLoading(false);
    }
  };

  const fillQuickDemo = (demoUser: string, demoRole: "admin" | "user") => {
    setUsername(demoUser);
    setPassword("password123");
    setError(null);
  };

  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-6">
        {/* Brand Header */}
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/30">
            <Sparkles className="h-6 w-6" />
          </div>
          <h2 className="mt-4 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            {step === "credentials"
              ? "Sign in to Congress Alpha"
              : step === "mfa"
              ? "Two-Factor Verification"
              : "Set up Two-Factor Authentication"}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground sm:text-sm">
            {step === "credentials"
              ? "Executive Congressional Stock Surveillance & STOCK Act Audit"
              : step === "mfa"
              ? "Enter the 6-digit TOTP code from your authenticator app"
              : "Scan the provisioning key to configure your authenticator"}
          </p>
        </div>

        {/* Error Notification */}
        {error && (
          <div className="flex items-center gap-2 rounded-xl border border-rose-500/30 bg-rose-950/60 p-3.5 text-xs text-rose-300">
            <AlertCircle className="h-4 w-4 flex-shrink-0 text-rose-400" />
            <div className="flex-1">{error}</div>
          </div>
        )}

        {/* Login Card */}
        <div className="rounded-2xl border border-border/60 bg-card p-6 shadow-xl sm:p-8">
          {step === "credentials" && (
            <form onSubmit={handleCredentialsSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Username or ID
                </label>
                <div className="relative mt-1">
                  <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-muted-foreground">
                    <User className="h-4 w-4" />
                  </span>
                  <input
                    type="text"
                    required
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="e.g. admin or house.analyst"
                    className="w-full rounded-xl border border-border/60 bg-background py-2.5 pl-10 pr-4 text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Password
                </label>
                <div className="relative mt-1">
                  <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-muted-foreground">
                    <Lock className="h-4 w-4" />
                  </span>
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full rounded-xl border border-border/60 bg-background py-2.5 pl-10 pr-4 text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || !username || !password}
                className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 py-3 text-xs font-semibold text-white shadow-lg transition-all hover:bg-emerald-600 disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <span>Continue to Security Check</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </>
                )}
              </button>

              {/* Demo Quick-Fill Pill Buttons */}
              <div className="border-t border-border/40 pt-4 text-center">
                <span className="text-[11px] text-muted-foreground">Quick Fill Demo Roles:</span>
                <div className="mt-2 flex justify-center gap-2">
                  <button
                    type="button"
                    onClick={() => fillQuickDemo("admin", "admin")}
                    className="rounded-lg border border-border/50 bg-muted/30 px-2.5 py-1 text-[11px] font-medium text-foreground hover:bg-accent transition-colors"
                  >
                    Admin (Both Chambers)
                  </button>
                  <button
                    type="button"
                    onClick={() => fillQuickDemo("user-house", "user")}
                    className="rounded-lg border border-border/50 bg-muted/30 px-2.5 py-1 text-[11px] font-medium text-foreground hover:bg-accent transition-colors"
                  >
                    User (House Only)
                  </button>
                </div>
              </div>
            </form>
          )}

          {step === "mfa" && (
            <form onSubmit={handleMfaSubmit} className="space-y-5">
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-950/20 p-3 text-xs text-emerald-300">
                <div className="flex items-center gap-2 font-semibold">
                  <Smartphone className="h-4 w-4 text-emerald-400" />
                  <span>Mandatory 2FA Enforced</span>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                  Open Google Authenticator, 1Password, or Authy on your mobile device and enter the 6-digit code.
                </p>
              </div>

              <div>
                <label className="block text-center text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  6-Digit Verification Code
                </label>
                <div className="mt-2 flex justify-center">
                  <input
                    type="text"
                    maxLength={6}
                    autoFocus
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                    placeholder="123456"
                    className="w-48 rounded-xl border border-border/60 bg-background py-3 text-center font-mono text-2xl font-bold tracking-widest text-emerald-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
                <div className="mt-2 text-center text-[10px] text-muted-foreground">
                  Demo code fallback: <span className="font-mono text-foreground">123456</span>
                </div>
              </div>

              <div className="space-y-2">
                <button
                  type="submit"
                  disabled={loading || totpCode.length < 6}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-500 py-3 text-xs font-semibold text-white shadow-lg transition-all hover:bg-emerald-600 disabled:opacity-50"
                >
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <span>Verify & Access Dashboard</span>
                      <ShieldCheck className="h-4 w-4" />
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setStep("credentials");
                    setError(null);
                  }}
                  className="w-full text-center text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  ← Back to username & password
                </button>
              </div>
            </form>
          )}

          {step === "mfa_setup" && (
            <div className="space-y-4 text-center">
              <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 text-xs text-amber-200">
                <h4 className="font-bold">Initial 2FA Enrollment Required</h4>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Your account requires mandatory two-factor authentication setup on first login.
                </p>
              </div>

              <div className="rounded-xl border border-border/60 bg-background p-4 text-xs font-mono text-foreground">
                <div className="text-[10px] text-muted-foreground">Manual Provisioning Key:</div>
                <div className="mt-1 font-bold text-emerald-400">JBSWY3DPEHPK3PXP</div>
              </div>

              <button
                type="button"
                onClick={() => setStep("mfa")}
                className="w-full rounded-xl bg-emerald-500 py-2.5 text-xs font-semibold text-white hover:bg-emerald-600 transition-colors"
              >
                I have saved this key → Enter Code
              </button>
            </div>
          )}
        </div>

        {/* Security Footer Notice */}
        <div className="flex items-center justify-center gap-2 text-[11px] text-muted-foreground">
          <Lock className="h-3 w-3" />
          <span>Protected by Chamber-Based Access Control (CBAC) & TOTP 2FA</span>
        </div>
      </div>
    </div>
  );
}
