/**
 * Shared display-formatting helpers for the UI.
 *
 * These keep empty-state placeholders, date formatting, and period bucketing
 * consistent across tables, cards, and charts.
 */

/** Muted fallback placeholder for empty cell values. */
export const EMPTY_PLACEHOLDER = "—";

/** True when a value is null, undefined, or the literal string "null"/"undefined". */
export function isBlank(value: unknown): boolean {
    if (value === null || value === undefined) return true;
    const text = String(value).trim().toLowerCase();
    return text === "" || text === "null" || text === "undefined";
}

/** Return the value as a string, or the em-dash placeholder when blank. */
export function orPlaceholder(value: unknown): string {
    return isBlank(value) ? EMPTY_PLACEHOLDER : String(value);
}

/**
 * Format an ISO timestamp as e.g. "Nov 21, 2026 13:37 UTC".
 * Returns the placeholder for blank or invalid input.
 */
export function formatUtc(iso?: string | null): string {
    if (isBlank(iso)) return EMPTY_PLACEHOLDER;
    const date = new Date(iso as string);
    if (Number.isNaN(date.getTime())) return EMPTY_PLACEHOLDER;
    const datePart = new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
    }).format(date);
    const timePart = new Intl.DateTimeFormat("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "UTC",
    }).format(date);
    return `${datePart} ${timePart} UTC`;
}

/**
 * Normalize a period/bucket label to "YYYY-MM". Returns null when the value is
 * blank (null, undefined, or the literal string "null"/"undefined").
 */
export function formatPeriod(value: unknown): string | null {
    if (isBlank(value)) return null;
    const text = String(value);
    // ISO date or datetime → the first 7 characters are YYYY-MM.
    const match = text.match(/^(\d{4})-(\d{2})/);
    if (match) return `${match[1]}-${match[2]}`;
    const date = new Date(text);
    if (Number.isNaN(date.getTime())) return null;
    const year = date.getUTCFullYear();
    const month = String(date.getUTCMonth() + 1).padStart(2, "0");
    return `${year}-${month}`;
}
