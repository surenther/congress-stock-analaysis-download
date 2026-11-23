import { NextResponse } from "next/server";
import { getSession } from "@/lib/session";

/** BFF: return the current session's user profile and scope. */
export async function GET() {
    const session = await getSession();
    if (!session) {
        return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    return NextResponse.json({
        username: session.username,
        roles: session.roles,
        allowed_chambers: session.allowedChambers,
    });
}
