"""Shared error contract.

Every tool returns the same shape, so a caller (usually a model) can branch
on `ok` instead of pattern-matching prose.

A clean skip is NOT a failure. They are reported in separate keys precisely
so a model cannot read "adzuna not configured" as "adzuna broke".
"""

from __future__ import annotations

from typing import Any, Literal

ErrorCode = Literal["invalid_input", "all_sources_failed"]

MAX_LIMIT = 50


def error(code: ErrorCode, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, **extra}}


def ok(**payload: Any) -> dict[str, Any]:
    return {"ok": True, **payload}


def validate_limit(limit: int) -> tuple[int, dict[str, Any] | None, int | None]:
    """Return (effective_limit, error_or_None, clamped_from_or_None).

    One implementation so every tool answers the same way to the same bad
    input. Returning the clamp instead of hiding it means the caller can see
    that it asked for 500 and got 50.
    """
    if not isinstance(limit, int) or isinstance(limit, bool):
        return 0, error("invalid_input", "limit must be an integer",
                        field="limit", given=repr(limit)), None
    if limit < 1:
        return 0, error("invalid_input", "limit must be at least 1",
                        field="limit", given=limit), None
    if limit > MAX_LIMIT:
        return MAX_LIMIT, None, limit
    return limit, None, None


# Provider behaviour the caller must know to avoid overclaiming. These ship
# in the response, not just the README, because the thing reading this output
# is a model that never saw the README.
SOURCE_CAVEATS: dict[str, str] = {
    "remotive": (
        "Remotive's public API ignores `search`, `limit` AND `category`: every "
        "request returns the same full feed (13 postings as of 2026-10-17). All "
        "filtering and truncation in these results was done locally by this "
        "server. Remotive's API terms require linking back to the posting URL "
        "and crediting Remotive as the source, and forbid republishing its jobs "
        "to third-party job sites."
    ),
    "adzuna": (
        "Adzuna salary figures are MODELLED ESTIMATES produced by Adzuna, not "
        "figures published by the employer. Never quote one as an employer's offer."
    ),
}
