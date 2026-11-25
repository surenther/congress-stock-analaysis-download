# Admin / Observability Service

FastAPI microservice that aggregates job state across the **downloader**,
**parser**, and **vectorizer** services and provides the **admin command
center**: pipeline orchestration (manual triggers + recurring schedules),
single-click retry of failed items, cluster health aggregation, and an audit-log
reader. All three domain services share the same PostgreSQL database, so this
service queries their job tables directly and normalizes the results into one
consistent shape for dashboards and operators.

All endpoints require the **`admin`** role.

## Port

| Service | Port |
|---------|------|
| admin-service | `8515` |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe (unauthenticated). |
| `GET` | `/api/v1/jobs` | Unified paginated list across all services. |
| `GET` | `/api/v1/jobs/summary` | Counts grouped by service and status. |
| `GET` | `/api/v1/jobs/{service}/{job_id}` | Single job detail. |
| `GET` | `/api/v1/jobs/{service}/{job_id}/items` | Per-document outcomes. |
| `POST` | `/api/v1/admin/pipeline/{service}/trigger` | Manually trigger a pipeline service. |
| `POST` | `/api/v1/admin/pipeline/jobs/{service}/{job_id}/retry` | Re-trigger a job's failed items. |
| `POST` | `/api/v1/admin/pipeline/jobs/{service}/{job_id}/cancel` | Request cooperative cancellation of a running job. |
| `GET` | `/api/v1/admin/health/cluster` | Probe every service's health + latency. |
| `GET` | `/api/v1/admin/audit-log` | Read recent audit-log entries. |
| `GET` | `/api/v1/admin/pipeline/schedule` | List recurring pipeline schedules. |
| `POST` | `/api/v1/admin/pipeline/schedule` | Create a recurring pipeline schedule. |
| `DELETE` | `/api/v1/admin/pipeline/schedule/{id}` | Delete a schedule. |

### `GET /api/v1/jobs`

Query parameters:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `service` | string | *(all)* | Filter to `downloader`, `parser`, or `vectorizer`. |
| `status` | string | *(all)* | Filter to `PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, or `CANCELLED`. |
| `limit` | integer | `50` | Page size (1–500). |
| `offset` | integer | `0` | Page offset. |

Results are ordered newest-first by `created_at`.

### `GET /api/v1/jobs/summary`

Returns total counts, per-service counts, per-status counts, and a
`breakdown` array of `{service, status, count}` pairs.

### `GET /api/v1/jobs/{service}/{job_id}`

Returns the normalized job row. `service` must be one of `downloader`,
`parser`, or `vectorizer`.

### `GET /api/v1/jobs/{service}/{job_id}/items`

Returns paginated per-document outcomes. Supports the same `status`, `limit`,
and `offset` filters as the per-service items endpoints. The downloader's items
table has no `cost` column, so `cost` is always `0` for downloader items.

### `POST /api/v1/admin/pipeline/{service}/trigger`

Proxies a trigger to the named pipeline service (`downloader`, `parser`, or
`vectorizer`) using the caller's bearer token. Body: `{ "chamber": "house",
"doc_ids": [...], "force": false, "limit": 50 }` (all optional). Returns the
upstream job response.

### `POST /api/v1/admin/pipeline/jobs/{service}/{job_id}/retry`

Looks up the `FAILED` items of a job and re-triggers them (single-click retry).
Returns `{ "service", "retried", "doc_ids", "result" }`.

### `POST /api/v1/admin/pipeline/jobs/{service}/{job_id}/cancel`

Requests **cooperative cancellation** of a running job by setting the job's
`cancel_requested` flag. The owning service stops at the next document/file
boundary and marks the job `CANCELLED`. Jobs already in a terminal state are
reported as-is. Returns `{ "service", "job_id", "status", "cancel_requested",
"message" }`.

### `GET /api/v1/admin/health/cluster`

Probes every microservice's health endpoint (auth `8512`, downloader `8511`,
parser `8513`, vectorizer `8514`, admin `8515`, RAG `8516`, and
LiteLLM `4000`) and returns `{ "checked_at", "services": [{ "service", "url",
"status", "http_status", "latency_ms" }] }`.

### `GET /api/v1/admin/audit-log`

Returns recent `audit_log` entries. Optional filters (combined with AND):
`action`, `actor` (username), `target_type`, `target_id`, and a `since`/`until`
ISO 8601 created-at window. Paginate with `limit`/`offset`. Invalid timestamps
return `422`.

### `GET|POST|DELETE /api/v1/admin/pipeline/schedule`

Manage recurring pipeline schedules. A background task checks due schedules once
per minute and triggers the service. `POST` body: `{ "service", "chamber",
"interval_minutes" }`.

## Normalized job shape

```json
{
  "service": "parser",
  "job_id": "…",
  "status": "COMPLETED",
  "chamber": "house",
  "requested_by": "admin",
  "mode": "bulk",
  "total_documents": 120,
  "processed_documents": 120,
  "total_cost": 0.0421,
  "created_at": "2026-11-20T12:00:00+00:00",
  "updated_at": "2026-11-20T12:05:00+00:00",
  "error_message": null
}
```

The downloader's `jobs` table does not track `mode`, `total_documents`,
`processed_documents`, or `total_cost`; those fields are returned as `null`.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string (shared with the domain services). |
| `JWT_SECRET_KEY` | ✅ | Shared JWT signing secret (must match the auth-service). |
| `JWT_ISSUER` | ❌ | Expected JWT issuer (default `congress-auth`). |
| `JWT_AUDIENCE` | ❌ | Expected JWT audience (default `congress-platform`). |
| `DOWNLOADER_SERVICE_URL` | ❌ | Downloader base URL (default `http://congress-service:8511`). |
| `PARSER_SERVICE_URL` | ❌ | Parser base URL (default `http://parser-service:8513`). |
| `VECTORIZER_SERVICE_URL` | ❌ | Vectorizer base URL (default `http://vectorizer-service:8514`). |
| `AUTH_SERVICE_URL` | ❌ | Auth base URL (default `http://auth-service:8512`). |
| `ADMIN_SERVICE_URL` | ❌ | Admin base URL (default `http://admin-service:8515`). |
| `RAG_SERVICE_URL` | ❌ | RAG base URL (default `http://rag-service:8516`). |
| `LITELLM_PROXY_URL` | ❌ | LiteLLM base URL (default `http://litellm-proxy:4000`). |
| `LOG_LEVEL` | ❌ | Log verbosity (default `INFO`). |

## Running locally

```bash
docker compose up -d --build admin-service
```

The API is then available at `http://localhost:8515` and the interactive Swagger
UI at `http://localhost:8515/docs`.

Then:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8515/api/v1/jobs?service=parser&status=FAILED&limit=20"
```

## Automated Testing

The admin service is covered by
[`tests/test_admin_service.py`](../../tests/test_admin_service.py), which
exercises health, the unified job list (with `service`/`status` filters and
pagination), the summary aggregation, single-job detail, per-job items, the
pipeline trigger/retry routes, cluster health, the audit log, schedule CRUD, and
the **admin-only** enforcement on every route (a `user` token gets `403`, no
token gets `401`).

```bash
# From the repository root, with the stack running and tests/.env.test configured:
pytest tests/test_admin_service.py -v
```

See the [test suite README](../../tests/README.md) for credential setup and the
contract vs. integration run modes.

---

## Notes

- The service **reads** the domain job tables and, for cancellation, sets the
  `cancel_requested` flag on a running job row (the only write it performs to
  those tables). It also creates and owns the `pipeline_schedules` table used by
  the scheduler.
- Cooperative cancellation requires each pipeline service to poll
  `cancel_requested` (configurable via `*_CANCEL_POLL_SECONDS`, default `5`) and
  stop at the next document/file boundary.
- It does not create or migrate the domain tables — those services own their
  schemas.
- Because it queries the shared database directly, it must be deployed with
  network access to the same PostgreSQL instance as the domain services.
- Pipeline triggers and cluster-health probes require network access to the
  other services (configured via the `*_SERVICE_URL` variables).
