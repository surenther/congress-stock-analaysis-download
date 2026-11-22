# Admin / Observability Service

Read-only FastAPI microservice that aggregates job state across the
**downloader**, **parser**, and **vectorizer** services. All three domain
services share the same PostgreSQL database, so this service queries their job
tables directly and normalizes the results into one consistent shape for
dashboards and operators.

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

### `GET /api/v1/jobs`

Query parameters:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `service` | string | *(all)* | Filter to `downloader`, `parser`, or `vectorizer`. |
| `status` | string | *(all)* | Filter to `PENDING`, `IN_PROGRESS`, `COMPLETED`, or `FAILED`. |
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
pagination), the summary aggregation, single-job detail, per-job items, and the
**admin-only** enforcement on every `/api/v1/jobs*` route (a `user` token gets
`403`, no token gets `401`).

```bash
# From the repository root, with the stack running and tests/.env.test configured:
pytest tests/test_admin_service.py -v
```

See the [test suite README](../../tests/README.md) for credential setup and the
contract vs. integration run modes.

---

## Notes

- The service is **read-only**; it never writes to the job tables.
- It does not create or migrate tables — the domain services own their schemas.
- Because it queries the shared database directly, it must be deployed with
  network access to the same PostgreSQL instance as the domain services.
