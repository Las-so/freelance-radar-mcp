"""Tool-surface snapshot plus real behaviour of the ok/error envelope.

An earlier version of this file was three tautologies that restated
errors.py back to itself, and a parameter check that discarded "ctx" and
therefore hid a crash. Both are fixed here: `ctx` must be ABSENT from the
public schema, and every tool is actually invoked.
"""

from __future__ import annotations

import asyncio

import pytest

from freelance_radar_mcp import server as srv
from freelance_radar_mcp.models import JobPosting

EXPECTED_TOOLS = {
    "source_status": set(),
    "search_jobs": {"query", "category", "limit"},
    "score_opportunities": {"capability_keywords", "query", "category", "limit"},
}


def _tools():
    return {t.name: t for t in asyncio.run(srv.mcp.list_tools())}


def test_exact_tool_set():
    assert set(_tools()) == set(EXPECTED_TOOLS)


def test_tool_parameters_and_no_ctx_leak():
    for name, expected in EXPECTED_TOOLS.items():
        props = set((_tools()[name].inputSchema.get("properties") or {}))
        # ctx is injected by FastMCP. If it reaches the public schema the
        # caller sees an unfillable parameter: that is a bug, not noise.
        assert "ctx" not in props, f"{name} leaks ctx into its public schema"
        assert props == expected, f"{name} parameters changed: {props}"


def test_every_tool_has_a_description():
    for name, tool in _tools().items():
        assert tool.description and len(tool.description) > 20, name


# --- envelope behaviour, exercised through the real tools ---

def _fake(n=3):
    return [
        JobPosting(id=f"remotive:{i}", source="remotive", title=f"Python dev {i}",
                   company="Acme", url="https://x/y")
        for i in range(n)
    ]


@pytest.fixture
def stub_sources(monkeypatch):
    async def fake_gather(query, category, limit, ctx=None):
        return _fake(), ["remotive"], [], ["adzuna: not set"]
    monkeypatch.setattr(srv, "_gather_jobs", fake_gather)


@pytest.fixture
def dead_sources(monkeypatch):
    async def fake_gather(query, category, limit, ctx=None):
        return [], [], ["remotive: boom"], ["adzuna: not set"]
    monkeypatch.setattr(srv, "_gather_jobs", fake_gather)


def test_search_jobs_success_is_ok_true_with_caveats(stub_sources):
    r = asyncio.run(srv.search_jobs(query="python"))
    assert r["ok"] is True
    assert r["count"] == 3
    assert "remotive" in r["caveats"]
    # the clean skip must NOT be reported as a failure
    assert r["sources_failed"] == []
    assert r["sources_not_configured"] == ["adzuna: not set"]


def test_total_failure_is_an_error_not_an_empty_list(dead_sources):
    r = asyncio.run(srv.search_jobs(query="python"))
    assert r["ok"] is False
    assert r["error"]["code"] == "all_sources_failed"
    assert r["error"]["sources_failed"] == ["remotive: boom"]


@pytest.mark.parametrize("bad", [0, -5, "ten", 1.5])
def test_bad_limit_rejected_identically_by_both_tools(stub_sources, bad):
    a = asyncio.run(srv.search_jobs(limit=bad))
    b = asyncio.run(srv.score_opportunities(capability_keywords=["python"], limit=bad))
    assert a["ok"] is False and a["error"]["code"] == "invalid_input"
    assert b["ok"] is False and b["error"]["code"] == "invalid_input"


def test_oversized_limit_is_clamped_and_says_so(stub_sources):
    r = asyncio.run(srv.search_jobs(limit=500))
    assert r["ok"] is True
    assert r["limit_clamped_from"] == 500


def test_blank_keywords_rejected(stub_sources):
    r = asyncio.run(srv.score_opportunities(capability_keywords=["", "   "]))
    assert r["ok"] is False
    assert r["error"]["code"] == "invalid_input"


def test_source_status_is_enveloped_and_carries_caveats():
    r = srv.source_status()  # sync tool, not a coroutine
    assert r["ok"] is True
    assert "caveat" in r["remotive"] and "caveat" in r["adzuna"]
