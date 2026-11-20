"""
Reusable authentication and authorization utilities.

This module provides JWT token creation/verification and Role-Based Access
Control (RBAC) dependencies. It is shared between the auth-service and the
downstream services (downloader, parser, vectorizer) so that all of them can
validate tokens issued by the auth-service.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

logger = logging.getLogger("auth")

# ==============================================================================
# JWT CONFIGURATION
# ==============================================================================
# The signing algorithm is FIXED to HS256 and is intentionally NOT configurable
# via the environment. Allowing the algorithm to be set to "none" (or to an
# asymmetric algorithm while the key is symmetric) enables algorithm-confusion
# token forgery.
ALGORITHM = "HS256"

# Placeholder values that must never be used as a real signing key.
_INSECURE_SECRETS = {
    "",
    "change-me-in-production",
    "change-me",
    "changeme",
    "secret",
    "your-secret-key",
    "sk-change-me",
}

# Minimum acceptable secret length (characters). `openssl rand -hex 32` yields 64.
_MIN_SECRET_LENGTH = 32

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip()

# Optional issuer/audience claims (defense-in-depth against token confusion).
JWT_ISSUER = os.getenv("JWT_ISSUER", "congress-auth")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "congress-platform")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Fail fast: refuse to start with a missing, weak, or placeholder secret.
if SECRET_KEY in _INSECURE_SECRETS or len(SECRET_KEY) < _MIN_SECRET_LENGTH:
    raise RuntimeError(
        "JWT_SECRET_KEY is unset, shorter than "
        f"{_MIN_SECRET_LENGTH} characters, or set to a known insecure default. "
        "Generate a strong value with `openssl rand -hex 32` and set it in the "
        "environment before starting the service."
    )

# The tokenUrl points to the auth-service login endpoint. It is only used by
# the OpenAPI docs to render the "Authorize" button.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# ==============================================================================
# OPTIONAL DATABASE-BACKED AUTHORIZATION
# ==============================================================================
# Downstream services (downloader, parser, vectorizer) call ``set_pool()`` at
# startup so that role and ``is_active`` checks are re-validated against the
# database on every request. This makes role changes and account deactivation
# take effect immediately instead of only after the token expires.
_pool = None


def set_pool(pool) -> None:
    """Register the asyncpg pool used for DB-backed authorization checks."""
    global _pool
    _pool = pool


async def _load_user(username: Optional[str]):
    """Fetch the current user row, or ``None`` if the pool is not configured.

    On a database error the check degrades to the token claims (the token is
    still cryptographically valid) so a transient DB outage does not take the
    whole platform down. The failure is logged for monitoring.
    """
    if _pool is None or not username:
        return None
    try:
        async with _pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT username, roles, is_active FROM users WHERE username = $1",
                username,
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("DB-backed authorization check failed: %s", exc)
        return None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update(
        {
            "exp": expire,
            "iat": now,
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        }
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Validate a JWT bearer token and return its decoded payload."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["exp", "sub"]},
        )
        sub: Optional[str] = payload.get("sub")
        if sub is None:
            raise credentials_exception
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise credentials_exception


def require_role(required_roles: List[str]):
    """Dependency factory that enforces Role-Based Access Control.

    When a database pool has been registered via ``set_pool()``, the caller's
    roles and ``is_active`` flag are re-validated against the ``users`` table on
    every request (so deactivation/role changes take effect immediately).
    Otherwise it falls back to the roles embedded in the token.

    Usage:
        @app.get("/protected", dependencies=[Depends(require_role(["admin"]))])
        def protected(): ...
    """

    async def role_checker(
        payload: Dict[str, Any] = Depends(verify_token),
    ) -> Dict[str, Any]:
        username = payload.get("sub")

        user = await _load_user(username)
        if user is not None:
            if not user["is_active"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User is inactive",
                )
            user_roles = user["roles"]
            if isinstance(user_roles, str):
                user_roles = json.loads(user_roles)
        else:
            # No pool configured (e.g. auth-service) — trust the token claims.
            user_roles = payload.get("roles", [])
        if not any(role in user_roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return payload

    return role_checker
