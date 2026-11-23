#!/usr/bin/env python3
"""
Database schema initialization for the Analytics Microservice.

Creates the reference and personalization tables the analytics service relies on
and (when the vectorizer's ``disclosure_embeddings`` table exists) a
``disclosure_facts`` materialized view that pre-joins disclosures with member
and sector metadata for fast dashboard queries.

Tables created (all idempotent):

* ``members``            — normalized member reference data (party, state, ...).
* ``committees``         — congressional committees.
* ``member_committees``  — member-to-committee assignments.
* ``ticker_sectors``     — ticker-to-sector/industry mapping.
* ``user_watchlists``    — per-user member/ticker bookmarks.

The module is import-safe (no side effects) and exposes:

* :func:`ensure_extensions`        — enable ``pgcrypto``.
* :func:`create_reference_tables`  — create the reference + watchlist tables.
* :func:`create_materialized_view` — create ``disclosure_facts`` when possible.
* :func:`refresh_materialized_view`— refresh ``disclosure_facts``.
* :func:`init_db`                  — convenience wrapper used at startup.
"""

import logging
import os

logger = logging.getLogger("analytics")

# ==============================================================================
# DDL
# ==============================================================================

MEMBERS_DDL = """
CREATE TABLE IF NOT EXISTS members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL UNIQUE,
    chamber VARCHAR(16) NOT NULL,
    party VARCHAR(32),
    state VARCHAR(64),
    district VARCHAR(16),
    photo_url TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_members_chamber ON members (chamber);
CREATE INDEX IF NOT EXISTS idx_members_normalized ON members (normalized_name);
"""

COMMITTEES_DDL = """
CREATE TABLE IF NOT EXISTS committees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    chamber VARCHAR(16) NOT NULL,
    UNIQUE (name, chamber)
);
"""

MEMBER_COMMITTEES_DDL = """
CREATE TABLE IF NOT EXISTS member_committees (
    id BIGSERIAL PRIMARY KEY,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    committee_id UUID NOT NULL REFERENCES committees(id) ON DELETE CASCADE,
    role VARCHAR(64),
    session VARCHAR(16),
    UNIQUE (member_id, committee_id, session)
);
CREATE INDEX IF NOT EXISTS idx_member_committees_member
    ON member_committees (member_id);
"""

TICKER_SECTORS_DDL = """
CREATE TABLE IF NOT EXISTS ticker_sectors (
    ticker VARCHAR(32) PRIMARY KEY,
    sector VARCHAR(128),
    industry VARCHAR(128),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ticker_sectors_sector
    ON ticker_sectors (sector);
"""

USER_WATCHLISTS_DDL = """
CREATE TABLE IF NOT EXISTS user_watchlists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    type VARCHAR(16) NOT NULL,
    value VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, type, value)
);
CREATE INDEX IF NOT EXISTS idx_user_watchlists_user
    ON user_watchlists (user_id);
"""

# SQL helper that computes the midpoint of a "$a - $b" disclosure value range.
# Used by the analytics endpoints to aggregate dollar volume.
VALUE_RANGE_MID_FN = """
CREATE OR REPLACE FUNCTION value_range_mid(vr TEXT) RETURNS NUMERIC AS $$
DECLARE
    nums NUMERIC[];
BEGIN
    IF vr IS NULL THEN
        RETURN NULL;
    END IF;
    nums := ARRAY(
        SELECT NULLIF(regexp_replace(m[1], '[^0-9]', '', 'g'), '')::NUMERIC
        FROM regexp_matches(vr, '\\$?[0-9][0-9,]*', 'g') AS m
    );
    IF array_length(nums, 1) IS NULL THEN
        RETURN NULL;
    END IF;
    IF array_length(nums, 1) = 1 THEN
        RETURN nums[1];
    END IF;
    RETURN (nums[1] + nums[2]) / 2;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
"""

# The materialized view is created only when the vectorizer's
# disclosure_embeddings table already exists. It pre-joins member and sector
# metadata so dashboard queries avoid repeated joins.
DISCLOSURE_FACTS_DDL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS disclosure_facts AS
SELECT
    e.id,
    e.doc_id,
    e.item_index,
    e.chamber,
    e.filer_name,
    m.party,
    m.state,
    m.district,
    e.filing_date,
    e.report_type,
    e.is_market_trade,
    e.ticker,
    e.asset_name,
    e.asset_category,
    e.action,
    e.date AS transaction_date,
    e.value_range,
    e.ownership,
    ts.sector,
    ts.industry,
    (e.filing_date - e.date) AS days_to_file
FROM disclosure_embeddings e
LEFT JOIN members m
    ON m.normalized_name = lower(trim(e.filer_name))
LEFT JOIN ticker_sectors ts
    ON ts.ticker = e.ticker;
"""

DISCLOSURE_FACTS_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_id ON disclosure_facts (id);",
    "CREATE INDEX IF NOT EXISTS idx_facts_chamber ON disclosure_facts (chamber);",
    "CREATE INDEX IF NOT EXISTS idx_facts_ticker ON disclosure_facts (ticker);",
    "CREATE INDEX IF NOT EXISTS idx_facts_filer ON disclosure_facts (filer_name);",
    "CREATE INDEX IF NOT EXISTS idx_facts_filing_date ON disclosure_facts (filing_date);",
    "CREATE INDEX IF NOT EXISTS idx_facts_txn_date ON disclosure_facts (transaction_date);",
    "CREATE INDEX IF NOT EXISTS idx_facts_sector ON disclosure_facts (sector);",
    "CREATE INDEX IF NOT EXISTS idx_facts_action ON disclosure_facts (action);",
]


# ==============================================================================
# SCHEMA MANAGEMENT
# ==============================================================================

async def ensure_extensions(conn) -> None:
    """Enable the ``pgcrypto`` extension (for ``gen_random_uuid``)."""
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")


async def create_reference_tables(conn) -> None:
    """Create the reference and personalization tables and helper functions."""
    await conn.execute(VALUE_RANGE_MID_FN)
    await conn.execute(MEMBERS_DDL)
    await conn.execute(COMMITTEES_DDL)
    await conn.execute(MEMBER_COMMITTEES_DDL)
    await conn.execute(TICKER_SECTORS_DDL)
    await conn.execute(USER_WATCHLISTS_DDL)


async def create_materialized_view(conn) -> bool:
    """Create ``disclosure_facts`` if ``disclosure_embeddings`` exists.

    Returns ``True`` when the view is present after this call, ``False`` when the
    source table does not exist yet (the view is created on a later startup once
    the vectorizer has populated the table).
    """
    exists = await conn.fetchval(
        "SELECT to_regclass('public.disclosure_embeddings') IS NOT NULL"
    )
    if not exists:
        logger.info(
            "disclosure_embeddings not present yet; skipping disclosure_facts view."
        )
        return False
    await conn.execute(DISCLOSURE_FACTS_DDL)
    for statement in DISCLOSURE_FACTS_INDEXES:
        await conn.execute(statement)
    logger.info("disclosure_facts materialized view ready.")
    return True


async def refresh_materialized_view(conn) -> None:
    """Refresh ``disclosure_facts`` (no-op when the view does not exist)."""
    exists = await conn.fetchval(
        "SELECT to_regclass('public.disclosure_facts') IS NOT NULL"
    )
    if not exists:
        return
    await conn.execute("REFRESH MATERIALIZED VIEW disclosure_facts;")


async def init_db(pool) -> None:
    """Ensure the extensions, tables, and materialized view exist."""
    async with pool.acquire() as conn:
        await ensure_extensions(conn)
        await create_reference_tables(conn)
        await create_materialized_view(conn)
    logger.info("Analytics schema ready (reference tables + disclosure_facts).")


if __name__ == "__main__":  # pragma: no cover - operator convenience
    import asyncio

    import asyncpg

    async def _main() -> None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise SystemExit("DATABASE_URL must be set.")
        pool = await asyncpg.create_pool(url, min_size=1, max_size=2)
        try:
            await init_db(pool)
        finally:
            await pool.close()

    asyncio.run(_main())
