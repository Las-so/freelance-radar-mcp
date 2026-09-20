"""A source that returns valid JSON of the wrong shape should fail with a
clear, named error rather than a bare AttributeError from somewhere deep in
the parsing code. Covers the case where a provider changes its API shape."""

import httpx
import pytest

from freelance_radar_mcp.sources import adzuna, remotive


def _client_returning(payload) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_remotive_rejects_non_object_payload():
    async with _client_returning(["not", "a", "dict"]) as client:
        with pytest.raises(ValueError, match="expected a JSON object"):
            await remotive.search(query="python", client=client)


@pytest.mark.asyncio
async def test_adzuna_rejects_non_object_payload(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "test-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test-key")
    async with _client_returning(["not", "a", "dict"]) as client:
        with pytest.raises(ValueError, match="expected a JSON object"):
            await adzuna.search(query="python", client=client)
