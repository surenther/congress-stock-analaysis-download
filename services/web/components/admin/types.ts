// Shared types for the Admin Command Center.

export interface ApiUser {
    id: string;
    username: string;
    email: string | null;
    roles: string[];
    allowed_chambers: string[];
    is_active: boolean;
    mfa_enabled: boolean;
    must_change_password?: boolean;
}

export interface ApiJob {
    service: string;
    job_id: string;
    status: string;
    chamber: string | null;
    requested_by?: string | null;
    mode?: string | null;
    total_documents: number | null;
    processed_documents: number | null;
    total_cost?: number | null;
    created_at: string | null;
    updated_at?: string | null;
    error_message: string | null;
}

export interface JobItem {
    doc_id: string | null;
    file_path: string | null;
    status: string;
    detail: string | null;
    cost?: number | null;
    created_at: string | null;
}

export interface JobSummary {
    total: number;
    by_service: Record<string, number>;
    by_status: Record<string, number>;
    breakdown: { service: string; status: string; count: number }[];
}

export interface Schedule {
    id: string;
    service: string;
    chamber: string | null;
    interval_minutes: number;
    enabled: boolean;
    last_run_at: string | null;
    next_run_at: string | null;
    created_by: string | null;
    created_at: string | null;
}

export interface AuditEntry {
    id: number;
    actor_username: string | null;
    action: string;
    target_type: string | null;
    target_id: string | null;
    metadata: Record<string, unknown> | null;
    ip: string | null;
    created_at: string | null;
}

export interface ClusterService {
    name: string;
    port: number;
    healthy: boolean;
    latency_ms?: number;
}

export interface BulkActionResult {
    action: string;
    requested: number;
    succeeded: number;
    failed: number;
    results: { user_id: string; ok: boolean; detail?: string }[];
}

export const PIPELINE_SERVICES = [
    { key: "downloader", label: "Downloader Service", port: 8511 },
    { key: "parser", label: "PDF/OCR Parser", port: 8513 },
    { key: "vectorizer", label: "LangChain Vectorizer", port: 8514 },
] as const;

export const JOB_STATUSES = [
    "PENDING",
    "IN_PROGRESS",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
] as const;
