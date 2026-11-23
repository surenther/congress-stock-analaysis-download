import { redirect } from "next/navigation";
import { getSession, landingPath } from "@/lib/session";

/** Role/scope-based landing (FR-1.3). */
export default async function DashboardIndex() {
    const session = await getSession();
    if (!session) redirect("/login");
    redirect(landingPath(session));
}
