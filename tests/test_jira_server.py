import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.config import settings
from integrations.jira_server import create_hitl_ticket


def _configure(monkeypatch, **overrides):
    defaults = dict(
        jira_base_url="https://example.atlassian.net", jira_email="reviewer@example.com",
        jira_api_token="token", jira_project_key="EXTR",
    )
    defaults.update(overrides)
    monkeypatch.setattr("integrations.jira_server.settings", dataclasses.replace(settings, **defaults))


@pytest.mark.asyncio
async def test_raises_when_not_configured(monkeypatch):
    _configure(monkeypatch, jira_api_token="")

    with pytest.raises(RuntimeError, match="JIRA_API_TOKEN"):
        await create_hitl_ticket(summary="s", description="d")


@pytest.mark.asyncio
async def test_creates_issue_against_configured_project(monkeypatch):
    _configure(monkeypatch)

    mock_response = MagicMock()
    mock_response.json.return_value = {"key": "EXTR-42"}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("integrations.jira_server.httpx.AsyncClient", MagicMock(return_value=mock_client))

    result = await create_hitl_ticket(summary="HITL review: liability_cap_status", description="details", priority="High")

    assert result == {"key": "EXTR-42", "url": "https://example.atlassian.net/browse/EXTR-42"}
    posted_payload = mock_client.post.await_args.kwargs["json"]
    assert posted_payload["fields"]["project"]["key"] == "EXTR"
    assert posted_payload["fields"]["priority"]["name"] == "High"
