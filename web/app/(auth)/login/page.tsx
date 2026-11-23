"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface LoginResponse {
    ok?: boolean;
    mfa_required?: boolean;
    must_setup_2fa?: boolean;
    must_change_password?: boolean;
    mfa_token?: string;
    detail?: string;
}

function LoginForm() {
    const router = useRouter();
    const params = useSearchParams();
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError(null);
        setLoading(true);
        try {
            const data = await apiFetch<LoginResponse>("/api/auth/login", {
                method: "POST",
                body: JSON.stringify({ username, password }),
            });
            if (data.ok) {
                router.push(params.get("next") || "/dashboard");
                return;
            }
            if (data.mfa_token) {
                sessionStorage.setItem("mfa_token", data.mfa_token);
            }
            if (data.must_change_password) {
                router.push("/change-password");
            } else if (data.must_setup_2fa) {
                router.push("/setup-2fa");
            } else if (data.mfa_required) {
                router.push("/mfa");
            } else {
                setError("Unexpected login response.");
            }
        } catch (err) {
            setError((err as Error).message);
        } finally {
            setLoading(false);
        }
    }

    return (
        <Card className="w-full max-w-sm">
            <CardHeader>
                <CardTitle>Sign in</CardTitle>
            </CardHeader>
            <CardContent>
                <form onSubmit={onSubmit} className="space-y-4">
                    <div className="space-y-2">
                        <Label htmlFor="username">Username</Label>
                        <Input
                            id="username"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            autoComplete="username"
                            required
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="password">Password</Label>
                        <Input
                            id="password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            autoComplete="current-password"
                            required
                        />
                    </div>
                    {error && <p className="text-sm text-destructive">{error}</p>}
                    <Button type="submit" className="w-full" disabled={loading}>
                        {loading ? "Signing in…" : "Sign in"}
                    </Button>
                    <a
                        href="/forgot-password"
                        className="block text-center text-sm text-muted-foreground hover:underline"
                    >
                        Forgot password?
                    </a>
                </form>
            </CardContent>
        </Card>
    );
}

export default function LoginPage() {
    return (
        <div className="flex min-h-screen items-center justify-center p-4">
            <Suspense
                fallback={<p className="text-sm text-muted-foreground">Loading…</p>}
            >
                <LoginForm />
            </Suspense>
        </div>
    );
}
