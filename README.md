# Congressional Financial Disclosures Platform

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791.svg)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An automated, multi-container platform to download, organize, **parse**, and monitor
official U.S. Congressional Financial Disclosures (including STOCK Act **Periodic
Transaction Reports** and **Annual Reports**) for both the **House of Representatives**
and the **Senate**. Filings are stored **outside the containers** on a host volume of
your choice, and access to the ingestion and parsing APIs is protected by a dedicated
authentication microservice.

---

## Table of Contents

1. [System Overview & Architecture](#system-overview--architecture)
2. [Documentation & Microservices](#documentation--microservices)
3. [Project Structure](#project-structure)
4. [Master Environment Variables Reference](#master-environment-variables-reference)
5. [End-to-End Quickstart & Testing Guide](#end-to-end-quickstart--testing-guide)
6. [Automatic Deployment with Gitea Actions](#automatic-deployment-with-gitea-actions)
7. [One-Off Batch Execution via Docker](#one-off-batch-execution-via-docker)
8. [Running Locally (Without Docker)](#running-locally-without-docker)
9. [Public Data & Responsible Use](#public-data--responsible-use)
10. [License](#license)

---

## System Overview & Architecture

The platform is composed of six cooperating pieces:

| Component | Container | Port | Purpose |
| :--- | :--- | :--- | :--- |
| **PostgreSQL + `pgvector`** | `congress-db` | `5432` | Persistent store for the `users` table (auth), the `jobs` table (downloader), and the `parse_jobs` table (parser). `pgvector` is bundled for future embedding/vector-index work. |
| **Auth Microservice** | `congress-auth-service` | `8512` | Centralized user store, bcrypt password hashing, JWT issuance, and RBAC primitives. |
| **Downloader Service** | `congress-downloader-api` | `8511` | FastAPI ingestion API with async, PostgreSQL-backed job processing and JWT-protected endpoints. |
| **Parser Service** | `congress-parser-service` | `8513` | FastAPI extraction API that turns raw House PDF / Senate HTML filings into standardized JSON (`parsed_json/{doc_id}.json`) using an LLM reached through the LiteLLM Proxy. |
| **LiteLLM Proxy** | `congress-litellm-proxy` | `4000` | Multi-provider LLM gateway that routes extraction requests to OpenRouter, Hugging Face, or a local Ollama/vLLM backend based on the requested model alias. |
| **SWAG / Nginx reverse proxy** *(optional, external)* | — | `443` | TLS termination and hostname-based routing in front of the two APIs. **Not included in `docker-compose.yml`** — see the note below. |

> **Reverse proxy note:** The repository ships **without** a bundled reverse proxy.
> In production you typically front the services with a
> [SWAG](https://github.com/linuxserver/docker-swag) (Nginx + Let's Encrypt)
> container or any Nginx instance that terminates TLS and proxies
> `/api/v1/auth/*` → `auth-service:8512`, `/api/v1/download/*` →
> `congress-service:8511`, and `/api/v1/parse/*` → `parser-service:8513`.
> Because it is external, there are **no SWAG/Nginx environment variables** in
> this repository's `.env.example`; configure the proxy's domain/TLS settings in
> the proxy's own configuration.

### Request flow

```text
                          ┌──────────────────────────────────────────────┐
                          │            Client / Developer                │
                          │   (curl, Swagger UI, browser, CI scripts)    │
                          └───────────────────────┬──────────────────────┘
                                                  │  HTTPS
                                                  ▼
                          ┌──────────────────────────────────────────────┐
                          │   SWAG / Nginx Reverse Proxy (optional)      │
                          │   TLS termination + routing by hostname      │
                          └───┬───────────────────┬──────────────────┬───┘
                              │                   │                  │
          /api/v1/auth/*      │   /api/v1/        │   /api/v1/       │
                              │   download/*      │   parse/*        │
                              ▼                   ▼                  ▼
              ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
              │ Auth Microservice │ │ Downloader Svc    │ │ Parser Svc        │
              │ congress-auth-    │ │ congress-         │ │ congress-parser-  │
              │ service :8512     │ │ downloader-api    │ │ service :8513     │
              │ - login / JWT     │ │ :8511             │ │ - parse jobs      │
              │ - /me profile     │ │ - trigger/poll    │ │ - LLM extraction  │
              └─────────┬─────────┘ │ - House/Senate    │ │ - House/Senate    │
                        │           └─────────┬─────────┘ └─────────┬─────────┘
                        │                     │                     │
                        │   validate JWT (shared secret)            │
                        │◄────────────────────┴─────────────────────┘
                        ▼                     ▼                     ▼
              ┌──────────────────────────────────────────────────────────────┐
              │   PostgreSQL 16 + pgvector (congress-db) :5432               │
              │   - users (auth)   - jobs (downloader)   - parse_jobs (parser)│
              └──────────────────────────────────────────────────────────────┘
                                     ▲
                                     │  read / write filings & parsed JSON
              ┌──────────────────────┴───────────────────────────────────────┐
              │   Host storage volume  (OUTPUT_BASE_DIR) mounted at /data     │
              └──────────────────────────────────────────────────────────────┘

              ┌──────────────────────────────────────────────────────────────┐
              │   LiteLLM Proxy (congress-litellm-proxy) :4000               │
              │   routes by model alias → OpenRouter / Hugging Face / Ollama │
              └──────────────────────────────────────────────────────────────┘
                                     ▲
                                     │  POST /chat/completions (master key)
                                     └───────────────  parser-service
```

### Key features

- **Dual-chamber ingestion** — House bulk ZIP + XML index pipeline; Senate
  agreement-gate + DataTables search pipeline.
- **Microservice architecture** — FastAPI REST APIs with background task
  execution, PostgreSQL-backed job status, healthcheck probes, and interactive
  Swagger docs (`/docs`).
- **Centralized auth** — a dedicated auth service issues JWTs; the downloader and
  parser enforce Role-Based Access Control (`admin` / `user`).
- **LLM-powered structured extraction** — House PDFs and Senate HTML filings are
  normalized into a single JSON schema under `/data/parsed_json/` by an LLM
  reached through a dedicated LiteLLM Proxy (OpenRouter / Hugging Face / local
  Ollama), with strict trade-vs-income classification and anti-hallucination
  rules.
- **External host storage** — configurable host volume mounting
  (`OUTPUT_BASE_DIR` → `/data`) so all files reside on your external drive.
- **Smart deduplication** — ZIP archives, XML indexes, and PDFs are skipped when
  already present, enabling safe, rapid re-runs.
- **Zero hardcoded URLs** — endpoints, URL patterns, date ranges, and paths are
  fully configurable via env files.

---

## Documentation & Microservices

Detailed, service-specific documentation lives next to each service:

- **[Downloader Service Documentation](./services/downloader/README.md)** —
  architecture, House/Senate pipelines, API endpoints, standalone run/test
  instructions, `curl` examples, and troubleshooting.
- **[Auth Service Documentation](./services/auth-service/README.md)** —
  authentication flow, endpoints, direct SQL user provisioning, standalone
  run/test instructions, and `curl` examples.
- **[Parser Service Documentation](./services/parser/README.md)** —
  the LiteLLM Proxy architecture, model provider selection, the extraction
  schema rules, API endpoints, and authenticated `curl` examples.

---

## Project Structure

This repository is organized as a multi-service monorepo. Each service lives in
its own directory under `services/` with its own `Dockerfile`, dependencies, and
configuration:

```text
.
├── .gitea/workflows/          # Gitea Actions CI/CD workflows
├── docker-compose.yml         # Orchestrates db, auth-service, downloader, and parser
├── .env.example               # Template for DB / JWT / storage configuration
├── services/
│   ├── auth-service/          # Centralized Authentication & Authorization (port 8512)
│   │   ├── app.py             # Login, JWT issuance (no public signup)
│   │   ├── scripts/           # Admin SQL for user provisioning
│   │   │   └── create_user.sql # create users / rotate bcrypt passwords
│   │   ├── auth_utils.py      # JWT verification + RBAC dependencies
│   │   ├── README.md          # ← Auth service documentation
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── downloader/            # Congressional filings downloader + FastAPI microservice
│   │   ├── app.py             # FastAPI microservice (port 8511) + async jobs
│   │   ├── auth_utils.py      # JWT verification + RBAC dependencies
│   │   ├── download_filings.py# House/Senate ingestion pipeline
│   │   ├── README.md          # ← Downloader service documentation
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── .env.house.example / .env.senate.example
│   ├── parser/                # Document extraction FastAPI microservice (port 8513)
│   │   ├── app.py             # FastAPI microservice (port 8513) + async parse jobs
│   │   ├── extraction_engine.py # Text extraction + LiteLLM Proxy client + system prompt
│   │   ├── litellm_config.yaml  # LiteLLM Proxy routing (OpenRouter/HF/Ollama)
│   │   ├── auth_utils.py      # JWT verification + RBAC dependencies
│   │   ├── README.md          # ← Parser service documentation
│   │   ├── Dockerfile
│   │   └── requirements.txt
└── README.md
```

### Services

| Service | Container | Port | Purpose |
| :--- | :--- | :--- | :--- |
| `db` | `congress-db` | `5432` | PostgreSQL 16 with `pgvector` (persistent `pgdata` volume). |
| `auth-service` | `congress-auth-service` | `8512` | Centralized user store, bcrypt password hashing, JWT issuance. |
| `congress-service` | `congress-downloader-api` | `8511` | Downloader API with async job processing and JWT-protected endpoints. |
| `parser-service` | `congress-parser-service` | `8513` | Document extraction API that produces standardized JSON from raw filings via an LLM. |
| `litellm-proxy` | `congress-litellm-proxy` | `4000` | Multi-provider LLM gateway (OpenRouter / Hugging Face / local Ollama). |
| `house-job` / `senate-job` | one-off | — | CLI batch jobs (profile `cli`). |

---

## Roles & Authorization

Authentication is centralized in the [Auth Service](./services/auth-service/README.md),
which issues signed JWTs. Every protected endpoint across the platform enforces a
shared **two-tier role model** via `require_role(...)` (see
[`auth_utils.py`](./services/auth-service/auth_utils.py:1)). Roles are stored as a
JSONB array on the `users` row and embedded in the JWT `roles` claim.

| Role | Description |
| :--- | :--- |
| `admin` | Full access — trigger downloads and parsing, view job status, fetch parsed documents. |
| `user` | Read-only — view job status and fetch parsed documents. |

| Endpoint | Required role |
| :--- | :--- |
| `POST /api/v1/download/trigger` | `admin` |
| `GET /api/v1/download/status/{job_id}` | `admin` or `user` |
| `POST /api/v1/parse/trigger` | `admin` |
| `GET /api/v1/parse/status/{job_id}` | `admin` or `user` |
| `GET /api/v1/parse/document/{doc_id}` | `admin` or `user` |
| `GET /api/v1/auth/me` | any authenticated user |

* **Write operations** (triggering downloads/parsing) require `admin`.
* **Read operations** (job status, parsed documents) allow `admin` and `user`.
* Unauthenticated requests return `401`; authenticated requests lacking the
  required role return `403`.

Accounts are provisioned out-of-band (there is no public registration endpoint)
using [`services/auth-service/scripts/create_user.sql`](./services/auth-service/scripts/create_user.sql:1).
See [Step 3a](#3a-create-a-user-then-authenticate-to-fetch-a-bearer-jwt) for
`admin` and `user` creation examples.

---

## Master Environment Variables Reference

All runtime configuration is driven by environment variables. The root
[`.env.example`](.env.example) is the single template consumed by
`docker-compose.yml`; the downloader additionally reads chamber-specific files
([`.env.house.example`](services/downloader/.env.house.example) and
[`.env.senate.example`](services/downloader/.env.senate.example)).

### How variables propagate to `docker-compose.yml`

1. Docker Compose automatically reads a file named **`.env`** located next to
   `docker-compose.yml` (copy `.env.example` → `.env`).
2. Compose substitutes `${VAR}` / `${VAR:-default}` references in
   `docker-compose.yml` using those values.
3. The resolved values are injected into each container's environment via the
   `environment:` blocks, and the host storage path is bound via the `volumes:`
   mapping `${OUTPUT_BASE_DIR:-./data}:/data`.
4. Inside the downloader container, the chamber env files are mounted from the
   host (`./services/downloader/.env.house` → `/app/.env.house`, and likewise for
   `.env.senate`), so edits are picked up on the next container creation.

```text
.env  ──▶  docker-compose.yml (${VAR} substitution)  ──▶  container environment
                                                       └─▶  volume mounts (/data, .env.house, .env.senate)
```

### 1. Storage

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `OUTPUT_BASE_DIR` | `./data` (host) / `/data` (container) | `congress-service`, `parser-service`, `house-job`, `senate-job` | Host folder where filings and parsed JSON are stored. The apps always read/write `/data` inside the container, which maps to this host folder. |

> **Security note:** This directory contains only public disclosure records, but
> ensure the host path has appropriate filesystem permissions and is excluded
> from version control (see [`.gitignore`](.gitignore)).

### 2. PostgreSQL (`pgvector/pgvector:pg16`)

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `POSTGRES_USER` | `congress` | `db`, `auth-service`, `congress-service`, `parser-service` | Database superuser name. |
| `POSTGRES_PASSWORD` | `congress_secret` | `db`, `auth-service`, `congress-service`, `parser-service` | Database password. |
| `POSTGRES_DB` | `congress_db` | `db`, `auth-service`, `congress-service`, `parser-service` | Database name. |
| `POSTGRES_PORT` | `5432` | `db` | Host port mapped to the container's `5432`. Change if `5432` is already in use. |
| `DATABASE_URL` | *(derived)* | `auth-service`, `congress-service`, `parser-service` | Full DSN, composed in `docker-compose.yml` as `postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`. |

> **Security note:** Change `POSTGRES_PASSWORD` from the default before any
> non-local deployment. The database is only reachable on the internal Compose
> network unless you publish `POSTGRES_PORT`.

### 3. JWT Authentication (shared by `auth-service`, `congress-service`, and `parser-service`)

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `JWT_SECRET_KEY` | `change-me-in-production` | `auth-service`, `congress-service`, `parser-service` | HMAC secret used to sign and verify JWTs. **Must be identical across all services.** |
| `JWT_ALGORITHM` | `HS256` | `auth-service`, `congress-service`, `parser-service` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | `auth-service` | Access-token lifetime in minutes. |

> **Security note:** `JWT_SECRET_KEY` is the single most sensitive value in the
> system — anyone who knows it can forge tokens. Generate a long random value
> (e.g. `openssl rand -hex 32`) and never commit the real `.env` to version
> control. `ACCESS_TOKEN_EXPIRE_MINUTES` is only read by the auth service when
> minting tokens; the downloader and parser validate expiry from the token itself.

### 4. LLM Providers & LiteLLM Proxy (used by `parser-service`)

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | *(empty)* | `litellm-proxy` | OpenRouter API key (default cloud provider — cheap DeepSeek Flash; Gemini 3.8 Flash selectable per job). |
| `HUGGINGFACE_API_KEY` | *(empty)* | `litellm-proxy` | Hugging Face Inference API token (open-weights hosted models). |
| `OLLAMA_API_BASE` | `http://host.docker.internal:11434` | `litellm-proxy` | Base URL of a self-hosted Ollama/vLLM server for local GPU models. |
| `LITELLM_MASTER_KEY` | `sk-change-me` | `litellm-proxy`, `parser-service` | Master key the parser uses to authenticate to the proxy. |
| `LITELLM_DEFAULT_MODEL` | `openrouter-deepseek-flash` | `parser-service` | Default model alias when a job does not specify one (cheap DeepSeek Flash). |
| `LITELLM_PORT` | `4000` | `litellm-proxy` | Host port mapped to the proxy's `4000`. |

> **Security note:** `OPENROUTER_API_KEY`, `HUGGINGFACE_API_KEY`, and
> `LITELLM_MASTER_KEY` are secrets. Never commit the resolved `.env` to version
> control. The proxy is only reachable on the internal Compose network unless you
> publish `LITELLM_PORT`.

### 5. Service ports

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `PORT` | `8511` | `congress-service` | Host port mapped to the downloader API's `8511`. |
| `AUTH_PORT` | `8512` | `auth-service` | Host port mapped to the auth API's `8512`. |
| `PARSER_PORT` | `8513` | `parser-service` | Host port mapped to the parser API's `8513`. |
| `LITELLM_PORT` | `4000` | `litellm-proxy` | Host port mapped to the LiteLLM Proxy's `4000`. |

### 6. Downloader pipeline variables (`.env.house` / `.env.senate`)

These are read by the ingestion engine, not by Compose. See the
[Downloader Service README](./services/downloader/README.md#configuration-reference)
for the full table. Summary:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `CHAMBER` | `House of Representatives` / `Senate` | Chamber name used in logs. |
| `YEAR` | `2026` | Filing year to target. |
| `OUTPUT_DIR` | `house_rep` / `senate` | Destination subfolder for this chamber. |
| `BASE_URL` | — | Portal base URL. |
| `PORTAL_URL` | — | Human-facing portal URL. |
| `AGREEMENT_URL` | — | *(Senate)* Statutory agreement gate URL. |
| `SEARCH_URL` | `{base_url}/search/` | *(Senate)* Search page URL. |
| `SEARCH_DATA_URL` | — | *(Senate)* DataTables JSON endpoint. |
| `AUTO_ACCEPT_AGREEMENT` | `false` | *(Senate)* Auto-submit the prohibitions checkbox. |
| `SENATE_REPORT_TYPES` | `annual,periodic` | *(Senate)* Report types to query. |
| `START_DATE` | `01/01/{year}` | *(Senate)* Date-filed range start. |
| `END_DATE` | `TODAY` | *(Senate)* Date-filed range end. |
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

### 7. Reverse proxy (SWAG / Nginx) — external

There are **no** reverse-proxy variables in this repository. Domain names, TLS
certificates, and routing rules are configured inside your external SWAG/Nginx
container. Point it at `auth-service:8512` and `congress-service:8511` on the
shared Docker network.

---

## End-to-End Quickstart & Testing Guide

### Prerequisites

- Docker Engine with the Compose plugin (`docker compose version`).
- `curl` (for the integration test).

### Step 1 — Clone and configure

```bash
git clone https://github.com/your-username/congress-stock-analysis.git
cd congress-stock-analysis

# Create the Compose env file from the template
cp .env.example .env

# (Optional) choose where filings are stored on the host
#   OUTPUT_BASE_DIR=./data                            -> ./data next to the compose file
#   OUTPUT_BASE_DIR=/home/surenther/unraid/stock-ai   -> that host folder
```

> **Important:** Inside the container `OUTPUT_BASE_DIR` must be `/data` (the
> mounted volume path). The root `.env` value only controls the **host** side of
> the bind mount.

### Step 2 — Spin up the whole stack

```bash
docker compose up -d --build
```

This starts `db`, `auth-service`, `congress-service`, `litellm-proxy`, and
`parser-service`. Verify:

```bash
docker compose ps
curl -s http://localhost:8512/health   # {"status":"healthy"}
curl -s http://localhost:8511/health   # {"status":"healthy", ...}
curl -s http://localhost:8513/health   # {"status":"healthy", ...}
curl -s http://localhost:4000/health/liveliness   # LiteLLM Proxy
```

Interactive API docs:

- Downloader Swagger UI → **`http://localhost:8511/docs`**
- Auth Swagger UI → **`http://localhost:8512/docs`**
- Parser Swagger UI → **`http://localhost:8513/docs`**
- LiteLLM Proxy → **`http://localhost:4000`** (OpenAI-compatible API)

### Step 3 — Integration test flow

#### 3a. Create a user, then authenticate to fetch a Bearer JWT

The Auth service does **not** expose a registration endpoint and does **not**
seed a default account. Provision your first user directly in PostgreSQL, then
log in with those credentials.

```bash
# Generate a bcrypt hash (you will be prompted for the password)
HASH=$(python3 -c "import bcrypt, getpass; \
  print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt(rounds=12)).decode())")

# Insert an ADMIN user (can trigger downloads and parsing).
# See services/auth-service/scripts/create_user.sql for the full documented flow.
# Adjust -U/-d if you changed POSTGRES_USER/DB.
docker compose exec -T db psql -U congress -d congress_db -v username="admin" \
  -v password_hash="$HASH" -v roles='["admin"]' <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
INSERT INTO users (id, username, hashed_password, roles, is_active, created_at)
VALUES (gen_random_uuid(), :'username', :'password_hash', :'roles'::jsonb, true, NOW());
SQL
```

To create a **read-only `user`** (can view job status and fetch parsed documents
but cannot trigger downloads/parsing), run the same command with a different
username and the `user` role:

```bash
docker compose exec -T db psql -U congress -d congress_db -v username="readonly_user" \
  -v password_hash="$HASH" -v roles='["user"]' <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
INSERT INTO users (id, username, hashed_password, roles, is_active, created_at)
VALUES (gen_random_uuid(), :'username', :'password_hash', :'roles'::jsonb, true, NOW());
SQL
```

Log in with the provisioned credentials, then capture the token:

```bash
curl -s -X POST "http://localhost:8512/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "your_password"}'

TOKEN=$(curl -s -X POST "http://localhost:8512/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "your_password"}' \
     | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
```

#### 3b. Pass the Bearer token to trigger a background download job

```bash
curl -s -X POST "http://localhost:8511/api/v1/download/trigger" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"chamber": "house", "year": "2026", "max_downloads": 0}'
```

Returns `202 Accepted` immediately:

```json
{ "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f", "status": "PENDING" }
```

#### 3c. Poll the job status using the returned `job_id`

```bash
JOB_ID="3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f"

curl -s "http://localhost:8511/api/v1/download/status/$JOB_ID" \
     -H "Authorization: Bearer $TOKEN"
```

The status transitions `PENDING` → `IN_PROGRESS` → `COMPLETED` (or `FAILED`
with an `error_message`):

```json
{
  "job_id": "3f1c9b2e-1a4d-4c8e-9f21-7b6a5d4c3e2f",
  "status": "COMPLETED",
  "created_at": "2026-11-18T19:57:14.925000+00:00",
  "updated_at": "2026-11-18T19:58:41.552000+00:00",
  "error_message": null
}
```

Downloaded filings appear under `OUTPUT_BASE_DIR` on the host, e.g.
`./data/house_rep/2026/01_January/Pelosi_Nancy/20026123.pdf`.

#### 3d. Parse the downloaded filings into standardized JSON

With the raw filings on disk, trigger the parser service (using the same Bearer
token). A minimal body runs **bulk mode** and processes every document on the
volume for both chambers:

```bash
curl -s -X POST "http://localhost:8513/api/v1/parse/trigger" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{}'
```

To extract a single filing instead, pass `file_path` (and optionally `doc_id` /
`chamber`):

```bash
curl -s -X POST "http://localhost:8513/api/v1/parse/trigger" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
           "doc_id": "20026123",
           "chamber": "House",
           "file_path": "house_rep/2026/01_January/Pelosi_Nancy/20026123.pdf",
           "model": "openrouter-deepseek-flash"
         }'
```

Returns `202 Accepted` with a `job_id`. Poll it and/or fetch a parsed document:

```bash
curl -s "http://localhost:8513/api/v1/parse/status/<job_id>" \
     -H "Authorization: Bearer $TOKEN"

curl -s "http://localhost:8513/api/v1/parse/document/20026123" \
     -H "Authorization: Bearer $TOKEN"
```

Standardized JSON is written to `./data/parsed_json/{doc_id}.json` on the host.

### Step 4 — Tear down

```bash
docker compose down          # stop and remove containers (keeps the pgdata volume)
docker compose down -v       # also remove the database volume
```

---

## Automatic Deployment with Gitea Actions

This repository includes a [Gitea Actions](https://docs.gitea.com/usage/actions/overview)
workflow ([`.gitea/workflows/deploy.yml`](.gitea/workflows/deploy.yml)) that
automatically builds and deploys the Docker services to your server whenever you
push to the `main` branch (or a `v*` tag).

### Prerequisites

- A Gitea Actions runner registered on the server with the label `ubuntu-latest`.
- Docker and the Docker Compose plugin installed on the server.
- The runner user must have permission to run `docker` commands (add it to the `docker` group).

### How it works

1. You commit and push to `main` (or create a `v*` tag).
2. The runner checks out the code.
3. The workflow builds **all three** service images and pushes them to the
   container registry, each tagged with `latest` and the short commit SHA (or the
   tag name):
   - `registry.surenther.xyz/congress-downloader` (from `services/downloader`)
   - `registry.surenther.xyz/congress-auth` (from `services/auth-service`)
   - `registry.surenther.xyz/congress-parser` (from `services/parser`)
4. The workflow SSHes into the server, deploys `docker-compose.yml` and the
   LiteLLM Proxy config (`services/parser/litellm_config.yaml`), creates sample
   `.env.house` / `.env.senate` / `.env` files if they don't exist yet, then runs
   `docker compose pull && docker compose up -d`.
5. The `congress-service`, `auth-service`, `parser-service`, and
   `litellm-proxy` containers are recreated with the new images/config.

> **Note:** All images must be pushed to the registry because the deploy server
> has no source checkout and therefore cannot `docker compose build`. If an image
> is missing from the registry, `docker compose pull` fails with
> `manifest ... not found`.

### Server setup (one-time)

The server only needs an empty deploy directory — **no repo clone required**.

1. Create the deploy directory (this is what you set as `DEPLOY_PATH`):
   ```bash
   mkdir -p /home/surenther/unraid/stock-ai
   ```
2. After the first deploy, edit the sample env files with your real
   configuration (they are created by the workflow if missing, and your edits are
   preserved on later deploys):
   ```bash
   nano /home/surenther/unraid/stock-ai/services/downloader/.env.house
   nano /home/surenther/unraid/stock-ai/services/downloader/.env.senate
   ```
   > **Important**: Inside the container, `OUTPUT_BASE_DIR` must be `/data` (the
   > mounted volume path). Do **not** change it to a host path in these files.
3. Edit the root `.env` to choose where filings are stored on the host:
   ```bash
   nano /home/surenther/unraid/stock-ai/.env
   ```
   ```bash
   OUTPUT_BASE_DIR=/home/surenther/unraid/stock-ai
   ```

### Required secrets

Add these secrets in **Gitea → Repository → Settings → Actions → Secrets**:

| Secret | Description |
| :--- | :--- |
| `DEPLOY_HOST` | Server hostname or IP |
| `DEPLOY_USER` | SSH user on the server |
| `DEPLOY_SSH_KEY` | SSH private key (newlines preserved) |
| `DEPLOY_PORT` | SSH port (defaults to `22` if unset) |
| `DEPLOY_PATH` | Absolute path to the compose directory on the server (e.g. `/opt/congress-filings`) |

### Manual trigger

You can also run the deployment manually from the Gitea **Actions** tab using the
**Run workflow** button.

---

## One-Off Batch Execution via Docker

If you prefer running standalone one-shot containers without keeping the web
server running:

```bash
# Download House filings
docker compose run --rm house-job

# Download Senate filings
docker compose run --rm senate-job
```

---

## Running Locally (Without Docker)

You can run the ingestion engine directly on your machine using Python 3.10+:

```bash
# 1. Navigate to the downloader service
cd services/downloader

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run House ingestion (e.g. download all or set a test limit)
python3 download_filings.py house
# Or limit downloads: MAX_DOWNLOADS=10 python3 download_filings.py house

# 5. Run Senate ingestion (e.g. download all or set a test limit)
python3 download_filings.py senate
# Or limit downloads: MAX_DOWNLOADS=10 python3 download_filings.py senate

# 6. (Optional) Run the local FastAPI microservice
uvicorn app:app --reload --port 8511
```

For the auth service, see the
[Auth Service README](./services/auth-service/README.md#running-the-service-standalone).

---

## Public Data & Responsible Use

This tool accesses publicly accessible records provided by congressional
disclosure portals. Users are responsible for ensuring their use complies with
public record guidelines, which state that disclosure data is provided for public
transparency and news reporting, and should not be used for commercial
solicitation, credit assessments, or unauthorized purposes.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
