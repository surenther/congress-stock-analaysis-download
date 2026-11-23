export type ServiceName = "auth" | "analytics" | "admin" | "rag";

/**
 * Resolve the base URL of a backend microservice (server-side only).
 */
export function serviceBaseUrl(service: ServiceName): string {
    const map: Record<ServiceName, string | undefined> = {
        auth: process.env.AUTH_SERVICE_URL,
        analytics: process.env.ANALYTICS_SERVICE_URL,
        admin: process.env.ADMIN_SERVICE_URL,
        rag: process.env.RAG_SERVICE_URL,
    };
    const url = map[service];
    if (!url) {
        throw new Error(`Missing base URL for service '${service}'`);
    }
    return url.replace(/\/$/, "");
}

export const SERVICE_NAMES: ServiceName[] = ["auth", "analytics", "admin", "rag"];

export function isServiceName(value: string): value is ServiceName {
    return (SERVICE_NAMES as string[]).includes(value);
}
