/**
 * Client-side validation for watchlist entries, mirroring the server-side rules
 * in `services/rag/validation.py`. Used to give the user live, as-you-type
 * feedback so free-form values are rejected before submission.
 */

export type WatchlistType = "ticker" | "member";

export interface WatchlistValidation {
    valid: boolean;
    /** The normalized value to submit (uppercased ticker / trimmed name). */
    normalized: string;
    /** Human-readable error, or undefined when valid. */
    error?: string;
}

// A ticker: 1-5 uppercase letters, optionally a class suffix (BRK.B, RDS-A).
const TICKER_RE = /^[A-Z]{1,5}([.\-][A-Z]{1,2})?$/;

// A member name: at least two words of letters (with common name punctuation).
const MEMBER_RE = /^[A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z][A-Za-z.'\-]*)+$/;

const MEMBER_MIN_LEN = 3;
const MEMBER_MAX_LEN = 60;

export function normalizeTicker(value: string): string {
    return (value || "").trim().toUpperCase();
}

export function normalizeMember(value: string): string {
    return (value || "").trim().replace(/\s+/g, " ");
}

export function validateWatchlistValue(
    type: WatchlistType,
    raw: string,
): WatchlistValidation {
    const value = (raw || "").trim();
    if (!value) {
        return { valid: false, normalized: "", error: "Enter a value." };
    }

    if (type === "ticker") {
        const normalized = normalizeTicker(value);
        if (!TICKER_RE.test(normalized)) {
            return {
                valid: false,
                normalized,
                error:
                    "Ticker must be 1-5 letters, optionally with a class suffix (e.g. AAPL, BRK.B).",
            };
        }
        return { valid: true, normalized };
    }

    const normalized = normalizeMember(value);
    if (
        normalized.length < MEMBER_MIN_LEN ||
        normalized.length > MEMBER_MAX_LEN ||
        !MEMBER_RE.test(normalized)
    ) {
        return {
            valid: false,
            normalized,
            error: "Member name must be a full name (first and last), letters only.",
        };
    }
    return { valid: true, normalized };
}
