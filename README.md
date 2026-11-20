# Congressional Financial Disclosures Platform

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791.svg)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An automated platform that **downloads**, **organizes**, and **parses** official
U.S. Congressional Financial Disclosures (STOCK Act **Periodic Transaction
Reports** and **Annual Reports**) for both the **House of Representatives** and
the **Senate**. Filings are stored **outside the containers** on a folder of your
choice, and the APIs are protected by a dedicated authentication service.

---

## Table of Contents

1. [What This Does](#what-this-does)
2. [New to Docker? Start Here](#new-to-docker-start-here)
3. [Quick Start (Copy & Paste)](#quick-start-copy--paste)
4. [What Just Happened? (Architecture)](#what-just-happened-architecture)
5. [Services & Ports](#services--ports)
6. [Roles & Authorization](#roles--authorization)
7. [Environment Variables Reference](#environment-variables-reference)
8. [Security](#security)
9. [Running Without Docker](#running-without-docker)
10. [Image Build & Manual Deployment](#image-build--manual-deployment)
11. [Troubleshooting](#troubleshooting)
12. [Public Data & Responsible Use](#public-data--responsible-use)
13. [License](#license)

---

## What This Does

- **Downloads** House and Senate financial disclosure filings (PDFs and HTML).
- **Stores** them on your own disk in a tidy folder structure.
- **Parses** them into clean, machine-readable JSON using an LLM.
- **Protects** everything behind a login (JWT + roles).

It runs as a small set of **containers** (see below) that talk to each other.

---

## New to Docker? Start Here

**Docker** runs each part of this project in its own isolated "container" — a
lightweight, self-contained box that already has everything it needs. You do
**not** install Python, PostgreSQL, or anything else on your computer; Docker
handles all of that.

You only need **two commands** to run the whole platform:

| Command | What it does |
| :--- | :--- |
| `docker compose up -d` | Starts everything in the background. |
| `docker compose down` | Stops everything. |

That's the whole idea. The rest of this guide is just filling in a few settings
and running those commands.

> **Prerequisite:** Install **Docker Desktop** from
> [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/),
> open it once, and wait until the whale icon says it is running. Verify with
> `docker compose version`.

---

## Quick Start (Copy & Paste)

Follow these steps in order. Each block is safe to copy and paste as-is.

### Step 1 — Get the code

```bash
git clone https://github.com/your-username/congress-stock-analysis.git
cd congress-stock-analysis
```

### Step 2 — Create your settings file and generate the required secrets

The platform **refuses to start** until three secrets are set (this is a security
feature — it prevents weak defaults). This one command creates `.env` and fills
in strong random values for you:

```bash
cp .env.example .env
python3 - <<'PY'
import secrets, pathlib
p = pathlib.Path(".env")
t = p.read_text()
t = t.replace("POSTGRES_PASSWORD=", f"POSTGRES_PASSWORD={secrets.token_hex(16)}", 1)
t = t.replace("JWT_SECRET_KEY=",    f"JWT_SECRET_KEY={secrets.token_hex(32)}", 1)
t = t.replace("LITELLM_MASTER_KEY=", f"LITELLM_MASTER_KEY=sk-{secrets.token_hex(24)}", 1)
p.write_text(t)
print("Done — secrets written to .env")
PY
```

> **What are these?**
> - `POSTGRES_PASSWORD` — the database password.
> - `JWT_SECRET_KEY` — the key that signs login tokens (must be ≥ 32 characters).
> - `LITELLM_MASTER_KEY` — the key the parser uses to talk to the LLM gateway.
>
> Prefer to set them by hand? Open `.env` in any text editor and fill in the three
> blank values. Generate each with `openssl rand -hex 32`.

### Step 3 — (Optional) Add an LLM key so parsing works

Downloading works without this, but **parsing** needs an LLM. Get a key from
[openrouter.ai](https://openrouter.ai/) and add it to `.env`:

```bash
# In .env:
OPENROUTER_API_KEY=sk-or-...your-key...
```

### Step 4 — Start everything

```bash
docker compose up -d --build
```

The first run takes a few minutes (it builds the images). When it finishes, check
that all containers are healthy:

```bash
docker compose ps
```

You should see `congress-db`, `congress-auth-service`, `congress-downloader-api`,
`congress-litellm-proxy`, and `congress-parser-service` running.

### Step 5 — Create your first user (an admin)

There is **no sign-up page** (by design). Create the first account directly in the
database. You will be prompted to type a password:

```bash
HASH=$(python3 -c "import bcrypt, getpass; \
  print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt(rounds=12)).decode())")

docker compose exec -T db psql -U congress -d congress_db -v username="admin" \
  -v password_hash="$HASH" -v roles='["admin"]' <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
INSERT INTO users (id, username, hashed_password, roles, is_active, created_at)
VALUES (gen_random_uuid(), :'username', :'password_hash', :'roles'::jsonb, true, NOW());
SQL
```

> If you changed `POSTGRES_USER`/`POSTGRES_DB` in `.env`, adjust `-U`/`-d` above.

### Step 6 — Log in and save your token

```bash
TOKEN=$(curl -s -X POST "http://localhost:8512/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "the-password-you-typed"}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

echo "$TOKEN"
```

### Step 7 — Download filings

```bash
curl -s -X POST "http://localhost:8511/api/v1/download/trigger" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chamber": "house", "year": "2026", "max_downloads": 10}'
```

This returns a `job_id` immediately. Check progress with:

```bash
curl -s "http://localhost:8511/api/v1/download/status/<job_id>" \
  -H "Authorization: Bearer $TOKEN"
```

Files land in `./data/house_rep/2026/...` on your computer.

### Step 8 — Parse the filings into JSON

```bash
curl -s -X POST "http://localhost:8513/api/v1/parse/trigger" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Parsed JSON is written to `./data/parsed_json/{doc_id}.json`.

### Step 9 — Stop everything

```bash
docker compose down        # stop (keeps your data)
docker compose down -v     # stop AND delete the database volume
```

### Handy links while it's running

| What | URL |
| :--- | :--- |
| Downloader API docs (Swagger) | http://localhost:8511/docs |
| Auth API docs (Swagger) | http://localhost:8512/docs |
| Parser API docs (Swagger) | http://localhost:8513/docs |
| LiteLLM Proxy | http://localhost:4000 |

---

## What Just Happened? (Architecture)

The platform is made of five cooperating containers:

```text
   You (curl / browser)
        │
        ▼
 ┌───────────────┐   ┌──────────────────┐   ┌──────────────────┐
 │ Auth Service  │   │ Downloader Svc   │   │ Parser Svc       │
 │ :8512         │   │ :8511            │   │ :8513            │
 │ login → JWT   │   │ fetch filings    │   │ LLM extraction   │
 └───────┬───────┘   └────────┬─────────┘   └────────┬─────────┘
         │  validate JWT (shared secret)              │
         ▼                    ▼                        ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ PostgreSQL 16 + pgvector  (congress-db)                       │
 │ users (auth) · jobs (downloader) · parse_jobs (parser)        │
 └──────────────────────────────────────────────────────────────┘
                              ▲
                              │  read / write filings & parsed JSON
 ┌────────────────────────────┴─────────────────────────────────┐
 │ Your folder (OUTPUT_BASE_DIR) mounted at /data                │
 └──────────────────────────────────────────────────────────────┘

 ┌──────────────────────────────────────────────────────────────┐
 │ LiteLLM Proxy :4000  →  OpenRouter / Hugging Face / Ollama    │
 └──────────────────────────────────────────────────────────────┘
```

- **Auth Service** — checks your password and hands out a signed **JWT** token.
- **Downloader Service** — fetches filings from the House/Senate portals.
- **Parser Service** — turns filings into structured JSON via an LLM.
- **LiteLLM Proxy** — a single gateway that routes to whichever LLM you use.
- **PostgreSQL** — stores users and job status.

> **Optional:** In production you usually put a reverse proxy (e.g. SWAG/Nginx) in
> front to add HTTPS. It is **not** included here; configure it separately and
> point it at `auth-service:8512`, `congress-service:8511`, and
> `parser-service:8513`.

---

## Services & Ports

| Service | Container | Port | Purpose |
| :--- | :--- | :--- | :--- |
| `db` | `congress-db` | `5432` *(internal only)* | PostgreSQL 16 + `pgvector`. |
| `auth-service` | `congress-auth-service` | `8512` | Login, JWT issuance, RBAC. |
| `congress-service` | `congress-downloader-api` | `8511` | Download API with async jobs. |
| `parser-service` | `congress-parser-service` | `8513` | Extraction API (LLM → JSON). |
| `litellm-proxy` | `congress-litellm-proxy` | `4000` | Multi-provider LLM gateway. |

> **Note:** The database is **not** published to your host — it is reachable only
> on the internal Docker network. This is intentional (see [Security](#security)).

---

## Roles & Authorization

Authentication is centralized in the [Auth Service](./services/auth-service/README.md),
which issues signed JWTs. Every protected endpoint enforces a shared **two-tier
role model** via `require_role(...)` (see
[`auth_utils.py`](./services/auth-service/auth_utils.py:1)). Roles are stored as a
JSONB array on the `users` row and embedded in the JWT `roles` claim.

| Role | Description |
| :--- | :--- |
| `admin` | Full access — trigger downloads and parsing, view status, fetch documents. |
| `user` | Read-only — view job status and fetch parsed documents. |

| Endpoint | Required role |
| :--- | :--- |
| `POST /api/v1/download/trigger` | `admin` |
| `GET /api/v1/download/status/{job_id}` | `admin` or `user` |
| `POST /api/v1/parse/trigger` | `admin` |
| `GET /api/v1/parse/status/{job_id}` | `admin` or `user` |
| `GET /api/v1/parse/document/{doc_id}` | `admin` or `user` |
| `GET /api/v1/auth/me` | any authenticated user |

* Unauthenticated requests return `401`; authenticated requests lacking the
  required role return `403`.

Accounts are provisioned out-of-band (there is no public registration endpoint)
using [`services/auth-service/scripts/create_user.sql`](./services/auth-service/scripts/create_user.sql:1).
See [Step 5](#step-5--create-your-first-user-an-admin) for an example.

---

## Environment Variables Reference

All runtime configuration is driven by environment variables. The root
[`.env.example`](.env.example) is the single template consumed by
`docker-compose.yml`; the downloader additionally reads chamber-specific files
([`.env.house.example`](services/downloader/.env.house.example) and
[`.env.senate.example`](services/downloader/.env.senate.example)).

### How variables reach the containers

1. Docker Compose automatically reads a file named **`.env`** next to
   `docker-compose.yml` (copy `.env.example` → `.env`).
2. Compose substitutes `${VAR}` / `${VAR:-default}` references in
   `docker-compose.yml` using those values.
3. The resolved values are injected into each container's environment, and the
   host storage path is bound via `${OUTPUT_BASE_DIR:-./data}:/data`.

### 1. Storage

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `OUTPUT_BASE_DIR` | `./data` (host) / `/data` (container) | `congress-service`, `parser-service` | Host folder where filings and parsed JSON are stored. The apps always read/write `/data` inside the container, which maps to this host folder. |

> **Permissions:** the containers run as a **non-root user (UID 10001)**, so the
> host folder must be writable by that UID. On Linux, run
> `sudo chown -R 10001:10001 ./data` if you see permission errors.

### 2. PostgreSQL (`pgvector/pgvector:pg16`)

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `POSTGRES_USER` | `congress` | all services | Database user name. |
| `POSTGRES_PASSWORD` | ***(required)*** | all services | Database password. **No default — Compose refuses to start until you set it.** |
| `POSTGRES_DB` | `congress_db` | all services | Database name. |
| `POSTGRES_PORT` | `5432` | `db` | Only used if you uncomment the `ports:` mapping in `docker-compose.yml` for local debugging. |
| `DATABASE_URL` | *(derived)* | `auth-service`, `congress-service`, `parser-service` | Full DSN, composed in `docker-compose.yml`. |

### 3. JWT Authentication (shared by all services)

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `JWT_SECRET_KEY` | ***(required)*** | all services | HMAC secret used to sign and verify JWTs. **Must be ≥ 32 characters and identical across all services.** No default. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | `auth-service` | Access-token lifetime in minutes. |

> The signing algorithm is **fixed to `HS256` in code** and is not configurable
> (this prevents algorithm-confusion attacks). Tokens also carry `iss`/`aud`
> claims that are validated on every request.

### 4. LLM Providers & LiteLLM Proxy (used by `parser-service`)

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `OPENROUTER_API_KEY` | *(empty)* | `litellm-proxy` | OpenRouter API key (default cloud provider). |
| `HUGGINGFACE_API_KEY` | *(empty)* | `litellm-proxy` | Hugging Face Inference API token. |
| `OLLAMA_API_BASE` | `http://host.docker.internal:11434` | `litellm-proxy` | Base URL of a self-hosted Ollama/vLLM server. |
| `LITELLM_MASTER_KEY` | ***(required)*** | `litellm-proxy`, `parser-service` | Master key the parser uses to authenticate to the proxy. No default. |
| `LITELLM_DEFAULT_MODEL` | `openrouter-deepseek-flash` | `parser-service` | Default model alias when a job does not specify one. |
| `LITELLM_PORT` | `4000` | `litellm-proxy` | Host port mapped to the proxy's `4000`. |

### 5. Service ports

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `PORT` | `8511` | `congress-service` | Host port for the downloader API. |
| `AUTH_PORT` | `8512` | `auth-service` | Host port for the auth API. |
| `PARSER_PORT` | `8513` | `parser-service` | Host port for the parser API. |
| `LITELLM_PORT` | `4000` | `litellm-proxy` | Host port for the LiteLLM Proxy. |

### 6. Downloader pipeline variables (`.env.house` / `.env.senate`)

Read by the ingestion engine, not by Compose. See the
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

### 7. Logging

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `LOG_LEVEL` | `INFO` | all services | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). View logs with `docker compose logs -f <container>`. |

### 8. Container registry

| Variable | Default | Used by | Description |
| :--- | :--- | :--- | :--- |
| `IMAGE_REGISTRY` | `docker.io/congress` | `docker-compose.yml`, Gitea build workflow | Registry host plus optional namespace used to name/pull the built images. |

---

## Security

This project was hardened following a security audit. The key protections:

- **No default secrets.** The services **refuse to start** unless
  `JWT_SECRET_KEY` (≥ 32 chars), `POSTGRES_PASSWORD`, and `LITELLM_MASTER_KEY`
  are set to strong values. There are no `change-me` fallbacks.
- **Fixed JWT algorithm.** Signing is hardcoded to `HS256`; tokens carry and
  validate `iss`/`aud`/`exp`/`sub` claims.
- **Database is not exposed.** The Postgres port is not published to the host.
- **Non-root containers.** All images run as UID **10001**.
- **Least-privilege file access.** The parser only reads files **inside** `/data`
  (absolute paths and `..` traversal are rejected).
- **SSRF protection.** The downloader only fetches URLs on the configured
  House/Senate host.
- **Login rate limiting.** Repeated failed logins are throttled (HTTP `429`).
- **No user enumeration.** Unknown, inactive, and wrong-password logins all
  return the same generic `401`.
- **Hardened XML parsing** (`defusedxml`) and **security headers** on every
  response.
- **Pinned dependencies and CI actions** for reproducible, tamper-resistant
  builds.

> **Reporting a vulnerability:** please open a private security advisory or email
> the maintainers rather than filing a public issue.

---

## Running Without Docker

You can run the ingestion engine directly with Python 3.10+:

```bash
cd services/downloader
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# House ingestion (loads .env.house)
python3 download_filings.py house
# Senate ingestion (loads .env.senate)
python3 download_filings.py senate
# Limit to 10 downloads for a quick test
MAX_DOWNLOADS=10 python3 download_filings.py house
```

For the auth service, see the
[Auth Service README](./services/auth-service/README.md#running-the-service-standalone).

---

## Image Build & Manual Deployment

Images are **built and pushed automatically** to a container registry by the
Gitea Actions workflow ([`.gitea/workflows/deploy.yml`](.gitea/workflows/deploy.yml))
on every push to `main` (or a `v*` tag). The workflow **does not deploy** —
deployment is performed **manually on the server** by pulling the images.

### Choosing a registry

Set the `IMAGE_REGISTRY` variable (registry host plus optional namespace) in two
places:

- **Gitea** (for the build workflow): Repository → Settings → Actions →
  Variables → add `IMAGE_REGISTRY` (e.g. `registry.example.com`,
  `docker.io/myuser`, or `ghcr.io/myorg`). If unset, it falls back to
  `docker.io/congress`.
- **Server `.env`** (for `docker-compose.yml`): set `IMAGE_REGISTRY` to the same
  value so Compose pulls the right images.

### What the workflow builds

| Image | Source |
| :--- | :--- |
| `${IMAGE_REGISTRY}/congress-downloader` | `services/downloader` |
| `${IMAGE_REGISTRY}/congress-auth` | `services/auth-service` |
| `${IMAGE_REGISTRY}/congress-parser` | `services/parser` |

Each image is tagged with `latest` and the short commit SHA (or the tag name).
The runner must already be authenticated to the registry.

### Server setup (one-time)

1. Create the deploy directory and enter it:
   ```bash
   mkdir -p /opt/congress-stock-analysis
   cd /opt/congress-stock-analysis
   ```
2. Create the directory layout the compose file expects:
   ```bash
   mkdir -p services/downloader services/parser
   ```
3. Create the root `.env` (from `.env.example`) and set your values — in
   particular `OUTPUT_BASE_DIR` and the three required secrets:
   ```bash
   cp .env.example .env
   nano .env
   ```
4. Create the downloader chamber env files (from the templates):
   ```bash
   cp services/downloader/.env.house.example services/downloader/.env.house
   cp services/downloader/.env.senate.example services/downloader/.env.senate
   ```
   > **Important:** inside the container, `OUTPUT_BASE_DIR` must be `/data` (the
   > mounted volume path). Do **not** change it to a host path in these files.

### Deploying an update

```bash
cd /opt/congress-stock-analysis
docker compose pull           # pull the freshly pushed registry images
docker compose up -d          # recreate containers with the new images
docker compose ps
```

If you also changed `docker-compose.yml` or the LiteLLM config, copy those first
(adjust host/path):

```bash
scp docker-compose.yml user@server:/opt/congress-stock-analysis/docker-compose.yml
scp services/parser/litellm_config.yaml \
    user@server:/opt/congress-stock-analysis/services/parser/litellm_config.yaml
```

To build locally instead of pulling, use `docker compose up -d --build`.

> **Note:** The `litellm-proxy` service uses a **pinned** public image
> (`ghcr.io/berriai/litellm:v1.110.2`) and mounts
> `services/parser/litellm_config.yaml` read-only, so updating that file and
> recreating the container (`docker compose up -d --force-recreate litellm-proxy`)
> is enough to change model routing.

### Verifying a deploy

```bash
curl -s http://localhost:8512/health   # auth
curl -s http://localhost:8511/health   # downloader
curl -s http://localhost:8513/health   # parser
curl -s http://localhost:4000/health/liveliness   # litellm proxy
docker compose logs -f congress-parser-service
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| :--- | :--- | :--- |
| `docker compose up` fails with `POSTGRES_PASSWORD must be set` (or `JWT_SECRET_KEY` / `LITELLM_MASTER_KEY`) | A required secret is missing. | Run [Step 2](#step-2--create-your-settings-file-and-generate-the-required-secrets) to fill `.env`. |
| A service exits at startup with `JWT_SECRET_KEY is unset, shorter than 32 characters...` | The JWT secret is missing or too short. | Set a ≥ 32-character `JWT_SECRET_KEY` in `.env`. |
| `permission denied` writing to `./data` | The host folder is not writable by UID 10001. | `sudo chown -R 10001:10001 ./data` (Linux). |
| `401 Invalid credentials` on login | No matching user, or wrong password. | Confirm the row exists (`SELECT username FROM users;`) and the password matches. |
| `429 Too many login attempts` | Login rate limit hit. | Wait a few minutes and try again. |
| `403 Insufficient permissions` | Token lacks the required role. | Provision the user with `admin` (write) or `user` (read). |
| Tokens rejected by the downloader/parser | `JWT_SECRET_KEY` mismatch between services. | Set the same `JWT_SECRET_KEY` for all services (Compose does this via `.env`). |
| Parser job `FAILED` with a proxy error | LiteLLM Proxy unreachable or missing provider key. | Check `docker compose logs congress-litellm-proxy`; set `OPENROUTER_API_KEY`. |
| Files not appearing on the host | Volume not mounted / wrong `OUTPUT_BASE_DIR`. | Confirm `OUTPUT_BASE_DIR` in `.env` and that the container writes to `/data`. |

---

## Public Data & Responsible Use

This tool accesses publicly accessible records provided by congressional
disclosure portals. Users are responsible for ensuring their use complies with
public record guidelines, which state that disclosure data is provided for public
transparency and news reporting, and should not be used for commercial
solicitation, credit assessments, or unauthorized purposes.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
