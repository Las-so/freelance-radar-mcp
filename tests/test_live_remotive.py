"""Live connector payload test — per the standing rule that any connector a
build depends on must be proven to actually connect AND deliver a real
payload, not just assumed to work from its docs.

This test makes a real network call. If Remotive changes its response shape
or goes down, this test is *supposed* to fail loudly rather than pass on
stale mocks.
"""

import pytest

from freelance_radar_mcp.sources import remotive


@pytest.mark.asyncio
async def test_remotive_returns_real_normalized_postings():
    jobs = await remotive.search(query="automation", limit=3)

    assert len(jobs) > 0, "live Remotive API returned zero jobs for a common query"

    first = jobs[0]
    assert first.id.startswith("remotive:")
    assert first.source == "remotive"
    assert first.title, "job title must not be empty"
    assert first.company, "company must not be empty"
    assert first.url.startswith("http"), "must be a real, followable URL"
