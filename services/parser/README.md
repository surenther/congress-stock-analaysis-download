# Document Parser & OCR Microservice

[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Tesseract](https://img.shields.io/badge/OCR-Tesseract-4285F4.svg)](https://github.com/tesseract-ocr/tesseract)

The **Document Parser & OCR Microservice** turns the raw Congressional disclosure
filings downloaded by the [Downloader Service](../downloader/README.md) into a
**standardized, machine-readable JSON** representation. It reads directly from the
external host volume mounted at `/data`, handles both **House PDF** and **Senate
HTML** formats, transparently falls back to OCR for scanned/image PDFs, and
persists one JSON document per filing under `/data/parsed_json/{doc_id}.json`.

> This service is part of the [Congressional Financial Disclosures platform](../../README.md).
> See the [main README](../../README.md) for the full multi-container architecture,
> the master environment-variable reference, and the end-to-end quickstart.

---

## Table of Contents

1. [Architecture & Inner Workings](#architecture--inner-workings)
2. [Parsing Engine](#parsing-engine)
3. [Standardized Output Schema](#standardized-output-schema)
4. [API Reference](#api-reference)
5. [Running the Service Standalone](#running-the-service-standalone)
6. [Testing with `curl`](#testing-with-curl)
7. [Troubleshooting](#troubleshooting)
8. [Configuration Reference](#configuration-reference)
9. [Related Documentation](#related-documentation)

---

## Architecture & Inner Workings

The service is a single FastAPI application ([`app.py`](app.py:1)) that wraps a
pure-Python parsing engine ([`parser_engine.py`](parser_engine.py:1)) and reuses
the shared JWT helpers in [`auth_utils.py`](auth_utils.py:1).

```text
                       ┌──────────────────────────────────────────────┐
   HTTP request ──────▶│  FastAPI app (app.py)  :8513                 │
                       │  ┌────────────────────────────────────────┐  │
                       │  │ JWT verification (auth_utils)          │  │
                       │  └────────────────────────────────────────┘  │
                       │  ┌──────────────────┐  ┌──────────────────┐  │
                       │  │ /api/v1/parse/   │  │ /health          │  │
                       │  │ trigger,status,  │  │                  │  │
                       │  │ document         │  │                  │  │
                       │  └────────┬─────────┘  └──────────────────┘  │
                       └───────────┼──────────────────────────────────┘
                                   │ BackgroundTasks
                                   ▼
                       ┌──────────────────────────────────────────────┐
                       │  parser_engine.run_parse()                   │
                       │  ┌───────────────┐   ┌────────────────────┐  │
                       │  │ Senate HTML   │   │ House PDF          │  │
                       │  │ BeautifulSoup │   │ pdfplumber / OCR   │  │
                       │  └───────┬───────┘   └─────────┬──────────┘  │
                       └──────────┼─────────────────────┼─────────────┘
                                  ▼                     ▼
                       ┌──────────────────────────────────────────────┐
                       │  Host storage volume mounted at /data        │
                       │  reads: {house_rep,senate}/.../*.{pdf,html}  │
                       │  writes: parsed_json/{doc_id}.json           │
                       └──────────────────────────────────────────────┘
```

### Component map

| File | Responsibility |
| :--- | :--- |
| [`app.py`](app.py:1) | FastAPI application: routes, request models, background task orchestration, PostgreSQL `parse_jobs` table lifecycle. |
| [`parser_engine.py`](parser_engine.py:1) | Format-agnostic parsing engine: Senate HTML parsing, House PDF parsing (digital + OCR), extension-form detection, normalization, JSON persistence. |
| [`auth_utils.py`](auth_utils.py:1) | Shared JWT creation/verification and the `require_role()` RBAC dependency factory (mirrors the downloader/auth-service primitives). |
| [`Dockerfile`](Dockerfile:1) | `python:3.11-slim` image with `tesseract-ocr`, `poppler-utils`, `libtesseract-dev`, and `curl`; exposes `8513`. |
| [`requirements.txt`](requirements.txt:1) | `fastapi`, `uvicorn[standard]`, `pdfplumber`, `pdf2image`, `pytesseract`, `beautifulsoup4`, `lxml`, `psycopg2-binary`, `pydantic`, `PyJWT`, `requests`. |

### Asynchronous job lifecycle

The `/api/v1/parse/trigger` endpoint persists job state in the PostgreSQL
`parse_jobs` table (`job_id UUID`, `status`, `created_at`, `updated_at`,
`error_message`). The blocking parsing pipeline runs in a worker thread via
`asyncio.to_thread`, so the API stays responsive.

```text
PENDING ──▶ IN_PROGRESS ──▶ COMPLETED
                     └────▶ FAILED  (error_message populated)
```

---

## Parsing Engine

### Senate HTML parser (`/data/senate/.../*.html` or `.htm`)

Uses **BeautifulSoup4** (with the `lxml` backend) to parse the Senate eFD filings
downloaded by `congress-service`:

1. **Header metadata** — extracts the Senator's name, sets `chamber: "Senate"`,
   resolves the filing date, and classifies the report type (`PTR` / `Annual` /
   `Amendment`) from the report title text.
2. **Trade tables** — walks every `<table>`, maps column headers
   (Ticker/Symbol, Asset, Type, Date, Amount) case-insensitively, and emits one
   transaction dict per data row.
3. **Path fallback** — when the header text is ambiguous, the filer name is
   derived from the `Last_First` folder written by the downloader.

### House PDF parser (`/data/house_rep/.../*.pdf`)

1. **Digital extraction** — uses **`pdfplumber`** to extract page text and grid
   (`extract_tables`) structures.
2. **OCR fallback** — when a page yields fewer than 50 characters of digital
   text, the PDF is rendered to images with **`pdf2image`** (backed by
   `poppler-utils`) and OCR'd with **`pytesseract`** (backed by `tesseract-ocr`).
3. **Extension filter check** — the header text of **Page 1** is inspected. If it
   contains `"EXTENSION REQUEST FORM"` **or** `"Committee on Ethics"`, the parser
   sets `report_type: "Extension"` and **skips table extraction** (returning an
   empty `transactions` list).
4. **Transaction extraction** — table rows are mapped to the standardized fields;
   a regex line-scanner over the OCR/plain text acts as a final fallback. Tickers
   are recovered from asset descriptions (e.g. `NVIDIA Corporation (NVDA)` →
   `NVDA`).

### Normalization

| Field | Normalization |
| :--- | :--- |
| `tx_type` | Collapses `P`/`Purchase`/`Buy` → `Purchase`; `S`/`Sale`/`Sell`/`Sold` → `Sale`. |
| `tx_date` / `filing_date` | Converted to ISO `YYYY-MM-DD` across common US formats. |
| `amount_range` | Preserved verbatim (e.g. `$15,001 - $50,000`). |
| `ticker` | Extracted from parenthesised symbols or `[ST]`-tagged descriptions. |

---

## Standardized Output Schema

Every parsed filing is written to `/data/parsed_json/{doc_id}.json`:

```json
{
  "doc_id": "10073198",
  "chamber": "House",
  "filer_name": "Laurie Buckhout",
  "filing_date": "2026-01-24",
  "report_type": "PTR",
  "transactions": [
    {
      "ticker": "NVDA",
      "asset_name": "NVIDIA Corporation",
      "tx_type": "Purchase",
      "tx_date": "2026-01-15",
      "amount_range": "$15,001 - $50,000"
    }
  ]
}
```

| Field | Type | Description |
| :--- | :--- | :--- |
| `doc_id` | string | Filing identifier (from the source filename). |
| `chamber` | string | `"House"` or `"Senate"`. |
| `filer_name` | string | Name of the filing member/Senator. |
| `filing_date` | string | Filing date (ISO `YYYY-MM-DD`). |
| `report_type` | string | `PTR`, `Annual`, `Amendment`, `Candidate`, `Termination`, or `Extension`. |
| `transactions` | array | One object per disclosed trade (empty for extension forms). |

---

## API Reference

Base URL (Docker Compose default): `http://localhost:8513`

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | — | Container healthcheck; reports storage path and writability. |
| `POST` | `/api/v1/parse/trigger` | Bearer JWT | Enqueues an async parsing job; returns `202` with `job_id`. |
| `GET` | `/api/v1/parse/status/{job_id}` | Bearer JWT | Returns the PostgreSQL-backed job state. |
| `GET` | `/api/v1/parse/document/{doc_id}` | Bearer JWT | Returns the standardized parsed JSON for a filing. |

> **Auth semantics:** every `/api/v1/parse/*` endpoint is protected with
> `Depends(verify_token)`. Unauthenticated requests return `401 Unauthorized`.
> Tokens are issued by the [Auth Service](../auth-service/README.md) and
> validated with the shared `JWT_SECRET_KEY`.

### Request model

**`ParseRequest`** (used by `POST /api/v1/parse/trigger`):

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `chamber` | string | ❌ | `null` | One of `house`, `senate`, `all` (omit for all). |
| `doc_id` | string | ❌ | `null` | Parse only a single filing by DocID. |
| `force` | boolean | ❌ | `false` | Reparse documents even if JSON already exists. |

---

## Running the Service Standalone

### Option A — Docker (recommended)

From the repository root, start the database, auth service, downloader, and parser:

```bash
docker compose up -d --build db auth-service congress-service parser-service

# Follow the parser logs
docker compose logs -f congress-parser-service
```

The API is then available at `http://localhost:8513` and the interactive Swagger
UI at `http://localhost:8513/docs`.

### Option B — Local Python (no Docker)

```bash
# 1. Enter the service directory
cd services/parser

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Point at a reachable PostgreSQL instance and the local storage root
export DATABASE_URL="postgresql://congress:congress_secret@localhost:5432/congress_db"
export JWT_SECRET_KEY="change-me-in-production"
export OUTPUT_BASE_DIR="./data"   # or /data inside Docker

# 5. Run the FastAPI microservice
uvicorn app:app --reload --port 8513
```

> OCR requires the `tesseract-ocr` binary and `poppler-utils` to be installed on
> the host. Outside the container these are absent, so scanned PDFs will not be
> OCR'd (digital PDFs and Senate HTML still parse normally).

### Running the parsing engine directly (CLI)

```bash
# Parse everything under /data (or $OUTPUT_BASE_DIR)
python3 parser_engine.py

# Parse only the Senate filings
python3 parser_engine.py --chamber=senate

# Parse a single filing and force a reparse
python3 parser_engine.py --doc-id=10073198 --force
```

---

## Testing with `curl`

### 1. Obtain a Bearer token

The endpoints require a JWT issued by the Auth Service. Provision a user
directly in PostgreSQL first — see
[`../auth-service/scripts/create_user.sql`](../auth-service/scripts/create_user.sql:1) —
then log in:

```bash
curl -s -X POST "http://localhost:8512/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"username": "your_username", "password": "your_password"}'
```

### 2. Trigger a parsing job

```bash
TOKEN="<paste access_token here>"

curl -s -X POST "http://localhost:8513/api/v1/parse/trigger" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"chamber": "all"}'
```

Expected response (`202 Accepted`):

```json
{ "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f", "status": "PENDING" }
```

### 3. Poll the job status

```bash
curl -s "http://localhost:8513/api/v1/parse/status/<job_id>" \
     -H "Authorization: Bearer $TOKEN"
```

### 4. Fetch a parsed document

```bash
curl -s "http://localhost:8513/api/v1/parse/document/10073198" \
     -H "Authorization: Bearer $TOKEN"
```

### 5. Health check

```bash
curl -s "http://localhost:8513/health"
```

```json
{
  "status": "healthy",
  "timestamp": "2026-11-18T19:57:14.925000",
  "storage_path": "/data",
  "storage_writable": true,
  "parsed_json_dir": "/data/parsed_json"
}
```

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
| :--- | :--- | :--- |
| `401 Unauthorized` on `/api/v1/parse/*` | Missing/expired/invalid JWT. | Re-run the login step; ensure `JWT_SECRET_KEY` matches the Auth Service. |
| `503`/connection errors at startup | PostgreSQL not ready. | The service `depends_on` a healthy `db`; check `docker compose logs db`. |
| No documents found | Nothing downloaded yet, or wrong `OUTPUT_BASE_DIR`. | Run the downloader first; confirm the volume is mounted at `/data`. |
| `transactions: []` for every House PDF | The extension filter matched `"Committee on Ethics"` on page 1. | This is by design (see [Parsing Engine](#parsing-engine)); adjust `EXTENSION_MARKERS` in [`parser_engine.py`](parser_engine.py:1) if needed. |
| OCR errors (`tesseract not found`) | System binaries missing. | Use the provided Docker image (includes `tesseract-ocr` + `poppler-utils`) or install them locally. |
| `storage_writable: false` in `/health` | Host volume is read-only or missing. | Fix host permissions on the mounted directory. |

---

## Configuration Reference

Runtime/container variables (`DATABASE_URL`, `POSTGRES_*`, `JWT_SECRET_KEY`,
`JWT_ALGORITHM`, `OUTPUT_BASE_DIR`) are injected by `docker-compose.yml`.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `OUTPUT_BASE_DIR` | `/data` (Docker) | Root storage directory (mounted host volume). Parsed JSON is written to `${OUTPUT_BASE_DIR}/parsed_json/`. |
| `DATABASE_URL` | `postgresql://congress:congress_secret@localhost:5432/congress_db` | PostgreSQL DSN for the `parse_jobs` table. |
| `POSTGRES_USER` | `congress` | Database user (injected for parity with the other services). |
| `POSTGRES_PASSWORD` | `congress_secret` | Database password (injected for parity). |
| `POSTGRES_DB` | `congress_db` | Database name (injected for parity). |
| `JWT_SECRET_KEY` | `change-me-in-production` | Shared secret used to verify JWTs issued by the Auth Service. |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm. |

---

## Related Documentation

- [Main repository README](../../README.md) — system architecture, master env-var reference, end-to-end quickstart.
- [Downloader Service README](../downloader/README.md) — produces the raw filings this service consumes.
- [Auth Service README](../auth-service/README.md) — JWT issuance and RBAC.
