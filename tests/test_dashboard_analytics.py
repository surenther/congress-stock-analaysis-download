#!/usr/bin/env python3
"""
Unit tests for the deterministic analytics engine and asset-class filtering.

These are fast, no-LLM, no-DB tests that exercise the pure helpers in
``services/rag/dashboard.py`` and ``services/rag/retriever.py``:

* asset-class normalization and SQL predicate mapping,
* readable horizontal-bar labels,
* deterministic KPI metric injection (real numbers, never LLM-authored),
* donut morphing (action breakdown vs asset-class distribution),
* the retriever's asset-class predicate.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Make the RAG service modules importable and satisfy the fail-fast master-key
# check in retriever.py before importing it.
_RAG_DIR = Path(__file__).resolve().parent.parent / "services" / "rag"
sys.path.insert(0, str(_RAG_DIR))
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-test-key")

import dashboard  # noqa: E402
import retriever  # noqa: E402

pytestmark = pytest.mark.contract


# ------------------------------------------------------------------------------
# Asset-class normalization + predicate
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["Stock", "Bond", "Other", "All"])
def test_normalize_asset_class_accepts_supported(value: str):
    assert dashboard._normalize_asset_class(value) == value


@pytest.mark.parametrize("value", [None, "", "stock", "Crypto", "Mutual Fund/ETF"])
def test_normalize_asset_class_falls_back_to_all(value):
    assert dashboard._normalize_asset_class(value) == "All"


def test_asset_class_clause_stock_and_bond():
    assert dashboard._asset_class_clause("Stock") == "AND asset_category = 'Stock'"
    assert dashboard._asset_class_clause("Bond") == "AND asset_category = 'Bond'"


def test_asset_class_clause_other_excludes_stock_and_bond():
    clause = dashboard._asset_class_clause("Other")
    assert "NOT IN ('Stock', 'Bond')" in clause
    assert clause.startswith("AND ")


def test_asset_class_clause_all_is_empty():
    assert dashboard._asset_class_clause("All") == ""
    assert dashboard._asset_class_clause(None) == ""


# ------------------------------------------------------------------------------
# Readable horizontal-bar labels
# ------------------------------------------------------------------------------
def test_readable_label_prefers_ticker():
    assert dashboard._readable_label("NVDA", "NVIDIA Corporation") == "NVDA"


def test_readable_label_uses_readable_name_without_ticker():
    # No truncated uppercase prefix like "USTRE" — a readable title instead.
    label = dashboard._readable_label(None, "US Treasury Note")
    assert label == "US Treasury Note"


def test_readable_label_truncates_long_name_at_word_boundary():
    label = dashboard._readable_label(None, "California Municipal Bond Fund Series A")
    assert label.endswith("…")
    assert len(label) <= 25


def test_readable_label_empty_is_dash():
    assert dashboard._readable_label(None, None) == "—"
    assert dashboard._readable_label(None, "") == "—"


# ------------------------------------------------------------------------------
# Deterministic KPI metric injection
# ------------------------------------------------------------------------------
def _kpi_spec() -> dict:
    return {
        "widgets": [
            {"id": "kpi-volume", "widget_type": "metric_card", "data": {"value": "15.0M", "prefix": "$"}},
            {"id": "kpi-members", "widget_type": "metric_card", "data": {"value": "42"}},
            {"id": "kpi-netflow", "widget_type": "metric_card", "data": {"value": "1.2M"}},
            {"id": "kpi-late", "widget_type": "metric_card", "data": {"value": "3"}},
        ]
    }


def test_inject_metrics_forces_real_values_and_format():
    spec = _kpi_spec()
    data = {
        "metrics": {
            "total_volume": 15000000.5,
            "active_members": 42,
            "net_flow": 375000.5,
            "late_filings_count": 3,
        }
    }
    dashboard._inject_metrics(spec, data)
    by_id = {w["id"]: w for w in spec["widgets"]}

    assert by_id["kpi-volume"]["data"]["value"] == 15000000.5
    assert by_id["kpi-volume"]["data"]["format"] == "currency"
    # LLM-authored prefix is dropped so the formatted value is clean.
    assert "prefix" not in by_id["kpi-volume"]["data"]

    assert by_id["kpi-members"]["data"]["value"] == 42
    assert by_id["kpi-members"]["data"]["format"] == "number"
    assert by_id["kpi-netflow"]["data"]["format"] == "currency"
    assert by_id["kpi-late"]["data"]["format"] == "number"


# ------------------------------------------------------------------------------
# Donut morphing
# ------------------------------------------------------------------------------
def _donut_spec() -> dict:
    return {
        "widgets": [
            {
                "id": "chart-sector-donut",
                "widget_type": "pie_chart",
                "data": {"nameKey": "sector", "valueKey": "value"},
            }
        ]
    }


def test_inject_data_donut_action_mode():
    spec = _donut_spec()
    data = {
        "monthly": [],
        "weekly": [],
        "top_assets": [],
        "late_filings": [],
        "committee_conflicts": [],
        "donut": {
            "mode": "action",
            "name_key": "name",
            "value_key": "value",
            "items": [
                {"name": "Purchases", "value": 100.0},
                {"name": "Sales", "value": 40.0},
                {"name": "Holdings / Exchanges", "value": 5.0},
            ],
        },
    }
    dashboard._inject_data(spec, data)
    donut = spec["widgets"][0]["data"]
    assert donut["nameKey"] == "name"
    assert donut["valueKey"] == "value"
    assert [i["name"] for i in donut["items"]] == [
        "Purchases",
        "Sales",
        "Holdings / Exchanges",
    ]


def test_inject_data_donut_class_mode():
    spec = _donut_spec()
    data = {
        "monthly": [],
        "weekly": [],
        "top_assets": [],
        "late_filings": [],
        "committee_conflicts": [],
        "donut": {
            "mode": "class",
            "name_key": "name",
            "value_key": "value",
            "items": [
                {"name": "Stock", "value": 200.0},
                {"name": "Bond", "value": 50.0},
            ],
        },
    }
    dashboard._inject_data(spec, data)
    donut = spec["widgets"][0]["data"]
    assert [i["name"] for i in donut["items"]] == ["Stock", "Bond"]


# ------------------------------------------------------------------------------
# Retriever asset-class predicate
# ------------------------------------------------------------------------------
def test_retriever_asset_class_predicate_stock():
    assert retriever._asset_class_predicate("Stock") == "AND asset_category = 'Stock'"


def test_retriever_asset_class_predicate_other():
    predicate = retriever._asset_class_predicate("Other")
    assert "NOT IN ('Stock', 'Bond')" in predicate


def test_retriever_asset_class_predicate_all_is_empty():
    assert retriever._asset_class_predicate("All") == ""
    assert retriever._asset_class_predicate(None) == ""


def test_search_sql_has_asset_predicate_placeholder():
    # The template must expose the {asset_predicate} slot used by hybrid_search.
    assert "{asset_predicate}" in retriever._SEARCH_SQL
    rendered = retriever._SEARCH_SQL.format(
        asset_predicate=retriever._asset_class_predicate("Stock")
    )
    assert "asset_category = 'Stock'" in rendered
