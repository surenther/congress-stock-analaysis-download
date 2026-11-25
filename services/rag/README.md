# RAG & Query Retrieval Microservice

[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![Port](https://img.shields.io/badge/port-8516-blue.svg)](#port--endpoints)

The RAG & Query Retrieval Microservice performs **chamber-scoped hybrid search**
and **Retrieval-Augmented Generation (RAG) synthesis** over the
`disclosure_embeddings` table in `congress-db`. It enforces strict
**Chamber-Based Access Control (CBAC)**: a user granted only `House` access can
never query or retrieve `Senate` disclosures — the request is rejected with an
immediate `403 Forbidden` **before** any embedding generation or LiteLLM call.

> This service is part of the [Congressional Financial Disclosures platform](../../README.md).
> See the [main README](../../README.md) for the full multi-container architecture,
> the master environment-variable reference, and the end-to-end quickstart.

---

## Table of Contents

1. [Port & Endpoints](#port--endpoints)
2. [Architecture & Inner Workings](#architecture--inner-workings)
3. [Chamber-Based Access Control (CBAC)](#chamber-based-access-control-cbac)
4. [How to Authenticate a User for a Particular Chamber](#how-to-authenticate-a-user-for-a-particular-chamber)
5. [Hybrid SQL Query Layout](#hybrid-sql-query-layout)
6. [API Reference](#api-reference)
7. [Running the Service Standalone](#running-the-service-standalone)
8. [Testing with `curl`](#testing-with-curl)
9. [Troubleshooting](#troubleshooting)
10. [Configuration Reference](#configuration-reference)
11. [Related Documentation](#related-documentation)

---

## Port & Endpoints

The service listens on container port **8516** (changed from 8515 to avoid a
collision with the admin-service). Docker Compose maps it to the host via
`${RAG_PORT:-8516}:8516`.

| Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | — | Container health probe. |
| `POST` | `/api/v1/rag/query` | `admin` \| `user` | Full RAG: guardrails → embeddings → scoped SQL → LiteLLM synthesis. |
| `POST` | `/api/v1/rag/query/stream` | `admin` \| `user` | Same pipeline, streamed as Server-Sent Events. |
| `POST` | `/api/v1/rag/search-structured` | `admin` \| `user` | Raw structured search; **no LLM** call. |
| `POST` | `/api/v1/rag/export` | `admin` \| `user` | Export structured search results as CSV or PDF. |

Base URL (Docker Compose default): `http://localhost:8516`
Swagger UI: `http://localhost:8516/docs`

---

## Architecture & Inner Workings

```mermaid
flowchart TD
    Client["Client with JWT<br/>(allowed_chambers claim)"] -->|"POST /api/v1/rag/query"| App["RAG Service :8516<br/>FastAPI app.py"]
    App --> Auth["auth_utils<br/>verify JWT + require_role"]
    Auth --> Guard["guardrails<br/>pre-LLM CBAC check"]
    Guard -->|"chamber not allowed"| Forbidden["403 Forbidden<br/>(before any LLM call)"]
    Guard -->|"allowed"| Embed["retriever<br/>embed query via LiteLLM"]
    Embed --> LiteLLM["LiteLLM Proxy :4000"]
    Embed --> SQL["Scoped SQL<br/>chamber = ANY(allowed_chambers)"]
    SQL --> DB[("congress-db<br/>disclosure_embeddings")]
    SQL --> Synth["rag_engine<br/>synthesize answer"]
    Synth --> LiteLLM
    Synth --> Answer["Answer + sources<br/>(chamber-scoped)"]
```

### Component map

| File | Responsibility |
| :--- | :--- |
| [`app.py`](app.py:1) | FastAPI app, lifespan pool + pgvector codec, request/response models, security headers, `/health`, `/api/v1/rag/query`, `/api/v1/rag/query/stream`, `/api/v1/rag/search-structured`, `/api/v1/rag/export`, `/api/v1/rag/dashboard/analytics`. |
| [`auth_utils.py`](auth_utils.py:1) | JWT HS256 verification, `require_role`, `set_pool`, and `get_allowed_chambers` (admin override → both chambers; else the signed `allowed_chambers` claim; DB re-validated when a pool is registered). |
| [`guardrails.py`](guardrails.py:1) | Pre-LLM CBAC guardrail: rejects `filters.chamber` outside the grant and detects explicit cross-chamber intent in the prompt text. |
| [`scope_errors.py`](scope_errors.py:1) | The structured `CHAMBER_SCOPE_VIOLATION` 403 contract enforced across endpoints. |
| [`retriever.py`](retriever.py:1) | LiteLLM `/v1/embeddings` query-vector client + parameterized hybrid SQL with `chamber = ANY($1::text[])`; structured no-LLM search. |
| [`rag_engine.py`](rag_engine.py:1) | System prompt embedding `allowed_chambers`; LiteLLM `/v1/chat/completions` call forwarding `user_id` + `allowed_chambers` metadata headers; returns answer + grounded citations; `synthesize_stream` for SSE. |
| [`scripts/mint_test_token.py`](scripts/mint_test_token.py:1) | Offline dev helper to mint House-only/Senate-only tokens for verifying the 403 guardrail. |
| [`Dockerfile`](Dockerfile:1) | `python:3.11-slim`, non-root UID `10001`, exposes `8516`, healthcheck. |
| [`requirements.txt`](requirements.txt:1) | Pinned dependencies (includes `reportlab` for PDF export). |

### Data source

The service reads (never writes) the `disclosure_embeddings` table populated by
the [Vectorizer Service](../vectorizer/README.md). Relevant columns:

```text
doc_id, item_index, chamber, filer_name, filing_date, report_type,
contains_market_trades, is_market_trade, ticker, asset_name, asset_category,
action, date, value_range, ownership, comment, chunk_text, embedding vector(1536)
```

> **Embedding-model alignment:** the query embedding model and the model used to
> populate `disclosure_embeddings` are the **same** `EMBEDDING_MODEL` variable,
> shared by the vectorizer and the RAG service. This guarantees query and stored
> vectors always share a model (required for meaningful similarity). The default
> `openrouter-embed` is 1536-dimension and OpenAI-compatible.

---

## Chamber-Based Access Control (CBAC)

CBAC is enforced in **three layers**, so a bug in one layer cannot leak data:

1. **JWT claim** — the auth-service signs an `allowed_chambers` claim into the
   token. Admins are always granted both chambers; users carry their grant
   (e.g. `["House"]`).
2. **Pre-LLM guardrail** ([`guardrails.py`](guardrails.py:1)) — before any
   embedding or LLM call:
   - If `filters.chamber` is outside the user's `allowed_chambers`, reject.
   - If the prompt text explicitly requests an unauthorized chamber (e.g. a
     House-only user asks for "Senate filings" or "Senate trades"), reject.
3. **Database pre-filter** ([`retriever.py`](retriever.py:1)) — the SQL always
   includes `chamber = ANY($1::text[])` bound to the user's `allowed_chambers`,
   so even a logic bypass cannot return out-of-scope rows.

### Role behavior

| Role | `allowed_chambers` source | Guardrail |
| :--- | :--- | :--- |
| `admin` | Hardcoded override → `["House", "Senate"]` (claim ignored) | Never blocked |
| `user` | Signed `allowed_chambers` claim (defaults to both if unspecified) | Blocked with `403` if it requests an out-of-scope chamber |

### 403 error payloads

Both guardrail violations return the **same structured payload** (so an attacker
cannot probe which check tripped). The frontend keys off `code` to render an
inline access-restriction banner:

```json
{
  "detail": {
    "code": "CHAMBER_SCOPE_VIOLATION",
    "message": "Access Denied: You are not authorized to query disclosures for this chamber.",
    "requested_chamber": "Senate",
    "allowed_chambers": ["House"]
  }
}
```

HTTP status: `403 Forbidden`. The same contract is honored by the
[Web UI & Analytics Portal](../web/README.md).

---

## How to Authenticate a User for a Particular Chamber

Chamber scoping is carried by the signed `allowed_chambers` JWT claim. The
auth-service issues that claim at login; the RAG service enforces it. To
authenticate a user who may query only one chamber, provision the account with
the desired grant and then log in normally.

### 1. Provision the account with a chamber grant

Use the auth-service provisioning script (see the
[Auth Service README](../auth-service/README.md#provisioning-users-directly-in-postgresql)).
The `allowed_chambers` value is JSONB:

```bash
# House-only user
docker compose exec -T db psql \
  -U "${POSTGRES_USER:-congress}" -d "${POSTGRES_DB:-congress_db}" \
  -v username='house_user' \
  -v password_hash='<paste the generated bcrypt hash>' \
  -v roles='["user"]' \
  -v allowed_chambers='["House"]' \
  -f services/auth-service/scripts/create_user.sql
```

For a Senate-only user pass `-v allowed_chambers='["Senate"]'`. For a user who
may query both chambers pass `-v allowed_chambers='["House", "Senate"]'` (the
default).

### 2. Log in and confirm the grant

```bash
# 2FA is mandatory: complete the mfa/verify step to obtain the access token.
TOKEN=$(curl -s -X POST http://localhost:8512/api/v1/auth/mfa/verify \
  -H "Content-Type: application/json" \
  -d '{"mfa_token":"<mfa_token>","code":"123456"}' | jq -r .access_token)

# Confirm the allowed_chambers claim the RAG service will enforce
curl -s http://localhost:8512/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq '.allowed_chambers'
# ["House"]
```

### 3. Call the RAG service with the token

```bash
# In-scope chamber → 200
curl -s -X POST http://localhost:8516/api/v1/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Recent House tech trades","filters":{"chamber":"House"}}' | jq

# Out-of-scope chamber → 403 (guardrail trips before any LLM call)
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST http://localhost:8516/api/v1/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Recent Senate tech trades","filters":{"chamber":"Senate"}}'
# 403
```

### Admin accounts

`admin` accounts are **not** chamber-restricted. The RAG service overrides the
claim to `["House", "Senate"]` for admins, so an admin token can query either
chamber regardless of the stored value. Only `user` accounts are scoped by the
claim.

### Offline guardrail testing (no database account)

Operators can mint a short-lived token signed with the shared `JWT_SECRET_KEY`
instead of provisioning a database user:

```bash
TOKEN=$(JWT_SECRET_KEY="$JWT_SECRET_KEY" python scripts/mint_test_token.py \
  --username house_user --roles user --chambers House)
```

The script's flags are `--username`, `--roles`, `--chambers`, and
`--expires-minutes`. Use `--chambers House` or `--chambers Senate` to scope the
token. This is a development helper only — never expose it in production.

---

## Hybrid SQL Query Layout

The scoped search is a single parameterized statement. The chamber pre-filter is
the database-level CBAC enforcement; optional filters bind safely as positional
parameters (no string interpolation → no SQL injection).

```sql
SELECT
    doc_id, chamber, filer_name, filing_date, report_type,
    contains_market_trades, is_market_trade, ticker, asset_name,
    asset_category, action, date, value_range, ownership, comment, chunk_text,
    (1 - (embedding <=> $1::vector)) AS similarity_score
FROM disclosure_embeddings
WHERE
    chamber = ANY($2::text[])              -- HARD-SCOPED to allowed_chambers
    AND ($3::text    IS NULL OR ticker = $3)
    AND ($4::boolean IS NULL OR is_market_trade = $4)
    AND ($5::date    IS NULL OR date >= $5::date)
    AND ($6::date    IS NULL OR date <= $6::date)
ORDER BY embedding <=> $1::vector ASC
LIMIT $7;
```

| Parameter | Meaning |
| :--- | :--- |
| `$1` | Query embedding vector (`vector(1536)`). |
| `$2` | `allowed_chambers` text array — the CBAC scope. |
| `$3` | Optional `ticker` filter (`NULL` = no filter). |
| `$4` | Optional `is_market_trade` filter (`NULL` = no filter). |
| `$5` | Optional inclusive `start_date` (`NULL` = no filter). |
| `$6` | Optional inclusive `end_date` (`NULL` = no filter). |
| `$7` | `LIMIT` (top_k). |

The **structured** endpoint uses the same chamber scoping and filters but omits
the vector ordering and embedding generation, returning raw rows ordered by
`filing_date DESC`.

---

## API Reference

### `POST /api/v1/rag/query`

Auth: `admin` or `user`.

Request body:

```json
{
  "prompt": "Which House members bought tech stocks?",
  "top_k": 10,
  "model": "openrouter-deepseek-flash",
  "filters": {
    "ticker": "NVDA",
    "chamber": "House",
    "is_market_trade": true,
    "start_date": "2026-01-01",
    "end_date": "2026-12-31"
  }
}
```

| Field | Type | Required | Notes |
| :--- | :--- | :---: | :--- |
| `prompt` | string | ✅ | The user's question. |
| `top_k` | int | — | Number of contexts (default `10`). |
| `model` | string | — | LiteLLM chat model alias override. |
| `filters.ticker` | string | — | Ticker filter. |
| `filters.chamber` | string | — | `House` or `Senate`; must be within the grant. |
| `filters.is_market_trade` | bool | — | Market-trade filter. |
| `filters.start_date` | date | — | Inclusive lower bound. |
| `filters.end_date` | date | — | Inclusive upper bound. |

Response:

```json
{
  "query": "Which House members bought tech stocks?",
  "answer": "According to disclosures, Representative Laurie Buckhout purchased...",
  "user_chamber_access": ["House"],
  "sources": [
    {
      "doc_id": "10073198",
      "document_id": "10073198",
      "filer_name": "Laurie Buckhout",
      "chamber": "House",
      "filing_date": "2026-01-24",
      "ticker": "NVDA",
      "asset_name": "NVIDIA Corporation",
      "action": "Purchase",
      "date": "2026-01-15",
      "value_range": "$15,001 - $50,000",
      "similarity_score": 0.892
    }
  ],
  "cost": 0.000412,
  "usage": {
    "prompt_tokens": 1842,
    "completion_tokens": 156,
    "total_tokens": 1998
  }
}
```

Each citation carries the metadata the UI renders on a grounded source card:
filer name, filing date, chamber, value range, and document id.

### `POST /api/v1/rag/query/stream`

Auth: `admin` or `user`. Runs the same guardrails → retrieval → synthesis
pipeline but streams the answer as **Server-Sent Events**:

```text
data: {"delta": "According to "}
data: {"delta": "disclosures, "}
...
data: [DONE]
```

The same CBAC guardrails run before any embedding or LLM call, so an
out-of-scope request returns the structured `403` above.

### `POST /api/v1/rag/export`

Auth: `admin` or `user`. Runs a chamber-scoped structured search and returns the
rows as a downloadable file.

Request body:

```json
{ "format": "csv", "top_k": 200, "filters": { "chamber": "House" } }
```

`format` is `csv` (default) or `pdf`. The response is a file attachment
(`text/csv` or `application/pdf`).

`cost` is the **total** request cost in USD (query embedding + synthesis), as
reported by the LiteLLM Proxy. `usage` is the token usage from the synthesis
LLM. The `answer` is returned as clean, concise Markdown (short paragraphs and
bullet points, minimal bold emphasis).

### `POST /api/v1/rag/search-structured`

Auth: `admin` or `user`. Returns raw matching rows **without** calling the LLM.

Request body:

```json
{
  "top_k": 50,
  "filters": { "chamber": "House", "ticker": "NVDA" }
}
```

Response:

```json
{
  "user_chamber_access": ["House"],
  "count": 2,
  "results": [
    {
      "doc_id": "10073198",
      "chamber": "House",
      "filer_name": "Laurie Buckhout",
      "ticker": "NVDA",
      "date": "2026-01-15",
      "value_range": "$15,001 - $50,000",
      "chunk_text": "..."
    }
  ]
}
```

---

## Running the Service Standalone

### Docker Compose (recommended)

From the repository root:

```bash
docker compose up -d --build rag-service
docker compose logs -f congress-rag-service
```

The service depends on `db`, `auth-service`, and `litellm-proxy`.

### Local development

```bash
cd services/rag
pip install -r requirements.txt
export DATABASE_URL="postgresql://congress:...@localhost:5432/congress_db"
export JWT_SECRET_KEY="$(openssl rand -hex 32)"
export LITELLM_PROXY_URL="http://localhost:4000"
export LITELLM_MASTER_KEY="sk-..."
uvicorn app:app --host 0.0.0.0 --port 8516 --reload
```

---

## Testing with `curl`

### 1. Health check

```bash
curl -s http://localhost:8516/health
# {"status":"healthy"}
```

### 2. Obtain a token

Log in through the auth-service (see the [Auth README](../auth-service/README.md)):

```bash
# 2FA is mandatory: complete the mfa/verify step to obtain the access token.
TOKEN=$(curl -s -X POST http://localhost:8512/api/v1/auth/mfa/verify \
  -H "Content-Type: application/json" \
  -d '{"mfa_token":"<mfa_token>","code":"123456"}' | jq -r .access_token)
```

### 3. Authorized query (House-only user, House scope)

```bash
curl -s -X POST http://localhost:8516/api/v1/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "prompt": "Which House members bought tech stocks?",
        "top_k": 5,
        "filters": {"chamber": "House", "ticker": "NVDA"}
      }' | jq
```

Expected: `200 OK` with an `answer` and `sources` all in the `House` chamber.

### 4. Unauthorized cross-chamber query (House-only user, Senate scope)

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8516/api/v1/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "prompt": "Show me Senate trades",
        "filters": {"chamber": "Senate"}
      }'
# 403
```

The response body is the canonical guardrail payload:

```json
{"detail": "Access Denied: You are not authorized to query disclosures for this chamber."}
```

### 5. Unauthorized cross-chamber intent in the prompt text

Even without a `filters.chamber`, a House-only user asking for Senate data is
rejected:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8516/api/v1/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "List recent Senate filings"}'
# 403
```

### 6. Structured search (no LLM)

```bash
curl -s -X POST http://localhost:8516/api/v1/rag/search-structured \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"top_k": 10, "filters": {"chamber": "House"}}' | jq
```

### 7. Mint a test token offline (verify the guardrail)

If you do not have a House-only account provisioned, mint a short-lived token
with the shared secret (operator-only):

```bash
TOKEN=$(JWT_SECRET_KEY="$JWT_SECRET_KEY" python scripts/mint_test_token.py \
  --username house_user --roles user --chambers House)
```

Then repeat steps 3–5 with this token. See
[How to Authenticate a User for a Particular Chamber](#how-to-authenticate-a-user-for-a-particular-chamber)
for the full provisioning walkthrough.

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
| :--- | :--- | :--- |
| `401 Unauthorized` | Missing/expired/invalid JWT. | Re-login; ensure `JWT_SECRET_KEY` matches the auth-service. |
| `403 Insufficient permissions` | Token lacks `admin`/`user`. | Provision the role in the auth-service. |
| `403 Access Denied...` | CBAC guardrail tripped. | Expected for cross-chamber requests; use an in-scope chamber or an admin token. |
| `500` on `/query` | LiteLLM proxy unreachable or embedding model mismatch. | Check `LITELLM_PROXY_URL`, `LITELLM_MASTER_KEY`, and that the embedding model matches the vectorizer's. |
| Empty `sources` | No rows match the filters/scope. | Verify the vectorizer has populated `disclosure_embeddings` for that chamber. |
| `similarity_score` low/irrelevant | Query embedding model differs from the stored one. | Ensure `EMBEDDING_MODEL` matches the model used to populate `disclosure_embeddings`. |

---

## Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | — (required) | PostgreSQL DSN for `congress-db`. |
| `POSTGRES_USER` | `congress` | DB user (informational; `DATABASE_URL` is authoritative). |
| `POSTGRES_PASSWORD` | — (required) | DB password. |
| `POSTGRES_DB` | `congress_db` | DB name. |
| `JWT_SECRET_KEY` | — (required) | Shared HS256 signing secret. |
| `JWT_ISSUER` | `congress-auth` | Expected `iss` claim. |
| `JWT_AUDIENCE` | `congress-platform` | Expected `aud` claim. |
| `LITELLM_PROXY_URL` | `http://litellm-proxy:4000` | LiteLLM proxy base URL. |
| `LITELLM_MASTER_KEY` | — (required) | Proxy master key. |
| `RAG_DEFAULT_MODEL` | `openrouter-deepseek-flash` | Default chat model alias. |
| `EMBEDDING_MODEL` | `openrouter-embed` | Query embedding model — shared with the vectorizer (must match stored embeddings). |
| `RAG_REQUEST_TIMEOUT` | `120` | Per-request timeout (seconds). |
| `RAG_MAX_CONTEXT_CHARS` | `60000` | Max context characters sent to the LLM. |
| `LOG_LEVEL` | `INFO` | Log verbosity. |

> These variables are injected by `docker-compose.yml`. See the
> [master environment-variable reference](../../README.md#master-environment-variables-reference).

---

## Automated Testing

The RAG service is covered by two distinct testing suites:

1. **Contract & CBAC Guardrail Tests (`tests/test_rag.py`):**
   Exercises health, `POST /api/v1/rag/query`, `POST /api/v1/rag/search-structured`, request validation, and the **Chamber-Based Access Control (CBAC)** guardrails (a House-only user querying Senate returns `403` before any embedding/LLM call). The CBAC tests can mint tokens offline via `JWT_SECRET_KEY` in `tests/.env.test`.

   ```bash
   pytest tests/test_rag.py -v
   pytest tests/test_rag.py -k cbac -v          # CBAC guardrails only
   ```

2. **RAG Quality & Retrieval Evaluation Suite (`tests/evaluation/`):**
   A dedicated benchmark evaluation harness under [`tests/evaluation/`](../../tests/evaluation/) that measures both **retrieval chunk quality** and **synthesized response accuracy** across a **219-query gold benchmark dataset**:
   - **Retrieval Metrics:** Mean Reciprocal Rank (MRR $\ge 0.70$), Normalized Discounted Cumulative Gain (nDCG@5 $\ge 0.65$, nDCG@10 $\ge 0.60$), Hit Rate@5 ($\ge 85\%$), and Precision@5.
   - **Generation Metrics:** Faithfulness/Groundedness ($\ge 90\%$, detecting hallucinations), Factual Entity Recall ($\ge 80\%$), Token F1, Negative Refusal Accuracy ($\ge 95\%$), and CBAC Zero-Leakage ($100\%$).

   ```bash
   # Run evaluation unit tests and reference benchmark:
   pytest tests/evaluation/ -v

   # Run CLI benchmark runner (offline reference):
   python -m tests.evaluation.run_eval --output report.md

   # Run live evaluation against running container (:8516):
   python -m tests.evaluation.run_eval --live --rag-url http://localhost:8516 --token "$ADMIN_TOKEN" --limit 25
   ```

See the [test suite README](../../tests/README.md#6-rag-evaluation-suite-testsevaluation) for the full breakdown of benchmark categories and mathematical formulas.

---

## Related Documentation

- [Main repository README](../../README.md) — architecture, ports, quickstart.
- [Auth Service README](../auth-service/README.md) — JWT issuance and the `allowed_chambers` claim.
- [Vectorizer Service README](../vectorizer/README.md) — populates `disclosure_embeddings`.
- [Parser Service README](../parser/README.md) — produces the standardized JSON.
- [pgvector documentation](https://github.com/pgvector/pgvector) — vector operators and indexes.
- [LiteLLM Proxy documentation](https://docs.litellm.ai/docs/proxy/quick_start) — upstream proxy reference.
