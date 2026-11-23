import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { AppShell } from "@/components/app-shell";

export default async function AdminLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const session = await getSession();
    if (!session) redirect("/login");
    if (!session.roles.includes("admin")) redirect("/dashboard");
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
