import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.config import settings
from integrations.notifier import HitlEvent, HitlNotifier


def _event(**overrides) -> HitlEvent:
    defaults = dict(
        file_name="contract_0005.pdf", entity_key="contract_0005",
        field_name="liability_cap_status", value="unknown", reason="low_confidence",
    )
    defaults.update(overrides)
    return HitlEvent(**defaults)


def _set_enabled(monkeypatch, enabled: bool) -> None:
    monkeypatch.setattr("integrations.notifier.settings", dataclasses.replace(settings, enable_mcp_notifications=enabled))


@pytest.mark.asyncio
async def test_disabled_by_default_never_connects(monkeypatch):
    _set_enabled(monkeypatch, False)
    mock_connect = AsyncMock()
    monkeypatch.setattr(HitlNotifier, "_connect", mock_connect)

    async with HitlNotifier() as notifier:
        await notifier.notify(_event())

    mock_connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_enabled_calls_both_jira_and_slack_tools(monkeypatch):
    _set_enabled(monkeypatch, True)

    jira_session = MagicMock()
    jira_session.call_tool = AsyncMock(return_value=MagicMock(isError=False))
    slack_session = MagicMock()
    slack_session.call_tool = AsyncMock(return_value=MagicMock(isError=False))
    mock_connect = AsyncMock(side_effect=[jira_session, slack_session])
    monkeypatch.setattr(HitlNotifier, "_connect", mock_connect)

    async with HitlNotifier() as notifier:
        await notifier.notify(_event(field_name="liability_cap_status", value="uncapped", reason="negation_ambiguous"))

    jira_args = jira_session.call_tool.await_args
    assert jira_args.args[0] == "create_hitl_ticket"
    assert "liability_cap_status" in jira_args.args[1]["summary"]

    slack_args = slack_session.call_tool.await_args
    assert slack_args.args[0] == "post_hitl_alert"
    assert "negation_ambiguous" in slack_args.args[1]["text"]


@pytest.mark.asyncio
async def test_tool_call_failure_is_non_fatal(monkeypatch):
    _set_enabled(monkeypatch, True)

    jira_session = MagicMock()
    jira_session.call_tool = AsyncMock(side_effect=RuntimeError("Jira API error"))
    slack_session = MagicMock()
    slack_session.call_tool = AsyncMock(return_value=MagicMock(isError=False))
    mock_connect = AsyncMock(side_effect=[jira_session, slack_session])
    monkeypatch.setattr(HitlNotifier, "_connect", mock_connect)

    async with HitlNotifier() as notifier:
        await notifier.notify(_event())  # must not raise despite the Jira failure

    slack_session.call_tool.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_reported_error_does_not_raise(monkeypatch):
    _set_enabled(monkeypatch, True)

    jira_session = MagicMock()
    jira_session.call_tool = AsyncMock(return_value=MagicMock(isError=True, content=[MagicMock(text="not configured")]))
    slack_session = MagicMock()
    slack_session.call_tool = AsyncMock(return_value=MagicMock(isError=False))
    mock_connect = AsyncMock(side_effect=[jira_session, slack_session])
    monkeypatch.setattr(HitlNotifier, "_connect", mock_connect)

    async with HitlNotifier() as notifier:
        await notifier.notify(_event())

    jira_session.call_tool.assert_awaited_once()
