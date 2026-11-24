/**
 * Build a `/search` deep-link with the given filters applied.
 *
 * Empty/undefined values are dropped so the resulting querystring only carries
 * the filters the user actually selected. Used by dashboard widgets (KPI cards,
 * chart points, table rows) to drill into the underlying disclosure records.
 */
export function buildSearchHref(
    params: Record<string, string | undefined | null>,
): string {
    const sp = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null && value !== "") {
            sp.set(key, value);
        }
    }
    const qs = sp.toString();
    return qs ? `/search?${qs}` : "/search";
}