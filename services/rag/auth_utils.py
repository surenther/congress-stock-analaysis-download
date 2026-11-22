"""
Authentication, authorization, and Chamber-Based Access Control (CBAC) utilities
for the RAG & Query Retrieval Microservice.

This module validates JWTs issued by the auth-service (HS256, shared
``JWT_SECRET_KEY``) and resolves the set of chambers a caller is permitted to
query. It mirrors the platform-wide ``auth_utils`` conventions so the RAG
service behaves consistently with the downloader, parser, vectorizer, and admin
services.

Chamber resolution rules
------------------------
* ``admin`` role  -> always ``["House", "Senate"]`` (hard override; the JWT
  ``allowed_chambers`` claim is ignored for admins).
* ``user`` role   -> the signed ``allowed_chambers`` claim, e.g. ``["House"]``.
  Defaults to ``["House", "Senate"]`` when the claim is absent or empty.

When a database pool has been registered via :func:`set_pool`, the caller's
roles, ``is_active`` flag, and ``allowed_chambers`` are re-validated against the
``users`` table on every request so revocations take effect immediately rather
than only at token expiry. On a transient DB error the check degrades to the
cryptographically-valid token claims (logged for monitoring).
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

logger = logging.getLogger("rag")

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

# The two chambers this platform supports. Order is stable for deterministic
# output in responses and logs.
ALL_CHAMBERS: List[str] = ["House", "Senate"]

# ==============================================================================
# OPTIONAL DATABASE-BACKED AUTHORIZATION
# ==============================================================================
# The RAG service calls ``set_pool()`` at startup so that role, ``is_active``,
# and ``allowed_chambers`` checks are re-validated against the database on every
# request. This makes revocations take effect immediately instead of only after
# the token expires.
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
                "SELECT username, roles, is_active, allowed_chambers "
                "FROM users WHERE username = $1",
                username,
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("DB-backed authorization check failed: %s", exc)
        return None


def _coerce_list(value: Any) -> List[str]:
    """Coerce a JSONB/str/list value into a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if isinstance(item, str)]
    return []


def _normalize_chambers(chambers: List[str]) -> List[str]:
    """Keep only known chambers, de-duplicate, and preserve stable order."""
    seen = set()
    result: List[str] = []
    for chamber in chambers:
        if chamber in ALL_CHAMBERS and chamber not in seen:
            seen.add(chamber)
            result.append(chamber)
    return result


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
            user_roles = _coerce_list(user["roles"])
        else:
            # No pool configured or DB unavailable — trust the token claims.
            user_roles = _coerce_list(payload.get("roles", []))

        if not any(role in user_roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return payload

    return role_checker


async def get_allowed_chambers(payload: Dict[str, Any]) -> List[str]:
    """Resolve the chambers a caller is permitted to query.

    * ``admin`` -> ``["House", "Senate"]`` (hard override).
    * ``user``  -> the signed ``allowed_chambers`` claim, defaulting to both
      chambers when absent/empty. When a DB pool is configured the value is
      re-validated against the ``users`` table so revocations apply immediately.

    The returned list is always a non-empty subset of ``ALL_CHAMBERS``.
    """
    username = payload.get("sub")

    # Prefer DB-backed values when available (immediate revocation).
    user = await _load_user(username)
    if user is not None:
        roles = _coerce_list(user["roles"])
        claim_chambers = _coerce_list(user["allowed_chambers"])
    else:
        roles = _coerce_list(payload.get("roles", []))
        claim_chambers = _coerce_list(payload.get("allowed_chambers", []))

    # Admin override: admins are never chamber-restricted.
    if "admin" in roles:
        return list(ALL_CHAMBERS)

    normalized = _normalize_chambers(claim_chambers)
    if not normalized:
        # Default to both chambers when the claim is unspecified.
        return list(ALL_CHAMBERS)
    return normalized
