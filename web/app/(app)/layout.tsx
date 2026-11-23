import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { AppShell } from "@/components/app-shell";

export default async function AppLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const session = await getSession();
    if (!session) redirect("/login");
    return (
        <AppShell
            session={{
                username: session.username,
                roles: session.roles,
                allowedChambers: session.allowedChambers,
            }}
        >
            {children}
        </AppShell>
    );
}
