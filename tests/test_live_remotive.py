"""Live connector tests.

Standing rule: any connector a build depends on is proven to actually
connect AND deliver a real payload, not assumed to work from its docs.
These make real network calls on purpose.

WHY THIS FILE WAS REWRITTEN (2026-10-18): it used to assert that
search(query="automation") returned at least one job. Remotive's entire
public feed is 13 postings, so that assertion depended on what those 13
rotating jobs happened to say. A week with no "automation" posting turned
the build red with nothing wrong in this repo. That is a flaky test: it
fails for reasons the code cannot control, and a red build nobody trusts
is worse than no build at all.

What these assert instead:
  1. the connector reaches Remotive and returns a well-formed payload
     (shape, not content)
  2. a query that cannot match anything returns nothing, which proves the
     local filter is doing real work against live data
  3. Remotive still ignores `search` server-side

Test 3 is DELIBERATELY coupled to provider behaviour. If Remotive ever
fixes its search parameter, this goes red, and that is the point: it is a
signal to delete the local-filter workaround, not a bug. An actionable
failure, unlike the one this file used to produce.
"""

import httpx
import pytest

from freelance_radar_mcp.http import make_client
from freelance_radar_mcp.sources import remotive


@pytest.mark.asyncio
async def test_connector_reaches_remotive_and_payload_is_well_formed():
    """No query: the whole feed, checked for shape only."""
    jobs = await remotive.search(limit=5)

    assert len(jobs) > 0, "live Remotive API returned zero jobs for an unfiltered call"
    assert len(jobs) <= 5, "limit must be enforced locally even though the API ignores it"

    for job in jobs:
        assert job.id.startswith("remotive:")
        assert job.source == "remotive"
        assert job.title, "job title must not be empty"
        assert job.company, "company must not be empty"
        assert job.url.startswith("http"), "must be a real, followable URL"


@pytest.mark.asyncio
async def test_local_filter_actually_filters_live_data():
    """A term no posting can contain must return nothing.

    Content-independent: it does not matter what today's 13 jobs say, only
    that an impossible term matches none of them. If the local filter were
    removed, this returns the whole feed and fails.
    """
    jobs = await remotive.search(query="zzzqqqnotarealword", limit=50)
    assert jobs == [], f"local filter let {len(jobs)} non-matching jobs through"


@pytest.mark.asyncio
async def test_remotive_still_ignores_search_server_side():
    """Regression guard on the provider behaviour the design depends on.

    Going red here means Remotive FIXED their search. That is good news and
    an instruction to simplify, not a defect in this repo.
    """
    async with make_client(headers={"User-Agent": remotive.USER_AGENT}) as client:
        plain = await client.get(remotive.BASE_URL)
        searched = await client.get(remotive.BASE_URL, params={"search": "shopify"})

    plain.raise_for_status()
    searched.raise_for_status()

    ids_plain = [j.get("id") for j in plain.json().get("jobs", [])]
    ids_searched = [j.get("id") for j in searched.json().get("jobs", [])]

    assert ids_plain == ids_searched, (
        "Remotive now appears to honour ?search=. Delete the local-filter "
        "workaround in sources/remotive.py and simplify _matches."
    )
