#!/usr/bin/env python3
"""
Idempotent database migrations for the Auth Service.

All statements are safe to run on every startup (``IF NOT EXISTS`` /
``ADD COLUMN IF NOT EXISTS``). They extend the legacy ``users`` table with the
columns required for mandatory TOTP 2FA, password lifecycle management, account
lockout, and audit logging, and create the supporting tables:

* ``refresh_tokens`` — rotating refresh tokens for session management.
* ``email_tokens``   — single-use welcome / password-reset tokens.
* ``audit_log``      — append-only record of auth and admin lifecycle events.

The module is import-safe (no side effects) and exposes
:func:`apply_migrations`, which is called from the FastAPI lifespan.
"""

import logging

logger = logging.getLogger("auth")

# ==============================================================================
# USERS TABLE — 2FA, password lifecycle, lockout
# ==============================================================================
USERS_COLUMNS_DDL = """
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS totp_secret TEXT,
    ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS totp_verified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS recovery_codes_hash JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
"""

# A unique, case-insensitive email index (only when an email is present).
USERS_EMAIL_INDEX_DDL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower
    ON users (LOWER(email))
    WHERE email IS NOT NULL;
"""

# ==============================================================================
# REFRESH TOKENS
# ==============================================================================
REFRESH_TOKENS_DDL = """
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    user_agent TEXT,
    ip VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user
    ON refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires
    ON refresh_tokens (expires_at);
"""

# ==============================================================================
# EMAIL TOKENS (welcome + password reset)
# ==============================================================================
EMAIL_TOKENS_DDL = """
CREATE TABLE IF NOT EXISTS email_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    purpose VARCHAR(32) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_tokens_user
    ON email_tokens (user_id, purpose);
CREATE INDEX IF NOT EXISTS idx_email_tokens_expires
    ON email_tokens (expires_at);
"""

# ==============================================================================
# AUDIT LOG
# ==============================================================================
AUDIT_LOG_DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor_user_id UUID,
    actor_username VARCHAR(255),
    action VARCHAR(64) NOT NULL,
    target_type VARCHAR(64),
    target_id VARCHAR(255),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_created
    ON audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor
    ON audit_log (actor_username);
CREATE INDEX IF NOT EXISTS idx_audit_log_action
    ON audit_log (action);
"""

# Ordered list of statements applied on startup.
_MIGRATIONS = [
    ("users_columns", USERS_COLUMNS_DDL),
    ("users_email_index", USERS_EMAIL_INDEX_DDL),
    ("refresh_tokens", REFRESH_TOKENS_DDL),
    ("email_tokens", EMAIL_TOKENS_DDL),
    ("audit_log", AUDIT_LOG_DDL),
]


async def apply_migrations(conn) -> None:
    """Apply all idempotent migrations using an acquired connection."""
    for name, ddl in _MIGRATIONS:
        await conn.execute(ddl)
        logger.debug("Applied migration: %s", name)
    logger.info("Auth schema migrations applied (%d statements).", len(_MIGRATIONS))
