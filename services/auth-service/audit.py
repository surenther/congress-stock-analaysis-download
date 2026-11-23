#!/usr/bin/env python3
"""
Append-only audit logging for the Auth Service.

Records authentication and administrative lifecycle events in the ``audit_log``
table. Audit writes never raise: a failure to record an event must not break the
request that triggered it.
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("auth")


async def record(
    pool,
    action: str,
    *,
    actor_user_id: Optional[str] = None,
    actor_username: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
) -> None:
    """Insert an ``audit_log`` row. Never raises."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_log
                    (actor_user_id, actor_username, action, target_type,
                     target_id, metadata, ip)
                VALUES ($1::uuid, $2, $3, $4, $5, $6::jsonb, $7)
                """,
                actor_user_id,
                actor_username,
                action,
                target_type,
                target_id,
                json.dumps(metadata or {}),
                ip,
            )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to write audit log (%s): %s", action, exc)
