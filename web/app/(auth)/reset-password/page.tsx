"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function ResetForm() {
    const router = useRouter();
    const params = useSearchParams();
    const token = params.get("token") ?? "";
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setLoading(true);
        try {
            await apiFetch("/api/auth/reset-password", {
                method: "POST",
                body: JSON.stringify({ token, new_password: password }),
            });
            router.push("/login");
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setLoading(false);
        }
    }

    return (
        <Card className="w-full max-w-sm">
            <CardHeader>
                <CardTitle>Choose a new password</CardTitle>
            </CardHeader>
            <CardContent>
                <form onSubmit={onSubmit} className="space-y-4">
                    <div className="space-y-2">
                        <Label htmlFor="password">New password</Label>
                        <Input
                            id="password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                        />
                        <p className="text-xs text-muted-foreground">
                            At least 12 characters with upper, lower, and a digit.
                        </p>
                    </div>
                    {error && <p className="text-sm text-destructive">{error}</p>}
                    <Button type="submit" className="w-full" disabled={loading || !token}>
                        {loading ? "Saving…" : "Set password"}
                    </Button>
                    {!token && (
                        <p className="text-sm text-destructive">
                            Missing or invalid reset token.
                        </p>
                    )}
                </form>
            </CardContent>
        </Card>
    );
}

export default function ResetPasswordPage() {
    return (
        <div className="flex min-h-screen items-center justify-center p-4">
            <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>
                <ResetForm />
            </Suspense>
        </div>
    );
}
