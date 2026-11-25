#!/usr/bin/env python3
"""
Centralized Authentication & Authorization Microservice.

Provides bcrypt credential verification, mandatory TOTP two-factor
authentication, JWT access-token issuance, rotating refresh tokens, password
lifecycle management (first-login change, self-service reset), and admin-only
user management. User accounts are provisioned by administrators; there is
intentionally no public registration API.

Sign-in flow
------------
1. ``POST /api/v1/auth/login`` verifies the password and returns a short-lived
   ``mfa_token`` describing the next required step (password change, 2FA setup,
   or 2FA verification). No access token is issued yet.
2. The client completes the required step and receives access + refresh tokens.
3. ``POST /api/v1/auth/refresh`` rotates the refresh token; ``/logout`` revokes
   it.
"""

import hashlib
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, status
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field

import audit
import email_utils
import security
from auth_utils import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_mfa_token,
    require_role,
    verify_mfa_token,
    verify_token,
)
from migrations import apply_migrations

# ==============================================================================
# LOGGING
# ==============================================================================
logger = logging.getLogger("auth")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(_handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL must be set (e.g. "
        "postgresql://user:password@db:5432/congress_db)."
    )

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

pool: Optional[asyncpg.Pool] = None

# ==============================================================================
# LOGIN RATE LIMITING (in-memory sliding window)
# ==============================================================================
_LOGIN_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "300"))
_LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_MAX_ATTEMPTS", "10"))
_login_attempts: Dict[str, Deque[float]] = defaultdict(deque)

# Account lockout after repeated failed password attempts.
_MAX_FAILED_LOGINS = int(os.getenv("MAX_FAILED_LOGINS", "5"))
_LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))

# Email token lifetimes.
_RESET_TOKEN_MINUTES = int(os.getenv("RESET_TOKEN_MINUTES", "60"))
_WELCOME_TOKEN_MINUTES = int(os.getenv("WELCOME_TOKEN_MINUTES", "1440"))


def _enforce_login_rate_limit(key: str) -> None:
    """Raise HTTP 429 if ``key`` has exceeded the login attempt budget."""
    now = time.monotonic()
    window = _login_attempts[key]
    while window and now - window[0] > _LOGIN_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )
    window.append(now)


def _user_ref(username: str) -> str:
    """Return a short, non-reversible reference for logging (avoids PII)."""
    return hashlib.sha256(username.encode("utf-8")).hexdigest()[:12]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _as_list(value: Any) -> List[str]:
    """Coerce a JSONB/str/list value into a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return []


# ==============================================================================
# LIFESPAN
# ==============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the connection pool and ensure the schema exists."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                username VARCHAR(255) UNIQUE NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                roles JSONB NOT NULL DEFAULT '[]'::jsonb,
                allowed_chambers JSONB NOT NULL DEFAULT '["House", "Senate"]'::jsonb,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        await conn.execute(
            """
            ALTER TABLE users
                ADD COLUMN IF NOT EXISTS allowed_chambers JSONB
                NOT NULL DEFAULT '["House", "Senate"]'::jsonb;
            """
        )
        await conn.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'users'
                      AND column_name = 'client_id'
                ) AND NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'users'
                      AND column_name = 'username'
                ) THEN
                    ALTER TABLE users RENAME COLUMN client_id TO username;
                END IF;

                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'users'
                      AND column_name = 'created_at'
                ) THEN
                    ALTER TABLE users
                        ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
                END IF;
            END $$;
            """
        )
        await apply_migrations(conn)
    # Register the pool so require_role() re-validates against the DB.
    from auth_utils import set_pool

    set_pool(pool)
    yield
    await pool.close()


app = FastAPI(
    title="Congressional Auth Service",
    description="Centralized authentication and authorization microservice.",
    version="2.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Attach baseline security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
    return response


# ==============================================================================
# MODELS
# ==============================================================================

class LoginResponse(BaseModel):
    """Result of a password login. Tokens are only issued after 2FA."""

    mfa_required: bool = Field(..., description="True when TOTP verification is needed.")
    must_change_password: bool = Field(default=False)
    must_setup_2fa: bool = Field(default=False)
    mfa_token: Optional[str] = Field(
        default=None, description="Short-lived token for the next required step."
    )
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: Optional[int] = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str


class MfaSetupRequest(BaseModel):
    mfa_token: str


class MfaSetupResponse(BaseModel):
    otpauth_uri: str
    qr_png_base64: str
    secret: str


class MfaEnableRequest(BaseModel):
    mfa_token: str
    code: str


class MfaEnableResponse(BaseModel):
    enabled: bool
    recovery_codes: List[str]
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MfaDisableRequest(BaseModel):
    password: str
    code: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


class UserOut(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    roles: List[str]
    allowed_chambers: List[str]
    is_active: bool
    mfa_enabled: bool = False
    must_change_password: bool = False


class AdminUserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=255)
    email: Optional[EmailStr] = None
    roles: List[str] = Field(default_factory=lambda: ["user"])
    allowed_chambers: List[str] = Field(default_factory=lambda: ["House", "Senate"])
    send_welcome: bool = True


class AdminUserUpdate(BaseModel):
    roles: Optional[List[str]] = None
    allowed_chambers: Optional[List[str]] = None
    is_active: Optional[bool] = None


class AdminBulkUserAction(BaseModel):
    """Body for a bulk user-management action (admin only)."""

    user_ids: List[str] = Field(..., min_length=1, description="Target user UUIDs.")
    action: str = Field(
        ...,
        description="One of: activate, deactivate, reset-2fa, set-chambers.",
    )
    allowed_chambers: Optional[List[str]] = Field(
        default=None,
        description="Required when action='set-chambers'.",
    )


class StatusResponse(BaseModel):
    status: str


# ==============================================================================
# HELPERS
# ==============================================================================

async def _load_user_by_username(username: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT id, username, email, hashed_password, roles, allowed_chambers, "
            "is_active, totp_enabled, totp_secret, recovery_codes_hash, "
            "must_change_password, failed_login_attempts, locked_until "
            "FROM users WHERE username = $1",
            username,
        )


async def _load_user_by_id(user_id: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT id, username, email, roles, allowed_chambers, is_active, "
            "totp_enabled, must_change_password "
            "FROM users WHERE id = $1::uuid",
            user_id,
        )


async def _issue_tokens(user_row, request: Request) -> Dict[str, Any]:
    """Create an access token and a stored, rotating refresh token."""
    username = user_row["username"]
    roles = _as_list(user_row["roles"])
    allowed = _as_list(user_row["allowed_chambers"])
    mfa_enabled = bool(user_row["totp_enabled"])
    session_id = str(uuid.uuid4())

    access_token = create_access_token(
        data={
            "sub": username,
            "roles": roles,
            "allowed_chambers": allowed,
            "amr": ["pwd", "totp"] if mfa_enabled else ["pwd"],
            "mfa": mfa_enabled,
            "session_id": session_id,
            "must_change_password": bool(user_row["must_change_password"]),
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    refresh_token = security.generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at, user_agent, ip)
            VALUES ($1::uuid, $2, $3, $4, $5)
            """,
            str(user_row["id"]),
            security.hash_token(refresh_token),
            expires_at,
            request.headers.get("user-agent"),
            _client_ip(request),
        )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


async def _revoke_all_refresh_tokens(user_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE refresh_tokens SET revoked_at = NOW() "
            "WHERE user_id = $1::uuid AND revoked_at IS NULL",
            user_id,
        )


async def _verify_credentials(username: str, password: str):
    """Validate credentials, applying lockout and failure counters."""
    user = await _load_user_by_username(username)
    if not user or not user["is_active"]:
        logger.warning("Login failed: unknown/inactive ref=%s", _user_ref(username))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = datetime.now(timezone.utc)
    if user["locked_until"] and user["locked_until"] > now:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to failed login attempts.",
        )

    if not pwd_context.verify(password, user["hashed_password"]):
        attempts = (user["failed_login_attempts"] or 0) + 1
        locked_until = (
            now + timedelta(minutes=_LOCKOUT_MINUTES)
            if attempts >= _MAX_FAILED_LOGINS
            else None
        )
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET failed_login_attempts = $1, locked_until = $2, "
                "updated_at = NOW() WHERE id = $3",
                attempts,
                locked_until,
                user["id"],
            )
        logger.warning(
            "Login failed: rejected ref=%s attempts=%d", _user_ref(username), attempts
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET failed_login_attempts = 0, locked_until = NULL, "
            "last_login_at = NOW(), updated_at = NOW() WHERE id = $1",
            user["id"],
        )
    return user


async def _principal_from_request(
    request: Request, allow_mfa_scope: Optional[str] = None
) -> Dict[str, Any]:
    """Resolve the caller from the Authorization header.

    Accepts a normal access token, or (when ``allow_mfa_scope`` is set) a
    short-lived MFA token carrying that scope.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = header.split(" ", 1)[1].strip()
    try:
        return verify_token(token)
    except HTTPException:
        if allow_mfa_scope:
            return verify_mfa_token(token, allow_mfa_scope)
        raise


def _user_out(user) -> Dict[str, Any]:
    return {
        "id": str(user["id"]),
        "username": user["username"],
        "email": user.get("email"),
        "roles": _as_list(user["roles"]),
        "allowed_chambers": _as_list(user["allowed_chambers"]),
        "is_active": bool(user["is_active"]),
        "mfa_enabled": bool(user.get("totp_enabled")),
        "must_change_password": bool(user.get("must_change_password")),
    }


# ==============================================================================
# GENERAL
# ==============================================================================

@app.get("/health", tags=["General"])
async def health():
    """Health check endpoint for Docker container probes."""
    return {"status": "healthy"}


# ==============================================================================
# AUTHENTICATION
# ==============================================================================

@app.post("/api/v1/auth/login", response_model=LoginResponse, tags=["Auth"])
async def login(request: Request):
    """Verify a password and return the next required authentication step.

    No access token is issued here. The response indicates whether the caller
    must change their password, enroll TOTP, or verify TOTP, and returns a
    short-lived ``mfa_token`` for that step.
    """
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            body = {}
        username = body.get("username") or body.get("client_id")
        password = body.get("password")
    else:
        form = await request.form()
        username = form.get("username") or form.get("client_id")
        password = form.get("password")

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="username (or client_id) and password are required",
        )

    client_ip = _client_ip(request)
    _enforce_login_rate_limit(f"ip:{client_ip}")
    _enforce_login_rate_limit(f"user:{username}")

    user = await _verify_credentials(username, password)

    if user["must_change_password"]:
        await audit.record(
            pool, "login.password_change_required",
            actor_user_id=str(user["id"]), actor_username=username, ip=client_ip,
        )
        return LoginResponse(
            mfa_required=False,
            must_change_password=True,
            mfa_token=create_mfa_token(username, "password_change"),
        )

    if not user["totp_enabled"]:
        await audit.record(
            pool, "login.mfa_setup_required",
            actor_user_id=str(user["id"]), actor_username=username, ip=client_ip,
        )
        return LoginResponse(
            mfa_required=False,
            must_setup_2fa=True,
            mfa_token=create_mfa_token(username, "mfa_setup"),
        )

    await audit.record(
        pool, "login.password_ok",
        actor_user_id=str(user["id"]), actor_username=username, ip=client_ip,
    )
    return LoginResponse(
        mfa_required=True,
        mfa_token=create_mfa_token(username, "mfa"),
    )


@app.post("/api/v1/auth/mfa/verify", response_model=TokenPair, tags=["Auth"])
async def mfa_verify(body: MfaVerifyRequest, request: Request):
    """Verify a TOTP (or recovery) code and issue access + refresh tokens."""
    payload = verify_mfa_token(body.mfa_token, "mfa")
    username = payload["sub"]
    user = await _load_user_by_username(username)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user["totp_enabled"] or not user["totp_secret"]:
        raise HTTPException(status_code=400, detail="2FA is not enabled for this account.")

    secret = security.decrypt_secret(user["totp_secret"])
    if security.verify_totp(secret, body.code):
        tokens = await _issue_tokens(user, request)
        await audit.record(
            pool, "mfa.verify.success",
            actor_user_id=str(user["id"]), actor_username=username,
            ip=_client_ip(request),
        )
        return tokens

    # Fall back to a single-use recovery code.
    hashed = _as_list(user["recovery_codes_hash"])
    matched, remaining = security.consume_recovery_code(body.code, hashed)
    if matched:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET recovery_codes_hash = $1::jsonb, updated_at = NOW() "
                "WHERE id = $2",
                json.dumps(remaining),
                user["id"],
            )
        tokens = await _issue_tokens(user, request)
        await audit.record(
            pool, "mfa.verify.recovery_code",
            actor_user_id=str(user["id"]), actor_username=username,
            ip=_client_ip(request),
        )
        return tokens

    await audit.record(
        pool, "mfa.verify.failure",
        actor_user_id=str(user["id"]), actor_username=username,
        ip=_client_ip(request),
    )
    raise HTTPException(status_code=401, detail="Invalid verification code.")


@app.post("/api/v1/auth/mfa/setup", response_model=MfaSetupResponse, tags=["Auth"])
async def mfa_setup(body: MfaSetupRequest):
    """Begin TOTP enrollment: return the otpauth URI and a QR code.

    The (encrypted) secret is stored immediately but 2FA is not enabled until
    ``/mfa/enable`` confirms a valid code.
    """
    payload = verify_mfa_token(body.mfa_token, "mfa_setup")
    username = payload["sub"]
    user = await _load_user_by_username(username)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user["totp_enabled"]:
        raise HTTPException(status_code=400, detail="2FA is already enabled.")

    secret = security.generate_totp_secret()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET totp_secret = $1, updated_at = NOW() WHERE id = $2",
            security.encrypt_secret(secret),
            user["id"],
        )
    uri = security.build_otpauth_uri(secret, username)
    return {
        "otpauth_uri": uri,
        "qr_png_base64": security.qr_png_base64(uri),
        "secret": secret,
    }


@app.post("/api/v1/auth/mfa/enable", response_model=MfaEnableResponse, tags=["Auth"])
async def mfa_enable(body: MfaEnableRequest, request: Request):
    """Confirm a TOTP code, enable 2FA, and return one-time recovery codes."""
    payload = verify_mfa_token(body.mfa_token, "mfa_setup")
    username = payload["sub"]
    user = await _load_user_by_username(username)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user["totp_secret"]:
        raise HTTPException(status_code=400, detail="Call /mfa/setup first.")

    secret = security.decrypt_secret(user["totp_secret"])
    if not security.verify_totp(secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid verification code.")

    recovery_codes = security.generate_recovery_codes()
    hashed = security.hash_recovery_codes(recovery_codes)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET totp_enabled = TRUE, totp_verified_at = NOW(), "
            "recovery_codes_hash = $1::jsonb, updated_at = NOW() WHERE id = $2",
            json.dumps(hashed),
            user["id"],
        )
    user = await _load_user_by_username(username)
    tokens = await _issue_tokens(user, request)
    await audit.record(
        pool, "mfa.enable",
        actor_user_id=str(user["id"]), actor_username=username, ip=_client_ip(request),
    )
    return {"enabled": True, "recovery_codes": recovery_codes, **tokens}


@app.post("/api/v1/auth/mfa/disable", response_model=StatusResponse, tags=["Auth"])
async def mfa_disable(
    body: MfaDisableRequest,
    request: Request,
    payload: Dict[str, Any] = Depends(verify_token),
):
    """Disable 2FA for the authenticated user (password + code required)."""
    username = payload["sub"]
    user = await _load_user_by_username(username)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not pwd_context.verify(body.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid password.")

    ok = False
    if user["totp_secret"]:
        ok = security.verify_totp(security.decrypt_secret(user["totp_secret"]), body.code)
    if not ok:
        hashed = _as_list(user["recovery_codes_hash"])
        ok, _ = security.consume_recovery_code(body.code, hashed)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid verification code.")

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET totp_enabled = FALSE, totp_secret = NULL, "
            "recovery_codes_hash = '[]'::jsonb, updated_at = NOW() WHERE id = $1",
            user["id"],
        )
    await audit.record(
        pool, "mfa.disable",
        actor_user_id=str(user["id"]), actor_username=username, ip=_client_ip(request),
    )
    return {"status": "disabled"}


@app.post("/api/v1/auth/change-password", response_model=LoginResponse, tags=["Auth"])
async def change_password(body: ChangePasswordRequest, request: Request):
    """Change the caller's password.

    Accepts either a normal access token or a ``password_change`` MFA token
    (used for the mandatory first-login update).
    """
    payload = await _principal_from_request(request, allow_mfa_scope="password_change")
    username = payload["sub"]
    user = await _load_user_by_username(username)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not pwd_context.verify(body.current_password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    try:
        security.validate_password_strength(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    new_hash = pwd_context.hash(body.new_password)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET hashed_password = $1, must_change_password = FALSE, "
            "password_changed_at = NOW(), updated_at = NOW() WHERE id = $2",
            new_hash,
            user["id"],
        )
    await _revoke_all_refresh_tokens(str(user["id"]))
    await audit.record(
        pool, "password.change",
        actor_user_id=str(user["id"]), actor_username=username, ip=_client_ip(request),
    )

    if not user["totp_enabled"]:
        return LoginResponse(
            mfa_required=False,
            must_setup_2fa=True,
            mfa_token=create_mfa_token(username, "mfa_setup"),
        )
    return LoginResponse(mfa_required=True, mfa_token=create_mfa_token(username, "mfa"))


@app.post("/api/v1/auth/forgot-password", response_model=StatusResponse, tags=["Auth"])
async def forgot_password(body: ForgotPasswordRequest, request: Request):
    """Send a password-reset email. Always returns 202 (no user enumeration)."""
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, username, email FROM users "
            "WHERE LOWER(email) = LOWER($1) AND is_active = TRUE",
            body.email,
        )
    if user:
        token = security.generate_opaque_token()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=_RESET_TOKEN_MINUTES)
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO email_tokens (user_id, token_hash, purpose, expires_at) "
                "VALUES ($1::uuid, $2, 'reset', $3)",
                str(user["id"]),
                security.hash_token(token),
                expires_at,
            )
        await email_utils.send_email(
            user["email"],
            "Reset your password",
            email_utils.reset_email_body(user["username"], token),
        )
        await audit.record(
            pool, "password.reset_requested",
            actor_user_id=str(user["id"]), actor_username=user["username"],
            ip=_client_ip(request),
        )
    return {"status": "accepted"}


@app.post("/api/v1/auth/reset-password", response_model=StatusResponse, tags=["Auth"])
async def reset_password(body: ResetPasswordRequest, request: Request):
    """Consume a welcome/reset token and set a new password."""
    token_hash = security.hash_token(body.token)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, user_id, purpose FROM email_tokens "
            "WHERE token_hash = $1 AND used_at IS NULL AND expires_at > NOW()",
            token_hash,
        )
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or expired token.")
    try:
        security.validate_password_strength(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    new_hash = pwd_context.hash(body.new_password)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET hashed_password = $1, must_change_password = FALSE, "
            "password_changed_at = NOW(), updated_at = NOW() WHERE id = $2::uuid",
            new_hash,
            str(row["user_id"]),
        )
        await conn.execute(
            "UPDATE email_tokens SET used_at = NOW() WHERE id = $1", row["id"]
        )
    await _revoke_all_refresh_tokens(str(row["user_id"]))
    await audit.record(
        pool, f"password.reset.{row['purpose']}",
        target_type="user", target_id=str(row["user_id"]), ip=_client_ip(request),
    )
    return {"status": "ok"}


@app.post("/api/v1/auth/refresh", response_model=TokenPair, tags=["Auth"])
async def refresh(body: RefreshRequest, request: Request):
    """Rotate a refresh token and issue a new access + refresh token pair."""
    token_hash = security.hash_token(body.refresh_token)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, user_id FROM refresh_tokens "
            "WHERE token_hash = $1 AND revoked_at IS NULL AND expires_at > NOW()",
            token_hash,
        )
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    user = await _load_user_by_id(str(row["user_id"]))
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE refresh_tokens SET revoked_at = NOW() WHERE id = $1", row["id"]
        )
    return await _issue_tokens(user, request)


@app.post("/api/v1/auth/logout", response_model=StatusResponse, tags=["Auth"])
async def logout(body: LogoutRequest):
    """Revoke a refresh token (best-effort)."""
    if body.refresh_token:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE refresh_tokens SET revoked_at = NOW() "
                "WHERE token_hash = $1 AND revoked_at IS NULL",
                security.hash_token(body.refresh_token),
            )
    return {"status": "ok"}


@app.get("/api/v1/auth/me", response_model=UserOut, tags=["Auth"])
async def me(payload: dict = Depends(verify_token)):
    """Return the current user's profile and scope."""
    user = await _load_user_by_username(payload.get("sub"))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_out(user)


# ==============================================================================
# ADMIN — USER & PERMISSION MANAGEMENT
# ==============================================================================

@app.get(
    "/api/v1/admin/users",
    response_model=List[UserOut],
    tags=["Admin"],
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_users():
    """List all user accounts (admin only)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, username, email, roles, allowed_chambers, is_active, "
            "totp_enabled, must_change_password FROM users ORDER BY created_at DESC"
        )
    return [_user_out(row) for row in rows]


@app.post(
    "/api/v1/admin/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Admin"],
    dependencies=[Depends(require_role(["admin"]))],
)
async def create_user(
    body: AdminUserCreate,
    request: Request,
    payload: Dict[str, Any] = Depends(verify_token),
):
    """Create a user account and optionally send a welcome email (admin only)."""
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT 1 FROM users WHERE username = $1", body.username
        )
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists.")

    # Unusable random password; the user sets their own via the welcome link.
    placeholder = pwd_context.hash(security.generate_opaque_token())
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users
                (username, email, hashed_password, roles, allowed_chambers,
                 is_active, must_change_password, created_by)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, TRUE, TRUE, $6)
            RETURNING id, username, email, roles, allowed_chambers, is_active,
                      totp_enabled, must_change_password
            """,
            body.username,
            body.email,
            placeholder,
            json.dumps(body.roles),
            json.dumps(body.allowed_chambers),
            payload.get("sub"),
        )

    if body.send_welcome and body.email:
        token = security.generate_opaque_token()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=_WELCOME_TOKEN_MINUTES
        )
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO email_tokens (user_id, token_hash, purpose, expires_at) "
                "VALUES ($1::uuid, $2, 'welcome', $3)",
                str(row["id"]),
                security.hash_token(token),
                expires_at,
            )
        await email_utils.send_email(
            body.email,
            "Your account is ready",
            email_utils.welcome_email_body(body.username, token),
        )

    await audit.record(
        pool, "admin.user.create",
        actor_username=payload.get("sub"), target_type="user",
        target_id=str(row["id"]), metadata={"username": body.username},
        ip=_client_ip(request),
    )
    return _user_out(row)


@app.patch(
    "/api/v1/admin/users/{user_id}",
    response_model=UserOut,
    tags=["Admin"],
    dependencies=[Depends(require_role(["admin"]))],
)
async def update_user(
    user_id: str,
    body: AdminUserUpdate,
    request: Request,
    payload: Dict[str, Any] = Depends(verify_token),
):
    """Update a user's roles, chamber scope, or active flag (admin only)."""
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE id = $1::uuid", user_id
        )
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    sets: List[str] = []
    params: List[Any] = []
    if body.roles is not None:
        params.append(json.dumps(body.roles))
        sets.append(f"roles = ${len(params)}::jsonb")
    if body.allowed_chambers is not None:
        params.append(json.dumps(body.allowed_chambers))
        sets.append(f"allowed_chambers = ${len(params)}::jsonb")
    if body.is_active is not None:
        params.append(body.is_active)
        sets.append(f"is_active = ${len(params)}")
    if not sets:
        raise HTTPException(status_code=422, detail="No fields to update.")

    sets.append("updated_at = NOW()")
    params.append(user_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE users SET {', '.join(sets)} WHERE id = ${len(params)}::uuid "
            "RETURNING id, username, email, roles, allowed_chambers, is_active, "
            "totp_enabled, must_change_password",
            *params,
        )
    await audit.record(
        pool, "admin.user.update",
        actor_username=payload.get("sub"), target_type="user", target_id=user_id,
        metadata=body.model_dump(exclude_none=True), ip=_client_ip(request),
    )
    return _user_out(row)


@app.post(
    "/api/v1/admin/users/{user_id}/reset-password",
    response_model=StatusResponse,
    tags=["Admin"],
    dependencies=[Depends(require_role(["admin"]))],
)
async def admin_reset_password(
    user_id: str,
    request: Request,
    payload: Dict[str, Any] = Depends(verify_token),
):
    """Force a password reset by emailing a reset link (admin only)."""
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, username, email FROM users WHERE id = $1::uuid", user_id
        )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user["email"]:
        raise HTTPException(status_code=422, detail="User has no email address.")

    token = security.generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_RESET_TOKEN_MINUTES)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO email_tokens (user_id, token_hash, purpose, expires_at) "
            "VALUES ($1::uuid, $2, 'reset', $3)",
            str(user["id"]),
            security.hash_token(token),
            expires_at,
        )
    await email_utils.send_email(
        user["email"],
        "Reset your password",
        email_utils.reset_email_body(user["username"], token),
    )
    await audit.record(
        pool, "admin.user.reset_password",
        actor_username=payload.get("sub"), target_type="user", target_id=user_id,
        ip=_client_ip(request),
    )
    return {"status": "ok"}


@app.post(
    "/api/v1/admin/users/{user_id}/reset-2fa",
    response_model=StatusResponse,
    tags=["Admin"],
    dependencies=[Depends(require_role(["admin"]))],
)
async def admin_reset_2fa(
    user_id: str,
    request: Request,
    payload: Dict[str, Any] = Depends(verify_token),
):
    """Clear a user's TOTP enrollment so they can re-enroll (admin only)."""
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE id = $1::uuid", user_id
        )
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET totp_enabled = FALSE, totp_secret = NULL, "
            "recovery_codes_hash = '[]'::jsonb, updated_at = NOW() "
            "WHERE id = $1::uuid",
            user_id,
        )
    await audit.record(
        pool, "admin.user.reset_2fa",
        actor_username=payload.get("sub"), target_type="user", target_id=user_id,
        ip=_client_ip(request),
    )
    return {"status": "ok"}


@app.post(
    "/api/v1/admin/users/bulk",
    tags=["Admin"],
    dependencies=[Depends(require_role(["admin"]))],
)
async def bulk_user_action(
    body: AdminBulkUserAction,
    request: Request,
    payload: Dict[str, Any] = Depends(verify_token),
):
    """Apply one action to many users (admin only).

    Best-effort: each user is processed independently and the response reports
    per-user success/failure. Supported actions are ``activate``,
    ``deactivate`` (also revokes refresh tokens), ``reset-2fa`` and
    ``set-chambers`` (requires ``allowed_chambers``).
    """
    action = body.action.lower().strip()
    valid = {"activate", "deactivate", "reset-2fa", "set-chambers"}
    if action not in valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"action must be one of: {', '.join(sorted(valid))}",
        )
    if action == "set-chambers" and not body.allowed_chambers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="allowed_chambers is required for action='set-chambers'.",
        )

    results: List[Dict[str, Any]] = []
    for user_id in body.user_ids:
        try:
            uuid.UUID(user_id)
        except ValueError:
            results.append(
                {"user_id": user_id, "ok": False, "detail": "Invalid user id"}
            )
            continue
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM users WHERE id = $1::uuid", user_id
            )
        if not existing:
            results.append(
                {"user_id": user_id, "ok": False, "detail": "User not found"}
            )
            continue
        try:
            if action == "activate":
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE users SET is_active = TRUE, updated_at = NOW() "
                        "WHERE id = $1::uuid",
                        user_id,
                    )
            elif action == "deactivate":
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE users SET is_active = FALSE, updated_at = NOW() "
                        "WHERE id = $1::uuid",
                        user_id,
                    )
                await _revoke_all_refresh_tokens(user_id)
            elif action == "reset-2fa":
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE users SET totp_enabled = FALSE, totp_secret = NULL, "
                        "recovery_codes_hash = '[]'::jsonb, updated_at = NOW() "
                        "WHERE id = $1::uuid",
                        user_id,
                    )
            elif action == "set-chambers":
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE users SET allowed_chambers = $1::jsonb, "
                        "updated_at = NOW() WHERE id = $2::uuid",
                        json.dumps(body.allowed_chambers),
                        user_id,
                    )
            await audit.record(
                pool, f"admin.user.bulk.{action}",
                actor_username=payload.get("sub"), target_type="user",
                target_id=user_id, metadata={"action": action},
                ip=_client_ip(request),
            )
            results.append({"user_id": user_id, "ok": True})
        except Exception as exc:  # keep going; report per-user failure
            results.append({"user_id": user_id, "ok": False, "detail": str(exc)})

    succeeded = sum(1 for r in results if r["ok"])
    return {
        "action": action,
        "requested": len(body.user_ids),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
        "results": results,
    }


@app.delete(
    "/api/v1/admin/users/{user_id}",
    response_model=StatusResponse,
    tags=["Admin"],
    dependencies=[Depends(require_role(["admin"]))],
)
async def deactivate_user(
    user_id: str,
    request: Request,
    payload: Dict[str, Any] = Depends(verify_token),
):
    """Soft-deactivate a user account (admin only)."""
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE id = $1::uuid", user_id
        )
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET is_active = FALSE, updated_at = NOW() "
            "WHERE id = $1::uuid",
            user_id,
        )
    await _revoke_all_refresh_tokens(user_id)
    await audit.record(
        pool, "admin.user.deactivate",
        actor_username=payload.get("sub"), target_type="user", target_id=user_id,
        ip=_client_ip(request),
    )
    return {"status": "ok"}
