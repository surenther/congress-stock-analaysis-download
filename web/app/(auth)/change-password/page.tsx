"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ChangeResponse {
    mfa_required?: boolean;
    must_setup_2fa?: boolean;
    mfa_token?: string;
}

export default function ChangePasswordPage() {
    const router = useRouter();
    const [current, setCurrent] = useState("");
    const [next, setNext] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setLoading(true);
        const mfaToken = sessionStorage.getItem("mfa_token");
        try {
            const data = await apiFetch<ChangeResponse>("/api/auth/change-password", {
                method: "POST",
                body: JSON.stringify({
                    mfa_token: mfaToken,
                    current_password: current,
                    new_password: next,
                }),
            });
            if (data.mfa_token) sessionStorage.setItem("mfa_token", data.mfa_token);
            if (data.must_setup_2fa) {
                router.push("/setup-2fa");
            } else if (data.mfa_required) {
                router.push("/mfa");
            } else {
                router.push("/dashboard");
            }
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
                    <CardTitle>Change password</CardTitle>
                </CardHeader>
                <CardContent>
                    <form onSubmit={onSubmit} className="space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="current">Current password</Label>
                            <Input
                                id="current"
                                type="password"
                                value={current}
                                onChange={(e) => setCurrent(e.target.value)}
                                required
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="next">New password</Label>
                            <Input
                                id="next"
                                type="password"
                                value={next}
                                onChange={(e) => setNext(e.target.value)}
                                required
                            />
                            <p className="text-xs text-muted-foreground">
                                At least 12 characters with upper, lower, and a digit.
                            </p>
                        </div>
                        {error && <p className="text-sm text-destructive">{error}</p>}
                        <Button type="submit" className="w-full" disabled={loading}>
                            {loading ? "Saving…" : "Update password"}
                        </Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
