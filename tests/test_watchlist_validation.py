#!/usr/bin/env python3
"""
Unit tests for watchlist input validation (services/rag/validation.py).

These are fast, no-DB tests that assert free-form values are rejected and that
valid tickers / member names are normalized correctly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_RAG_DIR = Path(__file__).resolve().parent.parent / "services" / "rag"
sys.path.insert(0, str(_RAG_DIR))

import validation  # noqa: E402

pytestmark = pytest.mark.contract


# ------------------------------------------------------------------------------
# Tickers
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["AAPL", "NVDA", "F", "BRK.B", "RDS-A", "goog"])
def test_valid_tickers(value: str):
    ok, normalized, error = validation.validate_watchlist_value("ticker", value)
    assert ok, error
    assert normalized == value.upper()


@pytest.mark.parametrize(
    "value",
    ["", "  ", "TOOLONGTICKER", "AA1", "A B", "AAPL!", "123", "$AAPL", "BRK..B"],
)
def test_invalid_tickers(value: str):
    ok, _normalized, error = validation.validate_watchlist_value("ticker", value)
    assert not ok
    assert error


def test_ticker_is_uppercased_and_trimmed():
    ok, normalized, _ = validation.validate_watchlist_value("ticker", "  aapl ")
    assert ok
    assert normalized == "AAPL"


# ------------------------------------------------------------------------------
# Members
# ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value",
    ["Josh Gottheimer", "Nancy Pelosi", "A. Ocasio-Cortez", "Mary Jo O'Brien"],
)
def test_valid_members(value: str):
    ok, normalized, error = validation.validate_watchlist_value("member", value)
    assert ok, error
    assert normalized == value


@pytest.mark.parametrize(
    "value",
    ["", "  ", "Pelosi", "12345", "John 123", "a", "J@ne Doe", "X" * 61],
)
def test_invalid_members(value: str):
    ok, _normalized, error = validation.validate_watchlist_value("member", value)
    assert not ok
    assert error


def test_member_whitespace_is_collapsed():
    ok, normalized, _ = validation.validate_watchlist_value("member", "  Josh   Gottheimer ")
    assert ok
    assert normalized == "Josh Gottheimer"


# ------------------------------------------------------------------------------
# Unknown type
# ------------------------------------------------------------------------------
def test_unknown_type_is_rejected():
    ok, _normalized, error = validation.validate_watchlist_value("company", "Acme")
    assert not ok
    assert "type" in error
