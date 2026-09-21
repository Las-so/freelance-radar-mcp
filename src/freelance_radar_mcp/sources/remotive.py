"""Adapter for the Remotive public jobs API.

Remotive publishes a documented, public, unauthenticated JSON API intended
for exactly this kind of programmatic consumption:
    https://remotive.com/api/remote-jobs

No key, no login, no scraping — this calls the same documented endpoint
Remotive tells developers to use. It is the "always works, zero setup"
source; adzuna.py is the "bring your own API key" source that sits next
to it using the same JobPosting shape.
"""

from __future__ import annotations

import httpx

from ..http import make_client
from ..models import JobPosting

BASE_URL = "https://remotive.com/api/remote-jobs"
USER_AGENT = "freelance-radar-mcp/0.1 (+https://github.com/Las-so/freelance-radar-mcp)"


async def search(
    query: str | None = None,
    category: str | None = None,
    limit: int = 10,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[JobPosting]:
    """Search Remotive's public jobs feed and return normalized postings.

    Raises httpx.HTTPStatusError / httpx.TransportError on a real failure —
    callers (the MCP tool layer) decide how to surface that; this module
    never silently swallows a broken connector.
    """
    params: dict[str, str | int] = {"limit": max(1, min(limit, 100))}
    if query:
        params["search"] = query
    if category:
        params["category"] = category

    owns_client = client is None
    client = client or make_client(headers={"User-Agent": USER_AGENT})
    try:
        resp = await client.get(BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns_client:
            await client.aclose()

    if not isinstance(data, dict):
        raise ValueError(
            f"Remotive returned {type(data).__name__}, expected a JSON object — "
            "the API shape may have changed."
        )

    postings: list[JobPosting] = []
    for job in data.get("jobs", [])[:limit]:
        postings.append(
            JobPosting(
                id=f"remotive:{job.get('id')}",
                source="remotive",
                title=job.get("title", "").strip(),
                company=job.get("company_name", "").strip(),
                url=job.get("url", ""),
                location=job.get("candidate_required_location"),
                category=job.get("category"),
                tags=tuple(job.get("tags") or ()),
                description_snippet=_snippet(job.get("description")),
                posted_at=job.get("publication_date"),
                salary=job.get("salary") or None,
            )
        )
    return postings


def _snippet(html_description: str | None, max_len: int = 280) -> str | None:
    if not html_description:
        return None
    # Remotive descriptions are HTML; strip tags with no extra dependency.
    import re

    text = re.sub(r"<[^>]+>", " ", html_description)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"
