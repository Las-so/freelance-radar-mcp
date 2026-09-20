"""freelance-radar-mcp — MCP server entry point.

Exposes three tools over stdio:
  - source_status        : which job sources are live right now, and why
  - search_jobs           : normalized postings from every configured source
  - score_opportunities   : search_jobs() + transparent relevance scoring

Every tool call hits a real, documented, public API at call time — nothing
here is cached demo data, and nothing here scrapes or touches an endpoint
outside what the provider publishes for programmatic use.
"""

from __future__ import annotations

import asyncio
import logging

from mcp.server.fastmcp import FastMCP

from .http import make_client
from .models import JobPosting
from .scoring import score_jobs
from .sources import adzuna, remotive

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("freelance-radar-mcp")

mcp = FastMCP(
    "freelance-radar",
    instructions=(
        "Search official, public job/freelance APIs (Remotive always on; "
        "Adzuna if ADZUNA_APP_ID/ADZUNA_APP_KEY are set) and optionally score "
        "results against a list of your own capability keywords. No scraping, "
        "no scraping-as-a-service, no unofficial endpoints."
    ),
)


async def _gather_jobs(query: str | None, category: str | None, limit: int) -> tuple[list[JobPosting], list[str], list[str]]:
    """Fan out to every configured source in parallel.

    Returns (postings, sources_used, sources_skipped_with_reason).
    """
    async with make_client() as client:
        tasks: list[asyncio.Task] = []
        labels: list[str] = []

        tasks.append(asyncio.create_task(remotive.search(query, category, limit, client=client)))
        labels.append("remotive")

        if adzuna.is_configured():
            tasks.append(asyncio.create_task(adzuna.search(query, "us", limit, client=client)))
            labels.append("adzuna")

        results = await asyncio.gather(*tasks, return_exceptions=True)

    postings: list[JobPosting] = []
    used: list[str] = []
    skipped: list[str] = []
    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            skipped.append(f"{label}: {result}")
            logger.warning("source %s failed: %s", label, result)
            continue
        used.append(label)
        postings.extend(result)

    if not adzuna.is_configured():
        skipped.append("adzuna: ADZUNA_APP_ID/ADZUNA_APP_KEY not set (optional source, skipped cleanly)")

    return postings, used, skipped


@mcp.tool()
def source_status() -> dict:
    """Report which job sources are live and why — call this first to see
    what you're actually querying before trusting the results."""
    return {
        "remotive": {"configured": True, "auth": "none (public API)"},
        "adzuna": {
            "configured": adzuna.is_configured(),
            "auth": "app_id + app_key (env vars ADZUNA_APP_ID / ADZUNA_APP_KEY)",
            "signup_url": "https://developer.adzuna.com/",
        },
    }


@mcp.tool()
async def search_jobs(query: str = "", category: str = "", limit: int = 10) -> dict:
    """Search every configured job source and return normalized postings.

    Args:
        query: free-text search, e.g. "automation" or "shopify developer".
        category: optional Remotive category slug, e.g. "software-dev".
        limit: max postings per source (1-50).
    """
    postings, used, skipped = await _gather_jobs(query or None, category or None, max(1, min(limit, 50)))
    return {
        "sources_used": used,
        "sources_skipped": skipped,
        "count": len(postings),
        "jobs": [p.to_dict() for p in postings],
    }


@mcp.tool()
async def score_opportunities(
    capability_keywords: list[str],
    query: str = "",
    category: str = "",
    limit: int = 15,
) -> dict:
    """Search job sources, then score every result against your own capability
    keywords (0-100, title matches weighted 2x body matches). Highest score first.

    Args:
        capability_keywords: e.g. ["MCP", "python", "automation", "shopify", "API integration"].
        query: free-text search passed through to the sources.
        category: optional Remotive category slug.
        limit: max postings per source before scoring.
    """
    postings, used, skipped = await _gather_jobs(query or None, category or None, max(1, min(limit, 50)))
    scored = score_jobs(postings, capability_keywords)
    return {
        "sources_used": used,
        "sources_skipped": skipped,
        "count": len(scored),
        "ranked": [s.to_dict() for s in scored],
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
