// Shared fetch helpers for the Admin Command Center.

export function authHeaders(token: string | null): Record<string, string> {
    return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Fetch JSON from a BFF route, attaching the bearer token and surfacing the
 * upstream `detail` message on failure.
 */
export async function apiFetch<T>(
    url: string,
    token: string | null,
    init?: RequestInit,
): Promise<T> {
    const res = await fetch(url, {
        ...init,
        headers: {
            ...(init?.body ? { "Content-Type": "application/json" } : {}),
            ...(init?.headers || {}),
            ...authHeaders(token),
        },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        throw new Error(
            (data as { detail?: string }).detail || `Request failed (${res.status})`,
        );
    }
    return data as T;
}

/** Format an ISO timestamp for display, or return an em dash. */
export function formatDate(value: string | null | undefined): string {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    return d.toLocaleString();
}

/** Human-friendly relative time (e.g. "3m ago"). */
export function timeAgo(value: string | null | undefined): string {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return value;
    const seconds = Math.floor((Date.now() - d.getTime()) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}
