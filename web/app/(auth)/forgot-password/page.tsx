"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function ForgotPasswordPage() {
    const [email, setEmail] = useState("");
    const [sent, setSent] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setLoading(true);
        try {
            await apiFetch("/api/auth/forgot-password", {
                method: "POST",
                body: JSON.stringify({ email }),
            });
            setSent(true);
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
                    <CardTitle>Reset your password</CardTitle>
                </CardHeader>
                <CardContent>
                    {sent ? (
                        <p className="text-sm text-muted-foreground">
                            If an account exists for that email, a reset link has been sent.
                        </p>
                    ) : (
                        <form onSubmit={onSubmit} className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="email">Email</Label>
                                <Input
                                    id="email"
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                />
                            </div>
                            {error && <p className="text-sm text-destructive">{error}</p>}
                            <Button type="submit" className="w-full" disabled={loading}>
                                {loading ? "Sending…" : "Send reset link"}
                            </Button>
                            <a
                                href="/login"
                                className="block text-center text-sm text-muted-foreground hover:underline"
                            >
                                Back to sign in
                            </a>
                        </form>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
