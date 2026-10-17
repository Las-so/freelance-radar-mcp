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

from mcp.server.fastmcp import Context, FastMCP

from .errors import SOURCE_CAVEATS, error, ok, validate_limit
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


async def _gather_jobs(
    query: str | None,
    category: str | None,
    limit: int,
    ctx: Context = None,  # injected by FastMCP
) -> tuple[list[JobPosting], list[str], list[str], list[str]]:
    """Fan out to every configured source in parallel.

    Returns (postings, sources_used, sources_failed, sources_not_configured).
    """
    if ctx is not None:
        await ctx.report_progress(0, 100, "contacting sources")

    async with make_client() as client:
        tasks: list[asyncio.Task] = []
        labels: list[str] = []

        tasks.append(asyncio.create_task(remotive.search(query, category, limit, client=client)))
        labels.append("remotive")

        if adzuna.is_configured():
            tasks.append(asyncio.create_task(adzuna.search(query, "us", limit, client=client)))
            labels.append("adzuna")

        results = await asyncio.gather(*tasks, return_exceptions=True)

    if ctx is not None:
        await ctx.report_progress(70, 100, "normalizing results")

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

    not_configured: list[str] = []
    if not adzuna.is_configured():
        not_configured.append("adzuna: ADZUNA_APP_ID/ADZUNA_APP_KEY not set")

    if ctx is not None:
        await ctx.report_progress(100, 100, "done")

    return postings, used, skipped, not_configured


@mcp.tool()
def source_status() -> dict:
    """Report which job sources are live and why — call this first to see
    what you're actually querying before trusting the results."""
    return ok(
        remotive={"configured": True, "auth": "none (public API)",
                  "caveat": SOURCE_CAVEATS["remotive"]},
        adzuna={
            "configured": adzuna.is_configured(),
            "auth": "app_id + app_key (env vars ADZUNA_APP_ID / ADZUNA_APP_KEY)",
            "signup_url": "https://developer.adzuna.com/",
            "caveat": SOURCE_CAVEATS["adzuna"],
        },
    )


@mcp.tool()
async def search_jobs(
    query: str = "", category: str = "", limit: int = 10, ctx: Context = None
) -> dict:
    """Search every configured job source and return normalized postings.

    Args:
        query: free-text search, e.g. "automation" or "shopify developer".
        category: optional Remotive category slug, e.g. "software-dev".
        limit: max postings per source (1-50).
    """
    n, bad, clamped_from = validate_limit(limit)
    if bad:
        return bad

    postings, used, failed, unconfigured = await _gather_jobs(
        query or None, category or None, n, ctx
    )
    if not used:
        return error(
            "all_sources_failed",
            "Every configured source failed; these results are not an empty search.",
            sources_failed=failed,
            sources_not_configured=unconfigured,
        )
    return ok(
        sources_used=used,
        sources_failed=failed,
        sources_not_configured=unconfigured,
        caveats={s: SOURCE_CAVEATS[s] for s in used if s in SOURCE_CAVEATS},
        filtered_locally=bool(query or category),
        limit_clamped_from=clamped_from,
        count=len(postings),
        jobs=[p.to_dict() for p in postings],
    )


@mcp.tool()
async def score_opportunities(
    capability_keywords: list[str],
    query: str = "",
    category: str = "",
    limit: int = 15,
    ctx: Context = None,  # injected by FastMCP
) -> dict:
    """Search job sources, then score every result against your own capability
    keywords (0-100, title matches weighted 2x body matches). Highest score first.

    Args:
        capability_keywords: e.g. ["MCP", "python", "automation", "shopify", "API integration"].
        query: free-text search passed through to the sources.
        category: optional Remotive category slug.
        limit: max postings per source before scoring.
    """
    if not capability_keywords or not any(
        isinstance(k, str) and k.strip() for k in capability_keywords
    ):
        return error(
            "invalid_input",
            "capability_keywords must contain at least one non-blank keyword; "
            "blank keywords score every posting 0 and the ranking is noise.",
            field="capability_keywords",
        )

    n, bad, clamped_from = validate_limit(limit)
    if bad:
        return bad

    postings, used, failed, unconfigured = await _gather_jobs(
        query or None, category or None, n, ctx
    )
    if not used:
        return error(
            "all_sources_failed",
            "Every configured source failed; this ranking is not an empty result set.",
            sources_failed=failed,
            sources_not_configured=unconfigured,
        )
    scored = score_jobs(postings, capability_keywords)
    return ok(
        sources_used=used,
        sources_failed=failed,
        sources_not_configured=unconfigured,
        caveats={s: SOURCE_CAVEATS[s] for s in used if s in SOURCE_CAVEATS},
        filtered_locally=bool(query or category),
        limit_clamped_from=clamped_from,
        count=len(scored),
        ranked=[s.to_dict() for s in scored],
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
