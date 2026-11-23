# Automated API Test Suite

End-to-end HTTP tests for every service in the platform: **auth-service**,
**downloader**, **parser**, **vectorizer**, **admin-service**, **rag**, and
**analytics-service**. The Next.js **web** app has its own Vitest + Playwright
suite under [`web/`](../web/README.md).

The suite talks to the real APIs over HTTP, so it validates the same contracts
the platform exposes. It runs in two modes:

| Mode | Marker filter | What it does | LLM spend |
| :--- | :--- | :--- | :--- |
| **Contract / negative** (default) | `-m "not llm and not slow"` | Auth, RBAC, validation, 404/409, security headers, response schemas | None |
| **Full integration** | `-m "llm"` | Triggers downloader/parser/vectorizer jobs, polls to completion, runs RAG end-to-end | Yes |

---

## 1. Configure credentials

Copy the template and paste your values:

```bash
cp tests/.env.test.example tests/.env.test
```

`tests/.env.test` is **git-ignored**. Fill in:

- **Base URLs** — the host-side ports of the running stack (defaults match
  `docker-compose.yml`; use the `+100` ports if you run `docker-compose.test.yml`).
- **Login credentials** — `TEST_ADMIN_*`, `TEST_USER_*`, `TEST_HOUSE_USER_*`,
  `TEST_SENATE_USER_*`. These accounts must exist in the database (see
  [Provisioning test users](#4-provisioning-test-users)).
- **TOTP secrets** — `TEST_ADMIN_TOTP_SECRET`, `TEST_USER_TOTP_SECRET`,
  `TEST_HOUSE_USER_TOTP_SECRET`, `TEST_SENATE_USER_TOTP_SECRET`. Because 2FA is
  mandatory, the harness needs each account's base32 TOTP secret to generate a
  code at login. Accounts that still require a password change or 2FA enrollment
  are skipped.
- **`JWT_SECRET_KEY`** (optional) — if set, the suite can mint tokens offline
  (mirroring [`services/rag/scripts/mint_test_token.py`](../services/rag/scripts/mint_test_token.py))
  instead of logging in. Handy for CBAC tests that need a specific
  `allowed_chambers` grant.
- **`TEST_DOC_ID`** (optional) — a known parsed doc_id for document-retrieval tests.
- **`RUN_LLM_TESTS`** — set to `true` to enable the integration suite.

Tests that need a value you have not provided are **skipped**, not failed.

---

## 2. Start the stack

Either the normal stack:

```bash
docker compose up -d
```

…or the isolated test stack (separate DB + volume, shifted ports):

```bash
POSTGRES_PASSWORD=... JWT_SECRET_KEY=... LITELLM_MASTER_KEY=... \
  docker compose -f docker-compose.test.yml up -d --build
```

---

## 3. Install test dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r tests/requirements-test.txt
```

---

## 4. Provisioning test users

The test database starts empty. Create the accounts referenced in
`tests/.env.test` using the same SQL as the main README
([Step 5](../README.md#step-5--create-your-first-user-an-admin)). For example,
to create an admin and a House-only user:

> **2FA:** the accounts you create start with `must_change_password = FALSE` and
> `totp_enabled = FALSE`. On first login the harness will be asked to enroll 2FA;
> enroll each account once (via the web UI or the `/mfa/setup` + `/mfa/enable`
> endpoints), then paste the base32 secret into the matching
> `TEST_*_TOTP_SECRET` variable.

```bash
# Admin
HASH=$(python3 -c "import bcrypt, getpass; \
  print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt(rounds=12)).decode())")
docker compose exec -T db psql -U congress -d congress_db -v username="test_admin" \
  -v password_hash="$HASH" -v roles='["admin"]' -v chambers='["House","Senate"]' <<'SQL'
INSERT INTO users (id, username, hashed_password, roles, allowed_chambers, is_active, created_at)
VALUES (gen_random_uuid(), :'username', :'password_hash', :'roles'::jsonb, :'chambers'::jsonb, true, NOW())
ON CONFLICT (username) DO UPDATE
  SET hashed_password = EXCLUDED.hashed_password,
      roles = EXCLUDED.roles,
      allowed_chambers = EXCLUDED.allowed_chambers,
      is_active = TRUE;
SQL
```

Repeat with `roles='["user"]'` and `chambers='["House"]'` (or `["Senate"]`) for
the CBAC test users. When using `docker-compose.test.yml`, replace `-d congress_db`
with `-d congress_test_db`.

---

## 5. Run the tests

```bash
# Contract / negative suite (fast, no LLM spend)
pytest tests -m "not llm and not slow"

# Full integration suite (spends LLM credits; requires RUN_LLM_TESTS=true)
pytest tests -m "llm" --maxfail=1

# Everything, including the slow rate-limit test
pytest tests
```

Useful options:

```bash
pytest tests -v                       # verbose
pytest tests/test_rag.py -v           # one module
pytest tests -k cbac                  # tests matching a keyword
pytest tests -m integration           # only integration tests
```

---

## 6. What is covered

| Module | Focus |
| :--- | :--- |
| [`test_auth_service.py`](test_auth_service.py) | health, login (valid/invalid/missing/form), `/me`, rate limiting |
| [`test_auth_2fa.py`](test_auth_2fa.py) | 2FA flow, password lifecycle, refresh/logout, admin user management |
| [`test_downloader.py`](test_downloader.py) | health, trigger auth/role/validation, status, items, lifecycle |
| [`test_parser.py`](test_parser.py) | health, bulk/single trigger, status, items, document retrieval |
| [`test_vectorizer.py`](test_vectorizer.py) | health, single/bulk trigger, status, items, embedding metadata |
| [`test_admin_service.py`](test_admin_service.py) | health, jobs list/summary/detail/items, pipeline triggers/retry, cluster health, audit log, schedules, admin-only enforcement |
| [`test_rag.py`](test_rag.py) | health, query, structured search, CBAC 403 guardrails, streaming, export, validation |
| [`test_analytics.py`](test_analytics.py) | health, scope, dashboard, top-assets, volume-trends, late-filings, committee-sector, grid, export, watchlists, CBAC |
| [`test_cross_cutting.py`](test_cross_cutting.py) | security headers, RBAC matrix (401 vs 403), 409 concurrency |

---

## 7. Notes

- **Login rate limiting:** the auth service allows 10 login attempts per IP per
  300s. The suite caches tokens per account to stay well under this. The
  `test_login_rate_limit` test deliberately exhausts the budget and is marked
  `slow` (excluded by default).
- **Concurrency:** the downloader/parser/vectorizer allow only one active job at
  a time. Integration tests that trigger jobs skip gracefully if a job is
  already running (409).
- **Idempotency:** integration tests use `limit=1` to keep runs tiny and avoid
  large downloads or LLM bills.
