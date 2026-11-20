#!/usr/bin/env python3
"""
Centralized Authentication & Authorization Microservice.

Provides bcrypt credential verification, JWT issuance, and token verification
for the rest of the platform. User accounts are provisioned out-of-band
directly in PostgreSQL; there is intentionally no public registration API.
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import List, Optional

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, status
from passlib.context import CryptContext
from pydantic import BaseModel

from auth_utils import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, verify_token

# ==============================================================================
# LOGGING
# ==============================================================================
# A dedicated "auth" logger with its own handler so our INFO/DEBUG lines always
# appear in `docker logs` regardless of uvicorn's logging configuration.
# Set LOG_LEVEL=DEBUG for verbose detail.
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

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://congress:congress_secret@localhost:5432/congress_db",
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the connection pool and ensure the users table exists.

    User accounts are NOT created or seeded here. Provision and rotate
    credentials exclusively through the SQL script in
    ``scripts/create_user.sql`` or a direct ``psql`` session.
    """
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
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        # Migrate legacy installations that used ``client_id`` and lacked a
        # ``created_at`` timestamp. This is idempotent and safe to run on every
        # startup.
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
    yield
    await pool.close()


app = FastAPI(
    title="Congressional Auth Service",
    description="Centralized authentication and authorization microservice.",
    version="1.0.0",
    lifespan=lifespan,
)


class Token(BaseModel):
    access_token: str
    token_type: str


class UserOut(BaseModel):
    id: str
    username: str
    roles: List[str]
    is_active: bool


@app.get("/health", tags=["General"])
async def health():
    """Health check endpoint for Docker container probes."""
    return {"status": "healthy"}


async def _authenticate(username: str, password: str):
    """Validate credentials against the users table and return the user row."""
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT username, hashed_password, roles, is_active "
            "FROM users WHERE username = $1",
            username,
        )

    if not user:
        logger.warning("Login failed: unknown user=%s", username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user["is_active"]:
        logger.warning("Login failed: inactive user=%s", username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )
    if not pwd_context.verify(password, user["hashed_password"]):
        logger.warning("Login failed: bad password user=%s", username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@app.post("/api/v1/auth/login", response_model=Token, tags=["Auth"])
async def login(request: Request):
    """Authenticate a user and return a signed JWT access token.

    Accepts either:
      * JSON body:  {"username": "...", "password": "..."}  (or "client_id")
      * Form body:  username=...&password=...  (OAuth2 password flow / Swagger)

    Accounts are provisioned out-of-band via ``scripts/create_user.sql``;
    there is intentionally no public registration endpoint.
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

    user = await _authenticate(username, password)

    roles = user["roles"]
    if isinstance(roles, str):
        roles = json.loads(roles)

    access_token = create_access_token(
        data={"sub": user["username"], "roles": roles},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    logger.info("Login success: user=%s roles=%s", user["username"], roles)
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/v1/auth/me", response_model=UserOut, tags=["Auth"])
async def me(payload: dict = Depends(verify_token)):
    """Return the decoded token payload for the current user."""
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, username, roles, is_active FROM users WHERE username = $1",
            payload.get("sub"),
        )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    roles = user["roles"]
    if isinstance(roles, str):
        roles = json.loads(roles)
    return {
        "id": str(user["id"]),
        "username": user["username"],
        "roles": roles,
        "is_active": user["is_active"],
    }
