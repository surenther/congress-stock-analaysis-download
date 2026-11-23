"""
Structured chamber-scope error contract for the RAG service.

A cross-chamber request returns HTTP 403 with a machine-readable body so the
frontend can render an inline access-restriction banner instead of a generic
error:

    {
      "detail": {
        "code": "CHAMBER_SCOPE_VIOLATION",
        "message": "Access Denied: ...",
        "requested_chamber": "Senate",
        "allowed_chambers": ["House"]
      }
    }

This module is intentionally dependency-light (FastAPI only) so it can be
mirrored in the analytics service without pulling in extra packages.
"""

from typing import List, Optional

from fastapi import HTTPException, status

# Stable machine-readable code the frontend keys off of.
CHAMBER_SCOPE_VIOLATION = "CHAMBER_SCOPE_VIOLATION"

# Human-readable message shown in the inline banner.
ACCESS_DENIED_MESSAGE = (
    "Access Denied: You are not authorized to query disclosures for this chamber."
)


def chamber_scope_violation(
    requested_chamber: Optional[str],
    allowed_chambers: List[str],
) -> HTTPException:
    """Build the canonical structured 403 chamber-scope exception."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": CHAMBER_SCOPE_VIOLATION,
            "message": ACCESS_DENIED_MESSAGE,
            "requested_chamber": requested_chamber,
            "allowed_chambers": list(allowed_chambers),
        },
    )
