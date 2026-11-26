#!/usr/bin/env python3
"""
Unit tests for the RAG synthesis engine's late-filing computation and
watchlist-aware system prompt (services/rag/rag_engine.py).

Fast, no-LLM, no-DB tests.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_RAG_DIR = Path(__file__).resolve().parent.parent / "services" / "rag"
sys.path.insert(0, str(_RAG_DIR))
# rag_engine fails fast on a missing master key; satisfy it before import.
os.environ.setdefault("LITELLM_MASTER_KEY", "sk-test-key")

import rag_engine  # noqa: E402

pytestmark = pytest.mark.contract


# ------------------------------------------------------------------------------
# _late_fields — mirrors dashboard._late_filing_predicate
# ------------------------------------------------------------------------------
def test_late_fields_ptr_over_45_days_is_late():
    days, is_late = rag_engine._late_fields(
        {"filing_date": "2025-03-01", "date": "2025-01-01", "report_type": "PTR"}
    )
    assert days == 59
    assert is_late is True


def test_late_fields_ptr_within_45_days_is_not_late():
    days, is_late = rag_engine._late_fields(
        {"filing_date": "2025-02-01", "date": "2025-01-01", "report_type": "PTR"}
    )
    assert days == 31
    assert is_late is False


def test_late_fields_exactly_45_days_is_not_late():
    # 45 days is the deadline; only > 45 is late.
    days, is_late = rag_engine._late_fields(
        {"filing_date": "2025-02-15", "date": "2025-01-01", "report_type": "PTR"}
    )
    assert days == 45
    assert is_late is False


def test_late_fields_annual_report_never_late():
    days, is_late = rag_engine._late_fields(
        {"filing_date": "2025-06-01", "date": "2025-01-01", "report_type": "Annual"}
    )
    assert days == 151
    assert is_late is False


def test_late_fields_null_report_type_treated_as_ptr():
    days, is_late = rag_engine._late_fields(
        {"filing_date": "2025-03-01", "date": "2025-01-01", "report_type": None}
    )
    assert is_late is True


def test_late_fields_missing_dates_return_none():
    assert rag_engine._late_fields({"filing_date": None, "date": "2025-01-01"}) == (
        None,
        None,
    )
    assert rag_engine._late_fields({"filing_date": "2025-01-01", "date": None}) == (
        None,
        None,
    )


def test_late_fields_negative_gap_returns_none():
    # Filing before the trade (clerical typo) is not a valid interval.
    assert rag_engine._late_fields(
        {"filing_date": "2024-12-01", "date": "2025-01-01", "report_type": "PTR"}
    ) == (None, None)


# ------------------------------------------------------------------------------
# System prompt — watchlist awareness
# ------------------------------------------------------------------------------
def test_build_system_prompt_includes_watchlist():
    prompt = rag_engine.build_system_prompt(
        ["House"], {"members": ["josh gottheimer"], "tickers": ["NVDA"]}
    )
    assert "josh gottheimer" in prompt
    assert "NVDA" in prompt


def test_build_system_prompt_without_watchlist_says_none():
    prompt = rag_engine.build_system_prompt(["House"])
    assert "watchlist" in prompt.lower()
    assert "none" in prompt.lower()


def test_build_system_prompt_mentions_late_rule():
    prompt = rag_engine.build_system_prompt(["House"])
    assert "45" in prompt
    assert "is_late" in prompt
