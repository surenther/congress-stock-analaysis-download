-- ============================================================================
-- create_user.sql — Provision / rotate users directly in PostgreSQL
-- ============================================================================
--
-- The Auth microservice intentionally exposes NO public registration endpoint
-- and NO automatic default-user seeding. Every account must be created here
-- (or via an equivalent direct ``psql`` / migration) by an administrator.
--
-- The ``users`` table is created by the service on startup:
--
--     id               UUID PRIMARY KEY DEFAULT gen_random_uuid()
--     username         VARCHAR(255) UNIQUE NOT NULL
--     hashed_password  VARCHAR(255) NOT NULL         -- bcrypt ($2b$...) hash
--     roles            JSONB NOT NULL DEFAULT '[]'::jsonb
--     is_active        BOOLEAN NOT NULL DEFAULT TRUE
--     created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
--
-- ----------------------------------------------------------------------------
-- STEP 1 — Generate a secure bcrypt hash for the new password
-- ----------------------------------------------------------------------------
--
-- NEVER store or commit a plaintext password. Generate a bcrypt hash using one
-- of the options below, then paste the resulting ``$2b$...`` string into the
-- INSERT statement in STEP 2.
--
-- Option A — Python (recommended; uses the same library the service verifies
-- with). Run this ON THE HOST / ADMIN WORKSTATION, not inside the database:
--
--     python3 -c "import bcrypt, getpass; \
--       print(bcrypt.hashpw(getpass.getpass('Password: ').encode(), \
--                           bcrypt.gensalt(rounds=12)).decode())"
--
--   The ``bcrypt`` package is already a service dependency. If it is not
--   installed: ``pip install 'bcrypt>=4.0.1,<4.1'``.
--
-- Option B — Docker (no local Python packages required):
--
--     docker run --rm -it python:3.11-slim sh -c \
--       "pip install -q 'bcrypt>=4.0.1,<4.1' && python -c \
--        'import bcrypt, getpass; \
--         print(bcrypt.hashpw(getpass.getpass(\"Password: \").encode(), \
--                             bcrypt.gensalt(rounds=12)).decode())'"
--
-- Option C — pgcrypto inside PostgreSQL (no host tooling required):
--
--     SELECT crypt('YourStrongPassword', gen_salt('bf', 12));
--
--   ``crypt``/``gen_salt`` come from the pgcrypto extension. The statement
--   below enables it if it is not already present. The service verifies this
--   ``$2a$`` hash correctly with passlib.
--
-- Security guidance:
--   * Use a unique, high-entropy password (>= 12 characters).
--   * Prefer passing secrets interactively (getpass / psql prompts) so they do
--     not end up in your shell history.
--   * Rotate a credential by updating ``hashed_password`` for that row.
--
-- ----------------------------------------------------------------------------
-- STEP 2 — Enable pgcrypto (idempotent; safe to run repeatedly)
-- ----------------------------------------------------------------------------
-- Needed for ``crypt()``/``gen_salt()`` in Option C and for ``gen_random_uuid()``
-- on PostgreSQL versions older than 13. PostgreSQL 16 includes gen_random_uuid()
-- in core, so this is harmless there.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------------------------------------------------------
-- STEP 3 — Insert the user
-- ----------------------------------------------------------------------------
--
-- Option A — literal values (replace every <PLACEHOLDER> first):
--
--   The hash below is an EXAMPLE ONLY and does not correspond to a known
--   password. Replace it with the hash you generated in STEP 1.
--
-- INSERT INTO users (id, username, hashed_password, roles, is_active, created_at)
-- VALUES (
--     gen_random_uuid(),
--     'your_username',
--     '$2b$12$YourGeneratedBcryptHashHere',
--     '["admin"]'::jsonb,
--     true,
--     NOW()
-- );

-- Option B — parameterized via psql variables (avoids editing the file and
-- keeps the plaintext password out of the SQL text). Invoke as:
--
--     psql "$DATABASE_URL" \
--          -v username="alice" \
--          -v password_hash="$(python3 -c 'import bcrypt,getpass; print(bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt(rounds=12)).decode())')" \
--          -v roles='["downloader"]' \
--          -f services/auth-service/scripts/create_user.sql
--
--   ``:username`` / ``:password_hash`` are substituted by psql. ``:roles`` is
--   interpolated as a quoted JSON string and then cast to jsonb.
INSERT INTO users (id, username, hashed_password, roles, is_active, created_at)
VALUES (
    gen_random_uuid(),
    :'username',
    :'password_hash',
    :'roles'::jsonb,
    true,
    NOW()
)
ON CONFLICT (username) DO NOTHING;

-- ----------------------------------------------------------------------------
-- STEP 4 (optional) — Generate the hash entirely in SQL and insert in one go
-- ----------------------------------------------------------------------------
-- Replace 'change-me' with a strong password. Prefer the interactive psql
-- ``\password``-style flow or STEP 1 Option A for anything sensitive.
--
-- INSERT INTO users (id, username, hashed_password, roles, is_active, created_at)
-- VALUES (
--     gen_random_uuid(),
--     'your_username',
--     crypt('change-me', gen_salt('bf', 12)),
--     '["admin"]'::jsonb,
--     true,
--     NOW()
-- )
-- ON CONFLICT (username) DO NOTHING;

-- ----------------------------------------------------------------------------
-- STEP 5 — Rotate an existing password (optional)
-- ----------------------------------------------------------------------------
--
-- UPDATE users
-- SET hashed_password = :'password_hash'
-- WHERE username = :'username';