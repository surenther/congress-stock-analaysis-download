#!/usr/bin/env python3
"""
Offline development helper: mint a signed JWT for testing the RAG service's
Chamber-Based Access Control (CBAC) guardrail.

This script is NOT a production endpoint. It runs locally and requires the
shared ``JWT_SECRET_KEY`` (which only operators hold), so it cannot be used to
escalate privileges over the network. It is intended to verify that a House-only
(or Senate-only) user receives ``403 Forbidden`` when querying the other chamber.

Usage
-----
    # House-only user token (expires in 60 minutes)
    JWT_SECRET_KEY=... python scripts/mint_test_token.py \
        --username house_user --roles user --chambers House

    # Senate-only user token
    JWT_SECRET_KEY=... python scripts/mint_test_token.py \
        --username senate_user --roles user --chambers Senate

    # Admin token (chamber restriction bypassed by the RAG service)
    JWT_SECRET_KEY=... python scripts/mint_test_token.py \
        --username admin_user --roles admin

The token is printed to stdout. Pipe it into curl, e.g.:

    TOKEN=$(JWT_SECRET_KEY=... python scripts/mint_test_token.py \
        --username house_user --roles user --chambers House)
    curl -s -X POST http://localhost:8516/api/v1/rag/query \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"prompt": "Senate trades in NVDA", "filters": {"chamber": "Senate"}}'
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import jwt

ALGORITHM = "HS256"
JWT_ISSUER = os.getenv("JWT_ISSUER", "congress-auth")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "congress-platform")


def _parse_chambers(raw: str):
    """Parse a comma-separated chamber list into a canonical list."""
    allowed = {"House", "Senate"}
    chambers = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = [c for c in chambers if c not in allowed]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"Invalid chamber(s): {', '.join(invalid)}. Use House and/or Senate."
        )
    return chambers


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mint a signed JWT for testing the RAG CBAC guardrail."
    )
    parser.add_argument("--username", required=True, help="Subject (sub) claim.")
    parser.add_argument(
        "--roles",
        default="user",
        help="Comma-separated roles (default: user). Use 'admin' to bypass CBAC.",
    )
    parser.add_argument(
        "--chambers",
        default="House,Senate",
        type=_parse_chambers,
        help="Comma-separated allowed chambers (default: House,Senate).",
    )
    parser.add_argument(
        "--expires-minutes",
        type=int,
        default=60,
        help="Token lifetime in minutes (default: 60).",
    )
    args = parser.parse_args()

    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not secret:
        print(
            "ERROR: JWT_SECRET_KEY is not set. Export the shared secret first.",
            file=sys.stderr,
        )
        return 1

    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    now = datetime.now(timezone.utc)
    payload = {
        "sub": args.username,
        "roles": roles,
        "allowed_chambers": args.chambers,
        "iat": now,
        "exp": now + timedelta(minutes=args.expires_minutes),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }

    token = jwt.encode(payload, secret, algorithm=ALGORITHM)
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
