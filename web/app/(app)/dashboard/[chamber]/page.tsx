import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { DashboardRenderer } from "@/components/dashboard/dashboard-renderer";

export default async function DashboardChamberPage({
    params,
}: {
    params: Promise<{ chamber: string }>;
}) {
    const session = await getSession();
    if (!session) redirect("/login");

    const { chamber } = await params;
    const allowed = session.roles.includes("admin")
        ? ["house", "senate", "combined"]
        : session.allowedChambers.map((c) => c.toLowerCase());
    if (!allowed.includes(chamber)) redirect("/dashboard");

    return <DashboardRenderer chamber={chamber} />;
}
