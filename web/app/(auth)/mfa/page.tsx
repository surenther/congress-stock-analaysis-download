"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function MfaPage() {
    const router = useRouter();
    const [code, setCode] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setLoading(true);
        const mfaToken = sessionStorage.getItem("mfa_token");
        if (!mfaToken) {
            setError("Your session expired. Please sign in again.");
            setLoading(false);
            return;
        }
        try {
            await apiFetch("/api/auth/mfa/verify", {
                method: "POST",
                body: JSON.stringify({ mfa_token: mfaToken, code }),
            });
            sessionStorage.removeItem("mfa_token");
            router.push("/dashboard");
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="flex min-h-screen items-center justify-center p-4">
            <Card className="w-full max-w-sm">
                <CardHeader>
                    <CardTitle>Two-factor verification</CardTitle>
                </CardHeader>
                <CardContent>
                    <form onSubmit={onSubmit} className="space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="code">Authentication code</Label>
                            <Input
                                id="code"
                                inputMode="numeric"
                                placeholder="123456"
                                value={code}
                                onChange={(e) => setCode(e.target.value)}
                                required
                            />
                            <p className="text-xs text-muted-foreground">
                                Enter the 6-digit code from your authenticator app, or a recovery
                                code.
                            </p>
                        </div>
                        {error && <p className="text-sm text-destructive">{error}</p>}
                        <Button type="submit" className="w-full" disabled={loading}>
                            {loading ? "Verifying…" : "Verify"}
                        </Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
