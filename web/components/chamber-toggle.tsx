"use client";

import { usePathname, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

/**
 * Chamber toggle. Admins and dual-scope users can switch between House,
 * Senate, and Combined; single-chamber users only see their chamber.
 */
export function ChamberToggle({
    allowed,
    isAdmin,
}: {
    allowed: string[];
    isAdmin: boolean;
}) {
    const router = useRouter();
    const pathname = usePathname();
    const options = isAdmin
        ? ["house", "senate", "combined"]
        : allowed.map((c) => c.toLowerCase());
    const current = pathname.split("/")[2] ?? "";

    return (
        <div className="flex gap-1">
            {options.map((opt) => (
                <Button
                    key={opt}
                    size="sm"
                    variant={current === opt ? "default" : "outline"}
                    onClick={() => router.push(`/dashboard/${opt}`)}
                >
                    {opt.charAt(0).toUpperCase() + opt.slice(1)}
                </Button>
            ))}
        </div>
    );
}
