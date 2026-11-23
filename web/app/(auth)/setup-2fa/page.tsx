"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface SetupResponse {
    otpauth_uri: string;
    qr_png_base64: string;
    secret: string;
}

export default function Setup2faPage() {
    const router = useRouter();
    const [setup, setSetup] = useState<SetupResponse | null>(null);
    const [code, setCode] = useState("");
    const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        const mfaToken = sessionStorage.getItem("mfa_token");
        if (!mfaToken) {
            router.push("/login");
            return;
        }
        apiFetch<SetupResponse>("/api/auth/mfa/setup", {
            method: "POST",
            body: JSON.stringify({ mfa_token: mfaToken }),
        })
            .then(setSetup)
            .catch((err) => setError((err as Error).message));
    }, [router]);

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setLoading(true);
        const mfaToken = sessionStorage.getItem("mfa_token");
        try {
            const data = await apiFetch<{ recovery_codes: string[] }>(
                "/api/auth/mfa/enable",
                {
                    method: "POST",
                    body: JSON.stringify({ mfa_token: mfaToken, code }),
                },
            );
            sessionStorage.removeItem("mfa_token");
            setRecoveryCodes(data.recovery_codes);
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setLoading(false);
        }
    }

    if (recoveryCodes) {
        return (
            <div className="flex min-h-screen items-center justify-center p-4">
                <Card className="w-full max-w-md">
                    <CardHeader>
                        <CardTitle>Save your recovery codes</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <p className="text-sm text-muted-foreground">
                            Store these one-time codes somewhere safe. Each can be used once if
                            you lose access to your authenticator.
                        </p>
                        <div className="grid grid-cols-2 gap-2 rounded-md border p-4 font-mono text-sm">
                            {recoveryCodes.map((c) => (
                                <span key={c}>{c}</span>
                            ))}
                        </div>
                        <Button className="w-full" onClick={() => router.push("/dashboard")}>
                            Continue to dashboard
                        </Button>
                    </CardContent>
                </Card>
            </div>
        );
    }

    return (
        <div className="flex min-h-screen items-center justify-center p-4">
            <Card className="w-full max-w-md">
                <CardHeader>
                    <CardTitle>Set up two-factor authentication</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    {setup ? (
                        <>
                            <p className="text-sm text-muted-foreground">
                                Scan this QR code with Google Authenticator or Authy, then enter
                                the 6-digit code to confirm.
                            </p>
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                                src={`data:image/png;base64,${setup.qr_png_base64}`}
                                alt="TOTP QR code"
                                className="mx-auto h-48 w-48"
                            />
                            <p className="break-all text-center text-xs text-muted-foreground">
                                Manual key: <span className="font-mono">{setup.secret}</span>
                            </p>
                            <form onSubmit={onSubmit} className="space-y-4">
                                <div className="space-y-2">
                                    <Label htmlFor="code">Verification code</Label>
                                    <Input
                                        id="code"
                                        inputMode="numeric"
                                        value={code}
                                        onChange={(e) => setCode(e.target.value)}
                                        required
                                    />
                                </div>
                                {error && <p className="text-sm text-destructive">{error}</p>}
                                <Button type="submit" className="w-full" disabled={loading}>
                                    {loading ? "Enabling…" : "Enable 2FA"}
                                </Button>
                            </form>
                        </>
                    ) : (
                        <p className="text-sm text-muted-foreground">
                            {error ?? "Preparing enrollment…"}
                        </p>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
