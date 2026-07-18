import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.config import settings
from integrations.slack_server import post_hitl_alert


def _configure(monkeypatch, **overrides):
    monkeypatch.setattr("integrations.slack_server.settings", dataclasses.replace(settings, **overrides))


@pytest.mark.asyncio
async def test_raises_when_not_configured(monkeypatch):
    _configure(monkeypatch, slack_bot_token="")

    with pytest.raises(RuntimeError, match="SLACK_BOT_TOKEN"):
        await post_hitl_alert(text="alert")


@pytest.mark.asyncio
async def test_raises_when_no_channel_available(monkeypatch):
    _configure(monkeypatch, slack_bot_token="xoxb-token", slack_channel="")

    with pytest.raises(RuntimeError, match="channel"):
        await post_hitl_alert(text="alert")


@pytest.mark.asyncio
async def test_posts_to_configured_default_channel(monkeypatch):
    _configure(monkeypatch, slack_bot_token="xoxb-token", slack_channel="#hitl-review")

    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "ts": "123.456", "channel": "#hitl-review"}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("integrations.slack_server.httpx.AsyncClient", MagicMock(return_value=mock_client))

    result = await post_hitl_alert(text="HITL review: liability_cap_status")

    assert result == {"ts": "123.456", "channel": "#hitl-review"}
    posted_payload = mock_client.post.await_args.kwargs["json"]
    assert posted_payload["channel"] == "#hitl-review"


@pytest.mark.asyncio
async def test_slack_api_error_raises(monkeypatch):
    _configure(monkeypatch, slack_bot_token="xoxb-token", slack_channel="#hitl-review")

    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("integrations.slack_server.httpx.AsyncClient", MagicMock(return_value=mock_client))

    with pytest.raises(RuntimeError, match="channel_not_found"):
        await post_hitl_alert(text="alert")
