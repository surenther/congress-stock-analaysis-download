# Vectorizer & pgvector Ingestion Microservice

[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![pgvector](https://img.shields.io/badge/PostgreSQL-pgvector-336791.svg)](https://github.com/pgvector/pgvector)
[![LiteLLM](https://img.shields.io/badge/LLM-LiteLLM%20Proxy-6E56CF.svg)](https://docs.litellm.ai/)

The **Vectorizer Microservice** consumes the standardized JSON documents produced
by the [Parser Service](../parser/README.md) (`/data/parsed_json/{doc_id}.json`),
converts every disclosure item into a **rich semantic text block**, generates
**vector embeddings** through the shared **[LiteLLM Proxy](https://docs.litellm.ai/docs/proxy/quick_start)**
container, and stores both the relational metadata and the embeddings in
PostgreSQL (`congress-db`) using **[pgvector](https://github.com/pgvector/pgvector)**.

> This service is part of the [Congressional Financial Disclosures platform](../../README.md).
> See the [main README](../../README.md) for the full multi-container architecture,
> the master environment-variable reference, and the end-to-end quickstart.

---

## Table of Contents

1. [Architecture & Inner Workings](#architecture--inner-workings)
2. [Database Schema & Vector Index](#database-schema--vector-index)
3. [Semantic Chunking](#semantic-chunking)
4. [LiteLLM Embedding Gateway](#litellm-embedding-gateway)
5. [Smart Deduplication & Skipping](#smart-deduplication--skipping)
6. [API Reference](#api-reference)
7. [Running the Service Standalone](#running-the-service-standalone)
8. [Testing with `curl`](#testing-with-curl)
9. [Troubleshooting](#troubleshooting)
10. [Configuration Reference](#configuration-reference)
11. [Related Documentation](#related-documentation)

---

## Architecture & Inner Workings

The service is a single FastAPI application ([`app.py`](app.py:1)) that wraps a
semantic chunker ([`chunker.py`](chunker.py:1)), an embedding client
([`embedder.py`](embedder.py:1)), a schema initializer ([`db_init.py`](db_init.py:1)),
and reuses the shared JWT helpers in [`auth_utils.py`](auth_utils.py:1). It never
talks to an embedding provider directly — every embedding request flows through
the `litellm-proxy` container.

```text
   HTTP request ──────▶┌──────────────────────────────────────────────┐
                       │  FastAPI app (app.py)  :8514                 │
                       │  ┌────────────────────────────────────────┐  │
                       │  │ JWT verification + RBAC (auth_utils)   │  │
                       │  └────────────────────────────────────────┘  │
                       │  ┌──────────────────┐  ┌──────────────────┐  │
                       │  │ /api/v1/         │  │ /health          │  │
                       │  │ vectorize/       │  │                  │  │
                       │  │ trigger,         │  │                  │  │
                       │  │ trigger-bulk,    │  │                  │  │
                       │  │ status, document │  │                  │  │
                       │  └────────┬─────────┘  └──────────────────┘  │
                       └───────────┼──────────────────────────────────┘
                                   │ BackgroundTasks
                                   ▼
                       ┌──────────────────────────────────────────────┐
                       │  chunker.build_chunks()                      │
                       │  reads /data/parsed_json/{doc_id}.json       │
                       │  → rich natural-language chunk per item      │
                       └───────────┬──────────────────────────────────┘
                                   │ POST /v1/embeddings (master key)
                                   ▼
                       ┌──────────────────────────────────────────────┐
                       │  LiteLLM Proxy  (litellm-proxy :4000)        │
                       │  routes by model alias:                      │
                       │   • openrouter-embed       → OpenRouter      │
                       │   • local-embed            → Ollama          │
                       └───────────┬──────────────────────────────────┘
                                   │ float[] vectors
                                   ▼
                       ┌──────────────────────────────────────────────┐
                       │  congress-db (PostgreSQL 16 + pgvector)      │
                       │  disclosure_embeddings (vector(1536))        │
                       │  HNSW cosine index · B-Tree metadata indexes │
                       └──────────────────────────────────────────────┘
```

### Component map

| File | Responsibility |
| :--- | :--- |
| [`app.py`](app.py:1) | FastAPI application: routes, request models, background task orchestration, PostgreSQL `vectorizer_jobs` table lifecycle, RBAC gating. |
| [`chunker.py`](chunker.py:1) | Reads the parser's standardized JSON, enforces path containment, and builds the rich semantic text block per disclosure item. |
| [`embedder.py`](embedder.py:1) | LiteLLM Proxy embeddings client, batch handling, pgvector upsert (`ON CONFLICT`), and the smart deduplication logic. |
| [`db_init.py`](db_init.py:1) | Enables the `vector`/`pgcrypto` extensions, registers the asyncpg vector codec, and creates the tables + indexes. |
| [`auth_utils.py`](auth_utils.py:1) | Shared JWT creation/verification and the `require_role()` RBAC dependency factory (mirrors the parser/downloader/auth-service primitives). |
| [`Dockerfile`](Dockerfile:1) | `python:3.11-slim` image; runs as non-root UID `10001`; exposes `8514`. |
| [`requirements.txt`](requirements.txt:1) | `fastapi`, `uvicorn[standard]`, `pydantic`, `PyJWT`, `asyncpg`, `httpx`, `psycopg2-binary`, `pgvector` (all pinned). |

### Asynchronous job lifecycle

The trigger endpoints persist job state in the PostgreSQL `vectorizer_jobs` table
(`job_id UUID`, `mode`, `doc_id`, `chamber`, `model`, `requested_by`,
`total_documents`, `processed_documents`, `status`, `created_at`, `updated_at`,
`error_message`). The blocking embedding pipeline runs in a worker thread via
`asyncio.to_thread`, so the API stays responsive. Bulk jobs update
`processed_documents` after each document, so progress is observable while the
job runs.

```text
PENDING ──▶ IN_PROGRESS ──▶ COMPLETED
                     └────▶ FAILED  (error_message populated)
```

### Concurrency & single-job enforcement

Only **one** vectorization job may run at a time. Before a new job is created,
the trigger checks the `vectorizer_jobs` table for any row in `PENDING` or
`IN_PROGRESS` state. If one exists, the request is rejected with **`409
Conflict`** and the response names the running job:

```json
{
  "detail": "A vectorization job is already running (job_id=..., status=IN_PROGRESS, mode=bulk). Wait for it to complete before triggering another job to avoid overloading the embedding backend."
}
```

This prevents overlapping runs from overloading the embedding backend. The check
and the insert are performed atomically under a PostgreSQL transaction-scoped
advisory lock, so two simultaneous triggers cannot both start a job.

A job that stops making progress (its row is not updated for
`VECTORIZER_STALE_JOB_HOURS`, default `2`) is treated as stale — for example if
the container was killed mid-run — and is automatically reaped (marked `FAILED`)
before the next trigger, so a crashed job can never block triggers forever.

### Logging

The service logs to stdout with a timestamped, leveled format, so everything is
visible via `docker compose logs -f congress-vectorizer-service`:

```text
2026-11-20 14:10:01 | INFO    | vectorizer | Received vectorize trigger: job=... mode=bulk chamber=all model=openrouter-embed force=False requested_by=admin
2026-11-20 14:10:01 | INFO    | vectorizer | Job ... [bulk] started: chamber=all model=openrouter-embed documents=10 force=False
2026-11-20 14:10:02 | INFO    | vectorizer | [1/10] SKIPPED_ALREADY_VECTORIZED doc_id=10078016
2026-11-20 14:10:03 | INFO    | vectorizer | VECTORIZED doc_id=10077852 model=openrouter-embed items=7 cost=$0.000041
2026-11-20 14:10:03 | INFO    | vectorizer | [2/10] OK doc_id=10077852 status=VECTORIZED items=7 cost=$0.000041
2026-11-20 14:10:20 | INFO    | vectorizer | Job ... [bulk] finished: vectorized=8 skipped=2 failed=0
```

Set `LOG_LEVEL=DEBUG` for per-request detail (proxy URL, batch size, HTTP status).

---

## Database Schema & Vector Index

The schema is created idempotently at startup by [`db_init.py`](db_init.py:1)
(and can be provisioned standalone with `python db_init.py`).

### `vectorizer_jobs` — job tracking

| Column | Type | Notes |
| :--- | :--- | :--- |
| `job_id` | `UUID` | Primary key. |
| `mode` | `VARCHAR(20)` | `single` or `bulk`. |
| `doc_id` | `VARCHAR(64)` | Document ID (single mode). |
| `chamber` | `VARCHAR(16)` | Chamber or `all` (bulk mode). |
| `model` | `VARCHAR(100)` | Embedding model alias used. |
| `requested_by` | `VARCHAR(255)` | Username that triggered the job. |
| `total_documents` | `INTEGER` | Total documents to process (bulk). |
| `processed_documents` | `INTEGER` | Documents processed so far (bulk). |
| `status` | `VARCHAR(20)` | `PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`. |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | Timestamps. |
| `error_message` | `TEXT` | Error detail or partial-failure/skip summary. |

### `disclosure_embeddings` — metadata + vectors

```sql
CREATE TABLE IF NOT EXISTS disclosure_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id VARCHAR(64) NOT NULL,
    item_index INT NOT NULL,
    chamber VARCHAR(16) NOT NULL,
    filer_name VARCHAR(255),
    filing_date DATE,
    report_type VARCHAR(64),
    contains_market_trades BOOLEAN NOT NULL DEFAULT false,
    is_market_trade BOOLEAN NOT NULL DEFAULT false,
    ticker VARCHAR(32),
    asset_name TEXT NOT NULL,
    asset_category VARCHAR(64),
    action VARCHAR(64),
    date DATE,
    value_range VARCHAR(128),
    ownership VARCHAR(32),
    comment TEXT,
    chunk_text TEXT NOT NULL,
    embedding vector(1536), -- Dimension = EMBEDDING_DIM (default 1536d)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(doc_id, item_index)
);
```

### Index layout

| Index | Type | Purpose |
| :--- | :--- | :--- |
| `idx_disclosure_ticker` | B-Tree | Fast exact filtering by ticker symbol. |
| `idx_disclosure_filer` | B-Tree | Fast exact filtering by filer name. |
| `idx_disclosure_trade` | B-Tree | Fast filtering of market trades vs. non-trade items. |
| `idx_disclosure_date` | B-Tree | Fast filtering by transaction date. |
| `idx_disclosure_vector` | **HNSW** (`vector_cosine_ops`) | Sub-millisecond approximate nearest-neighbour similarity search. |

```sql
-- B-Tree indexes for fast exact SQL filtering
CREATE INDEX IF NOT EXISTS idx_disclosure_ticker ON disclosure_embeddings(ticker);
CREATE INDEX IF NOT EXISTS idx_disclosure_filer ON disclosure_embeddings(filer_name);
CREATE INDEX IF NOT EXISTS idx_disclosure_trade ON disclosure_embeddings(is_market_trade);
CREATE INDEX IF NOT EXISTS idx_disclosure_date ON disclosure_embeddings(date);

-- HNSW index for sub-millisecond vector similarity search
CREATE INDEX IF NOT EXISTS idx_disclosure_vector
ON disclosure_embeddings USING hnsw (embedding vector_cosine_ops);
```

> **Dimension note:** the column dimension is driven by `EMBEDDING_DIM` (default
> `1536`, matching `openrouter-embed` / `text-embedding-3-small`). To use a model
> with a different dimension — e.g. the free Hugging Face `hf-embed` (384d) or
> Ollama's `local-embed` (768d) — set `EMBEDDING_DIM` to the matching value and
> recreate the `disclosure_embeddings` table (`CREATE TABLE IF NOT EXISTS` will
> not alter an existing column, so drop it first if it already exists).

### Example similarity query

```sql
-- Nearest neighbours to a query vector (cosine distance, ascending = closest)
SELECT doc_id, item_index, ticker, asset_name, chunk_text,
       embedding <=> $1 AS distance
FROM disclosure_embeddings
WHERE is_market_trade = true
ORDER BY embedding <=> $1
LIMIT 10;
```

---

## Semantic Chunking

[`chunker.py`](chunker.py:1) reads `/data/parsed_json/{doc_id}.json` and, for each
object in `items[]`, formats a rich natural-language chunk:

```text
Filer: {filer_name} ({chamber}) | Report: {report_type} | Filing Date: {filing_date} | Item: {asset_name} | Ticker: {ticker or 'N/A'} | Category: {asset_category} | Action: {action} | Transaction Date: {date or 'N/A'} | Value Range: {value_range or 'N/A'} | Owner: {ownership or 'N/A'} | Context: {comment or 'None'}
```

For example, a single NVIDIA purchase becomes:

```text
Filer: Laurie Buckhout (House) | Report: PTR | Filing Date: 2026-01-24 | Item: NVIDIA Corporation | Ticker: NVDA | Category: Stock | Action: Purchase | Transaction Date: 2026-01-15 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None
```

### Path containment

Files are read **strictly** from `/data/parsed_json/`. The resolved path is
verified with
`(Path("/data/parsed_json") / filename).resolve().is_relative_to(Path("/data/parsed_json").resolve())`.
Absolute paths and `..` traversal are rejected with **`400 Bad Request`**, so the
service cannot be used to read arbitrary container files.

---

## LiteLLM Embedding Gateway

[`embedder.py`](embedder.py:1) posts batches of chunk text to the LiteLLM Proxy's
OpenAI-compatible embeddings endpoint:

* **URL:** `http://litellm-proxy:4000/v1/embeddings` (falls back to `/embeddings`
  on HTTP 404).
* **Auth:** `Authorization: Bearer ${LITELLM_MASTER_KEY}`.
* **Body:** `{"model": "<alias>", "input": ["<chunk>", ...]}`.

The returned float arrays are upserted into `disclosure_embeddings` with
`ON CONFLICT (doc_id, item_index) DO UPDATE`, so re-runs are idempotent.

### Model provider parameters

| Alias | Backend | Dimensions | Required env var |
| :--- | :--- | :--- | :--- |
| `openrouter-embed` *(default)* | OpenRouter (`openai/text-embedding-3-small`) | 1536 | `OPENROUTER_API_KEY` |
| `text-embedding-3-small` | OpenAI (via LiteLLM) | 1536 | `OPENAI_API_KEY` |
| `hf-embed` | Hugging Face Inference API (`BAAI/bge-small-en-v1.5`, free tier) | 384 | `HUGGINGFACE_API_KEY` |
| `local-embed` | Local Ollama (`nomic-embed-text`) | 768 | `OLLAMA_API_BASE` |

Aliases are defined in [`../parser/litellm_config.yaml`](../parser/litellm_config.yaml:1).
Add a new embedding model by appending an entry to `model_list` and passing its
`model_name` as `embedding_model` in the trigger request — no code changes needed.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `EMBEDDING_MODEL` | `openrouter-embed` | Default embedding model alias. |
| `EMBEDDING_DIM` | `1536` | Expected vector dimension (must match the column). |
| `EMBEDDING_BATCH_SIZE` | `64` | Chunks per embeddings request. |
| `EMBEDDING_REQUEST_TIMEOUT` | `120` | Per-request timeout (seconds). |

---

## Smart Deduplication & Skipping

Before embedding a document, the service checks whether rows for its `doc_id`
already exist in `disclosure_embeddings`:

* **`force_revectorize = false` (default) and rows exist** → embedding generation
  is skipped, the log records `SKIPPED_ALREADY_VECTORIZED`, the skipped counter is
  incremented, and the `vectorizer_jobs` row is updated.
* **`force_revectorize = true`** → the existing rows for the `doc_id` are deleted
  and the document is re-embedded.

This makes bulk runs cheap and idempotent: only new or changed documents incur
embedding cost.

### Limit semantics (bulk mode)

`limit` is the maximum number of **unvectorized/new** documents the bulk job will
process — not the number of parsed JSON files inspected. The trigger scans
`/data/parsed_json/`, looks up which `doc_id`s already have rows in
`disclosure_embeddings`, skips those documents, and queues the first `limit`
missing documents. It stops scanning as soon as `limit` new documents have been
queued.

* `limit: N` → queue at most `N` new documents.
* `limit: 0` → process **all** unvectorized documents (no cap).
* `force_revectorize: true` → bypass the deduplication check and re-vectorize up
  to `limit` documents even if embeddings already exist.

The bulk trigger response reports the scan outcome immediately:

```json
{
  "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f",
  "status": "IN_PROGRESS",
  "mode": "bulk",
  "total_jsons_scanned": 1234,
  "skipped_already_vectorized": 1200,
  "queued_for_vectorization": 34
}
```

---

## Cost Tracking

Every LiteLLM call's cost (USD) is captured from the proxy's
`x-litellm-response-cost` response header (falling back to a `response_cost` /
`cost` field in the body) and accumulated per job. The running total is stored in
`vectorizer_jobs.total_cost` and returned as `total_cost` by the status endpoint,
so you can see exactly what a single or bulk vectorization run cost.

```json
{
  "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f",
  "mode": "bulk",
  "total_documents": 10,
  "processed_documents": 10,
  "total_cost": 0.000412,
  "status": "COMPLETED"
}
```

---

## API Reference

Base URL (Docker Compose default): `http://localhost:8514`

| Method | Endpoint | Auth | Role | Description |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | — | — | Container healthcheck; returns a minimal `{"status": "healthy"}`. |
| `POST` | `/api/v1/vectorize/trigger` | Bearer JWT | `admin` | Enqueues a single-document vectorization job; returns `202` with `job_id`. Returns `409` if a job is already running. |
| `POST` | `/api/v1/vectorize/trigger-bulk` | Bearer JWT | `admin` | Enqueues a bulk vectorization job; returns `202` with `job_id`. Returns `409` if a job is already running. |
| `GET` | `/api/v1/vectorize/status/{job_id}` | Bearer JWT | `admin`, `user` | Returns the PostgreSQL-backed job state. |
| `GET` | `/api/v1/vectorize/document/{doc_id}` | Bearer JWT | `admin`, `user` | Returns the stored chunk metadata (no raw vectors) for a document. |

> **Auth semantics:** every `/api/v1/vectorize/*` endpoint is protected with the
> shared JWT middleware (`require_role(...)`). Unauthenticated requests return
> `401 Unauthorized`; authenticated requests lacking the required role return
> `403 Forbidden`. Tokens are issued by the [Auth Service](../auth-service/README.md)
> and validated with the shared `JWT_SECRET_KEY`.

### Roles & authorization

| Role | `POST /trigger` | `POST /trigger-bulk` | `GET /status/{job_id}` | `GET /document/{doc_id}` |
| :--- | :---: | :---: | :---: | :---: |
| `admin` | ✅ | ✅ | ✅ | ✅ |
| `user` | ❌ (`403`) | ❌ (`403`) | ✅ | ✅ |
| *(no role / unauthenticated)* | ❌ (`401`/`403`) | ❌ (`401`/`403`) | ❌ (`401`/`403`) | ❌ (`401`/`403`) |

### Request models

**`VectorizeRequest`** (`POST /api/v1/vectorize/trigger`):

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `doc_id` | string | ✅ | — | Document ID of the parsed JSON to vectorize. |
| `embedding_model` | string | ❌ | `openrouter-embed` | LiteLLM embedding model alias. |
| `force` | boolean | ❌ | `false` | Re-vectorize even if embeddings already exist. |

**`BulkVectorizeRequest`** (`POST /api/v1/vectorize/trigger-bulk`):

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `chamber` | string | ❌ | `all` | `house`, `senate`, or `all`. |
| `embedding_model` | string | ❌ | `openrouter-embed` | LiteLLM embedding model alias. |
| `limit` | integer | ❌ | `0` | Maximum number of **new/unvectorized** documents to queue. Already-vectorized documents are skipped and do not count toward the limit. `0` = process all unvectorized documents. |
| `force_revectorize` | boolean | ❌ | `false` | Re-vectorize documents even if embeddings already exist. |
| `force` | boolean | ❌ | `false` | Deprecated alias for `force_revectorize` (kept for backward compatibility). |

---

## Running the Service Standalone

### Option A — Docker (recommended)

From the repository root, start the database, auth service, downloader, LiteLLM
proxy, parser, and vectorizer:

```bash
docker compose up -d --build db auth-service congress-service litellm-proxy parser-service vectorizer-service

# Follow the vectorizer logs
docker compose logs -f congress-vectorizer-service
```

The API is then available at `http://localhost:8514` and the interactive Swagger
UI at `http://localhost:8514/docs`.

### Option B — Local Python (no Docker)

```bash
# 1. Enter the service directory
cd services/vectorizer

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Point at a reachable PostgreSQL instance, the LiteLLM Proxy, and storage
export DATABASE_URL="postgresql://congress:YOUR_DB_PASSWORD@localhost:5432/congress_db"
export JWT_SECRET_KEY="$(openssl rand -hex 32)"   # must be >= 32 characters
export OUTPUT_BASE_DIR="./data"                 # or /data inside Docker
export LITELLM_PROXY_URL="http://localhost:4000"
export LITELLM_MASTER_KEY="sk-$(openssl rand -hex 24)"

# 5. (Optional) Provision the schema without starting the API
python db_init.py

# 6. Run the FastAPI microservice
uvicorn app:app --reload --port 8514
```

---

## Testing with `curl`

### 1. Obtain a Bearer token

```bash
curl -s -X POST "http://localhost:8512/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"username": "your_username", "password": "your_password"}'
```

### 2. Trigger a single-document vectorization (admin role required)

```bash
TOKEN="<paste access_token here>"

curl -s -X POST "http://localhost:8514/api/v1/vectorize/trigger" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
           "doc_id": "10073198",
           "embedding_model": "openrouter-embed",
           "force": false
         }'
```

Expected response (`202 Accepted`):

```json
{ "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f", "status": "PENDING", "mode": "single" }
```

### 3. Trigger a bulk vectorization (admin role required)

```bash
curl -s -X POST "http://localhost:8514/api/v1/vectorize/trigger-bulk" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
           "chamber": "all",
           "embedding_model": "openrouter-embed",
           "force": false
         }'
```

### 4. Poll the job status (admin or user role)

```bash
curl -s "http://localhost:8514/api/v1/vectorize/status/<job_id>" \
     -H "Authorization: Bearer $TOKEN"
```

```json
{
  "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f",
  "doc_id": null,
  "chamber": "all",
  "model": "openrouter-embed",
  "requested_by": "admin",
  "mode": "bulk",
  "total_documents": 10,
  "processed_documents": 10,
  "status": "COMPLETED",
  "created_at": "2026-11-20T14:10:01+00:00",
  "updated_at": "2026-11-20T14:10:20+00:00",
  "error_message": null
}
```

### 5. Fetch the stored embedding metadata for a document

```bash
curl -s "http://localhost:8514/api/v1/vectorize/document/10073198" \
     -H "Authorization: Bearer $TOKEN"
```

### 6. Health check

```bash
curl -s "http://localhost:8514/health"
```

```json
{ "status": "healthy" }
```

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
| :--- | :--- | :--- |
| `401 Unauthorized` on `/api/v1/vectorize/*` | Missing/expired/invalid JWT. | Re-run the login step; ensure `JWT_SECRET_KEY` matches the Auth Service. |
| `403 Forbidden` on a trigger endpoint | Caller lacks the `admin` role. | Use an account whose `roles` include `admin`. |
| `409 Conflict` on a trigger endpoint | A vectorization job is already `PENDING`/`IN_PROGRESS`. | Wait for the running job to finish (poll `/api/v1/vectorize/status/{job_id}`), or let it be reaped after `VECTORIZER_STALE_JOB_HOURS`. |
| `400 Invalid doc_id` | Absolute path or `..` traversal in `doc_id`. | Pass a bare document ID (e.g. `10073198`). |
| `404 Parsed document not found` | The parser has not produced `parsed_json/{doc_id}.json`. | Run the parser first, or verify `OUTPUT_BASE_DIR`. |
| Job `FAILED` with a proxy error | LiteLLM Proxy unreachable or no embedding model configured. | Check `docker compose logs congress-litellm-proxy`; verify `LITELLM_PROXY_URL`, `LITELLM_MASTER_KEY`, and the embedding alias in [`../parser/litellm_config.yaml`](../parser/litellm_config.yaml:1). |
| `Embedding count mismatch` | Provider returned fewer vectors than inputs. | Reduce `EMBEDDING_BATCH_SIZE`; check the proxy logs. |
| `expected 1536 dimensions, not N` | Model dimension ≠ column dimension. | Use a 1536-d model or change `vector(N)` in [`db_init.py`](db_init.py:1) and `EMBEDDING_DIM`. |
| `permission denied` reading `/data` | Host volume not readable by UID 10001. | `sudo chown -R 10001:10001 <host folder>` (Linux). |

---

## Configuration Reference

Runtime/container variables are injected by `docker-compose.yml`.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `OUTPUT_BASE_DIR` | `/data` (Docker) | Root storage directory (mounted host volume). Parsed JSON is read from `${OUTPUT_BASE_DIR}/parsed_json/`. |
| `DATABASE_URL` | ***(required)*** | PostgreSQL DSN for the `vectorizer_jobs` and `disclosure_embeddings` tables. The service refuses to start if unset. |
| `POSTGRES_USER` | `congress` | Database user (injected for parity with the other services). |
| `POSTGRES_PASSWORD` | ***(required)*** | Database password (injected for parity). |
| `POSTGRES_DB` | `congress_db` | Database name (injected for parity). |
| `JWT_SECRET_KEY` | ***(required)*** | Shared secret used to verify JWTs issued by the Auth Service. **Must be ≥ 32 characters and match the other services.** |
| `LITELLM_PROXY_URL` | `http://litellm-proxy:4000` | Base URL of the LiteLLM Proxy container. |
| `LITELLM_MASTER_KEY` | ***(required)*** | Service master key used to authenticate to the proxy. No default. |
| `EMBEDDING_MODEL` | `openrouter-embed` | Default embedding model alias. |
| `EMBEDDING_DIM` | `1536` | Expected vector dimension (must match the `vector(N)` column). |
| `EMBEDDING_BATCH_SIZE` | `64` | Chunks per embeddings request. |
| `EMBEDDING_REQUEST_TIMEOUT` | `120` | Per-request timeout (seconds) for the proxy embeddings call. |
| `VECTORIZER_STALE_JOB_HOURS` | `2` | A `PENDING`/`IN_PROGRESS` job with no progress for this many hours is reaped (marked `FAILED`) so it cannot block future triggers. `0` disables reaping. |
| `LOG_LEVEL` | `INFO` | Vectorizer log verbosity (`DEBUG` shows per-request detail). |

> The JWT signing algorithm is **fixed to `HS256` in code** and is not
> configurable.

---

## Related Documentation

- [Main repository README](../../README.md) — system architecture, master env-var reference, end-to-end quickstart.
- [Parser Service README](../parser/README.md) — produces the standardized JSON this service consumes.
- [Auth Service README](../auth-service/README.md) — JWT issuance and RBAC.
- [pgvector documentation](https://github.com/pgvector/pgvector) — vector types and index reference.
- [LiteLLM Proxy documentation](https://docs.litellm.ai/docs/proxy/quick_start) — upstream proxy reference.
