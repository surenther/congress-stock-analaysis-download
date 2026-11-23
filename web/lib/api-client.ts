export interface ApiError extends Error {
    status?: number;
    detail?: unknown;
}

/**
 * Fetch JSON from a BFF route, throwing a typed error on non-2xx responses.
 */
export async function apiFetch<T>(
    path: string,
    init?: RequestInit,
): Promise<T> {
    const resp = await fetch(path, {
        ...init,
        headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    const text = await resp.text();
    const data = text ? JSON.parse(text) : null;
    if (!resp.ok) {
        const detail = data?.detail;
        const message =
            typeof detail === "string"
                ? detail
                : (detail?.message ?? "Request failed");
        const error = new Error(message) as ApiError;
        error.status = resp.status;
        error.detail = detail;
        throw error;
    }
    return data as T;
}

/** Build a BFF proxy URL for a backend service path. */
export function proxyUrl(service: string, path: string): string {
    const suffix = path.startsWith("/") ? path : `/${path}`;
    return `/api/proxy/${service}${suffix}`;
}

/** Extract the structured chamber-scope violation code, if present. */
export function scopeViolationCode(error: unknown): string | null {
    const detail = (error as ApiError)?.detail;
    if (detail && typeof detail === "object" && "code" in detail) {
        return (detail as { code?: string }).code ?? null;
    }
    return null;
}
