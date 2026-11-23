#!/usr/bin/env python3
"""
Reference-data seeding for the Analytics Microservice.

Loads member, committee, and ticker-sector reference data used by the
committee/sector correlation and sector analytics. Data is read from optional
JSON files in ``services/analytics-service/data/``:

* ``members.json``           — [{full_name, chamber, party, state, district, photo_url}]
* ``committees.json``        — [{name, chamber}]
* ``member_committees.json`` — [{member, committee, role, session}]
* ``ticker_sectors.json``    — [{ticker, sector, industry}]

A small built-in ticker→sector map is always applied so sector analytics work
out of the box. Run standalone with ``python seed.py``.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("analytics")

DATA_DIR = Path(__file__).resolve().parent / "data"

# Minimal built-in ticker -> sector map (extend via data/ticker_sectors.json).
BUILTIN_TICKER_SECTORS: Dict[str, Dict[str, str]] = {
    "NVDA": {"sector": "Technology", "industry": "Semiconductors"},
    "AMD": {"sector": "Technology", "industry": "Semiconductors"},
    "INTC": {"sector": "Technology", "industry": "Semiconductors"},
    "AAPL": {"sector": "Technology", "industry": "Consumer Electronics"},
    "MSFT": {"sector": "Technology", "industry": "Software"},
    "GOOGL": {"sector": "Communication Services", "industry": "Internet Content"},
    "META": {"sector": "Communication Services", "industry": "Internet Content"},
    "AMZN": {"sector": "Consumer Discretionary", "industry": "Internet Retail"},
    "TSLA": {"sector": "Consumer Discretionary", "industry": "Auto Manufacturers"},
    "JPM": {"sector": "Financials", "industry": "Banks"},
    "BAC": {"sector": "Financials", "industry": "Banks"},
    "GS": {"sector": "Financials", "industry": "Capital Markets"},
    "XOM": {"sector": "Energy", "industry": "Oil & Gas"},
    "CVX": {"sector": "Energy", "industry": "Oil & Gas"},
    "PFE": {"sector": "Health Care", "industry": "Pharmaceuticals"},
    "JNJ": {"sector": "Health Care", "industry": "Pharmaceuticals"},
    "UNH": {"sector": "Health Care", "industry": "Healthcare Plans"},
    "LMT": {"sector": "Industrials", "industry": "Aerospace & Defense"},
    "RTX": {"sector": "Industrials", "industry": "Aerospace & Defense"},
    "BA": {"sector": "Industrials", "industry": "Aerospace & Defense"},
    "NOC": {"sector": "Industrials", "industry": "Aerospace & Defense"},
    "GD": {"sector": "Industrials", "industry": "Aerospace & Defense"},
    "SPY": {"sector": "ETF", "industry": "Broad Market"},
    "QQQ": {"sector": "ETF", "industry": "Technology"},
    "BTC": {"sector": "Crypto", "industry": "Digital Assets"},
    "ETH": {"sector": "Crypto", "industry": "Digital Assets"},
}


def _load_json(name: str) -> List[Dict[str, Any]]:
    path = DATA_DIR / name
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - data dependent
        logger.warning("Failed to read %s: %s", path, exc)
        return []


def _normalize(name: str) -> str:
    return " ".join(name.lower().split())


async def seed_ticker_sectors(conn) -> int:
    rows = dict(BUILTIN_TICKER_SECTORS)
    for item in _load_json("ticker_sectors.json"):
        ticker = str(item.get("ticker", "")).upper()
        if ticker:
            rows[ticker] = {
                "sector": item.get("sector"),
                "industry": item.get("industry"),
            }
    for ticker, meta in rows.items():
        await conn.execute(
            "INSERT INTO ticker_sectors (ticker, sector, industry) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (ticker) DO UPDATE SET sector = EXCLUDED.sector, "
            "industry = EXCLUDED.industry, updated_at = NOW()",
            ticker,
            meta.get("sector"),
            meta.get("industry"),
        )
    return len(rows)


async def seed_members(conn) -> int:
    count = 0
    for member in _load_json("members.json"):
        full_name = member.get("full_name")
        if not full_name:
            continue
        await conn.execute(
            "INSERT INTO members "
            "(full_name, normalized_name, chamber, party, state, district, photo_url) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) "
            "ON CONFLICT (normalized_name) DO UPDATE SET "
            "full_name = EXCLUDED.full_name, chamber = EXCLUDED.chamber, "
            "party = EXCLUDED.party, state = EXCLUDED.state, "
            "district = EXCLUDED.district, photo_url = EXCLUDED.photo_url, "
            "updated_at = NOW()",
            full_name,
            _normalize(full_name),
            member.get("chamber"),
            member.get("party"),
            member.get("state"),
            member.get("district"),
            member.get("photo_url"),
        )
        count += 1
    return count


async def seed_committees(conn) -> int:
    count = 0
    for committee in _load_json("committees.json"):
        name = committee.get("name")
        chamber = committee.get("chamber")
        if not name or not chamber:
            continue
        await conn.execute(
            "INSERT INTO committees (name, chamber) VALUES ($1, $2) "
            "ON CONFLICT (name, chamber) DO NOTHING",
            name,
            chamber,
        )
        count += 1
    return count


async def seed_member_committees(conn) -> int:
    count = 0
    for assignment in _load_json("member_committees.json"):
        member_name = assignment.get("member")
        committee_name = assignment.get("committee")
        if not member_name or not committee_name:
            continue
        member_id = await conn.fetchval(
            "SELECT id FROM members WHERE normalized_name = $1",
            _normalize(member_name),
        )
        committee_id = await conn.fetchval(
            "SELECT id FROM committees WHERE name = $1 LIMIT 1", committee_name
        )
        if not member_id or not committee_id:
            continue
        await conn.execute(
            "INSERT INTO member_committees (member_id, committee_id, role, session) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
            member_id,
            committee_id,
            assignment.get("role"),
            assignment.get("session"),
        )
        count += 1
    return count


async def seed_all(pool) -> Dict[str, int]:
    """Seed all reference data and return per-table row counts."""
    async with pool.acquire() as conn:
        result = {
            "ticker_sectors": await seed_ticker_sectors(conn),
            "members": await seed_members(conn),
            "committees": await seed_committees(conn),
            "member_committees": await seed_member_committees(conn),
        }
    logger.info("Reference data seeded: %s", result)
    return result


if __name__ == "__main__":  # pragma: no cover - operator convenience
    import asyncpg

    async def _main() -> None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise SystemExit("DATABASE_URL must be set.")
        pool = await asyncpg.create_pool(url, min_size=1, max_size=2)
        try:
            await seed_all(pool)
        finally:
            await pool.close()

    asyncio.run(_main())
