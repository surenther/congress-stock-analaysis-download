"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { apiFetch, proxyUrl } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";

interface User {
    id: string;
    username: string;
    email: string | null;
    roles: string[];
    allowed_chambers: string[];
    is_active: boolean;
    mfa_enabled: boolean;
}

export default function AdminUsersPage() {
    const qc = useQueryClient();
    const [username, setUsername] = useState("");
    const [email, setEmail] = useState("");
    const [role, setRole] = useState("user");
    const [chambers, setChambers] = useState("House,Senate");

    const users = useQuery({
        queryKey: ["admin-users"],
        queryFn: () =>
            apiFetch<User[]>(proxyUrl("auth", "/api/v1/admin/users")),
    });

    const create = useMutation({
        mutationFn: () =>
            apiFetch(proxyUrl("auth", "/api/v1/admin/users"), {
                method: "POST",
                body: JSON.stringify({
                    username,
                    email: email || null,
                    roles: [role],
                    allowed_chambers: chambers
                        .split(",")
                        .map((c) => c.trim())
                        .filter(Boolean),
                    send_welcome: Boolean(email),
                }),
            }),
        onSuccess: () => {
            setUsername("");
            setEmail("");
            qc.invalidateQueries({ queryKey: ["admin-users"] });
        },
    });

    const toggleActive = useMutation({
        mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
            apiFetch(proxyUrl("auth", `/api/v1/admin/users/${id}`), {
                method: "PATCH",
                body: JSON.stringify({ is_active: !isActive }),
            }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
    });

    const reset2fa = useMutation({
        mutationFn: (id: string) =>
            apiFetch(proxyUrl("auth", `/api/v1/admin/users/${id}/reset-2fa`), {
                method: "POST",
            }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
    });

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-semibold">User Management</h1>

            <Card>
                <CardHeader>
                    <CardTitle>Create user</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-wrap items-end gap-3">
                    <Input
                        className="max-w-[180px]"
                        placeholder="username"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                    />
                    <Input
                        className="max-w-[220px]"
                        placeholder="email (optional)"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                    />
                    <select
                        className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                        value={role}
                        onChange={(e) => setRole(e.target.value)}
                    >
                        <option value="user">user</option>
                        <option value="admin">admin</option>
                    </select>
                    <Input
                        className="max-w-[200px]"
                        placeholder="House,Senate"
                        value={chambers}
                        onChange={(e) => setChambers(e.target.value)}
                    />
                    <Button
                        onClick={() => create.mutate()}
                        disabled={!username || create.isPending}
                    >
                        <UserPlus className="h-4 w-4" /> Create
                    </Button>
                </CardContent>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>Users</CardTitle>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Username</TableHead>
                                <TableHead>Email</TableHead>
                                <TableHead>Roles</TableHead>
                                <TableHead>Chambers</TableHead>
                                <TableHead>2FA</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead />
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {(users.data ?? []).map((user) => (
                                <TableRow key={user.id}>
                                    <TableCell className="font-medium">{user.username}</TableCell>
                                    <TableCell>{user.email ?? "—"}</TableCell>
                                    <TableCell>{user.roles.join(", ")}</TableCell>
                                    <TableCell>{user.allowed_chambers.join(", ")}</TableCell>
                                    <TableCell>
                                        <Badge variant={user.mfa_enabled ? "success" : "secondary"}>
                                            {user.mfa_enabled ? "on" : "off"}
                                        </Badge>
                                    </TableCell>
                                    <TableCell>
                                        <Badge variant={user.is_active ? "success" : "destructive"}>
                                            {user.is_active ? "active" : "inactive"}
                                        </Badge>
                                    </TableCell>
                                    <TableCell className="space-x-1">
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() =>
                                                toggleActive.mutate({
                                                    id: user.id,
                                                    isActive: user.is_active,
                                                })
                                            }
                                        >
                                            {user.is_active ? "Deactivate" : "Activate"}
                                        </Button>
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => reset2fa.mutate(user.id)}
                                        >
                                            Reset 2FA
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                            {!users.data?.length && (
                                <TableRow>
                                    <TableCell colSpan={7} className="text-muted-foreground">
                                        No users yet.
                                    </TableCell>
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    );
}
