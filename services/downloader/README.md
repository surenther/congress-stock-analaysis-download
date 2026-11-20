# Downloader Microservice

[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

The **Downloader Microservice** is the data-ingestion engine of the Congressional
Financial Disclosures platform. It downloads, organizes, and monitors official
U.S. Congressional financial disclosure filings (STOCK Act **Periodic Transaction
Reports** and **Annual Reports**) for both the **U.S. House of Representatives**
and the **U.S. Senate**, and exposes them through a FastAPI REST API with
asynchronous, PostgreSQL-backed job tracking. The raw filings it stores on the
`/data` volume are consumed downstream by the
[Parser Service](../parser/README.md) and, in turn, the
[Vectorizer Service](../vectorizer/README.md).

> This service is part of the [Congressional Financial Disclosures platform](../../README.md).
> See the [main README](../../README.md) for the full multi-container architecture,
> the master environment-variable reference, and the end-to-end quickstart.

---

## Table of Contents

1. [Architecture & Inner Workings](#architecture--inner-workings)
2. [API Reference](#api-reference)
3. [Running the Service Standalone](#running-the-service-standalone)
4. [Testing with `curl`](#testing-with-curl)
5. [Troubleshooting](#troubleshooting)
6. [Configuration Reference](#configuration-reference)
7. [Related Documentation](#related-documentation)

---

## Architecture & Inner Workings

The service is a single FastAPI application ([`app.py`](app.py:1)) that wraps a
pure-Python ingestion engine ([`download_filings.py`](download_filings.py:1)) and
reuses the shared JWT/RBAC helpers in [`auth_utils.py`](auth_utils.py:1).

```text
                       ┌──────────────────────────────────────────────┐
   HTTP request ──────▶│  FastAPI app (app.py)  :8511                 │
                       │  ┌────────────────────────────────────────┐  │
                       │  │ JWT verification + RBAC (auth_utils)   │  │
                       │  └────────────────────────────────────────┘  │
                       │  ┌──────────────────┐  ┌──────────────────┐  │
                       │  │ Async endpoints  │  │ Legacy endpoints │  │
                       │  │ /api/v1/download │  │ /download/*      │  │
                       │  └────────┬─────────┘  └────────┬─────────┘  │
                       └───────────┼─────────────────────┼────────────┘
                                   │                     │
                    BackgroundTasks│                     │BackgroundTasks
                                   ▼                     ▼
                       ┌──────────────────────────────────────────────┐
                       │  download_filings.run_pipeline()             │
                       │  ┌───────────────┐   ┌────────────────────┐  │
                       │  │ House pipeline│   │ Senate pipeline    │  │
                       │  │ ZIP + XML     │   │ Agreement gate +   │  │
                       │  │ index         │   │ DataTables API     │  │
                       │  └───────┬───────┘   └─────────┬──────────┘  │
                       └──────────┼─────────────────────┼─────────────┘
                                  ▼                     ▼
                       ┌──────────────────────────────────────────────┐
                       │  Host storage volume mounted at /data        │
                       │  {OUTPUT_BASE_DIR}/{OUTPUT_DIR}/{YEAR}/...   │
                       └──────────────────────────────────────────────┘
```

### Component map

| File | Responsibility |
| :--- | :--- |
| [`app.py`](app.py:1) | FastAPI application: routes, request models, background task orchestration, PostgreSQL `jobs` table lifecycle. |
| [`download_filings.py`](download_filings.py:1) | Chamber-agnostic ingestion engine: env-file resolution, House ZIP/XML pipeline, Senate agreement-gate + DataTables pipeline, dedup/skip logic, filesystem layout. |
| [`auth_utils.py`](auth_utils.py:1) | Shared JWT creation/verification and the `require_role()` RBAC dependency factory. |
| [`Dockerfile`](Dockerfile:1) | `python:3.11-slim` image; copies the `.env.*.example` templates to runtime `.env.house` / `.env.senate`; runs as non-root UID `10001`; exposes `8511`. |
| [`requirements.txt`](requirements.txt:1) | `requests`, `python-dotenv`, `fastapi`, `uvicorn[standard]`, `pydantic`, `asyncpg`, `PyJWT`, `python-multipart`, `defusedxml` (all pinned). |

### House of Representatives pipeline

1. **Bulk archive download** — fetches the annual disclosure ZIP archive from
   `ZIP_URL_TEMPLATES` (e.g. `{base_url}/public_disc/financial-pdfs/{year}FD.ZIP`)
   and saves it as `ZIP_FILENAME_TEMPLATE` (default `{year}FD.zip`).
2. **XML index extraction** — extracts the master XML index from the archive.
3. **XML parsing** — walks the XML tree for record elements (`member`, `senator`,
   `filing`, `record`, `row`) and pulls `DocID`, name, filing type, filing date,
   and state/district using case-insensitive tag lookups.
4. **PDF download** — for each record, tries `PTR_PDF_URL_TEMPLATE` (for `P`
   filings) or `FINANCIAL_PDF_URL_TEMPLATE`, falling back to the other. If the
   response is HTML containing an embedded `.pdf` link, it follows that link;
   otherwise it stores the electronic report as `.html`.

### Senate pipeline

1. **Agreement gate** — when `AUTO_ACCEPT_AGREEMENT=true`, POSTs the statutory
   prohibitions checkbox (`prohibition_agreement=1`) to `AGREEMENT_URL` to
   authorize the session (CSRF token is read from the `csrftoken` cookie or the
   form).
2. **Search page navigation** — loads `SEARCH_URL` and dynamically discovers the
   report-type checkbox parameters (Annual / Periodic Transactions) and the
   date-field names.
3. **DataTables query** — POSTs to `SEARCH_DATA_URL` with a dynamic date range
   (`START_DATE` → `END_DATE`, where `END_DATE=TODAY` resolves to the current
   date) and paginates through the JSON results.
4. **Report download** — resolves each report link and stores the PDF (or the
   electronic HTML report) locally.

### Deduplication & skip logic

Before any network call, the engine checks whether the target file already exists
and is non-empty. ZIP archives, XML indexes, and individual PDFs/HTML reports are
all skipped when present, unless `FORCE_DOWNLOAD=true`. This makes re-runs fast
and bandwidth-friendly.

### Network safety

Every outbound request is restricted to the configured chamber host (`BASE_URL`)
and its subdomains, so a compromised or spoofed search response cannot redirect
the downloader at internal services or cloud metadata endpoints (SSRF
protection). The House XML index is parsed with `defusedxml` to guard against
XXE / entity-expansion attacks.

### Storage hierarchy

```text
{OUTPUT_BASE_DIR}/{OUTPUT_DIR}/{YEAR}/{Month filed}/{Name}/{doc_id}.pdf
```

Example (with `OUTPUT_BASE_DIR=/data`):

```text
/data/
├── house_rep/
│   └── 2026/
│       ├── 2026FD.zip
│       ├── 2026FD.xml
│       └── 01_January/
│           └── Pelosi_Nancy/
│               └── 20026123.pdf
└── senate/
    └── 2026/
        └── 01_January/
            └── Schumer_Chuck/
                ├── 10023456.pdf
                └── 10023789.html
```

### Asynchronous job lifecycle

The async endpoints persist job state in the PostgreSQL `jobs` table
(`job_id UUID`, `status`, `created_at`, `updated_at`, `error_message`). The
blocking ingestion pipeline runs in a worker thread via `asyncio.to_thread`, so
the API stays responsive.

```text
PENDING ──▶ IN_PROGRESS ──▶ COMPLETED
                     └────▶ FAILED  (error_message populated)
```

### Concurrency & single-job enforcement

Only **one** download job may run at a time. Before a new job is created, the
trigger checks the `jobs` table for any row in `PENDING` or `IN_PROGRESS` state.
If one exists, the request is rejected with **`409 Conflict`** and the response
names the running job:

```json
{
  "detail": "A download job is already running (job_id=..., status=IN_PROGRESS, chamber=all). Wait for it to complete before triggering another job to avoid overlapping downloads."
}
```

This prevents overlapping runs from competing for bandwidth and hammering the
House/Senate sites. The check and the insert are performed atomically under a
PostgreSQL transaction-scoped advisory lock, so two simultaneous triggers cannot
both start a job.

A job that stops making progress (its row is not updated for
`DOWNLOADER_STALE_JOB_HOURS`, default `2`) is treated as stale — for example if
the container was killed mid-run — and is automatically reaped (marked `FAILED`)
before the next trigger, so a crashed job can never block triggers forever.

### Logging

The service logs to stdout with a timestamped, leveled format, visible via
`docker compose logs -f congress-service`:

```text
2026-11-20 14:05:01 | INFO    | downloader | Received download trigger: job=... chamber=house year=2026 max_downloads=0 force=False requested_by=admin
2026-11-20 14:05:01 | INFO    | downloader | Job ... [download] started: chamber=house year=2026 max_downloads=0 force=False
2026-11-20 14:05:01 | INFO    | downloader | Job ... [download] running house pipeline (env=.env.house)
2026-11-20 14:07:42 | INFO    | downloader | Job ... [download] house pipeline finished
2026-11-20 14:07:42 | INFO    | downloader | Job ... [download] completed
```

Set `LOG_LEVEL=DEBUG` for more detail. Failures are logged at `ERROR`.

---

## API Reference

Base URL (Docker Compose default): `http://localhost:8511`

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | — | Container healthcheck; returns a minimal `{"status": "healthy"}`. |
| `POST` | `/api/v1/download/trigger` | Bearer JWT (`admin`) | Enqueues an async download job; returns `202` with `job_id`. Returns `409` if a job is already running. |
| `GET` | `/api/v1/download/status/{job_id}` | Bearer JWT (`admin` or `user`) | Returns the PostgreSQL-backed job state. |

> **Auth semantics:** unauthenticated requests to the async endpoints return
> `401 Unauthorized`; authenticated requests lacking the required role return
> `403 Forbidden`. Tokens are issued by the
> [Auth Service](../auth-service/README.md) and validated with the shared
> `JWT_SECRET_KEY`.

### Roles & authorization

The downloader enforces the platform's shared two-tier role model via
`require_role(...)` from [`auth_utils.py`](auth_utils.py:1):

| Role | `POST /trigger` | `GET /status/{job_id}` |
| :--- | :---: | :---: |
| `admin` | ✅ | ✅ |
| `user` | ❌ (`403`) | ✅ |
| *(no role / unauthenticated)* | ❌ (`401`/`403`) | ❌ (`401`/`403`) |

* **`admin`** — write access: can trigger download jobs and view their status.
* **`user`** — read-only: can view job status but cannot trigger downloads.

Roles are stored as a JSONB array on the `users` row and embedded in the JWT
`roles` claim. Provision accounts with
[`../auth-service/scripts/create_user.sql`](../auth-service/scripts/create_user.sql:1)
(see the `admin` and `user` examples there).

### Request models

**`AsyncDownloadRequest`** (used by `POST /api/v1/download/trigger`):

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `chamber` | string | ✅ | — | One of `house`, `senate`, `all`. |
| `year` | string | ❌ | `null` | Reporting year (e.g. `"2026"`). Falls back to `YEAR`. |
| `limit` | integer | ❌ | `0` | Maximum number of **new/unprocessed** filings to download **per chamber**. Already-present files are skipped and do not count toward the limit. `0` = process all unprocessed filings. |
| `force` | boolean | ❌ | `false` | Bypass deduplication and re-download up to `limit` filings. |
| `max_downloads` | integer | ❌ | `0` | Deprecated alias for `limit` (kept for backward compatibility). Also applied per chamber. |
| `force_download` | boolean | ❌ | `false` | Deprecated alias for `force` (kept for backward compatibility). |

#### Limit semantics

`limit` is the maximum number of **unprocessed/new** filings the job will
download **per chamber** — not the number of candidates inspected. The trigger
scans candidates in order, skips any filing whose PDF/HTML already exists in
`/data/`, and queues the first `limit` missing filings. It stops scanning as soon
as `limit` new filings have been queued.

* `limit: N` → queue at most `N` new downloads **per chamber**.
* `limit: 0` → process **all** unprocessed filings (no cap).
* `force: true` → bypass the deduplication check and re-download up to `limit`
  filings even if they already exist.

When `chamber: "all"`, the limit is applied **independently** to House and
Senate. For example, `{"chamber": "all", "limit": 5}` queues up to **5 House
AND 5 Senate** filings (10 total), rather than splitting a single shared budget
of 5 across both chambers.

The trigger response reports the scan outcome immediately:

```json
{
  "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f",
  "total_candidates_scanned": 1234,
  "skipped_already_downloaded": 1200,
  "queued_for_download": 34,
  "status": "IN_PROGRESS"
}
```

---

## Running the Service Standalone

### Option A — Docker (recommended)

From the repository root, start only the downloader and its dependencies:

```bash
# Start the database, auth service, and downloader
docker compose up -d --build db auth-service congress-service

# Follow the downloader logs
docker compose logs -f congress-service
```

The API is then available at `http://localhost:8511` and the interactive Swagger
UI at `http://localhost:8511/docs`.

### Option B — Local Python (no Docker)

```bash
# 1. Enter the service directory
cd services/downloader

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Provide configuration (copy the templates)
cp .env.house.example .env.house
cp .env.senate.example .env.senate

# 5. Run the FastAPI microservice
uvicorn app:app --reload --port 8511
```

> When running locally without Docker, set `OUTPUT_BASE_DIR` in `.env.house` /
> `.env.senate` to a local path (or leave it empty to write relative to the
> current directory). Inside Docker it must remain `/data`.

### Running the ingestion engine directly (CLI)

The engine can also be run without the API:

```bash
# House ingestion (loads .env.house)
python3 download_filings.py house

# Senate ingestion (loads .env.senate)
python3 download_filings.py senate

# Limit to 10 downloads for a quick smoke test
MAX_DOWNLOADS=10 python3 download_filings.py house

# Point at a custom env file
python3 download_filings.py --env=/path/to/custom.env
```

---

## Testing with `curl`

### 1. Obtain a Bearer token

The async endpoints require a JWT issued by the Auth Service. The Auth
service does **not** expose a registration endpoint and does **not** seed a
default account. Provision a user directly in PostgreSQL first — see
[`../auth-service/scripts/create_user.sql`](../auth-service/scripts/create_user.sql:1) —
then log in with those credentials.

```bash
curl -s -X POST "http://localhost:8512/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"username": "your_username", "password": "your_password"}'
```

Expected response:

```json
{ "access_token": "<JWT>", "token_type": "bearer" }
```

### 2. Trigger a download job

```bash
TOKEN="<paste access_token here>"

curl -s -X POST "http://localhost:8511/api/v1/download/trigger" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"chamber": "house", "year": "2026", "limit": 0}'
```

Expected response (`202 Accepted`):

```json
{
  "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f",
  "total_candidates_scanned": 1234,
  "skipped_already_downloaded": 1200,
  "queued_for_download": 34,
  "status": "IN_PROGRESS"
}
```

### 3. Poll the job status

```bash
curl -s "http://localhost:8511/api/v1/download/status/<job_id>" \
     -H "Authorization: Bearer $TOKEN"
```

Expected response while running:

```json
{
  "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f",
  "status": "IN_PROGRESS",
  "created_at": "2026-11-18T19:57:14.925000+00:00",
  "updated_at": "2026-11-18T19:57:20.101000+00:00",
  "error_message": null
}
```

Expected response when finished:

```json
{
  "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f",
  "status": "COMPLETED",
  "created_at": "2026-11-18T19:57:14.925000+00:00",
  "updated_at": "2026-11-18T19:58:41.552000+00:00",
  "error_message": null
}
```

On failure, `status` is `FAILED` and `error_message` contains the exception text.

### 4. Health check

```bash
curl -s "http://localhost:8511/health"
```

```json
{ "status": "healthy" }
```

> The health endpoint intentionally returns only a minimal status so it does not
> disclose internal paths or configuration to unauthenticated callers.

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
| :--- | :--- | :--- |
| `401 Unauthorized` on `/api/v1/download/*` | Missing/expired/invalid JWT. | Re-run the login step; ensure `JWT_SECRET_KEY` matches the Auth Service. |
| `403 Forbidden` on `/api/v1/download/trigger` | Token lacks the `admin` role. | Provision an `admin` user via [`../auth-service/scripts/create_user.sql`](../auth-service/scripts/create_user.sql:1), then log in again. |
| `403 Forbidden` on `/api/v1/download/status/*` | Token lacks the `admin` or `user` role. | Provision a user with the `admin` or `user` role, then log in again. |
| `409 Conflict` on `/api/v1/download/trigger` | A download job is already `PENDING`/`IN_PROGRESS`. | Wait for the running job to finish (poll `/api/v1/download/status/{job_id}`), or let it be reaped after `DOWNLOADER_STALE_JOB_HOURS`. |
| `503`/connection errors at startup | PostgreSQL not ready. | The service `depends_on` a healthy `db`; check `docker compose logs db`. |
| `[!] Error: No ZIP_URL_TEMPLATES configured in env.` | `.env.house` missing or not mounted. | Ensure `.env.house` exists and is mounted at `/app/.env.house`. |
| `[!] Error passing agreement gate` | Senate CSRF/session issue. | Verify `AGREEMENT_URL`/`BASE_URL` and that `AUTO_ACCEPT_AGREEMENT=true`. |
| Files not appearing on the host | Volume not mounted / wrong `OUTPUT_BASE_DIR`. | Confirm `OUTPUT_BASE_DIR` in the root `.env` and that the container writes to `/data`. |
| `permission denied` writing to `/data` | Host volume is read-only or not writable by UID 10001. | `sudo chown -R 10001:10001 <host folder>` (Linux). |
| Downloads re-fetching every run | `FORCE_DOWNLOAD=true`. | Set `FORCE_DOWNLOAD=false` to enable skip logic. |

---

## Configuration Reference

The downloader reads chamber-specific configuration from `.env.house` and
`.env.senate` (templates: [`.env.house.example`](.env.house.example) and
[`.env.senate.example`](.env.senate.example)). Runtime/container variables
(`DATABASE_URL`, `JWT_SECRET_KEY`, `OUTPUT_BASE_DIR`) are injected by
`docker-compose.yml`.

### Runtime / container variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | ***(required)*** | PostgreSQL DSN for the `jobs` table. The service refuses to start if unset. |
| `JWT_SECRET_KEY` | ***(required)*** | Shared secret used to verify JWTs issued by the Auth Service. **Must be ≥ 32 characters and match the other services.** |
| `OUTPUT_BASE_DIR` | `/data` (Docker) | Root storage directory (mounted host volume). Must be writable by UID `10001`. |
| `ENV_FILE` | — | Optional path to an explicit env file (used by the CLI resolver). |
| `DOWNLOADER_STALE_JOB_HOURS` | `2` | A `PENDING`/`IN_PROGRESS` job with no progress for this many hours is reaped (marked `FAILED`) so it cannot block future triggers. `0` disables reaping. |
| `LOG_LEVEL` | `INFO` | Log verbosity (`DEBUG` for verbose detail). |

> The JWT signing algorithm is **fixed to `HS256` in code** and is not
> configurable.

### Pipeline variables (`.env.house` / `.env.senate`)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `CHAMBER` | `House of Representatives` / `Senate` | Chamber name used in logs and headers. |
| `YEAR` | `2026` | Filing year to target. |
| `OUTPUT_DIR` | `house_rep` / `senate` | Destination subfolder for this chamber. |
| `BASE_URL` | — | Portal base URL (e.g. `https://disclosures-clerk.house.gov`). |
| `PORTAL_URL` | — | Human-facing portal URL (used in error hints). |
| `AGREEMENT_URL` | — | *(Senate)* Statutory agreement gate URL. |
| `SEARCH_URL` | `{base_url}/search/` | *(Senate)* Search page URL. |
| `SEARCH_DATA_URL` | — | *(Senate)* DataTables JSON endpoint. |
| `AUTO_ACCEPT_AGREEMENT` | `false` | *(Senate)* Auto-submit the prohibitions checkbox. |
| `SENATE_REPORT_TYPES` | `annual,periodic` | *(Senate)* Report types to query. |
| `START_DATE` | `01/01/{year}` | *(Senate)* Date-filed range start. |
| `END_DATE` | `TODAY` | *(Senate)* Date-filed range end (`TODAY` = current date). |
| `ZIP_URL_TEMPLATES` | — | *(House)* Comma-separated bulk ZIP URL templates. |
| `ZIP_FILENAME_TEMPLATE` | `{year}FD.zip` | *(House)* Local ZIP filename template. |
| `PTR_PDF_URL_TEMPLATE` | — | *(House)* PTR PDF URL template. |
| `FINANCIAL_PDF_URL_TEMPLATE` | — | *(House)* Annual/financial PDF URL template. |
| `FILING_TYPES` | `ALL` | Filing-type filter (`P,A,O,C,T,Z` or `ALL`). |
| `REP_NAME_FORMAT` | `last_first` | `last_first` (`Pelosi_Nancy`) or `first_last`. |
| `MONTH_FORMAT` | `01_January` | `01_January`, `January`, `01`, or `Jan`. |
| `REQUEST_DELAY` | `0.3` | Seconds between PDF downloads. |
| `MAX_DOWNLOADS` | `0` | Max files to download (`0` = all). |
| `FORCE_DOWNLOAD` | `false` | Overwrite existing local files. |
| `USER_AGENT` | Chrome UA string | HTTP `User-Agent` header. |

---

## Related Documentation

- [Main repository README](../../README.md) — system architecture, master env-var reference, end-to-end quickstart.
- [Auth Service README](../auth-service/README.md) — JWT issuance and RBAC.
- [Parser Service README](../parser/README.md) — downstream LLM-based extraction into standardized JSON.
- [Vectorizer Service README](../vectorizer/README.md) — downstream embedding generation into PostgreSQL (pgvector).
