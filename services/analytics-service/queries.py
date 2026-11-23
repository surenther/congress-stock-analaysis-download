#!/usr/bin/env python3
"""
SQL query builders for the Analytics Microservice.

Each builder returns a ``(sql, params)`` tuple using asyncpg positional
parameters (``$1``, ``$2``, ...). Chamber scoping is always applied first so a
caller can never read outside their ``allowed_chambers`` grant.
"""

import logging
from typing import Any, List, Optional, Tuple

logger = logging.getLogger("analytics")

ALL_CHAMBERS: List[str] = ["House", "Senate"]

# SQL expression computing the midpoint of a "$a - $b" value range.
VALUE_MID = "value_range_mid(value_range)"

# Columns the data grid may be sorted by (whitelist to prevent SQL injection).
SORTABLE_COLUMNS = {
    "filing_date",
    "transaction_date",
    "ticker",
    "filer_name",
    "action",
    "value_range",
    "chamber",
    "sector",
}


async def resolve_facts_table(conn) -> Optional[str]:
    """Return the analytics source table/view, or ``None`` if unavailable."""
    return await conn.fetchval(
        "SELECT CASE "
        "WHEN to_regclass('public.disclosure_facts') IS NOT NULL "
        "THEN 'disclosure_facts' "
        "WHEN to_regclass('public.disclosure_embeddings') IS NOT NULL "
        "THEN 'disclosure_embeddings' "
        "ELSE NULL END"
    )


def _chamber_clause(
    chambers: List[str], params: List[Any], column: str = "chamber"
) -> str:
    params.append(chambers)
    return f"{column} = ANY(${len(params)})"


def _date_clauses(
    start: Optional[str],
    end: Optional[str],
    params: List[Any],
    column: str = "transaction_date",
) -> List[str]:
    clauses: List[str] = []
    if start:
        params.append(start)
        clauses.append(f"{column} >= ${len(params)}::date")
    if end:
        params.append(end)
        clauses.append(f"{column} <= ${len(params)}::date")
    return clauses


def top_assets_sql(
    table: str,
    chambers: List[str],
    action: Optional[str],
    start: Optional[str],
    end: Optional[str],
    limit: int,
) -> Tuple[str, List[Any]]:
    """Top traded assets by trade count and dollar volume."""
    params: List[Any] = []
    where = ["is_market_trade = TRUE", _chamber_clause(chambers, params)]
    if action:
        params.append(action)
        where.append(f"action = ${len(params)}")
    where += _date_clauses(start, end, params)
    params.append(limit)
    sql = f"""
        SELECT ticker, asset_name, asset_category, action,
               COUNT(*) AS trade_count,
               COALESCE(SUM({VALUE_MID}), 0) AS total_value
        FROM {table}
        WHERE {' AND '.join(where)}
        GROUP BY ticker, asset_name, asset_category, action
        ORDER BY trade_count DESC, total_value DESC
        LIMIT ${len(params)}
    """
    return sql, params


def volume_trends_sql(
    table: str,
    chambers: List[str],
    granularity: str,
    start: Optional[str],
    end: Optional[str],
) -> Tuple[str, List[Any]]:
    """Trading volume time series grouped by period and action."""
    params: List[Any] = []
    where = ["is_market_trade = TRUE", _chamber_clause(chambers, params)]
    where += _date_clauses(start, end, params)
    params.append(granularity)
    sql = f"""
        SELECT date_trunc(${len(params)}, transaction_date)::date AS period,
               action,
               COUNT(*) AS trade_count,
               COALESCE(SUM({VALUE_MID}), 0) AS total_value
        FROM {table}
        WHERE {' AND '.join(where)}
        GROUP BY period, action
        ORDER BY period ASC, action ASC
    """
    return sql, params


def late_filings_sql(
    table: str,
    chambers: List[str],
    limit: int,
    offset: int,
) -> Tuple[str, List[Any]]:
    """Disclosures filed beyond the 45-day STOCK Act window."""
    params: List[Any] = []
    where = [
        "is_market_trade = TRUE",
        "days_to_file IS NOT NULL",
        "days_to_file > 45",
        _chamber_clause(chambers, params),
    ]
    params.append(limit)
    limit_idx = len(params)
    params.append(offset)
    offset_idx = len(params)
    sql = f"""
        SELECT doc_id, filer_name, chamber, filing_date, transaction_date,
               days_to_file, ticker, asset_name, action, value_range
        FROM {table}
        WHERE {' AND '.join(where)}
        ORDER BY days_to_file DESC
        LIMIT ${limit_idx} OFFSET ${offset_idx}
    """
    return sql, params


def late_filings_count_sql(
    table: str, chambers: List[str]
) -> Tuple[str, List[Any]]:
    params: List[Any] = []
    where = [
        "is_market_trade = TRUE",
        "days_to_file IS NOT NULL",
        "days_to_file > 45",
        _chamber_clause(chambers, params),
    ]
    sql = f"SELECT COUNT(*) FROM {table} WHERE {' AND '.join(where)}"
    return sql, params


def committee_sector_sql(
    table: str, chambers: List[str]
) -> Tuple[str, List[Any]]:
    """Correlate member committee assignments with traded sectors."""
    params: List[Any] = []
    where = [
        "f.is_market_trade = TRUE",
        "f.sector IS NOT NULL",
        _chamber_clause(chambers, params, column="f.chamber"),
    ]
    sql = f"""
        SELECT c.name AS committee, f.sector,
               COUNT(*) AS trade_count,
               COALESCE(SUM(value_range_mid(f.value_range)), 0) AS total_value
        FROM {table} f
        JOIN members m ON m.normalized_name = lower(trim(f.filer_name))
        JOIN member_committees mc ON mc.member_id = m.id
        JOIN committees c ON c.id = mc.committee_id
        WHERE {' AND '.join(where)}
        GROUP BY c.name, f.sector
        ORDER BY trade_count DESC
    """
    return sql, params


def _disclosure_where(
    chambers: List[str],
    ticker: Optional[str],
    member: Optional[str],
    action: Optional[str],
    start: Optional[str],
    end: Optional[str],
    min_value: Optional[float],
    max_value: Optional[float],
    params: List[Any],
) -> List[str]:
    where = ["is_market_trade = TRUE", _chamber_clause(chambers, params)]
    if ticker:
        params.append(ticker.upper())
        where.append(f"UPPER(ticker) = ${len(params)}")
    if member:
        params.append(f"%{member.lower()}%")
        where.append(f"LOWER(filer_name) LIKE ${len(params)}")
    if action:
        params.append(action)
        where.append(f"action = ${len(params)}")
    where += _date_clauses(start, end, params)
    if min_value is not None:
        params.append(min_value)
        where.append(f"{VALUE_MID} >= ${len(params)}")
    if max_value is not None:
        params.append(max_value)
        where.append(f"{VALUE_MID} <= ${len(params)}")
    return where


def disclosures_sql(
    table: str,
    chambers: List[str],
    ticker: Optional[str],
    member: Optional[str],
    action: Optional[str],
    start: Optional[str],
    end: Optional[str],
    min_value: Optional[float],
    max_value: Optional[float],
    sort: str,
    order: str,
    limit: int,
    offset: int,
) -> Tuple[str, List[Any]]:
    """Filtered, sorted, paginated disclosure grid."""
    params: List[Any] = []
    where = _disclosure_where(
        chambers, ticker, member, action, start, end, min_value, max_value, params
    )
    sort_col = sort if sort in SORTABLE_COLUMNS else "filing_date"
    direction = "ASC" if order.lower() == "asc" else "DESC"
    params.append(limit)
    limit_idx = len(params)
    params.append(offset)
    offset_idx = len(params)
    sql = f"""
        SELECT doc_id, filer_name, chamber, party, state, filing_date,
               transaction_date, days_to_file, ticker, asset_name,
               asset_category, action, value_range, ownership, sector
        FROM {table}
        WHERE {' AND '.join(where)}
        ORDER BY {sort_col} {direction} NULLS LAST
        LIMIT ${limit_idx} OFFSET ${offset_idx}
    """
    return sql, params


def disclosures_count_sql(
    table: str,
    chambers: List[str],
    ticker: Optional[str],
    member: Optional[str],
    action: Optional[str],
    start: Optional[str],
    end: Optional[str],
    min_value: Optional[float],
    max_value: Optional[float],
) -> Tuple[str, List[Any]]:
    params: List[Any] = []
    where = _disclosure_where(
        chambers, ticker, member, action, start, end, min_value, max_value, params
    )
    sql = f"SELECT COUNT(*) FROM {table} WHERE {' AND '.join(where)}"
    return sql, params


def watchlist_feed_sql(
    table: str,
    chambers: List[str],
    members: List[str],
    tickers: List[str],
    limit: int,
) -> Tuple[str, List[Any]]:
    """Recent disclosures matching the user's watched members or tickers."""
    params: List[Any] = []
    where = ["is_market_trade = TRUE", _chamber_clause(chambers, params)]
    match_clauses: List[str] = []
    if members:
        params.append([m.lower() for m in members])
        match_clauses.append(f"LOWER(filer_name) = ANY(${len(params)})")
    if tickers:
        params.append([t.upper() for t in tickers])
        match_clauses.append(f"UPPER(ticker) = ANY(${len(params)})")
    if not match_clauses:
        # No watchlist entries: return an empty result set deterministically.
        return "SELECT * FROM " + table + " WHERE FALSE", []
    where.append("(" + " OR ".join(match_clauses) + ")")
    params.append(limit)
    sql = f"""
        SELECT doc_id, filer_name, chamber, filing_date, transaction_date,
               ticker, asset_name, action, value_range
        FROM {table}
        WHERE {' AND '.join(where)}
        ORDER BY filing_date DESC NULLS LAST
        LIMIT ${len(params)}
    """
    return sql, params
