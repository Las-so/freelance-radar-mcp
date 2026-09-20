"""Confirms the optional source degrades cleanly instead of crashing the
whole tool call when no API key is present — the expected state for anyone
who hasn't signed up for Adzuna yet."""

import os

import pytest

from freelance_radar_mcp.sources import adzuna


@pytest.mark.asyncio
async def test_raises_clear_error_when_not_configured(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)

    assert adzuna.is_configured() is False

    with pytest.raises(adzuna.AdzunaNotConfigured):
        await adzuna.search(query="python")


def test_is_configured_true_when_both_env_vars_set(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "x")
    monkeypatch.setenv("ADZUNA_APP_KEY", "y")
    assert adzuna.is_configured() is True
