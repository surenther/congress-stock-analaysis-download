import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { DisclosureDataGrid } from "@/components/grid/disclosure-data-grid";

export default async function SearchPage() {
    const session = await getSession();
    if (!session) redirect("/login");
    const chamber = session.roles.includes("admin")
        ? "combined"
        : session.allowedChambers.length === 1
            ? session.allowedChambers[0].toLowerCase()
            : "combined";
    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-semibold">Search Disclosures</h1>
            <DisclosureDataGrid chamber={chamber} />
        </div>
    );
}
