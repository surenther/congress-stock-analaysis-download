# Document Extraction Microservice (LiteLLM Proxy)

[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![LiteLLM](https://img.shields.io/badge/LLM-LiteLLM%20Proxy-6E56CF.svg)](https://docs.litellm.ai/)

The **Document Extraction Microservice** turns the raw Congressional disclosure
filings downloaded by the [Downloader Service](../downloader/README.md) into a
**standardized, machine-readable JSON** representation. It reads directly from the
external host volume mounted at `/data`, extracts the raw document text, and
delegates all domain extraction to an LLM reached through a dedicated
**[LiteLLM Proxy](https://docs.litellm.ai/docs/proxy/quick_start)** container. The
proxy routes each request to one of three backends — **OpenRouter**, **Hugging
Face**, or a **local Ollama/vLLM** server — based on the requested model alias.

> This service is part of the [Congressional Financial Disclosures platform](../../README.md).
> See the [main README](../../README.md) for the full multi-container architecture,
> the master environment-variable reference, and the end-to-end quickstart.

> **Refactor note:** This service previously shipped hand-written regex scrapers
> and a `pdfplumber`/`pytesseract` OCR pipeline. Those have been **removed
> entirely**. Extraction is now performed by an LLM through the LiteLLM Proxy, so
> the domain logic lives in a single, tunable system prompt rather than in
> brittle parsing code.

---

## Table of Contents

1. [Architecture & Inner Workings](#architecture--inner-workings)
2. [LiteLLM Proxy & Model Providers](#litellm-proxy--model-providers)
3. [Extraction Schema & Rules](#extraction-schema--rules)
4. [System Prompt & Extraction Guidelines](#system-prompt--extraction-guidelines)
5. [API Reference](#api-reference)
6. [Running the Service Standalone](#running-the-service-standalone)
7. [Testing with `curl`](#testing-with-curl)
8. [Troubleshooting](#troubleshooting)
9. [Configuration Reference](#configuration-reference)
10. [Related Documentation](#related-documentation)

---

## Architecture & Inner Workings

The service is a single FastAPI application ([`app.py`](app.py:1)) that wraps a
thin extraction engine ([`extraction_engine.py`](extraction_engine.py:1)) and
reuses the shared JWT helpers in [`auth_utils.py`](auth_utils.py:1). It never
talks to an LLM provider directly — every extraction request flows through the
`litellm-proxy` container.

```text
                       ┌──────────────────────────────────────────────┐
   HTTP request ──────▶│  FastAPI app (app.py)  :8513                 │
                       │  ┌────────────────────────────────────────┐  │
                       │  │ JWT verification + RBAC (auth_utils)   │  │
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
                       │  extraction_engine.extract_document()        │
                       │  ┌───────────────┐   ┌────────────────────┐  │
                       │  │ read text     │   │ normalize + save   │  │
                       │  │ pypdf / bs4   │   │ JSON schema        │  │
                       │  └───────┬───────┘   └─────────▲──────────┘  │
                       └──────────┼─────────────────────┼─────────────┘
                                  │ POST /chat/completions (master key)
                                  ▼                     │
                       ┌──────────────────────────────────────────────┐
                       │  LiteLLM Proxy  (litellm-proxy :4000)        │
                       │  routes by model alias:                      │
                       │   • openrouter-deepseek-flash → OpenRouter  │
                       │   • openrouter-gemini-flash  → OpenRouter    │
                       │   • hf-qwen                  → Hugging Face  │
                       │   • local-llm                → Ollama / vLLM │
                       └──────────────────────────────────────────────┘
                                  │
                                  ▼
                       ┌──────────────────────────────────────────────┐
                       │  Host storage volume mounted at /data        │
                       │  reads: {house_rep,senate}/.../*.{pdf,html}  │
                       │  writes: parsed_json/{doc_id}.json           │
                       └──────────────────────────────────────────────┘
```

### Component map

| File | Responsibility |
| :--- | :--- |
| [`app.py`](app.py:1) | FastAPI application: routes, request models, background task orchestration, PostgreSQL `parse_jobs` table lifecycle, RBAC gating. |
| [`extraction_engine.py`](extraction_engine.py:1) | Raw text extraction (`pypdf` / BeautifulSoup), the LiteLLM Proxy client, the system prompt, output normalization, and JSON persistence. |
| [`litellm_config.yaml`](litellm_config.yaml:1) | LiteLLM Proxy routing config: maps model aliases to OpenRouter, Hugging Face, and local Ollama/vLLM backends. |
| [`auth_utils.py`](auth_utils.py:1) | Shared JWT creation/verification and the `require_role()` RBAC dependency factory (mirrors the downloader/auth-service primitives). |
| [`Dockerfile`](Dockerfile:1) | `python:3.11-slim` image (no OCR system binaries); runs as non-root UID `10001`; exposes `8513`. |
| [`requirements.txt`](requirements.txt:1) | `fastapi`, `uvicorn[standard]`, `pydantic`, `PyJWT`, `asyncpg`, `httpx`, `pypdf`, `beautifulsoup4`, `lxml`, `defusedxml` (all pinned). |

### Asynchronous job lifecycle

The `/api/v1/parse/trigger` endpoint persists job state in the PostgreSQL
`parse_jobs` table (`job_id UUID`, `doc_id`, `chamber`, `model`, `requested_by`,
`mode`, `total_documents`, `processed_documents`, `status`, `created_at`,
`updated_at`, `error_message`). The blocking extraction pipeline runs in a worker
thread via `asyncio.to_thread`, so the API stays responsive. Bulk jobs update
`processed_documents` after each document, so progress is observable while the
job runs.

```text
PENDING ──▶ IN_PROGRESS ──▶ COMPLETED
                     └────▶ FAILED  (error_message populated)
```

### Logging

The service logs to stdout with a timestamped, leveled format, so everything is
visible via `docker compose logs -f congress-parser-service`:

```text
2026-11-20 14:05:01 | INFO    | parser | Received parse trigger: job=... mode=bulk chamber=all doc_id=None file_path=None model=openrouter-deepseek-flash force=False requested_by=admin
2026-11-20 14:05:01 | INFO    | parser | Job ... [bulk] started: chamber=all model=openrouter-deepseek-flash documents=10 force=False
2026-11-20 14:05:02 | INFO    | parser | [1/10] SKIP doc_id=10078016 (already parsed) file=house_rep/2026/01_January/.../10078016.pdf
2026-11-20 14:05:03 | INFO    | parser | Extracting doc_id=10077852 chamber=House model=openrouter-deepseek-flash file=/data/house_rep/...
2026-11-20 14:05:03 | INFO    | parser | Read 18422 characters from 10077852.pdf (sending 18422 to the model)
2026-11-20 14:05:09 | INFO    | parser | Parsed doc_id=10077852 report_type=PTR contains_market_trades=True items=7 -> /data/parsed_json/10077852.json
2026-11-20 14:05:09 | INFO    | parser | [2/10] OK doc_id=10077852 chamber=House
2026-11-20 14:05:20 | INFO    | parser | Job ... [bulk] finished: parsed=8 skipped=2 failed=0
```

Set `LOG_LEVEL=DEBUG` for per-request detail (proxy URL, input size, JSON mode,
HTTP status). Errors (proxy failures, per-document failures) are logged at
`ERROR` with the proxy's response body.

---

## LiteLLM Proxy & Model Providers

The `litellm-proxy` container (see [`docker-compose.yml`](../../docker-compose.yml))
runs the official LiteLLM image on internal port **4000** and is configured by
[`litellm_config.yaml`](litellm_config.yaml:1). The parser selects a backend by
passing a **model alias** in the trigger request.

| Model alias | Backend | Underlying model | Required env var |
| :--- | :--- | :--- | :--- |
| `openrouter-deepseek-flash` *(default)* | OpenRouter | `deepseek/deepseek-v4.1-flash` (cheap) | `OPENROUTER_API_KEY` |
| `openrouter-gemini-flash` | OpenRouter | `google/gemini-3.8-flash:batch` (costly) | `OPENROUTER_API_KEY` |
| `hf-qwen` | Hugging Face Inference API | `Qwen/Qwen2.5-7B-Instruct` | `HUGGINGFACE_API_KEY` |
| `local-llm` | Local Ollama (or vLLM) | `qwen2.5:7b-instruct` | `OLLAMA_API_BASE` |

### How routing works

1. The parser POSTs to `http://litellm-proxy:4000/chat/completions` with
   `Authorization: Bearer <LITELLM_MASTER_KEY>` and a `model` alias.
2. LiteLLM looks up the alias in `model_list` and forwards the request to the
   matching provider, injecting the provider API key from the container
   environment (`os.environ/...`).
3. The response is returned in OpenAI-compatible JSON, which the parser
   normalizes into the standardized schema.

### Adding a provider or model

Append an entry to `model_list` in [`litellm_config.yaml`](litellm_config.yaml:1):

```yaml
  - model_name: my-new-alias
    litellm_params:
      model: openrouter/anthropic/claude-3.5-sonnet
      api_key: os.environ/OPENROUTER_API_KEY
```

Then pass `"model": "my-new-alias"` in the trigger request. No parser code
changes are required.

### Local GPU models (Ollama / vLLM)

* **Ollama** — run `ollama serve` on the host (or a GPU box) and set
  `OLLAMA_API_BASE` (default `http://host.docker.internal:11434`). The proxy
  reaches the host via the `host.docker.internal:host-gateway` mapping.
* **vLLM** — start a vLLM OpenAI-compatible server and change the alias's
  `model` prefix to `openai/` with `api_base` pointing at the vLLM endpoint.

---

## Extraction Schema & Rules

Every parsed filing is written to `/data/parsed_json/{doc_id}.json`:

```json
{
  "doc_id": "10073198",
  "chamber": "House",
  "filer_name": "Laurie Buckhout",
  "filing_date": "2026-01-24",
  "report_type": "PTR",
  "contains_market_trades": true,
  "items": [
    {
      "is_market_trade": true,
      "ticker": "NVDA",
      "asset_name": "NVIDIA Corporation",
      "asset_category": "Stock",
      "action": "Purchase",
      "date": "2026-01-15",
      "value_range": "$15,001 - $50,000",
      "ownership": "Self",
      "comment": null
    }
  ]
}
```

### Document metadata

| Field | Type | Description |
| :--- | :--- | :--- |
| `doc_id` | string | Filing identifier (supplied by the caller). |
| `chamber` | string | `"House"` or `"Senate"`. |
| `filer_name` | string \| null | Name of the filing member/Senator. |
| `filing_date` | string \| null | Filing date (ISO `YYYY-MM-DD`). |
| `report_type` | string | `PTR`, `Annual`, `Candidate`, `Termination`, or `Extension`. |
| `contains_market_trades` | boolean | `true` if any item is an active market trade. |
| `items` | array | One object per disclosed item (empty for extension forms). |

### Extracted item fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `is_market_trade` | boolean | Strictly distinguishes active market trades (stocks, options, bonds, crypto) from non-trade items. |
| `ticker` | string \| null | Populated **only** for active public-market assets; `null` for salary, bank deposits, or real estate. |
| `asset_name` | string \| null | Asset/company name, income source, or employer. |
| `asset_category` | string | `Stock`, `Option`, `Bond`, `Crypto`, `Mutual Fund/ETF`, `Earned Income/Salary`, `Bank Deposit`, `Real Estate`, or `Other`. |
| `action` | string | `Purchase`, `Sale`, `Partial Sale`, `Exchange`, `Received Income`, or `Holding Only`. |
| `date` | string \| null | Standardized `YYYY-MM-DD` if available. |
| `value_range` | string \| null | Disclosed dollar amount range (verbatim). |
| `ownership` | string | `Self`, `Spouse`, `Joint`, or `Dependent`. |
| `comment` | string \| null | Optional context notes. |

### Dual-category classification

Disclosures contain **both** stock trading reports (PTRs) and non-trade
disclosures (Annual reports listing salary, spouse earned income, consulting
fees, honoraria, bank accounts, blind trust holdings, or real estate). The
extraction engine strictly isolates the two:

* `is_market_trade: true` — active public-market assets (stocks, options, bonds,
  crypto, mutual funds/ETFs).
* `is_market_trade: false` — salary, spouse income, consulting fees, honoraria,
  bank deposits, real estate, and other non-trade items.

---

## System Prompt & Extraction Guidelines

All domain intelligence lives in the `SYSTEM_PROMPT` constant in
[`extraction_engine.py`](extraction_engine.py:1). It enforces:

1. **Trade vs. income classification** — strictly isolate stock/option/bond/crypto
   trades from salary, spouse income, or bank deposits.
2. **No invented tickers** — a ticker is populated only when the symbol is
   explicitly present in the text; it is `null` for salary or non-public assets.
3. **Extension form handling** — if Page 1 contains extension-request text, the
   document is classified as `Extension`, `contains_market_trades` is set to
   `false`, and item extraction is skipped.
4. **Date normalization** — all extracted dates are converted to strict
   `YYYY-MM-DD`.
5. **Factuality** — the model is strictly forbidden from hallucinating; it
   extracts only items explicitly present in the input text.

The engine also enforces these rules defensively in Python
(`normalize_document` / `_normalize_item`): enum values are coerced to the
allowed sets, dates are re-parsed, and non-trade items are stripped of any
ticker the model may have returned.

### Prompt-injection defense

Filing text is **untrusted input** (anyone can submit a filing). The system
prompt instructs the model to treat everything between the
`<<<DOCUMENT_START>>>` / `<<<DOCUMENT_END>>>` markers strictly as data, and to
ignore any instructions embedded in the document. Output is still normalized and
validated in Python as a second line of defense.

---

## API Reference

Base URL (Docker Compose default): `http://localhost:8513`

| Method | Endpoint | Auth | Role | Description |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | — | — | Container healthcheck; returns a minimal `{"status": "healthy"}`. |
| `POST` | `/api/v1/parse/trigger` | Bearer JWT | `admin` | Enqueues an async extraction job (bulk or single); returns `202` with `job_id`. |
| `GET` | `/api/v1/parse/status/{job_id}` | Bearer JWT | `admin`, `user` | Returns the PostgreSQL-backed job state. |
| `GET` | `/api/v1/parse/document/{doc_id}` | Bearer JWT | `admin`, `user` | Returns the standardized parsed JSON for a filing. |

> **Auth semantics:** every `/api/v1/parse/*` endpoint is protected with the
> shared JWT middleware (`require_role(...)`). Unauthenticated requests return
> `401 Unauthorized`; authenticated requests lacking the required role return
> `403 Forbidden`. Tokens are issued by the [Auth Service](../auth-service/README.md)
> and validated with the shared `JWT_SECRET_KEY`.

### Roles & authorization

The parser enforces the platform's shared two-tier role model via
`require_role(...)` from [`auth_utils.py`](auth_utils.py:1):

| Role | `POST /trigger` | `GET /status/{job_id}` | `GET /document/{doc_id}` |
| :--- | :---: | :---: | :---: |
| `admin` | ✅ | ✅ | ✅ |
| `user` | ❌ (`403`) | ✅ | ✅ |
| *(no role / unauthenticated)* | ❌ (`401`/`403`) | ❌ (`401`/`403`) | ❌ (`401`/`403`) |

* **`admin`** — write access: can trigger extraction jobs and read results.
* **`user`** — read-only: can view job status and fetch parsed documents.

Roles are stored as a JSONB array on the `users` row and embedded in the JWT
`roles` claim. Provision accounts with
[`../auth-service/scripts/create_user.sql`](../auth-service/scripts/create_user.sql:1)
(see the `admin` and `user` examples there).

### Request model

**`ParseRequest`** (used by `POST /api/v1/parse/trigger`). All fields are
optional — the endpoint supports two modes:

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `file_path` | string | ❌ | `null` | Path to a single raw document, **relative to `/data`**. Absolute paths and `..` traversal are rejected. **When omitted, the service runs in bulk mode.** |
| `doc_id` | string | ❌ | derived | Document ID (single mode). Derived from the filename if omitted. |
| `chamber` | string | ❌ | `all` (bulk) / derived (single) | `house`, `senate`, or `all`. |
| `model` | string | ❌ | `openrouter-deepseek-flash` | LiteLLM model alias (e.g. `openrouter-deepseek-flash` (cheap), `openrouter-gemini-flash` (costly), `hf-qwen`, `local-llm`). |
| `force` | boolean | ❌ | `false` | Reprocess a document even if its parsed JSON already exists (both modes; already-parsed documents are skipped by default). |

#### Bulk mode (default)

Omit `file_path` to process **every** document discovered on the `/data` volume
for the selected chamber(s). A minimal body triggers a full House + Senate run:

```json
{}
```

or scope it to one chamber:

```json
{ "chamber": "senate" }
```

The job reports progress via `total_documents` / `processed_documents` in the
status response. Documents whose parsed JSON (`parsed_json/{doc_id}.json`) already
exists and is non-empty are **skipped** unless `force` is `true`; the job's
`error_message` summarizes how many were parsed, skipped, and failed.

#### Single-document mode

Provide `file_path` (and optionally `doc_id` / `chamber`) to extract exactly one
filing:

```json
{
  "doc_id": "10073198",
  "chamber": "House",
  "file_path": "house_rep/2026/01_January/Buckhout_Laurie/10073198.pdf",
  "model": "openrouter-deepseek-flash"
}
```

If `parsed_json/{doc_id}.json` already exists (and is non-empty), the request is
short-circuited: a `COMPLETED` job is recorded with a `skipped` note and the
response carries `"skipped": true` — no LLM call is made. Set `"force": true` to
reparse.

> **Path safety:** `file_path` must resolve to a file **inside** the `/data`
> volume. Absolute paths, `..` traversal, and unsupported file types are
> rejected, so the service cannot be used to read arbitrary container files.

### LiteLLM pass-through security

When the parser calls the proxy it attaches the **service master key**
(`LITELLM_MASTER_KEY`) as a Bearer token and forwards caller metadata
(`user`, `roles`, `doc_id`, `chamber`, `source_file`) in the request `metadata`
field so the proxy can emit audit logs.

---

## Running the Service Standalone

### Option A — Docker (recommended)

From the repository root, start the database, auth service, downloader, LiteLLM
proxy, and parser:

```bash
docker compose up -d --build db auth-service congress-service litellm-proxy parser-service

# Follow the parser logs
docker compose logs -f congress-parser-service

# Follow the LiteLLM proxy logs
docker compose logs -f congress-litellm-proxy
```

The API is then available at `http://localhost:8513` and the interactive Swagger
UI at `http://localhost:8513/docs`. The LiteLLM Proxy is reachable at
`http://localhost:4000`.

### Option B — Local Python (no Docker)

```bash
# 1. Enter the service directory
cd services/parser

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

# 5. Run the FastAPI microservice
uvicorn app:app --reload --port 8513
```

> The LiteLLM Proxy must be running and reachable at `LITELLM_PROXY_URL` for
> extraction to succeed. Run it standalone with:
> `docker run -p 4000:4000 -v $PWD/litellm_config.yaml:/app/config.yaml ghcr.io/berriai/litellm:v1.110.2 --config /app/config.yaml --port 4000`

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

### 2. Trigger an extraction job (admin role required)

**Bulk mode** — process every document on the volume for both chambers:

```bash
TOKEN="<paste access_token here>"

curl -s -X POST "http://localhost:8513/api/v1/parse/trigger" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{}'
```

**Single-document mode** — extract one filing:

```bash
curl -s -X POST "http://localhost:8513/api/v1/parse/trigger" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
           "doc_id": "10073198",
           "chamber": "House",
           "file_path": "house_rep/2026/01_January/Buckhout_Laurie/10073198.pdf",
           "model": "openrouter-deepseek-flash"
         }'
```

Expected response (`202 Accepted`):

```json
{ "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f", "status": "PENDING", "mode": "bulk" }
```

### 3. Poll the job status (admin or user role)

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
{ "status": "healthy" }
```

> The health endpoint intentionally returns only a minimal status so it does not
> disclose internal paths or configuration to unauthenticated callers.

### 6. Verify the LiteLLM Proxy directly

```bash
curl -s "http://localhost:4000/health/liveliness"

curl -s -X POST "http://localhost:4000/chat/completions" \
     -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model": "openrouter-deepseek-flash", "messages": [{"role": "user", "content": "ping"}]}'
```

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
| :--- | :--- | :--- |
| `401 Unauthorized` on `/api/v1/parse/*` | Missing/expired/invalid JWT. | Re-run the login step; ensure `JWT_SECRET_KEY` matches the Auth Service. |
| `403 Forbidden` on `/api/v1/parse/trigger` | Caller lacks the `admin` role. | Use an account whose `roles` include `admin`. |
| `503`/connection errors at startup | PostgreSQL not ready. | The service `depends_on` a healthy `db`; check `docker compose logs db`. |
| Job `FAILED` with a proxy error | LiteLLM Proxy unreachable or misconfigured. | Check `docker compose logs congress-litellm-proxy`; verify `LITELLM_PROXY_URL` and `LITELLM_MASTER_KEY`. |
| Job `FAILED` with `HTTP 400` from the proxy | Invalid model ID or an unsupported `response_format`. | The proxy's error body is now included in `error_message`. Verify the OpenRouter model IDs (e.g. `deepseek/deepseek-v4.1-flash`, `google/gemini-3.8-flash:batch`) at https://openrouter.ai/models and in [`litellm_config.yaml`](litellm_config.yaml:1). |
| `AuthenticationError` from a provider | Missing/invalid provider API key. | Set `OPENROUTER_API_KEY` / `HUGGINGFACE_API_KEY` in `.env` and recreate the proxy. |
| `local-llm` jobs fail | No Ollama/vLLM server reachable. | Start Ollama on the host and confirm `OLLAMA_API_BASE`; ensure `host.docker.internal` resolves. |
| Model returns invalid JSON | Model too small / no JSON mode. | Prefer a JSON-capable model; the engine strips code fences and re-parses defensively. |
| `permission denied` writing to `/data` | Host volume is read-only or not writable by UID 10001. | `sudo chown -R 10001:10001 <host folder>` (Linux). |

---

## Configuration Reference

Runtime/container variables are injected by `docker-compose.yml`.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `OUTPUT_BASE_DIR` | `/data` (Docker) | Root storage directory (mounted host volume). Parsed JSON is written to `${OUTPUT_BASE_DIR}/parsed_json/`. Must be writable by UID `10001`. |
| `DATABASE_URL` | ***(required)*** | PostgreSQL DSN for the `parse_jobs` table. The service refuses to start if unset. |
| `POSTGRES_USER` | `congress` | Database user (injected for parity with the other services). |
| `POSTGRES_PASSWORD` | ***(required)*** | Database password (injected for parity). |
| `POSTGRES_DB` | `congress_db` | Database name (injected for parity). |
| `JWT_SECRET_KEY` | ***(required)*** | Shared secret used to verify JWTs issued by the Auth Service. **Must be ≥ 32 characters and match the other services.** |
| `LITELLM_PROXY_URL` | `http://litellm-proxy:4000` | Base URL of the LiteLLM Proxy container. |
| `LITELLM_MASTER_KEY` | ***(required)*** | Service master key used to authenticate to the proxy. No default. |
| `LITELLM_DEFAULT_MODEL` | `openrouter-deepseek-flash` | Default model alias when a job does not specify one. |
| `LITELLM_USE_JSON_MODE` | `false` | Send `response_format=json_object` to the provider (auto-dropped and retried on HTTP 400). |
| `LITELLM_REQUEST_TIMEOUT` | `180` | Per-request timeout (seconds) for the proxy call. |
| `PARSER_MAX_INPUT_CHARS` | `120000` | Max characters of document text sent to the model. |
| `LOG_LEVEL` | `INFO` | Parser log verbosity (`DEBUG` shows per-request detail). |

> The JWT signing algorithm is **fixed to `HS256` in code** and is not
> configurable.

### LiteLLM Proxy variables (used by the `litellm-proxy` container)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | *(empty)* | OpenRouter API key (default cloud provider). |
| `HUGGINGFACE_API_KEY` | *(empty)* | Hugging Face Inference API token. |
| `OLLAMA_API_BASE` | `http://host.docker.internal:11434` | Base URL of a self-hosted Ollama/vLLM server. |
| `LITELLM_MASTER_KEY` | ***(required)*** | Master key the proxy requires from clients. No default. |
| `LITELLM_PORT` | `4000` | Host port mapped to the proxy's `4000`. |

---

## Related Documentation

- [Main repository README](../../README.md) — system architecture, master env-var reference, end-to-end quickstart.
- [Downloader Service README](../downloader/README.md) — produces the raw filings this service consumes.
- [Auth Service README](../auth-service/README.md) — JWT issuance and RBAC.
- [LiteLLM Proxy documentation](https://docs.litellm.ai/docs/proxy/quick_start) — upstream proxy reference.
