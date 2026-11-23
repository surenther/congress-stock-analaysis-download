import crypto from "crypto";
import { cookies } from "next/headers";

const COOKIE = "congress_session";
const ALGO = "aes-256-gcm";

export const SESSION_COOKIE = COOKIE;

export interface SessionData {
    accessToken: string;
    refreshToken: string;
    username: string;
    roles: string[];
    allowedChambers: string[];
}

function key(): Buffer {
    const secret = process.env.SESSION_SECRET || "";
    if (secret.length < 32) {
        throw new Error("SESSION_SECRET must be at least 32 characters.");
    }
    return crypto.createHash("sha256").update(secret).digest();
}

export function encryptSession(data: SessionData): string {
    const iv = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv(ALGO, key(), iv);
    const enc = Buffer.concat([
        cipher.update(JSON.stringify(data), "utf8"),
        cipher.final(),
    ]);
    const tag = cipher.getAuthTag();
    return Buffer.concat([iv, tag, enc]).toString("base64url");
}

export function decryptSession(token: string): SessionData | null {
    try {
        const raw = Buffer.from(token, "base64url");
        const iv = raw.subarray(0, 12);
        const tag = raw.subarray(12, 28);
        const enc = raw.subarray(28);
        const decipher = crypto.createDecipheriv(ALGO, key(), iv);
        decipher.setAuthTag(tag);
        const dec = Buffer.concat([decipher.update(enc), decipher.final()]);
        return JSON.parse(dec.toString("utf8")) as SessionData;
    } catch {
        return null;
    }
}

export async function getSession(): Promise<SessionData | null> {
    const store = await cookies();
    const raw = store.get(COOKIE)?.value;
    if (!raw) return null;
    return decryptSession(raw);
}

export function sessionCookieOptions() {
    return {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax" as const,
        path: "/",
        maxAge: 60 * 60 * 8,
    };
}

/**
 * Determine the landing path for a session based on role and chamber scope.
 */
export function landingPath(session: SessionData): string {
    if (session.roles.includes("admin")) return "/dashboard/combined";
    const chambers = session.allowedChambers;
    if (chambers.length === 1 && chambers[0] === "House") return "/dashboard/house";
    if (chambers.length === 1 && chambers[0] === "Senate") return "/dashboard/senate";
    return "/dashboard/combined";
}
