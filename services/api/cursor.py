"""Opaque keyset-pagination cursors (T13). A cursor is the sort key of the last row returned; the next page is
`WHERE (sort key) < cursor`. Pages cost the same at row 10 and row 10 million, unlike OFFSET.
"""
from __future__ import annotations

import base64
import json

from fastapi import HTTPException, Query

DEFAULT_LIMIT, MAX_LIMIT = 50, 200


def encode(values: list) -> str:
    raw = json.dumps(values, default=str, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode(cursor: str | None, n: int) -> list | None:
    if not cursor:
        return None
    try:
        v = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except Exception:
        raise HTTPException(422, "cursor: not a cursor returned by this API") from None
    if not isinstance(v, list) or len(v) != n:
        raise HTTPException(422, "cursor: not a cursor returned by this API")
    return v


def page(rows: list[dict], limit: int, key) -> dict:
    """rows were fetched with LIMIT limit + 1: the extra row only says whether a next page exists."""
    more = len(rows) > limit
    rows = rows[:limit]
    return {"items": rows, "limit": limit, "next_cursor": encode(key(rows[-1])) if more and rows else None}


LimitQ = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
CursorQ = Query(None, max_length=512, description="next_cursor from the previous page")
