"use client";

import { ShieldAlert } from "lucide-react";

/** Inline access-restriction banner (FR-3.4). */
export function ScopeErrorBanner({
    message,
    allowedChambers,
    requestedChamber,
}: {
    message: string;
    allowedChambers?: string[];
    requestedChamber?: string | null;
}) {
    return (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
                <p className="font-medium">{message}</p>
                {requestedChamber && (
                    <p className="text-xs">
                        Requested: {requestedChamber}
                        {allowedChambers?.length
                            ? ` · Allowed: ${allowedChambers.join(", ")}`
                            : ""}
                    </p>
                )}
            </div>
        </div>
    );
}
