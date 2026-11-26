"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  ShieldCheck,
  Lock,
  User,
  ArrowRight,
  Sparkles,
  AlertCircle,
  Loader2,
  Smartphone,
} from "lucide-react";
import { BrandBadge } from "@/components/layout/BrandLogo";

interface SetupData {
  otpauth_uri: string;
  qr_png_base64: string;
  secret: string;
}

export default function LoginPage() {
  const router = useRouter();
  const { loginWithCredentials, verifyMfaCode, enableMfa } = useAuth();

  // Step: "credentials" | "mfa" | "mfa_setup"
  const [step, setStep] = useState<"credentials" | "mfa" | "mfa_setup">(
    "credentials",
  );

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const [mfaToken, setMfaToken] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [setupData, setSetupData] = useState<SetupData | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch the real TOTP enrollment material when entering the setup step.
  useEffect(() => {
    if (step !== "mfa_setup" || !mfaToken) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/auth/mfa/setup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mfa_token: mfaToken }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to start 2FA setup");
        if (!cancelled) setSetupData(data);
      } catch (err: any) {
        if (!cancelled) setError(err.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [step, mfaToken]);

  const handleCredentialsSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;

    setError(null);
    setLoading(true);

    try {
      const res = await loginWithCredentials(username.trim(), password);

      if (res.access_token) {
        router.push("/dashboard");
        return;
      }
      if (res.must_change_password) {
        setError(
          "Your account requires a password change before sign-in. Please contact your administrator.",
        );
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
      setError("Unexpected authentication response.");
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

  const handleMfaSetupSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (totpCode.trim().length < 6) {
      setError("Please enter the full 6-digit verification code.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const codes = await enableMfa(mfaToken, totpCode.trim());
      setRecoveryCodes(codes);
    } catch (err: any) {
      setError(err.message || "Failed to enable 2FA.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[calc(100vh-8rem)] items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-6">
        {/* Brand Header */}
        <div className="text-center">
          <BrandBadge size="lg" className="mx-auto" />
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
                : "Scan the QR code to configure your authenticator"}
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
              {recoveryCodes ? (
                <>
                  <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4 text-xs text-emerald-200">
                    <h4 className="font-bold">2FA Enabled</h4>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Save these one-time recovery codes somewhere safe.
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-2 rounded-xl border border-border/60 bg-background p-4 font-mono text-xs text-foreground">
                    {recoveryCodes.map((c) => (
                      <span key={c}>{c}</span>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() => router.push("/dashboard")}
                    className="w-full rounded-xl bg-emerald-500 py-2.5 text-xs font-semibold text-white hover:bg-emerald-600 transition-colors"
                  >
                    Continue to Dashboard
                  </button>
                </>
              ) : (
                <>
                  <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 text-xs text-amber-200">
                    <h4 className="font-bold">Initial 2FA Enrollment Required</h4>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Your account requires mandatory two-factor authentication setup on first login.
                    </p>
                  </div>

                  {setupData ? (
                    <>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={`data:image/png;base64,${setupData.qr_png_base64}`}
                        alt="TOTP QR code"
                        className="mx-auto h-40 w-40 rounded-lg border border-border/60 bg-white p-2"
                      />
                      <div className="rounded-xl border border-border/60 bg-background p-4 text-xs font-mono text-foreground">
                        <div className="text-[10px] text-muted-foreground">
                          Manual Provisioning Key:
                        </div>
                        <div className="mt-1 break-all font-bold text-emerald-400">
                          {setupData.secret}
                        </div>
                      </div>
                      <form onSubmit={handleMfaSetupSubmit} className="space-y-3">
                        <input
                          type="text"
                          maxLength={6}
                          value={totpCode}
                          onChange={(e) =>
                            setTotpCode(e.target.value.replace(/\D/g, ""))
                          }
                          placeholder="123456"
                          className="w-48 rounded-xl border border-border/60 bg-background py-3 text-center font-mono text-2xl font-bold tracking-widest text-emerald-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                        />
                        <button
                          type="submit"
                          disabled={loading || totpCode.length < 6}
                          className="w-full rounded-xl bg-emerald-500 py-2.5 text-xs font-semibold text-white hover:bg-emerald-600 transition-colors disabled:opacity-50"
                        >
                          {loading ? "Enabling…" : "Enable 2FA & Continue"}
                        </button>
                      </form>
                    </>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      {error || "Preparing enrollment…"}
                    </p>
                  )}
                </>
              )}
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
