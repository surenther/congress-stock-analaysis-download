"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
    LayoutDashboard,
    LogOut,
    Search,
    Shield,
    Star,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChamberToggle } from "@/components/chamber-toggle";
import { ChatAssistant } from "@/components/chat/chat-assistant";
import { cn } from "@/lib/utils";

export interface SessionInfo {
    username: string;
    roles: string[];
    allowedChambers: string[];
}

const NAV = [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { href: "/search", label: "Search", icon: Search },
    { href: "/watchlists", label: "Watchlists", icon: Star },
];

export function AppShell({
    session,
    children,
}: {
    session: SessionInfo;
    children: React.ReactNode;
}) {
    const pathname = usePathname();
    const router = useRouter();
    const isAdmin = session.roles.includes("admin");

    async function logout() {
        await fetch("/api/auth/logout", { method: "POST" });
        router.push("/login");
    }

    return (
        <div className="flex min-h-screen">
            <aside className="hidden w-60 flex-col border-r bg-muted/30 p-4 md:flex">
                <div className="mb-6 px-2 text-lg font-semibold">
                    Disclosure Analytics
                </div>
                <nav className="flex-1 space-y-1">
                    {NAV.map((item) => {
                        const Icon = item.icon;
                        const active = pathname.startsWith(item.href);
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={cn(
                                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm",
                                    active
                                        ? "bg-primary text-primary-foreground"
                                        : "hover:bg-accent",
                                )}
                            >
                                <Icon className="h-4 w-4" />
                                {item.label}
                            </Link>
                        );
                    })}
                    {isAdmin && (
                        <Link
                            href="/admin"
                            className={cn(
                                "flex items-center gap-3 rounded-md px-3 py-2 text-sm",
                                pathname.startsWith("/admin")
                                    ? "bg-primary text-primary-foreground"
                                    : "hover:bg-accent",
                            )}
                        >
                            <Shield className="h-4 w-4" />
                            Admin
                        </Link>
                    )}
                </nav>
            </aside>
            <div className="flex flex-1 flex-col">
                <header className="flex items-center justify-between border-b px-4 py-3">
                    <ChamberToggle
                        allowed={session.allowedChambers}
                        isAdmin={isAdmin}
                    />
                    <div className="flex items-center gap-3">
                        <span className="text-sm text-muted-foreground">
                            {session.username}
                        </span>
                        <Button variant="ghost" size="sm" onClick={logout}>
                            <LogOut className="h-4 w-4" /> Sign out
                        </Button>
                    </div>
                </header>
                <main className="flex-1 p-4 md:p-6">{children}</main>
            </div>
            <ChatAssistant />
        </div>
    );
}
