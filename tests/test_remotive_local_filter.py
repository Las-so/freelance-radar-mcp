"""Guards for verified provider bugs and for real-world payload junk.

Remotive ignores `search`, `limit` AND `category` (verified live
2026-10-17), so all three are applied in this module. The previous version
of this file claimed to guard the filter-before-slice ordering and did not:
it never called search(), so inverting the order left it green. These tests
call search() through a mock transport so the ordering is actually pinned.
"""

from __future__ import annotations

import httpx
import pytest

from freelance_radar_mcp.sources.remotive import _matches, _tag_list, search

JOB = {
    "title": "Senior Shopify Developer",
    "company_name": "Acme",
    "category": "Software Development",
    "tags": ["Shopify", "Liquid"],
    "description": "<p>Build <strong>storefronts</strong> and custom apps.</p>",
}


def _feed(jobs):
    def handler(request):
        return httpx.Response(200, json={"jobs": jobs, "job-count": len(jobs)})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --- _matches ---

def test_no_query_matches_everything():
    assert _matches(JOB, None) and _matches(JOB, "")


def test_case_insensitive_and_multi_field():
    assert _matches(JOB, "SHOPIFY")
    assert _matches(JOB, "liquid")
    assert _matches(JOB, "storefronts")


def test_terms_are_and_not_or():
    assert _matches(JOB, "shopify developer")
    assert not _matches(JOB, "shopify kubernetes")


def test_html_tag_names_do_not_match():
    # substring matching on raw HTML made "strong", "li" and "div" match
    # nearly every posting. Tokens over stripped text must not.
    for junk in ("strong", "li", "div", "href", "span"):
        assert not _matches(JOB, junk), junk


def test_token_match_not_substring():
    # "java" must not match "Javascript"
    job = dict(JOB, title="Javascript Engineer", tags=[], description="")
    assert not _matches(job, "java")
    assert _matches(job, "javascript")


def test_category_filtered_locally():
    assert _matches(JOB, None, "Software Development")
    assert not _matches(JOB, None, "Design")


@pytest.mark.parametrize("tags,expect", [
    ([1, 2, None], ["1", "2", "None"]),   # ints crashed str.join
    ("shopify", ["shopify"]),             # bare string became "s h o p i f y"
    ({"a": "shopify"}, ["shopify"]),      # dict silently lost its values
    (None, []),
])
def test_tag_normalization(tags, expect):
    assert _tag_list(tags) == expect


def test_junk_payloads_do_not_crash():
    assert not _matches({}, "shopify")
    assert _matches({}, None)
    assert not _matches(None, "shopify")
    assert _matches({"title": None, "description": 42, "tags": [7]}, None)


# --- search(): ordering and payload hardening ---

@pytest.mark.asyncio
async def test_match_deep_in_feed_survives_a_small_limit():
    """The invariant the old file claimed to guard and did not.

    A single match at position 55 of a 60-job feed must still be returned
    with limit=10. Slice-then-filter returns 0 here.
    """
    jobs = [{"id": i, "title": f"Filler {i}", "company_name": "C", "url": "u"}
            for i in range(60)]
    jobs[55] = {"id": 55, "title": "Shopify Architect", "company_name": "C", "url": "u"}
    async with _feed(jobs) as c:
        out = await search(query="shopify", limit=10, client=c)
    assert len(out) == 1 and out[0].id == "remotive:55"


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,expected", [(-5, 1), (0, 1), (3, 3), (500, 13)])
async def test_limit_is_clamped_for_the_local_slice_too(limit, expected):
    """A negative limit used to slice from the end and silently drop rows."""
    jobs = [{"id": i, "title": "Dev", "company_name": "C", "url": "u"} for i in range(13)]
    async with _feed(jobs) as c:
        out = await search(limit=limit, client=c)
    assert len(out) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"jobs": [{"id": 1, "title": None, "company_name": "A", "url": "u"}]},
    {"jobs": [{"id": 1, "title": "T", "company_name": None, "url": "u"}]},
    {"jobs": [{"id": 1, "title": "T", "company_name": "A", "url": "u", "description": 42}]},
    {"jobs": [{"id": 1, "title": "T", "company_name": "A", "url": "u", "tags": [5]}]},
    {"jobs": None},
    {"jobs": {"a": 1}},
    {"jobs": ["not-a-dict"]},
])
async def test_malformed_job_rows_do_not_kill_the_source(payload):
    """Any of these used to raise and take the whole Remotive source down."""
    def handler(request):
        return httpx.Response(200, json=payload)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        out = await search(limit=10, client=c)
    assert isinstance(out, list)
