"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { ChatDrawer } from "@/components/chat/ChatDrawer";

// Routes that must be reachable without a session (login, 2FA challenge, and
// the welcome / password-reset flow reached from an emailed token link).
const PUBLIC_ROUTES = ["/login", "/mfa", "/reset-password"];

function isPublicRoute(pathname: string | null): boolean {
    if (!pathname) return false;
    return PUBLIC_ROUTES.some(
        (route) => pathname === route || pathname.startsWith(`${route}/`),
    );
}

function LoadingScreen() {
    return (
        <div className="flex flex-1 items-center justify-center py-24">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin text-emerald-500" />
                <span>Loading your workspace…</span>
            </div>
        </div>
    );
}

/**
 * Client-side access shell.
 *
 * - Waits for the stored session to hydrate before deciding anything.
 * - Redirects unauthenticated users to `/login` and authenticated users away
 *   from the auth pages to the dashboard.
 * - On the auth pages it renders the standalone login screen (no app chrome).
 * - Only authenticated users see the header/footer/chat navigation, and the
 *   header itself filters its links by the user's role.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
    const { ready, isAuthenticated } = useAuth();
    const pathname = usePathname();
    const router = useRouter();
    const publicRoute = isPublicRoute(pathname);

    useEffect(() => {
        if (!ready) return;
        if (!isAuthenticated && !publicRoute) {
            router.replace("/login");
        } else if (isAuthenticated && publicRoute) {
            router.replace("/dashboard");
        }
    }, [ready, isAuthenticated, publicRoute, router]);

    // Auth pages (login / 2FA) render standalone. If a session already exists we
    // are redirecting, so show the loader to avoid a flash of the login form.
    if (publicRoute) {
        return isAuthenticated ? (
            <LoadingScreen />
        ) : (
            <main className="flex-1">{children}</main>
        );
    }

    // Still hydrating, or not authenticated (redirect in progress): keep the
    // chrome hidden so "Guest"/unauthenticated state is never shown.
    if (!ready || !isAuthenticated) {
        return <LoadingScreen />;
    }

    return (
        <>
            <Header />
            <main className="flex-1 pb-16">{children}</main>
            <Footer />
            <ChatDrawer />
        </>
    );
}