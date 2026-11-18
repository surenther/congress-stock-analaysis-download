# Auth & Authorization Microservice

[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

The **Auth & Authorization Microservice** is the centralized identity provider for
the Congressional Financial Disclosures platform. It stores users/clients,
hashes passwords with **bcrypt**, issues signed **JWT Bearer tokens**, and
provides the shared verification/RBAC primitives that the
[Downloader Service](../downloader/README.md) uses to protect its endpoints.

> This service is part of the [Congressional Financial Disclosures platform](../../README.md).
> See the [main README](../../README.md) for the full multi-container architecture,
> the master environment-variable reference, and the end-to-end quickstart.

---

## Table of Contents

1. [Architecture & Inner Workings](#architecture--inner-workings)
2. [Authentication Flow](#authentication-flow)
3. [API Reference](#api-reference)
4. [Running the Service Standalone](#running-the-service-standalone)
5. [Seeding Default Users & Roles](#seeding-default-users--roles)
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
                                    │  (asyncpg)    │  id, client_id,
                                    └───────────────┘  hashed_password,
                                          ▲            roles (JSONB), is_active
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
| [`app.py`](app.py:1) | FastAPI app: `users` table bootstrap, default-admin seeding, login/register/me routes, bcrypt hashing. |
| [`auth_utils.py`](auth_utils.py:1) | `create_access_token()`, `verify_token()`, and the `require_role()` RBAC dependency factory. Shared with the downloader. |
| [`Dockerfile`](Dockerfile:1) | `python:3.11-slim` image; installs `curl` for healthchecks; exposes `8512`. |
| [`requirements.txt`](requirements.txt:1) | `fastapi`, `uvicorn[standard]`, `pydantic`, `asyncpg`, `passlib[bcrypt]`, `bcrypt`, `PyJWT`, `python-multipart`. |

### Data model

On startup the service creates the `users` table if it does not exist:

```sql
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
```

---

## Authentication Flow

The platform uses a **User/Client credentials → JWT Bearer Token → Role/Permission
verification** flow:

1. **Credential submission** — the client POSTs `client_id`/`username` +
   `password` to `POST /api/v1/auth/login` (JSON or OAuth2 form body).
2. **Credential validation** — the service looks up the user by `client_id`,
   rejects missing users (`401`), inactive users (`403`), and bad passwords
   (`401`), then verifies the password with bcrypt.
3. **JWT generation** — on success it signs a token whose payload contains
   `sub` (the `client_id`), `roles`, and `exp` (expiry =
   `ACCESS_TOKEN_EXPIRE_MINUTES`), using `JWT_SECRET_KEY` / `JWT_ALGORITHM`.
4. **Token usage** — the client sends `Authorization: Bearer <JWT>` to protected
   endpoints.
5. **Verification & RBAC** — downstream services call `verify_token()` to decode
   and validate the token (signature + expiry), then `require_role([...])` to
   enforce that the token's `roles` include at least one required role. Missing
   or invalid tokens yield `401`; valid tokens without the required role yield
   `403`.

```text
credentials ──▶ [login] ──▶ bcrypt verify ──▶ sign JWT ──▶ Bearer token
                                                              │
                                                              ▼
                          [protected endpoint] ──▶ verify_token() ──▶ require_role()
                                                              │
                                         401 (invalid/expired) │ 403 (missing role)
```

---

## API Reference

Base URL (Docker Compose default): `http://localhost:8512`

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | — | Container healthcheck; returns `{"status": "healthy"}`. |
| `POST` | `/api/v1/auth/login` | — | Validates credentials and returns a signed JWT. Accepts JSON (`client_id`/`username` + `password`) or OAuth2 form data. |
| `POST` | `/api/v1/auth/register` | — | Registers a new client (bootstrap; restrict in production). Returns `201`. |
| `GET` | `/api/v1/auth/me` | Bearer JWT | Returns the current client's profile from the token. |

### Request/response models

**`UserCreate`** (`POST /api/v1/auth/register`):

| Field | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `client_id` | string | ✅ | — | Unique client identifier. |
| `password` | string | ✅ | — | Plaintext password (hashed with bcrypt before storage). |
| `roles` | string[] | ❌ | `[]` | Roles granted to the client (e.g. `["downloader"]`). |

**`Token`** (login response): `{ "access_token": "<JWT>", "token_type": "bearer" }`

**`UserOut`** (`GET /api/v1/auth/me`): `{ "id", "client_id", "roles", "is_active" }`

### JWT payload

```json
{
  "sub": "admin",
  "roles": ["admin"],
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

# 4. Point at a reachable PostgreSQL instance
export DATABASE_URL="postgresql://congress:congress_secret@localhost:5432/congress_db"
export JWT_SECRET_KEY="change-me-in-production"

# 5. Run the FastAPI microservice
uvicorn app:app --reload --port 8512
```

> The service requires a running PostgreSQL instance (the `pgvector/pgvector:pg16`
> image used by Compose works fine). The `users` table and the default admin user
> are created automatically on startup.

---

## Seeding Default Users & Roles

The service seeds a default admin user **on first startup** if it does not
already exist:

| `client_id` | `password` | `roles` |
| :--- | :--- | :--- |
| `admin` | `admin123` | `["admin"]` |

> ⚠️ **Security note:** `admin` / `admin123` is a development convenience only.
> Change or remove this account before exposing the service in production.

### Adding more users/roles

Register additional clients via the API (see below) or insert rows directly.
Roles are stored as a JSONB array; the downloader accepts the `admin` and
`downloader` roles.

```bash
curl -s -X POST "http://localhost:8512/api/v1/auth/register" \
     -H "Content-Type: application/json" \
     -d '{"client_id": "my-client", "password": "s3cret", "roles": ["downloader"]}'
```

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

```bash
curl -s -X POST "http://localhost:8512/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{"client_id": "admin", "password": "admin123"}'
```

Expected response:

```json
{ "access_token": "<JWT>", "token_type": "bearer" }
```

### 3. Log in (OAuth2 form body — used by the Swagger "Authorize" button)

```bash
curl -s -X POST "http://localhost:8512/api/v1/auth/login" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin&password=admin123"
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
  "client_id": "admin",
  "roles": ["admin"],
  "is_active": true
}
```

### 5. Register a new client

```bash
curl -s -X POST "http://localhost:8512/api/v1/auth/register" \
     -H "Content-Type: application/json" \
     -d '{"client_id": "my-client", "password": "s3cret", "roles": ["downloader"]}'
```

```json
{ "message": "User created successfully" }
```

### Error responses

| Scenario | Status | Body |
| :--- | :--- | :--- |
| Unknown user / wrong password | `401` | `{"detail": "Invalid credentials"}` |
| Inactive user | `403` | `{"detail": "User is inactive"}` |
| Missing fields | `422` | `{"detail": "client_id/username and password are required"}` |
| Duplicate `client_id` on register | `400` | `{"detail": "Client ID already exists"}` |
| Invalid/expired token on `/me` | `401` | `{"detail": "Could not validate credentials"}` / `{"detail": "Token has expired"}` |

---

## Troubleshooting

| Symptom | Likely cause | Resolution |
| :--- | :--- | :--- |
| Service exits at startup | PostgreSQL unreachable. | Verify `DATABASE_URL` and that `db` is healthy. |
| `401 Invalid credentials` for `admin` | Default user not seeded / wrong password. | Ensure the `users` table was created on startup; re-check the password. |
| Tokens rejected by the downloader | `JWT_SECRET_KEY` mismatch between services. | Set the same `JWT_SECRET_KEY` for both services (Compose does this via the root `.env`). |
| `403 Insufficient permissions` downstream | Token lacks `admin`/`downloader`. | Register the client with the required role. |
| `bcrypt` install errors | Incompatible `bcrypt` version. | The pinned range is `bcrypt>=4.0.1,<4.1`; reinstall from `requirements.txt`. |

---

## Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql://congress:congress_secret@localhost:5432/congress_db` | PostgreSQL DSN for the `users` table. |
| `JWT_SECRET_KEY` | `change-me-in-production` | HMAC secret used to sign/verify JWTs. **Must match the downloader.** |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token lifetime in minutes. |

> These variables are injected by `docker-compose.yml` from the root `.env` file.
> See the [master environment-variable reference](../../README.md#master-environment-variables-reference).

---

## Related Documentation

- [Main repository README](../../README.md) — system architecture, master env-var reference, end-to-end quickstart.
- [Downloader Service README](../downloader/README.md) — the primary consumer of issued JWTs.
