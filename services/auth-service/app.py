#!/usr/bin/env python3
"""
Centralized Authentication & Authorization Microservice.

Provides user management, password hashing (bcrypt), JWT issuance, and
token verification for the rest of the platform.
"""

import json
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import List, Optional

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, status
from passlib.context import CryptContext
from pydantic import BaseModel

from auth_utils import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token, verify_token

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://congress:congress_secret@localhost:5432/congress_db",
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the connection pool and initialize the users table on startup."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id VARCHAR(255) UNIQUE NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                roles JSONB NOT NULL DEFAULT '[]'::jsonb,
                is_active BOOLEAN NOT NULL DEFAULT TRUE
            );
            """
        )
        # Seed a default admin user for local development / testing.
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE client_id = $1", "admin"
        )
        if not existing:
            hashed = pwd_context.hash("admin123")
            await conn.execute(
                "INSERT INTO users (client_id, hashed_password, roles, is_active) "
                "VALUES ($1, $2, $3::jsonb, $4)",
                "admin",
                hashed,
                json.dumps(["admin"]),
                True,
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


class UserCreate(BaseModel):
    client_id: str
    password: str
    roles: List[str] = []


class UserOut(BaseModel):
    id: str
    client_id: str
    roles: List[str]
    is_active: bool


@app.get("/health", tags=["General"])
async def health():
    """Health check endpoint for Docker container probes."""
    return {"status": "healthy"}


async def _authenticate(client_id: str, password: str):
    """Validate credentials against the users table and return the user row."""
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT client_id, hashed_password, roles, is_active "
            "FROM users WHERE client_id = $1",
            client_id,
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )
    if not pwd_context.verify(password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@app.post("/api/v1/auth/login", response_model=Token, tags=["Auth"])
async def login(request: Request):
    """Authenticate a client and return a signed JWT access token.

    Accepts either:
      * JSON body:  {"client_id": "...", "password": "..."}  (or "username")
      * Form body:  username=...&password=...  (OAuth2 password flow / Swagger)
    """
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            body = {}
        client_id = body.get("client_id") or body.get("username")
        password = body.get("password")
    else:
        form = await request.form()
        client_id = form.get("username") or form.get("client_id")
        password = form.get("password")

    if not client_id or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="client_id/username and password are required",
        )

    user = await _authenticate(client_id, password)

    roles = user["roles"]
    if isinstance(roles, str):
        roles = json.loads(roles)

    access_token = create_access_token(
        data={"sub": user["client_id"], "roles": roles},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post(
    "/api/v1/auth/register",
    status_code=status.HTTP_201_CREATED,
    tags=["Auth"],
)
async def register(user: UserCreate):
    """Register a new client (admin-only in production; open for bootstrap)."""
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE client_id = $1", user.client_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Client ID already exists",
            )
        hashed = pwd_context.hash(user.password)
        await conn.execute(
            "INSERT INTO users (client_id, hashed_password, roles, is_active) "
            "VALUES ($1, $2, $3::jsonb, $4)",
            user.client_id,
            hashed,
            json.dumps(user.roles),
            True,
        )
    return {"message": "User created successfully"}


@app.get("/api/v1/auth/me", response_model=UserOut, tags=["Auth"])
async def me(payload: dict = Depends(verify_token)):
    """Return the decoded token payload for the current client."""
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, client_id, roles, is_active FROM users WHERE client_id = $1",
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
        "client_id": user["client_id"],
        "roles": roles,
        "is_active": user["is_active"],
    }
