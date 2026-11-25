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

/**
 * Resolve a dashboard time-horizon label to an inclusive start date
 * (`YYYY-MM-DD`), mirroring the backend's `_horizon_start` in
 * `services/rag/dashboard.py`. Returns `undefined` for "All Time" (no bound).
 *
 * Used so a drill-down from a horizon-scoped widget (KPI card, table row, pie
 * slice) carries the same date window into the disclosure grid — otherwise the
 * grid would show all-time records and the counts would not match the widget.
 */
export function horizonToStartDate(horizon?: string): string | undefined {
    if (!horizon) return undefined;
    const today = new Date();
    const fmt = (d: Date) =>
        `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
            d.getDate(),
        ).padStart(2, "0")}`;
    const daysAgo = (n: number) => {
        const d = new Date(today);
        d.setDate(d.getDate() - n);
        return fmt(d);
    };
    switch (horizon) {
        case "30 Days":
            return daysAgo(30);
        case "90 Days":
            return daysAgo(90);
        case "YTD":
            return `${today.getFullYear()}-01-01`;
        case "1 Year":
            return daysAgo(365);
        case "All Time":
        default:
            return undefined;
    }
}