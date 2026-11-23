# Auth & Authorization Microservice

[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

The **Auth & Authorization Microservice** is the centralized identity provider for
the Congressional Financial Disclosures platform. It stores users, hashes
passwords with **bcrypt**, enforces **mandatory TOTP two-factor authentication**,
issues signed **JWT access tokens** plus rotating **refresh tokens**, manages the
password lifecycle (first-login change, self-service reset), and exposes
**admin-only user management**. It also provides the shared verification/RBAC
primitives that the
[Downloader Service](../downloader/README.md), the
[Parser Service](../parser/README.md), the
[Vectorizer Service](../vectorizer/README.md), the
[Admin / Observability Service](../admin-service/README.md), the
[RAG Service](../rag/README.md), and the
[Web UI & Analytics Portal](../web/README.md) use to protect their endpoints.

> This service is part of the [Congressional Financial Disclosures platform](../../README.md).
> See the [main README](../../README.md) for the full multi-container architecture,
> the master environment-variable reference, and the end-to-end quickstart.

---

## Table of Contents

1. [Architecture & Inner Workings](#architecture--inner-workings)
2. [Authentication Flow](#authentication-flow)
3. [Roles & Authorization](#roles--authorization)
4. [How to Authenticate a User for a Particular Chamber](#how-to-authenticate-a-user-for-a-particular-chamber)
5. [API Reference](#api-reference)
6. [Running the Service Standalone](#running-the-service-standalone)
7. [Provisioning Users Directly in PostgreSQL](#provisioning-users-directly-in-postgresql)
8. [Testing with `curl`](#testing-with-curl)
9. [Troubleshooting](#troubleshooting)
10. [Configuration Reference](#configuration-reference)
11. [Related Documentation](#related-documentation)

---

## Architecture & Inner Workings

The service is a FastAPI application ([`app.py`](app.py:1)) backed by PostgreSQL
via `asyncpg`, with JWT/RBAC helpers in [`auth_utils.py`](auth_utils.py:1).

```mermaid
flowchart TD
    Client["Client"] -->|"POST /api/v1/auth/login"| Auth["Auth Service :8512"]
    Auth --> DB[("PostgreSQL<br/>users table<br/>roles + allowed_chambers")]
    Auth -->|"sign JWT"| JWT["JWT<br/>sub, roles,<br/>allowed_chambers"]
    JWT --> Downstream["Downstream services<br/>verify JWT + require_role"]
    Downstream --> RAG["RAG Service :8516<br/>enforces allowed_chambers (CBAC)"]
```

### Component map

| File | Responsibility |
| :--- | :--- |
| [`app.py`](app.py:1) | FastAPI app: `users` table bootstrap, all auth routes (login, 2FA, password lifecycle, refresh/logout, `/me`), and admin user management. **No public registration or default-user seeding.** |
| [`auth_utils.py`](auth_utils.py:1) | `create_access_token()`, `create_mfa_token()`, `verify_token()`, `verify_mfa_token()`, and the `require_role()` RBAC dependency factory. Shared with the downloader, parser, vectorizer, admin, analytics, and RAG services. |
| [`migrations.py`](migrations.py:1) | Idempotent DDL for the 2FA/password-lifecycle columns and the `refresh_tokens`, `email_tokens`, and `audit_log` tables. |
| [`security.py`](security.py:1) | TOTP helpers (secret generation, Fernet encryption at rest, QR provisioning, verification), recovery codes, opaque-token hashing, and password policy. |
| [`email_utils.py`](email_utils.py:1) | SMTP delivery of welcome and password-reset emails, with a console fallback when `SMTP_HOST` is unset. |
| [`audit.py`](audit.py:1) | Append-only audit logging of auth and admin lifecycle events. |
| [`scripts/create_user.sql`](scripts/create_user.sql:1) | Administrator-only SQL for provisioning users and rotating bcrypt password hashes directly in PostgreSQL. |
| [`Dockerfile`](Dockerfile:1) | `python:3.11-slim` image; installs `curl` for healthchecks; runs as non-root UID `10001`; exposes `8512`. |
| [`requirements.txt`](requirements.txt:1) | `fastapi`, `uvicorn[standard]`, `pydantic`, `asyncpg`, `passlib[bcrypt]`, `bcrypt`, `PyJWT`, `python-multipart`, `pyotp`, `cryptography`, `qrcode[pil]`, `email-validator`. |

### Data model

On startup the service creates the `users` table if it does not exist and then
applies idempotent migrations ([`migrations.py`](migrations.py:1)) that add the
2FA / password-lifecycle columns and the supporting tables.

```sql
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    roles JSONB NOT NULL DEFAULT '[]'::jsonb,
    allowed_chambers JSONB NOT NULL DEFAULT '["House", "Senate"]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- added by migrations.py:
    email VARCHAR(255),
    totp_secret TEXT,                       -- Fernet-encrypted TOTP secret
    totp_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    totp_verified_at TIMESTAMPTZ,
    recovery_codes_hash JSONB NOT NULL DEFAULT '[]'::jsonb,
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    password_changed_at TIMESTAMPTZ,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_by VARCHAR(255),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Supporting tables created by the same migrations:

| Table | Purpose |
| :--- | :--- |
| `refresh_tokens` | Rotating refresh tokens (hashed) with expiry/revocation. |
| `email_tokens` | Single-use welcome / password-reset tokens (hashed). |
| `audit_log` | Append-only record of auth and admin lifecycle events. |

> **Upgrading an existing database:** on startup the service renames a legacy
> `client_id` column to `username`, adds `created_at` if missing, adds the
> `allowed_chambers` column (defaulting to both chambers) if missing, and applies
> the 2FA/password-lifecycle migrations. All migrations are idempotent. No user
> rows are ever inserted automatically.

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

The platform uses a **password → mandatory TOTP 2FA → JWT access token (+
rotating refresh token) → role/permission verification** flow. No access token is
issued until 2FA is satisfied.

1. **Credential submission** — the user POSTs `username` (or the legacy
   `client_id` alias) + `password` to `POST /api/v1/auth/login`
   (JSON or OAuth2 form body).
2. **Credential validation** — the service looks up the user by `username` and
   verifies the password with bcrypt. Unknown users, inactive users, and bad
   passwords all return the **same generic `401`** (so the endpoint cannot be
   used to discover which usernames exist). Repeated failures are rate-limited
   (`429`) and, after `MAX_FAILED_LOGINS` failures, the account is locked for
   `LOCKOUT_MINUTES` (`423`).
3. **Next-step decision** — on a correct password the service returns a
   short-lived `mfa_token` (signed with `JWT_SECRET_KEY`, `MFA_TOKEN_EXPIRE_MINUTES`
   lifetime) and one of:
   - `must_change_password: true` — the account must set a new password first
     (`POST /api/v1/auth/change-password`).
   - `must_setup_2fa: true` — the account must enroll TOTP
     (`POST /api/v1/auth/mfa/setup` → `/mfa/enable`).
   - `mfa_required: true` — the account must verify a TOTP code
     (`POST /api/v1/auth/mfa/verify`).
4. **Token issuance** — only after the required step succeeds does the service
   return an **access token** (JWT) and a **refresh token** (opaque, stored
   hashed in `refresh_tokens`). The access token payload contains `sub`, `roles`,
   `allowed_chambers`, `amr`, `mfa`, `session_id`, `must_change_password`, `iat`,
   `iss`, `aud`, and `exp` (`ACCESS_TOKEN_EXPIRE_MINUTES`), signed with the fixed
   `HS256` algorithm.
5. **Token usage** — the client sends `Authorization: Bearer <JWT>` to protected
   endpoints. When the access token expires, `POST /api/v1/auth/refresh` rotates
   the refresh token and issues a new pair; `POST /api/v1/auth/logout` revokes it.
6. **Verification & RBAC** — downstream services call `verify_token()` to decode
   and validate the token (signature + expiry), then `require_role([...])` to
   enforce that the token's `roles` include at least one required role. Missing
   or invalid tokens yield `401`; valid tokens without the required role yield
   `403`.

> Accounts are **not** self-service. They are provisioned by an administrator
> using [`scripts/create_user.sql`](scripts/create_user.sql:1) or the admin
> user-management API. New accounts are created with `must_change_password = TRUE`
> and must enroll TOTP on first login.

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
* The admin/observability service's `/api/v1/jobs*` routes require `admin`, as do
  its pipeline-orchestration, cluster-health, audit-log, and schedule routes.
* The auth service's own `GET /api/v1/auth/me` requires only a valid token (any
  authenticated user); the `/api/v1/admin/users*` routes require `admin`.
* The [RAG Service](../rag/README.md) and the
  [Web UI](../web/README.md) additionally enforce **Chamber-Based Access
  Control (CBAC)**: `user` accounts may only read the chambers listed in their
  `allowed_chambers` claim; `admin` accounts always have both chambers.

> `POST /trigger*` covers both the single (`/trigger`) and bulk (`/trigger-bulk`)
> vectorizer endpoints; `GET /jobs*` covers all admin/observability endpoints.

Provision accounts with the `admin` or `user` role using
[`scripts/create_user.sql`](scripts/create_user.sql:1) — see
[Provisioning Users Directly in PostgreSQL](#provisioning-users-directly-in-postgresql).

---

## How to Authenticate a User for a Particular Chamber

The auth-service is the **source of truth** for chamber scoping. It stores each
account's `allowed_chambers` grant in the `users` table and signs it into the
JWT as the `allowed_chambers` claim. The
[RAG Service](../rag/README.md) and the
[Web UI](../web/README.md) then enforce that claim on every request.

### 1. Provision the account with a chamber grant

Set `allowed_chambers` to a JSONB array when creating the user. The default is
both chambers; restrict it for a single-chamber user:

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

Use `'["Senate"]'` for a Senate-only user, or `'["House", "Senate"]'` for both.
See [Provisioning Users Directly in PostgreSQL](#provisioning-users-directly-in-postgresql)
for the full SQL and password-hash steps.

### 2. Log in and confirm the claim

```bash
# 2FA is mandatory: complete the mfa/verify step to obtain the access token.
TOKEN=$(curl -s -X POST http://localhost:8512/api/v1/auth/mfa/verify \
  -H "Content-Type: application/json" \
  -d '{"mfa_token":"<mfa_token>","code":"123456"}' | jq -r .access_token)

curl -s http://localhost:8512/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq '.allowed_chambers'
# ["House"]
```

The same value is embedded in the JWT payload, so the RAG service can enforce it
without a database round-trip (it also re-validates against the `users` table as
defense in depth).

### 3. Use the token against the RAG service

```bash
# In-scope chamber → 200
curl -s -X POST http://localhost:8516/api/v1/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Recent House tech trades","filters":{"chamber":"House"}}' | jq

# Out-of-scope chamber → 403 (CBAC guardrail)
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST http://localhost:8516/api/v1/rag/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Recent Senate tech trades","filters":{"chamber":"Senate"}}'
# 403
```

### Admin accounts bypass the restriction

`admin` accounts are **not** chamber-restricted. The RAG service overrides the
claim to `["House", "Senate"]` for admins, so an admin token can query either
chamber regardless of the stored value. Only `user` accounts are scoped by the
claim.

### Changing a user's chamber grant

Update the column and the next login will carry the new claim:

```sql
UPDATE users SET allowed_chambers = '["Senate"]'::jsonb WHERE username = 'house_user';
```

> Tokens already issued keep their original claim until they expire. To revoke
> access immediately, rotate the user's password or shorten
> `ACCESS_TOKEN_EXPIRE_MINUTES`.

---

## API Reference

Base URL (Docker Compose default): `http://localhost:8512`

### Authentication & session

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | — | Container healthcheck; returns `{"status": "healthy"}`. |
| `POST` | `/api/v1/auth/login` | — | Validates credentials and returns the next required step (`mfa_required` / `must_setup_2fa` / `must_change_password`) plus a short-lived `mfa_token`. Accepts JSON (`username`/legacy `client_id` + `password`) or OAuth2 form data. |
| `POST` | `/api/v1/auth/mfa/verify` | `mfa_token` | Verifies a TOTP (or recovery) code and issues access + refresh tokens. |
| `POST` | `/api/v1/auth/mfa/setup` | `mfa_token` | Begins TOTP enrollment; returns the `otpauth_uri`, a base64 QR PNG, and the secret. |
| `POST` | `/api/v1/auth/mfa/enable` | `mfa_token` | Confirms a TOTP code, enables 2FA, returns one-time recovery codes, and issues tokens. |
| `POST` | `/api/v1/auth/mfa/disable` | Bearer JWT | Disables 2FA (password + code required). |
| `POST` | `/api/v1/auth/change-password` | Bearer JWT or `password_change` mfa_token | Changes the password (first-login and self-service). |
| `POST` | `/api/v1/auth/forgot-password` | — | Sends a password-reset email. Always returns `202` (no user enumeration). |
| `POST` | `/api/v1/auth/reset-password` | — | Consumes a welcome/reset token and sets a new password. |
| `POST` | `/api/v1/auth/refresh` | — | Rotates a refresh token and issues a new access + refresh pair. |
| `POST` | `/api/v1/auth/logout` | — | Revokes a refresh token. |
| `GET` | `/api/v1/auth/me` | Bearer JWT | Returns the current user's profile and scope. |

### Admin — user & permission management (all require `admin`)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/admin/users` | List all user accounts. |
| `POST` | `/api/v1/admin/users` | Create a user; optionally send a welcome email. |
| `PATCH` | `/api/v1/admin/users/{id}` | Update roles, chamber scope, or active flag. |
| `POST` | `/api/v1/admin/users/{id}/reset-password` | Force a password reset by email. |
| `POST` | `/api/v1/admin/users/{id}/reset-2fa` | Clear TOTP enrollment for re-enrollment. |
| `DELETE` | `/api/v1/admin/users/{id}` | Soft-deactivate an account. |

> **No registration endpoint.** `POST /api/v1/auth/register` has been removed.
> Accounts are provisioned out-of-band via
> [`scripts/create_user.sql`](scripts/create_user.sql:1) or the admin API.

### Request/response models

**`LoginResponse`** (login): `{ "mfa_required", "must_change_password", "must_setup_2fa", "mfa_token", "access_token", "refresh_token", "token_type", "expires_in" }` — `access_token`/`refresh_token` are only present once 2FA is satisfied.

**`TokenPair`** (mfa/verify, mfa/enable, refresh): `{ "access_token", "refresh_token", "token_type", "expires_in" }`

**`UserOut`** (`GET /api/v1/auth/me`): `{ "id", "username", "email", "roles", "allowed_chambers", "is_active", "mfa_enabled", "must_change_password" }`

### JWT payload

```json
{
  "sub": "your_username",
  "roles": ["user"],
  "allowed_chambers": ["House"],
  "amr": ["pwd", "totp"],
  "mfa": true,
  "session_id": "0b6f1c2a-9d3e-4f5a-8b7c-1e2d3f4a5b6c",
  "must_change_password": false,
  "iat": 1763488200,
  "iss": "congress-auth",
  "aud": "congress-platform",
  "exp": 1763490000
}
```

> The `allowed_chambers` claim drives Chamber-Based Access Control (CBAC) in the
> [RAG Service](../rag/README.md) and the [Web UI](../web/README.md). Admins always receive both chambers regardless
> of this claim; `user` accounts are restricted to the listed chambers. If the
> claim is omitted, services default to both chambers.

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
  -v roles='["admin"]' \
  -v allowed_chambers='["House", "Senate"]' <<'SQL'
CREATE EXTENSION IF NOT EXISTS pgcrypto;
INSERT INTO users (id, username, hashed_password, roles, allowed_chambers, is_active, created_at)
VALUES (gen_random_uuid(), :'username', :'password_hash', :'roles'::jsonb,
        :'allowed_chambers'::jsonb, true, NOW())
ON CONFLICT (username) DO UPDATE
   SET hashed_password  = EXCLUDED.hashed_password,
       roles            = EXCLUDED.roles,
       allowed_chambers = EXCLUDED.allowed_chambers,
       is_active        = TRUE;
SQL
```

For a read-only account, use `-v username="readonly_user" -v roles='["user"]'`.
To restrict a user to a single chamber, pass e.g.
`-v allowed_chambers='["House"]'` or `-v allowed_chambers='["Senate"]'`.

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
     -v allowed_chambers='["House", "Senate"]' \
     -f services/auth-service/scripts/create_user.sql
```

**Literal `INSERT`** (safe to re-run — it does nothing if the user exists):

```sql
INSERT INTO users (id, username, hashed_password, roles, allowed_chambers, is_active, created_at)
VALUES (
    gen_random_uuid(),
    'your_username',
    '$2b$12$YourGeneratedBcryptHashHere',
    '["admin"]'::jsonb,
    '["House", "Senate"]'::jsonb,
    true,
    NOW()
)
ON CONFLICT (username) DO NOTHING;
```

**Create a read-only `user` account restricted to House disclosures** (can view
job status and fetch parsed documents but cannot trigger downloads or parsing,
and cannot query Senate disclosures in the RAG service):

```sql
INSERT INTO users (id, username, hashed_password, roles, allowed_chambers, is_active, created_at)
VALUES (
    gen_random_uuid(),
    'house_user',
    '$2b$12$YourGeneratedBcryptHashHere',
    '["user"]'::jsonb,
    '["House"]'::jsonb,
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

Because 2FA is mandatory, the response is a **next-step** payload, not tokens:

```json
{ "mfa_required": true, "must_change_password": false, "must_setup_2fa": false, "mfa_token": "<short-lived token>" }
```

### 3. Complete the required step

- **First login (`must_change_password: true`)** — set a new password, then
  continue to 2FA setup:
  ```bash
  curl -s -X POST "http://localhost:8512/api/v1/auth/change-password" \
       -H "Authorization: Bearer <mfa_token>" \
       -H "Content-Type: application/json" \
       -d '{"current_password":"old","new_password":"Str0ngPassword!"}'
  ```
- **2FA enrollment (`must_setup_2fa: true`)** — get the QR/secret, then confirm:
  ```bash
  curl -s -X POST "http://localhost:8512/api/v1/auth/mfa/setup" \
       -H "Content-Type: application/json" -d '{"mfa_token":"<mfa_token>"}'
  curl -s -X POST "http://localhost:8512/api/v1/auth/mfa/enable" \
       -H "Content-Type: application/json" \
       -d '{"mfa_token":"<mfa_token>","code":"123456"}'
  ```
- **2FA verification (`mfa_required: true`)** — exchange the code for tokens:
  ```bash
  curl -s -X POST "http://localhost:8512/api/v1/auth/mfa/verify" \
       -H "Content-Type: application/json" \
       -d '{"mfa_token":"<mfa_token>","code":"123456"}'
  ```

The final response is a token pair:

```json
{ "access_token": "<JWT>", "refresh_token": "<opaque>", "token_type": "bearer", "expires_in": 1800 }
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
  "email": "you@example.com",
  "roles": ["admin"],
  "allowed_chambers": ["House", "Senate"],
  "is_active": true,
  "mfa_enabled": true,
  "must_change_password": false
}
```

### Error responses

| Scenario | Status | Body |
| :--- | :--- | :--- |
| Unknown user / wrong password / inactive user | `401` | `{"detail": "Invalid credentials"}` |
| Account locked after repeated failures | `423` | `{"detail": "Account temporarily locked due to failed login attempts."}` |
| Too many failed attempts (rate limit) | `429` | `{"detail": "Too many login attempts. Please try again later."}` |
| Missing fields | `422` | `{"detail": "username (or client_id) and password are required"}` |
| Invalid/expired `mfa_token` | `401` | `{"detail": "MFA session has expired. Please sign in again."}` |
| Invalid TOTP/recovery code | `401` | `{"detail": "Invalid verification code."}` |
| Weak new password | `422` | `{"detail": "Password must be at least 12 characters."}` |
| Invalid/expired reset token | `400` | `{"detail": "Invalid or expired token."}` |
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
| `JWT_SECRET_KEY` | ***(required)*** | HMAC secret used to sign/verify JWTs. **Must be ≥ 32 characters and match every other service.** The service refuses to start with a missing, short, or placeholder value. |
| `TOTP_ENCRYPTION_KEY` | ***(required)*** | Fernet key used to encrypt TOTP secrets at rest. The service refuses to start if unset. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access-token lifetime in minutes. |
| `MFA_TOKEN_EXPIRE_MINUTES` | `5` | Lifetime of the short-lived `mfa_token` between password auth and 2FA. |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh-token lifetime in days. |
| `SESSION_ABSOLUTE_EXPIRE_DAYS` | `30` | Absolute session cap in days. |
| `MAX_FAILED_LOGINS` | `5` | Failed password attempts before the account is locked. |
| `LOCKOUT_MINUTES` | `15` | Lockout duration after `MAX_FAILED_LOGINS` failures. |
| `MIN_PASSWORD_LENGTH` | `12` | Minimum password length enforced on change/reset. |
| `RESET_TOKEN_MINUTES` | `60` | Password-reset email token lifetime. |
| `WELCOME_TOKEN_MINUTES` | `1440` | Welcome/set-password email token lifetime. |
| `TOTP_ISSUER` | `Congressional Disclosures` | Issuer name shown in authenticator apps. |
| `RECOVERY_CODE_COUNT` | `10` | Number of one-time recovery codes generated at enrollment. |
| `APP_BASE_URL` | `http://localhost:3000` | Public web-app base URL used to build email links. |
| `SMTP_HOST` | *(empty)* | SMTP server. When empty, emails are logged to the console (dev mode). |
| `SMTP_PORT` | `587` | SMTP port. |
| `SMTP_USERNAME` | *(empty)* | SMTP username. |
| `SMTP_PASSWORD` | *(empty)* | SMTP password. |
| `SMTP_USE_TLS` | `true` | Use STARTTLS. |
| `EMAIL_FROM` | `no-reply@congress.local` | From address for outgoing email. |
| `LOGIN_RATE_WINDOW_SECONDS` | `300` | Sliding window (seconds) for the login rate limiter. |
| `LOGIN_RATE_MAX_ATTEMPTS` | `10` | Max login attempts per window (per IP and per username) before `429`. |
| `LOG_LEVEL` | `INFO` | Log verbosity (`DEBUG` for verbose detail). |

> The JWT signing algorithm is **fixed to `HS256` in code** and is not
> configurable.

> These variables are injected by `docker-compose.yml` from the root `.env` file.
> See the [master environment-variable reference](../../README.md#master-environment-variables-reference).

---

## Automated Testing

The auth service is covered by
[`tests/test_auth_service.py`](../../tests/test_auth_service.py) (health, login,
`/me`, rate limiting) and
[`tests/test_auth_2fa.py`](../../tests/test_auth_2fa.py) (the 2FA flow, password
lifecycle, refresh/logout, and admin user management). Cross-cutting auth and RBAC
checks live in [`tests/test_cross_cutting.py`](../../tests/test_cross_cutting.py).

```bash
# From the repository root, with the stack running and tests/.env.test configured:
pytest tests/test_auth_service.py tests/test_auth_2fa.py -v
```

> Accounts with 2FA enabled need their base32 secret in
> `TEST_*_TOTP_SECRET` (see the [test suite README](../../tests/README.md)) so the
> harness can generate codes.

See the [test suite README](../../tests/README.md) for credential setup and the
contract vs. integration run modes.

---

## Related Documentation

- [Main repository README](../../README.md) — system architecture, master env-var reference, end-to-end quickstart.
- [Downloader Service README](../downloader/README.md) — a primary consumer of issued JWTs.
- [Parser Service README](../parser/README.md) — another consumer of issued JWTs.
- [Vectorizer Service README](../vectorizer/README.md) — another consumer of issued JWTs.
