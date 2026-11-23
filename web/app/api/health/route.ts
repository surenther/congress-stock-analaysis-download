import { NextResponse } from "next/server";

/**
 * Liveness probe for the web container. Kept unauthenticated and minimal.
 */
export function GET() {
    return NextResponse.json({ status: "healthy" });
}
