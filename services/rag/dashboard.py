#!/usr/bin/env python3
"""
LLM-driven dashboard spec generation for the RAG & Query Retrieval Microservice.

Gathers **real** chamber-scoped aggregates from ``disclosure_embeddings`` and
asks the LiteLLM Proxy to synthesize a schema-driven ``DashboardLayoutSpec``
grounded in that data. There are no hardcoded or dummy values: the numeric
series and table rows always come from the database, and the LLM only authors
the presentation copy (titles, descriptions, metric labels).

If the dataset is empty or the LLM is unavailable, the caller returns an error
rather than fabricated content.
"""

import json
import logging
import os
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("rag")

# ==============================================================================
# CONFIGURATION
# ==============================================================================
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://litellm-proxy:4000")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "").strip()
DEFAULT_MODEL = os.getenv("RAG_DEFAULT_MODEL", "openrouter-deepseek-flash")
REQUEST_TIMEOUT = float(os.getenv("RAG_REQUEST_TIMEOUT", "180"))

# Map the UI time-horizon labels to a lookback window in days (None = all time).
HORIZON_DAYS: Dict[str, Optional[int]] = {
    "30 Days": 30,
    "90 Days": 90,
    "YTD": None,  # handled specially (start of current year)
    "1 Year": 365,
    "All Time": None,
}

# SQL helper that computes the midpoint of a "$a - $b" disclosure value range.
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


async def ensure_functions(pool) -> None:
    """Create the ``value_range_mid`` SQL helper (idempotent)."""
    async with pool.acquire() as conn:
        await conn.execute(VALUE_RANGE_MID_FN)


def _horizon_start(horizon: Optional[str]) -> Optional[date]:
    """Resolve a horizon label to an inclusive start date (or None for all time)."""
    if not horizon:
        return None
    if horizon == "YTD":
        return date(date.today().year, 1, 1)
    days = HORIZON_DAYS.get(horizon)
    if days is None:
        return None
    return date.today() - timedelta(days=days)


def _short_label(name: Optional[str]) -> str:
    """Derive a ticker-like label from an asset name (first 5 alphanumerics).

    Used for assets that have no ticker (funds, bonds, unlisted holdings) so the
    Top Traded Assets chart still shows a readable axis label.
    """
    if not name:
        return "—"
    alnum = re.sub(r"[^A-Za-z0-9]", "", name)
    return alnum[:5].upper() or "—"


async def _has_reference_tables(conn) -> bool:
    return bool(
        await conn.fetchval(
            "SELECT to_regclass('public.members') IS NOT NULL "
            "AND to_regclass('public.member_committees') IS NOT NULL "
            "AND to_regclass('public.committees') IS NOT NULL"
        )
    )


async def gather(
    conn,
    chambers: List[str],
    horizon: Optional[str],
) -> Dict[str, Any]:
    """Compute the real dashboard data bundle for the given scope and horizon."""
    table = "disclosure_embeddings"
    days = "(filing_date - date)"
    sector = "asset_category"

    params: List[Any] = [chambers]
    date_clause = ""
    start = _horizon_start(horizon)
    if start is not None:
        params.append(start)
        date_clause = f"AND date >= ${len(params)}::date"

    base_where = f"is_market_trade = TRUE AND chamber = ANY($1) {date_clause}"

    # --- Metrics -------------------------------------------------------------
    metrics_row = await conn.fetchrow(
        f"""
        SELECT
            COALESCE(SUM(value_range_mid(value_range)), 0) AS total_volume,
            COUNT(DISTINCT filer_name) AS active_members,
            COALESCE(SUM(value_range_mid(value_range))
                FILTER (WHERE action ILIKE 'Purchase%'), 0) AS purchases_volume,
            COALESCE(SUM(value_range_mid(value_range))
                FILTER (WHERE action ILIKE 'Sale%'), 0) AS sales_volume,
            COUNT(*) FILTER (WHERE {days} > 45) AS late_filings
        FROM {table}
        WHERE {base_where}
        """,
        *params,
    )
    purchases_volume = float(metrics_row["purchases_volume"] or 0)
    sales_volume = float(metrics_row["sales_volume"] or 0)
    net_flow = purchases_volume - sales_volume

    # --- Monthly volume (purchases vs sales) ---------------------------------
    monthly_rows = await conn.fetch(
        f"""
        SELECT
            to_char(date_trunc('month', date), 'YYYY-MM') AS month,
            COALESCE(SUM(value_range_mid(value_range))
                FILTER (WHERE action ILIKE 'Purchase%'), 0) AS purchases,
            COALESCE(SUM(value_range_mid(value_range))
                FILTER (WHERE action ILIKE 'Sale%'), 0) AS sales
        FROM {table}
        WHERE {base_where} AND date IS NOT NULL
        GROUP BY 1 ORDER BY 1
        """,
        *params,
    )

    # --- Weekly capital flow -------------------------------------------------
    weekly_rows = await conn.fetch(
        f"""
        SELECT
            to_char(date_trunc('week', date), 'YYYY-MM-DD') AS period,
            COALESCE(SUM(value_range_mid(value_range)), 0) AS total_flow,
            COALESCE(SUM(value_range_mid(value_range))
                FILTER (WHERE {sector} ILIKE '%tech%'
                           OR {sector} ILIKE '%semiconductor%'), 0) AS tech_flow
        FROM {table}
        WHERE {base_where} AND date IS NOT NULL
        GROUP BY 1 ORDER BY 1
        """,
        *params,
    )

    # --- Sector distribution -------------------------------------------------
    sector_rows = await conn.fetch(
        f"""
        SELECT
            COALESCE({sector}, 'Other') AS sector,
            COALESCE(SUM(value_range_mid(value_range)), 0) AS value
        FROM {table}
        WHERE {base_where}
        GROUP BY 1 ORDER BY 2 DESC LIMIT 8
        """,
        *params,
    )

    # --- Top traded assets ---------------------------------------------------
    top_rows = await conn.fetch(
        f"""
        SELECT
            ticker, asset_name,
            COALESCE(SUM(value_range_mid(value_range))
                FILTER (WHERE action ILIKE 'Purchase%'), 0) AS purchases_val,
            COALESCE(SUM(value_range_mid(value_range))
                FILTER (WHERE action ILIKE 'Sale%'), 0) AS sales_val,
            COUNT(*) AS trades_count
        FROM {table}
        WHERE {base_where}
        GROUP BY ticker, asset_name
        ORDER BY (COALESCE(SUM(value_range_mid(value_range)), 0)) DESC
        LIMIT 10
        """,
        *params,
    )

    # --- Late filings --------------------------------------------------------
    late_rows = await conn.fetch(
        f"""
        SELECT filer_name, chamber, ticker, asset_name,
               date AS trade_date, filing_date AS filed_date,
               {days} AS days_late
        FROM {table}
        WHERE {base_where} AND {days} > 45
        ORDER BY days_late DESC LIMIT 10
        """,
        *params,
    )

    # --- Committee vs sector conflicts (only when reference data exists) -----
    committee_rows: List[Any] = []
    if await _has_reference_tables(conn):
        committee_rows = await conn.fetch(
            f"""
            SELECT m.full_name AS member, c.name AS committee,
                   f.ticker, f.asset_category AS sector,
                   f.value_range AS estimated_vol
            FROM {table} f
            JOIN members m ON m.normalized_name = lower(trim(f.filer_name))
            JOIN member_committees mc ON mc.member_id = m.id
            JOIN committees c ON c.id = mc.committee_id
            WHERE f.is_market_trade = TRUE AND f.chamber = ANY($1)
            ORDER BY f.filing_date DESC NULLS LAST LIMIT 8
            """,
            chambers,
        )

    def _num(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    return {
        "metrics": {
            "total_volume": _num(metrics_row["total_volume"]),
            "active_members": int(metrics_row["active_members"] or 0),
            "net_flow": net_flow,
            "late_filings_count": int(metrics_row["late_filings"] or 0),
        },
        "monthly": [
            {
                "month": r["month"],
                "purchases": _num(r["purchases"]),
                "sales": _num(r["sales"]),
            }
            for r in monthly_rows
        ],
        "weekly": [
            {
                "period": r["period"],
                "total_flow": _num(r["total_flow"]),
                "tech_flow": _num(r["tech_flow"]),
            }
            for r in weekly_rows
        ],
        "sectors": [
            {"sector": r["sector"], "value": _num(r["value"])} for r in sector_rows
        ],
        "top_assets": [
            {
                "ticker": r["ticker"],
                "asset_name": r["asset_name"],
                "label": r["ticker"] or _short_label(r["asset_name"]),
                "purchases_val": _num(r["purchases_val"]),
                "sales_val": _num(r["sales_val"]),
                "trades_count": int(r["trades_count"] or 0),
            }
            for r in top_rows
        ],
        "late_filings": [
            {
                "filer_name": r["filer_name"],
                "chamber": r["chamber"],
                "ticker": r["ticker"],
                "asset_name": r["asset_name"],
                "trade_date": r["trade_date"].isoformat() if r["trade_date"] else None,
                "filed_date": r["filed_date"].isoformat() if r["filed_date"] else None,
                "days_late": int(r["days_late"] or 0),
            }
            for r in late_rows
        ],
        "committee_conflicts": [
            {
                "member": r["member"],
                "committee": r["committee"],
                "ticker": r["ticker"],
                "sector": r["sector"],
                "estimated_vol": r["estimated_vol"],
            }
            for r in committee_rows
        ],
    }


# ==============================================================================
# LLM SYNTHESIS
# ==============================================================================
SYSTEM_PROMPT = (
    "You are a congressional financial-intelligence analyst. You are given REAL "
    "aggregated disclosure data as JSON. Produce a single JSON object (no prose, "
    "no markdown fences) describing a dashboard layout. Use ONLY the numbers and "
    "entities provided — never invent values. The object must have this shape:\n"
    "{\n"
    '  "status": "success",\n'
    '  "chamber_scope": [<chambers>],\n'
    '  "time_horizon": "<horizon>",\n'
    '  "generated_at": "<iso8601>",\n'
    '  "metrics": { "total_volume": <num>, "active_members": <num>, '
    '"net_flow": <num>, "late_filings_count": <num> },\n'
    '  "widgets": [\n'
    '    { "id": "kpi-volume", "widget_type": "metric_card", "title": "...", '
    '"span": 1, "data": { "category": "...", "value": "...", '
    '"trend_label": "..." } },\n'
    '    { "id": "kpi-members", "widget_type": "metric_card", ... },\n'
    '    { "id": "kpi-netflow", "widget_type": "metric_card", ... },\n'
    '    { "id": "kpi-late", "widget_type": "metric_card", ... },\n'
    '    { "id": "chart-monthly-volume", "widget_type": "bar_chart", '
    '"title": "...", "description": "...", "span": 2, '
    '"data": { "xAxisKey": "month", "series": [ {"dataKey":"purchases",'
    '"name":"Purchases","color":"#10b981","stackId":"a"}, {"dataKey":"sales",'
    '"name":"Sales","color":"#f43f5e","stackId":"a"} ] } },\n'
    '    { "id": "chart-volume-timeline", "widget_type": "line_chart", '
    '"span": 2, "data": { "xAxisKey": "period", "series": [ '
    '{"dataKey":"total_flow","name":"Total Capital Flow","color":"#0ea5e9"}, '
    '{"dataKey":"tech_flow","name":"Tech / Semi Sector","color":"#8b5cf6"} ] } },\n'
    '    { "id": "chart-sector-donut", "widget_type": "pie_chart", "span": 2, '
    '"data": { "nameKey": "sector", "valueKey": "value" } },\n'
    '    { "id": "chart-top-assets", "widget_type": "bar_chart", "span": 2, '
    '"data": { "xAxisKey": "label", "orientation": "horizontal", '
    '"series": [ {"dataKey":"purchases_val","name":"Purchases","color":"#10b981",'
    '"stackId":"a"}, {"dataKey":"sales_val","name":"Sales","color":"#f43f5e",'
    '"stackId":"a"} ] } },\n'
    '    { "id": "table-top-assets", "widget_type": "data_table", "span": 2, '
    '"data": { "columns": [ {"key":"ticker","header":"Ticker","monospace":true}, '
    '{"key":"asset_name","header":"Asset Name"}, '
    '{"key":"purchases_val","header":"Total Bought","align":"right"}, '
    '{"key":"sales_val","header":"Total Sold","align":"right"}, '
    '{"key":"trades_count","header":"Trades","align":"center"} ] } },\n'
    '    { "id": "table-late-filings", "widget_type": "data_table", "span": 2, '
    '"data": { "columns": [ {"key":"filer_name","header":"Filer Name"}, '
    '{"key":"chamber","header":"Chamber"}, {"key":"ticker","header":"Ticker"}, '
    '{"key":"trade_date","header":"Trade Date"}, '
    '{"key":"filed_date","header":"Filed Date"}, '
    '{"key":"days_late","header":"Days Late","align":"center"} ] } },\n'
    '    { "id": "table-committee-conflicts", "widget_type": "data_table", '
    '"span": 2, "data": { "columns": [ {"key":"member","header":"Member"}, '
    '{"key":"committee","header":"Committee"}, {"key":"ticker","header":"Ticker"}, '
    '{"key":"sector","header":"Sector"}, '
    '{"key":"estimated_vol","header":"Volume Est.","align":"right"} ] } }\n'
    "  ]\n"
    "}\n"
    "Write concise, professional titles/descriptions grounded in the data. "
    "Emit every widget id listed above, in that order."
)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


# Deterministic layout: KPI cards span 1 (compact row), the monthly bar and
# weekly line share a row (span 2 each), the sector donut and the top-assets
# bar share a row (span 2 each), and the tables pair up (span 2 each).
LAYOUT_SPANS: Dict[str, int] = {
    "kpi-volume": 1,
    "kpi-members": 1,
    "kpi-netflow": 1,
    "kpi-late": 1,
    "chart-monthly-volume": 2,
    "chart-volume-timeline": 2,
    "chart-sector-donut": 2,
    "chart-top-assets": 2,
    "table-top-assets": 2,
    "table-late-filings": 2,
    "table-committee-conflicts": 2,
}

LAYOUT_ORDER: List[str] = [
    "kpi-volume",
    "kpi-members",
    "kpi-netflow",
    "kpi-late",
    "chart-monthly-volume",
    "chart-volume-timeline",
    "chart-sector-donut",
    "chart-top-assets",
    "table-top-assets",
    "table-late-filings",
    "table-committee-conflicts",
]


def _enforce_layout(spec: Dict[str, Any]) -> None:
    """Force a balanced, predictable widget order and grid span."""
    widgets = spec.get("widgets", [])
    by_id = {w.get("id"): w for w in widgets if isinstance(w, dict)}
    for widget_id, span in LAYOUT_SPANS.items():
        widget = by_id.get(widget_id)
        if widget is not None:
            widget["span"] = span
    ordered = [by_id[i] for i in LAYOUT_ORDER if i in by_id]
    known = set(LAYOUT_ORDER)
    ordered += [w for w in widgets if isinstance(w, dict) and w.get("id") not in known]
    spec["widgets"] = ordered


def _inject_data(spec: Dict[str, Any], data: Dict[str, Any]) -> None:
    """Overwrite widget data arrays with the real aggregates (by widget id)."""
    by_id = {w.get("id"): w for w in spec.get("widgets", [])}
    mapping = {
        "chart-monthly-volume": data["monthly"],
        "chart-volume-timeline": data["weekly"],
        "chart-sector-donut": data["sectors"],
        "chart-top-assets": data["top_assets"],
        "table-top-assets": data["top_assets"],
        "table-late-filings": data["late_filings"],
        "table-committee-conflicts": data["committee_conflicts"],
    }
    for widget_id, items in mapping.items():
        widget = by_id.get(widget_id)
        if widget and isinstance(widget.get("data"), dict):
            if widget.get("widget_type") == "data_table":
                widget["data"]["rows"] = items
                widget["data"]["total_count"] = len(items)
                widget["data"].setdefault("empty_message", "No records in scope.")
            else:
                widget["data"]["items"] = items


def synthesize_spec(
    data: Dict[str, Any],
    chambers: List[str],
    horizon: Optional[str],
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask the LLM to author the dashboard spec, then inject the real data."""
    if not LITELLM_MASTER_KEY:
        raise RuntimeError("LITELLM_MASTER_KEY is not configured.")

    resolved_model = model or DEFAULT_MODEL
    user_content = json.dumps(
        {
            "chamber_scope": chambers,
            "time_horizon": horizon or "All Time",
            "data": data,
        },
        default=str,
    )

    base = LITELLM_PROXY_URL.rstrip("/")
    headers = {
        "Authorization": f"Bearer {LITELLM_MASTER_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
    }

    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.post(
            f"{base}/v1/chat/completions", headers=headers, json=payload
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"LiteLLM Proxy returned HTTP {response.status_code} for dashboard "
                f"synthesis: {response.text[:500]}"
            )
        body = response.json()

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LiteLLM response shape: {body}") from exc

    try:
        spec = json.loads(_strip_fences(content))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"LLM did not return valid JSON: {content[:500]}") from exc

    if not isinstance(spec, dict) or not isinstance(spec.get("widgets"), list):
        raise RuntimeError("LLM returned a spec without a widgets array.")

    # Force the real metrics and inject the real data arrays.
    spec["status"] = "success"
    spec["chamber_scope"] = chambers
    spec["time_horizon"] = horizon or "All Time"
    spec["metrics"] = data["metrics"]
    _inject_data(spec, data)
    _enforce_layout(spec)
    return spec
