# Auth & Authorization Microservice

[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

The **Auth & Authorization Microservice** is the centralized identity provider for
the Congressional Financial Disclosures platform. It stores users/clients,
hashes passwords with **bcrypt**, issues signed **JWT Bearer tokens**, and
provides the shared verification/RBAC primitives that the
[Downloader Service](../downloader/README.md), the
[Parser Service](../parser/README.md), the
[Vectorizer Service](../vectorizer/README.md), and the
[Admin / Observability Service](../admin-service/README.md) use to protect their
endpoints.

> This service is part of the [Congressional Financial Disclosures platform](../../README.md).
> See the [main README](../../README.md) for the full multi-container architecture,
> the master environment-variable reference, and the end-to-end quickstart.

---

## Table of Contents

1. [Architecture & Inner Workings](#architecture--inner-workings)
2. [Authentication Flow](#authentication-flow)
3. [API Reference](#api-reference)
4. [Running the Service Standalone](#running-the-service-standalone)
5. [Provisioning Users Directly in PostgreSQL](#provisioning-users-directly-in-postgresql)
6. [Testing with `curl`](#testing-with-curl)
7. [Troubleshooting](#troubleshooting)
8. [Configuration Reference](#configuration-reference)
9. [Related Documentation](#related-documentation)

---

## Architecture & Inner Workings

The service is a FastAPI application ([`app.py`](app.py:1)) backed by PostgreSQL
via `asyncpg`, with JWT/RBAC helpers in [`auth_utils.py`](auth_utils.py:1).

```text
   Client ──▶ POST /api/v1/auth/login ──▶ app.py
                                          │  _authenticate()
                                          │  (bcrypt verify against users table)
                                          ▼
                                    ┌───────────────┐
                                    │  PostgreSQL   │  users table
                                    │  (asyncpg)    │  id, username,
                                    └───────────────┘  hashed_password,
                                          ▲            roles (JSONB), is_active,
                                          │            created_at
                                          │
                                          │  create_access_token()
                                          ▼
                              { "access_token": "<JWT>", "token_type": "bearer" }
                                          │
                                          ▼
   Downstream services ──▶ verify_token() / require_role()  (auth_utils.py)
```

### Component map

| File | Responsibility |
| :--- | :--- |
| [`app.py`](app.py:1) | FastAPI app: `users` table bootstrap/migration, `login` and `me` routes, bcrypt verification. **No public registration or default-user seeding.** |
| [`scripts/create_user.sql`](scripts/create_user.sql:1) | Administrator-only SQL for provisioning users and rotating bcrypt password hashes directly in PostgreSQL. |
| [`auth_utils.py`](auth_utils.py:1) | `create_access_token()`, `verify_token()`, and the `require_role()` RBAC dependency factory. Shared with the downloader, parser, vectorizer, and admin services. |
| [`Dockerfile`](Dockerfile:1) | `python:3.11-slim` image; installs `curl` for healthchecks; runs as non-root UID `10001`; exposes `8512`. |
| [`requirements.txt`](requirements.txt:1) | `fastapi`, `uvicorn[standard]`, `pydantic`, `asyncpg`, `passlib[bcrypt]`, `bcrypt`, `PyJWT`, `python-multipart`. |

### Data model

On startup the service creates the `users` table if it does not exist:

```sql
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

> **Upgrading an existing database:** on startup the service renames a legacy
> `client_id` column to `username` and adds `created_at` if missing. Both
> migrations are idempotent. No user rows are ever inserted automatically.

### Logging

The service logs to stdout with a timestamped, leveled format, visible via
`docker compose logs -f congress-auth-service`:

```text
2026-11-20 14:05:01 | INFO    | auth | Login success: user=admin roles=['admin']
2026-11-20 14:05:09 | WARNING | auth | Login failed: rejected ref=9f2c1a7b3d4e
2026-11-20 14:05:12 | WARNING | auth | Login failed: unknown user ref=1a2b3c4d5e6f
```

Set `LOG_LEVEL=DEBUG` for more detail. Passwords are never logged, and
failed-login entries use a short, non-reversible reference instead of the
username (to avoid logging PII).

---

## Authentication Flow

The platform uses a **User credentials → JWT Bearer Token → Role/Permission
verification** flow:

1. **Credential submission** — the user POSTs `username` (or the legacy
   `client_id` alias) + `password` to `POST /api/v1/auth/login`
   (JSON or OAuth2 form body).
2. **Credential validation** — the service looks up the user by `username` and
   verifies the password with bcrypt. Unknown users, inactive users, and bad
   passwords all return the **same generic `401`** (so the endpoint cannot be
   used to discover which usernames exist). Repeated failures are rate-limited
   (`429`).
3. **JWT generation** — on success it signs a token whose payload contains
   `sub` (the `username`), `roles`, `iat`, `iss`, `aud`, and `exp` (expiry =
   `ACCESS_TOKEN_EXPIRE_MINUTES`), using `JWT_SECRET_KEY` and the fixed `HS256`
   algorithm.
4. **Token usage** — the client sends `Authorization: Bearer <JWT>` to protected
   endpoints.
5. **Verification & RBAC** — downstream services call `verify_token()` to decode
   and validate the token (signature + expiry), then `require_role([...])` to
   enforce that the token's `roles` include at least one required role. Missing
   or invalid tokens yield `401`; valid tokens without the required role yield
   `403`.

> Accounts are **not** self-service. They are provisioned out-of-band by an
> administrator using [`scripts/create_user.sql`](scripts/create_user.sql:1).

```text
credentials ──▶ [login] ──▶ bcrypt verify ──▶ sign JWT ──▶ Bearer token
                                                              │
                                                              ▼
                          [protected endpoint] ──▶ verify_token() ──▶ require_role()
                                                              │
                                         401 (invalid/expired) │ 403 (missing role)
```

---

## Roles & Authorization

The platform uses a shared **two-tier role model**. Roles are stored as a JSONB
array on the `users` row and embedded in the JWT `roles` claim, which downstream
services enforce with `require_role(...)`.

| Role | Description | Downloader `POST /trigger` | Downloader `GET /status` | Parser `POST /trigger` | Parser `GET /status` | Vectorizer `POST /trigger*` | Vectorizer `GET /status` | Admin `GET /jobs*` |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `admin` | Full access — trigger downloads, parsing, and vectorization; view status; fetch documents; read the observability API. | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `user` | Read-only — view job status and fetch parsed documents. | ❌ (`403`) | ✅ | ❌ (`403`) | ✅ | ❌ (`403`) | ✅ | ❌ (`403`) |
| *(none)* | Unauthenticated or role-less token. | ❌ (`401`/`403`) | ❌ (`401`/`403`) | ❌ (`401`/`403`) | ❌ (`401`/`403`) | ❌ (`401`/`403`) | ❌ (`401`/`403`) | ❌ (`401`/`403`) |

* **Write operations** (triggering downloads/parsing/vectorization) require `admin`.
* **Read operations** (job status, parsed documents) allow `admin` and `user`.
* The admin/observability service's `/api/v1/jobs*` routes require `admin`.
* The auth service's own `GET /api/v1/auth/me` requires only a valid token (any
  authenticated user).

> `POST /trigger*` covers both the single (`/trigger`) and bulk (`/trigger-bulk`)
> vectorizer endpoints; `GET /jobs*` covers all admin/observability endpoints.

Provision accounts with the `admin` or `user` role using
[`scripts/create_user.sql`](scripts/create_user.sql:1) — see
[Provisioning Users Directly in PostgreSQL](#provisioning-users-directly-in-postgresql).

---

## API Reference

Base URL (Docker Compose default): `http://localhost:8512`

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | — | Container healthcheck; returns `{"status": "healthy"}`. |
| `POST` | `/api/v1/auth/login` | — | Validates credentials and returns a signed JWT. Accepts JSON (`username`/legacy `client_id` + `password`) or OAuth2 form data. |
| `GET` | `/api/v1/auth/me` | Bearer JWT | Returns the current user's profile from the token. |

> **No registration endpoint.** `POST /api/v1/auth/register` has been removed.
> Accounts are provisioned out-of-band via
> [`scripts/create_user.sql`](scripts/create_user.sql:1).

### Request/response models

**`Token`** (login response): `{ "access_token": "<JWT>", "token_type": "bearer" }`

**`UserOut`** (`GET /api/v1/auth/me`): `{ "id", "username", "roles", "is_active" }`

### JWT payload

```json
{
  "sub": "your_username",
  "roles": ["admin"],
  "iat": 1763488200,
  "iss": "congress-auth",
  "aud": "congress-platform",
  "exp": 1763490000
}
```

---

## Running the Service Standalone

### Option A — Docker (recommended)

From the repository root, start the database and the auth service:

```bash
docker compose up -d --build db auth-service

# Follow the auth service logs
docker compose logs -f congress-auth-service
```

The API is then available at `http://localhost:8512` and the interactive Swagger
UI at `http://localhost:8512/docs`.

### Option B — Local Python (no Docker)

```bash
# 1. Enter the service directory
cd services/auth-service

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Point at a reachable PostgreSQL instance and set a strong JWT secret
export DATABASE_URL="postgresql://congress:YOUR_DB_PASSWORD@localhost:5432/congress_db"
export JWT_SECRET_KEY="$(openssl rand -hex 32)"   # must be >= 32 characters

# 5. Run the FastAPI microservice
uvicorn app:app --reload --port 8512
```

> The service requires a running PostgreSQL instance (the `pgvector/pgvector:pg16`
> image used by Compose works fine). Only the `users` table is created on startup;
> **no user accounts are seeded** — provision them with the SQL script described
> in [Provisioning Users Directly in PostgreSQL](#provisioning-users-directly-in-postgresql).

---

## Provisioning Users Directly in PostgreSQL

There is **no public registration endpoint** and **no default account**. An
administrator must create every user out-of-band with
[`scripts/create_user.sql`](scripts/create_user.sql:1) (or an equivalent
`psql`/migration). Roles are stored as a JSONB array; see
[Roles & Authorization](#roles--authorization) for the role model.

### 1. Generate a bcrypt hash

Run this on an admin workstation (uses the same `bcrypt` version the service
verifies with). It prompts for the password and prints a `$2b$12$...` hash:

```bash
HASH=$(python3 -c "import bcrypt, getpass; \
  print(bcrypt.hashpw(getpass.getpass('New password: ').encode(), \
                      bcrypt.gensalt(rounds=12)).decode())")
echo "$HASH"
```

Alternatively, generate it inside PostgreSQL with pgcrypto:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
SELECT crypt('YourStrongPassword', gen_salt('bf', 12));
```

### 2. Add a user (Docker — recommended)

The platform runs in Docker, so the simplest way to provision an account is to
run `psql` **inside the `db` container**. This upsert creates the account if it
does not exist and rotates the password/roles if it does:

```bash
docker compose exec -T db psql \
  -U "${POSTGRES_USER:-congress}" -d "${POSTGRES_DB:-congress_db}" \
  -v username="admin" \
  -v password_hash="$HASH" \
  -v roles='["admin"]' <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
INSERT INTO users (id, username, hashed_password, roles, is_active, created_at)
VALUES (gen_random_uuid(), :'username', :'password_hash', :'roles'::jsonb, true, NOW())
ON CONFLICT (username) DO UPDATE
   SET hashed_password = EXCLUDED.hashed_password,
       roles           = EXCLUDED.roles,
       is_active       = TRUE;
SQL
```

For a read-only account, use `-v username="readonly_user" -v roles='["user"]'`.

> `-U` / `-d` default to `congress` / `congress_db`; the shell expansions above
> pick up `POSTGRES_USER` / `POSTGRES_DB` automatically if you changed them in
> `.env`. The command reads the new password interactively (never on the shell
> history).

### 3. Update / rotate a password (Docker — recommended)

To change the password of an **existing** account without touching its roles:

```bash
docker compose exec -T db psql \
  -U "${POSTGRES_USER:-congress}" -d "${POSTGRES_DB:-congress_db}" \
  -v username="admin" \
  -v password_hash="$HASH" <<'SQL'
UPDATE users
   SET hashed_password = :'password_hash'
 WHERE username = :'username';
SQL
```

Confirm the row changed by checking for `UPDATE 1` in the output.

> **Rotating a password does not invalidate existing JWTs.** If a token may have
> leaked, also rotate `JWT_SECRET_KEY` in `.env` and restart the services so all
> previously issued tokens are rejected.

### 4. Raw SQL reference

The equivalent statements, for when you run `psql` directly (e.g. on the host or
through a migration tool) instead of via Docker.

**Insert a user** (the parameterized `psql` form keeps secrets out of the SQL
text):

```bash
psql "$DATABASE_URL" \
     -v username="alice" \
     -v password_hash="<paste the generated $2b$ hash>" \
     -v roles='["admin"]' \
     -f services/auth-service/scripts/create_user.sql
```

**Literal `INSERT`** (safe to re-run — it does nothing if the user exists):

```sql
INSERT INTO users (id, username, hashed_password, roles, is_active, created_at)
VALUES (
    gen_random_uuid(),
    'your_username',
    '$2b$12$YourGeneratedBcryptHashHere',
    '["admin"]'::jsonb,
    true,
    NOW()
)
ON CONFLICT (username) DO NOTHING;
```

**Create a read-only `user` account** (can view job status and fetch parsed
documents but cannot trigger downloads or parsing):

```sql
INSERT INTO users (id, username, hashed_password, roles, is_active, created_at)
VALUES (
    gen_random_uuid(),
    'readonly_user',
    '$2b$12$YourGeneratedBcryptHashHere',
    '["user"]'::jsonb,
    true,
    NOW()
)
ON CONFLICT (username) DO NOTHING;
```

**Rotate a password:**

```sql
UPDATE users
SET hashed_password = '$2b$12$YourNewGeneratedBcryptHashHere'
WHERE username = 'your_username';
```

> ⚠️ **Security note:** never commit plaintext passwords or real hashes to
> version control. Treat the `users` table as the source of truth and manage it
> with your normal database backup/secret-handling controls.

---

## Testing with `curl`

### 1. Health check

```bash
curl -s "http://localhost:8512/health"
```

```json
{ "status": "healthy" }
```

### 2. Log in (JSON body)

Use the credentials of a user you provisioned in
[Provisioning Users Directly in PostgreSQL](#provisioning-users-directly-in-postgresql).

```bash
curl -s -X POST "http://localhost:8512/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"username": "your_username", "password": "your_password"}'
```

Expected response:

```json
{ "access_token": "<JWT>", "token_type": "bearer" }
```

### 3. Log in (OAuth2 form body — used by the Swagger "Authorize" button)

```bash
curl -s -X POST "http://localhost:8512/api/v1/auth/login" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=your_username&password=your_password"
```

### 4. Inspect the current profile

```bash
TOKEN="<paste access_token here>"

curl -s "http://localhost:8512/api/v1/auth/me" \
     -H "Authorization: Bearer $TOKEN"
```

Expected response:

```json
{
  "id": "0b6f1c2a-9d3e-4f5a-8b7c-1e2d3f4a5b6c",
  "username": "your_username",
  "roles": ["admin"],
  "is_active": true
}
```

### Error responses

| Scenario | Status | Body |
| :--- | :--- | :--- |
| Unknown user / wrong password / inactive user | `401` | `{"detail": "Invalid credentials"}` |
| Too many failed attempts | `429` | `{"detail": "Too many login attempts. Please try again later."}` |
| Missing fields | `422` | `{"detail": "username (or client_id) and password are required"}` |
| Attempting to call the removed register route | `404` | `{"detail": "Not Found"}` |
| Invalid/expired token on `/me` | `401` | `{"detail": "Could not validate credentials"}` / `{"detail": "Token has expired"}` |

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
| :--- | :--- | :--- |
| Service exits at startup | PostgreSQL unreachable. | Verify `DATABASE_URL` and that `db` is healthy. |
| `401 Invalid credentials` | No matching user, or wrong password. | Confirm the row exists (`SELECT username FROM users;`) and that the stored hash was generated for the password you are sending. |
| No users exist after a fresh deploy | Accounts are intentionally not seeded. | Provision the first admin with [`scripts/create_user.sql`](scripts/create_user.sql:1). |
| Tokens rejected by a downstream service | `JWT_SECRET_KEY` mismatch between services. | Set the same `JWT_SECRET_KEY` for all services (Compose does this via the root `.env`). |
| `403 Insufficient permissions` downstream | Token lacks the required role. | Provision the user with `admin` (write) or `user` (read) — e.g. `'["user"]'::jsonb`. |
| `bcrypt` install errors | Incompatible `bcrypt` version. | `bcrypt` is pinned to `4.0.1` (passlib 1.7.4 is incompatible with ≥ 4.1); reinstall from `requirements.txt`. |

---

## Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | ***(required)*** | PostgreSQL DSN for the `users` table. The service refuses to start if unset. |
| `JWT_SECRET_KEY` | ***(required)*** | HMAC secret used to sign/verify JWTs. **Must be ≥ 32 characters and match the downloader/parser.** The service refuses to start with a missing, short, or placeholder value. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token lifetime in minutes. |
| `LOGIN_RATE_WINDOW_SECONDS` | `300` | Sliding window (seconds) for the login rate limiter. |
| `LOGIN_RATE_MAX_ATTEMPTS` | `10` | Max login attempts per window (per IP and per username) before `429`. |
| `LOG_LEVEL` | `INFO` | Log verbosity (`DEBUG` for verbose detail). |

> The JWT signing algorithm is **fixed to `HS256` in code** and is not
> configurable.

> These variables are injected by `docker-compose.yml` from the root `.env` file.
> See the [master environment-variable reference](../../README.md#master-environment-variables-reference).

---

## Related Documentation

- [Main repository README](../../README.md) — system architecture, master env-var reference, end-to-end quickstart.
- [Downloader Service README](../downloader/README.md) — a primary consumer of issued JWTs.
- [Parser Service README](../parser/README.md) — another consumer of issued JWTs.
- [Vectorizer Service README](../vectorizer/README.md) — another consumer of issued JWTs.
