#!/usr/bin/env python3
"""
Input validation helpers for user-supplied watchlist values.

A watchlist entry is either a **ticker** (a stock symbol such as ``AAPL`` or
``BRK.B``) or a **member** (a congressional member's full name). Free-form
values are rejected so the watchlist cannot be polluted with arbitrary text.

The same rules are mirrored on the client in
``services/web/lib/watchlist-validation.ts`` for live, as-you-type feedback;
this module is the server-side source of truth.
"""

import re
from typing import Tuple

# A ticker: 1-5 uppercase letters, optionally a class suffix (``BRK.B``, ``RDS-A``).
TICKER_RE = re.compile(r"^[A-Z]{1,5}([.\-][A-Z]{1,2})?$")

# A member name: at least two words of letters (with common name punctuation).
MEMBER_RE = re.compile(r"^[A-Za-z][A-Za-z.'\-]*(?:\s+[A-Za-z][A-Za-z.'\-]*)+$")

MEMBER_MIN_LEN = 3
MEMBER_MAX_LEN = 60


def normalize_ticker(value: str) -> str:
    """Uppercase and trim a ticker value."""
    return (value or "").strip().upper()


def normalize_member(value: str) -> str:
    """Collapse internal whitespace and trim a member name."""
    return re.sub(r"\s+", " ", (value or "").strip())


def validate_watchlist_value(kind: str, value: str) -> Tuple[bool, str, str]:
    """Validate a watchlist value.

    Returns a ``(is_valid, normalized_value, error_message)`` tuple. When
    ``is_valid`` is true, ``error_message`` is an empty string.
    """
    if kind == "ticker":
        normalized = normalize_ticker(value)
        if not TICKER_RE.match(normalized):
            return (
                False,
                normalized,
                "Ticker must be 1-5 letters, optionally with a class suffix "
                "(e.g. AAPL, BRK.B).",
            )
        return True, normalized, ""

    if kind == "member":
        normalized = normalize_member(value)
        if (
            len(normalized) < MEMBER_MIN_LEN
            or len(normalized) > MEMBER_MAX_LEN
            or not MEMBER_RE.match(normalized)
        ):
            return (
                False,
                normalized,
                "Member name must be a full name (first and last), letters only.",
            )
        return True, normalized, ""

    return False, value, "type must be 'member' or 'ticker'."
