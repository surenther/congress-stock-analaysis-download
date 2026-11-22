"""
Pre-LLM Chamber-Based Access Control (CBAC) guardrails.

These checks run BEFORE any embedding generation or LiteLLM call so that an
unauthorized cross-chamber request is rejected immediately with a ``403
Forbidden`` — no database query, no embedding cost, and no LLM spend.

Two independent checks are enforced:

1. **Explicit filter check** — if the request supplies ``filters.chamber`` and
   that chamber is not in the caller's ``allowed_chambers``, reject.
2. **Prompt intent check** — if the free-text prompt explicitly asks for a
   chamber the caller cannot access (e.g. a House-only user asking for "Senate
   filings" or "Senate trades"), reject even when no ``filters.chamber`` was
   supplied. This closes the obvious bypass of simply omitting the filter.

The 403 payload is intentionally identical for both checks so callers cannot
probe which specific rule tripped.
"""

import logging
import re
from typing import List, Optional

from fastapi import HTTPException, status

logger = logging.getLogger("rag")

# Exact guardrail message required by the platform specification.
ACCESS_DENIED_DETAIL = (
    "Access Denied: You are not authorized to query disclosures for this chamber."
)

# Chambers this platform supports.
ALL_CHAMBERS: List[str] = ["House", "Senate"]

# Words that indicate the user is explicitly asking about a chamber's records.
# Matched case-insensitively against the prompt text. We deliberately keep this
# list tight to avoid false positives on generic financial language.
_CHAMBER_INTENT_PATTERNS = {
    "House": re.compile(
        r"\b(house|representatives?|rep\.?)\b", re.IGNORECASE
    ),
    "Senate": re.compile(
        r"\b(senate|senators?|sen\.?)\b", re.IGNORECASE
    ),
}


def _forbidden() -> HTTPException:
    """Build the canonical 403 guardrail exception."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=ACCESS_DENIED_DETAIL,
    )


def _normalize_chamber(value: Optional[str]) -> Optional[str]:
    """Normalize a chamber string to its canonical ``House``/``Senate`` form."""
    if not value:
        return None
    lowered = value.strip().lower()
    for chamber in ALL_CHAMBERS:
        if lowered == chamber.lower():
            return chamber
    return None


def enforce_chamber_filter(
    requested_chamber: Optional[str],
    allowed_chambers: List[str],
) -> None:
    """Reject an explicit ``filters.chamber`` outside the caller's grant.

    ``requested_chamber`` may be ``None`` (no filter) or a chamber name. An
    unknown chamber value is treated as a request for a chamber the caller
    cannot access and is rejected.
    """
    if requested_chamber is None:
        return

    canonical = _normalize_chamber(requested_chamber)
    if canonical is None or canonical not in allowed_chambers:
        logger.warning(
            "CBAC guardrail: requested chamber %r not in allowed %s",
            requested_chamber,
            allowed_chambers,
        )
        raise _forbidden()


def enforce_prompt_intent(
    prompt: str,
    allowed_chambers: List[str],
) -> None:
    """Reject prompts that explicitly request an unauthorized chamber.

    A prompt is rejected when it mentions a chamber that is NOT in the caller's
    ``allowed_chambers``. Mentioning an allowed chamber is fine. If the prompt
    mentions both chambers and the caller is restricted to one, it is rejected
    because the request spans an unauthorized chamber.
    """
    if not prompt:
        return

    mentioned = {
        chamber
        for chamber, pattern in _CHAMBER_INTENT_PATTERNS.items()
        if pattern.search(prompt)
    }
    if not mentioned:
        return

    unauthorized = mentioned - set(allowed_chambers)
    if unauthorized:
        logger.warning(
            "CBAC guardrail: prompt references unauthorized chamber(s) %s "
            "(allowed %s)",
            sorted(unauthorized),
            allowed_chambers,
        )
        raise _forbidden()


def enforce_chamber_guardrails(
    prompt: str,
    requested_chamber: Optional[str],
    allowed_chambers: List[str],
) -> None:
    """Run all pre-LLM chamber guardrails.

    Raises ``HTTPException(403)`` on the first violation. Callers should invoke
    this before generating embeddings or calling LiteLLM.
    """
    enforce_chamber_filter(requested_chamber, allowed_chambers)
    enforce_prompt_intent(prompt, allowed_chambers)
