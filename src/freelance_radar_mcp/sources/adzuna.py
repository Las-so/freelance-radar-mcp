"""Adapter for the Adzuna Jobs API — the "bring your own API key" source.

Adzuna requires a free developer app_id/app_key pair (signup at
https://developer.adzuna.com/, a few minutes, no cost). This module is the
concrete example of the Authentication & Authorized Access pattern: nothing
here works until *you* hold a real, scoped credential, and that credential
is read from the environment, never hardcoded or shared.

Not wired to run automatically — search() raises AdzunaNotConfigured until
ADZUNA_APP_ID and ADZUNA_APP_KEY are set, so the server degrades cleanly to
Remotive-only rather than failing the whole tool call.
"""

from __future__ import annotations

import os

import httpx

from ..http import make_client
from ..models import JobPosting

BASE_URL = "https://api.adzuna.com/v1/api/jobs"


class AdzunaNotConfigured(RuntimeError):
    """Raised when ADZUNA_APP_ID / ADZUNA_APP_KEY are not set."""


def is_configured() -> bool:
    return bool(os.environ.get("ADZUNA_APP_ID")) and bool(os.environ.get("ADZUNA_APP_KEY"))


async def search(
    query: str | None = None,
    country: str = "us",
    limit: int = 10,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[JobPosting]:
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise AdzunaNotConfigured(
            "ADZUNA_APP_ID / ADZUNA_APP_KEY are not set. Get a free key at "
            "https://developer.adzuna.com/ and export both env vars — "
            "Remotive results still work without this."
        )

    params: dict[str, str | int] = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": max(1, min(limit, 50)),
        "content-type": "application/json",
    }
    if query:
        params["what"] = query

    url = f"{BASE_URL}/{country}/search/1"

    owns_client = client is None
    client = client or make_client()
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns_client:
            await client.aclose()

    postings: list[JobPosting] = []
    for job in data.get("results", [])[:limit]:
        company = (job.get("company") or {}).get("display_name", "")
        location = (job.get("location") or {}).get("display_name")
        salary_min = job.get("salary_min")
        salary_max = job.get("salary_max")
        salary = None
        if salary_min or salary_max:
            salary = f"{salary_min or '?'}-{salary_max or '?'}"
        postings.append(
            JobPosting(
                id=f"adzuna:{job.get('id')}",
                source="adzuna",
                title=(job.get("title") or "").strip(),
                company=company,
                url=job.get("redirect_url", ""),
                location=location,
                category=(job.get("category") or {}).get("label"),
                tags=(),
                description_snippet=(job.get("description") or "")[:280] or None,
                posted_at=job.get("created"),
                salary=salary,
            )
        )
    return postings
