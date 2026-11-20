#!/usr/bin/env python3
"""
Database schema initialization for the Vectorizer Microservice.

Ensures the ``pgvector`` extension is active and creates the two tables the
service relies on:

* ``vectorizer_jobs``       — asynchronous job tracking (mirrors ``parse_jobs``).
* ``disclosure_embeddings`` — relational metadata + 1536-d vector embeddings.

The module is import-safe (no side effects) and exposes:

* :func:`ensure_vector_extension` — enable the ``vector`` / ``pgcrypto`` extensions.
* :func:`register_vector_codec`   — asyncpg codec for the ``vector`` column type.
* :func:`create_schema`           — create tables + indexes (idempotent).
* :func:`init_db`                 — convenience wrapper used at startup.

A standalone entrypoint (``python db_init.py``) is provided for operators who
want to provision the schema without starting the API.
"""

import asyncio
import logging
import os

logger = logging.getLogger("vectorizer")

# Expected embedding dimension. Must match the model selected in the LiteLLM
# Proxy (e.g. 1536 for text-embedding-3-small, 384 for BAAI/bge-small-en-v1.5,
# 768 for nomic-embed-text). The `disclosure_embeddings.embedding` column is
# created with this dimension.
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

# ==============================================================================
# DDL
# ==============================================================================

# Job-tracking table. Mirrors the parser's ``parse_jobs`` shape so operators can
# reason about both services identically.
VECTORIZER_JOBS_DDL = """
CREATE TABLE IF NOT EXISTS vectorizer_jobs (
    job_id UUID PRIMARY KEY,
    mode VARCHAR(20) NOT NULL DEFAULT 'single',
    doc_id VARCHAR(64),
    chamber VARCHAR(16),
    model VARCHAR(100),
    requested_by VARCHAR(255),
    total_documents INTEGER,
    processed_documents INTEGER NOT NULL DEFAULT 0,
    total_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    error_message TEXT
);
"""

# Per-document outcome tracking for vectorization jobs. One row per document
# attempted within a job (SUCCESS / SKIPPED / FAILED), mirroring the parser's
# ``parse_job_items`` and the downloader's ``download_job_items`` tables.
VECTORIZER_JOB_ITEMS_DDL = """
CREATE TABLE IF NOT EXISTS vectorizer_job_items (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL,
    doc_id VARCHAR(64),
    file_path TEXT,
    status VARCHAR(20) NOT NULL,
    detail TEXT,
    cost DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vectorizer_job_items_job
    ON vectorizer_job_items (job_id, status);
"""

# Metadata + vector store. One row per disclosure item (chunk).
# The `{dim}` placeholder is filled with EMBEDDING_DIM at creation time so the
# column matches the selected embedding model (default 1536d).
DISCLOSURE_EMBEDDINGS_DDL = """
CREATE TABLE IF NOT EXISTS disclosure_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id VARCHAR(64) NOT NULL,
    item_index INT NOT NULL,
    chamber VARCHAR(16) NOT NULL,
    filer_name VARCHAR(255),
    filing_date DATE,
    report_type VARCHAR(64),
    contains_market_trades BOOLEAN NOT NULL DEFAULT false,
    is_market_trade BOOLEAN NOT NULL DEFAULT false,
    ticker VARCHAR(32),
    asset_name TEXT NOT NULL,
    asset_category VARCHAR(64),
    action VARCHAR(64),
    date DATE,
    value_range VARCHAR(128),
    ownership VARCHAR(32),
    comment TEXT,
    chunk_text TEXT NOT NULL,
    embedding vector({dim}), -- Dimension matches EMBEDDING_DIM (default 1536d)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(doc_id, item_index)
);
"""

# B-Tree indexes for fast exact SQL filtering.
INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_disclosure_ticker ON disclosure_embeddings(ticker);",
    "CREATE INDEX IF NOT EXISTS idx_disclosure_filer ON disclosure_embeddings(filer_name);",
    "CREATE INDEX IF NOT EXISTS idx_disclosure_trade ON disclosure_embeddings(is_market_trade);",
    "CREATE INDEX IF NOT EXISTS idx_disclosure_date ON disclosure_embeddings(date);",
    # HNSW index for sub-millisecond vector similarity search (cosine distance).
    "CREATE INDEX IF NOT EXISTS idx_disclosure_vector "
    "ON disclosure_embeddings USING hnsw (embedding vector_cosine_ops);",
]


# ==============================================================================
# SCHEMA MANAGEMENT
# ==============================================================================

async def ensure_vector_extension(conn) -> None:
    """Enable the ``vector`` (pgvector) and ``pgcrypto`` extensions.

    ``pgcrypto`` provides ``gen_random_uuid()`` on older PostgreSQL builds; it is
    a no-op on PostgreSQL 13+ where the function is built in.
    """
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")


async def register_vector_codec(conn) -> None:
    """Register the asyncpg codec for the ``vector`` column type.

    Passed as the ``init`` callback of ``asyncpg.create_pool`` so every pooled
    connection can transparently encode/decode Python lists as ``vector`` values.
    The ``vector`` extension must already exist when this runs.
    """
    from pgvector.asyncpg import register_vector

    await register_vector(conn)


async def create_schema(conn) -> None:
    """Create the job-tracking and embeddings tables plus their indexes."""
    await conn.execute(VECTORIZER_JOBS_DDL)
    await conn.execute(VECTORIZER_JOB_ITEMS_DDL)
    await conn.execute(DISCLOSURE_EMBEDDINGS_DDL.format(dim=EMBEDDING_DIM))
    for statement in INDEX_DDL:
        await conn.execute(statement)


async def init_db(pool) -> None:
    """Ensure the extensions and schema exist using a pooled connection."""
    async with pool.acquire() as conn:
        await ensure_vector_extension(conn)
        await create_schema(conn)
    logger.info(
        "Database schema ready: vectorizer_jobs + disclosure_embeddings "
        "(vector(%d), pgvector HNSW index active)",
        EMBEDDING_DIM,
    )


async def _main() -> None:
    """Standalone entrypoint: provision the schema without starting the API."""
    import asyncpg

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set to run db_init.py")

    # The extension must exist before the vector codec can be registered.
    conn = await asyncpg.connect(database_url)
    try:
        await ensure_vector_extension(conn)
    finally:
        await conn.close()

    pool = await asyncpg.create_pool(
        database_url, min_size=1, max_size=2, init=register_vector_codec
    )
    try:
        await init_db(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(_main())
