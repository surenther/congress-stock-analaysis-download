# Downloader Microservice

[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

The **Downloader Microservice** is the data-ingestion engine of the Congressional
Financial Disclosures platform. It downloads, organizes, and monitors official
U.S. Congressional financial disclosure filings (STOCK Act **Periodic Transaction
Reports** and **Annual Reports**) for both the **U.S. House of Representatives**
and the **U.S. Senate**, and exposes them through a FastAPI REST API with
asynchronous, PostgreSQL-backed job tracking.

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
| [`Dockerfile`](Dockerfile:1) | `python:3.11-slim` image; copies the `.env.*.example` templates to runtime `.env.house` / `.env.senate`; exposes `8511`. |
| [`requirements.txt`](requirements.txt:1) | `requests`, `python-dotenv`, `fastapi`, `uvicorn[standard]`, `pydantic`, `asyncpg`, `PyJWT`, `python-multipart`. |

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

---

## API Reference

Base URL (Docker Compose default): `http://localhost:8511`

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | — | Container healthcheck; reports storage path and writability. |
| `GET` | `/status` | — | In-memory status of the legacy sync jobs (House/Senate). |
| `POST` | `/api/v1/download/trigger` | Bearer JWT (`admin` or `downloader`) | Enqueues an async download job; returns `202` with `job_id`. |
| `GET` | `/api/v1/download/status/{job_id}` | Bearer JWT (`admin` or `downloader`) | Returns the PostgreSQL-backed job state. |
| `POST` | `/download/house` | — | Legacy: triggers a House download in the background. |
| `POST` | `/download/senate` | — | Legacy: triggers a Senate download in the background. |
| `POST` | `/download/all` | — | Legacy: sequentially queues both downloads. |

> **Auth semantics:** unauthenticated requests to the async endpoints return
> `401 Unauthorized`; authenticated requests lacking the required role return
> `403 Forbidden`. Tokens are issued by the
> [Auth Service](../auth-service/README.md) and validated with the shared
> `JWT_SECRET_KEY`.

### Request models

**`AsyncDownloadRequest`** (used by `POST /api/v1/download/trigger`):

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `chamber` | string | ✅ | — | One of `house`, `senate`, `all`. |
| `year` | string | ❌ | `null` | Reporting year (e.g. `"2026"`). Falls back to `YEAR`. |
| `max_downloads` | integer | ❌ | `0` | Max files to download (`0` = all). |
| `force_download` | boolean | ❌ | `false` | Overwrite existing local files. |

**`DownloadRequest`** (used by the legacy `/download/*` endpoints): same as above
minus `chamber`.

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
     -d '{"chamber": "house", "year": "2026", "max_downloads": 0}'
```

Expected response (`202 Accepted`):

```json
{ "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f", "status": "PENDING" }
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

### 4. Legacy (unauthenticated) endpoints

```bash
# Trigger a House download in the background
curl -s -X POST "http://localhost:8511/download/house" \
     -H "Content-Type: application/json" \
     -d '{"year": "2026", "max_downloads": 50}'

# Trigger a Senate download in the background
curl -s -X POST "http://localhost:8511/download/senate" \
     -H "Content-Type: application/json" \
     -d '{"year": "2026", "max_downloads": 0}'

# Poll the in-memory legacy job status
curl -s "http://localhost:8511/status"
```

Expected `/status` response:

```json
{
  "timestamp": "2026-11-18T19:57:14.925000",
  "output_directory": "/data/house_rep",
  "jobs": {
    "house": {
      "status": "IDLE",
      "last_run": null,
      "year": null,
      "stats": null,
      "message": "No jobs executed yet."
    },
    "senate": {
      "status": "IDLE",
      "last_run": null,
      "year": null,
      "stats": null,
      "message": "No jobs executed yet."
    }
  }
}
```

### 5. Health check

```bash
curl -s "http://localhost:8511/health"
```

```json
{
  "status": "healthy",
  "timestamp": "2026-11-18T19:57:14.925000",
  "storage_path": "/data/house_rep",
  "storage_writable": true
}
```

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
| :--- | :--- | :--- |
| `401 Unauthorized` on `/api/v1/download/*` | Missing/expired/invalid JWT. | Re-run the login step; ensure `JWT_SECRET_KEY` matches the Auth Service. |
| `403 Forbidden` on `/api/v1/download/*` | Token lacks the `admin`/`downloader` role. | Register a client with the right role or use the seeded `admin` user. |
| `503`/connection errors at startup | PostgreSQL not ready. | The service `depends_on` a healthy `db`; check `docker compose logs db`. |
| `[!] Error: No ZIP_URL_TEMPLATES configured in env.` | `.env.house` missing or not mounted. | Ensure `.env.house` exists and is mounted at `/app/.env.house`. |
| `[!] Error passing agreement gate` | Senate CSRF/session issue. | Verify `AGREEMENT_URL`/`BASE_URL` and that `AUTO_ACCEPT_AGREEMENT=true`. |
| Files not appearing on the host | Volume not mounted / wrong `OUTPUT_BASE_DIR`. | Confirm `OUTPUT_BASE_DIR` in the root `.env` and that the container writes to `/data`. |
| `storage_writable: false` in `/health` | Host volume is read-only or missing. | Fix host permissions on the mounted directory. |
| Downloads re-fetching every run | `FORCE_DOWNLOAD=true`. | Set `FORCE_DOWNLOAD=false` to enable skip logic. |

---

## Configuration Reference

The downloader reads chamber-specific configuration from `.env.house` and
`.env.senate` (templates: [`.env.house.example`](.env.house.example) and
[`.env.senate.example`](.env.senate.example)). Runtime/container variables
(`DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `OUTPUT_BASE_DIR`) are
injected by `docker-compose.yml`.

### Runtime / container variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql://congress:congress_secret@localhost:5432/congress_db` | PostgreSQL DSN for the `jobs` table. |
| `JWT_SECRET_KEY` | `change-me-in-production` | Shared secret used to verify JWTs issued by the Auth Service. |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm. |
| `OUTPUT_BASE_DIR` | `/data` (Docker) | Root storage directory (mounted host volume). |
| `ENV_FILE` | — | Optional path to an explicit env file (used by the CLI resolver). |

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
- [OCR Processor (planned)](../ocr_processor/README.md) — downstream text/table extraction.
