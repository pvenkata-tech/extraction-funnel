"""
MCP server wrapping Slack as a tool: post an alert when a field lands in the
HITL queue or a high-risk finding is flagged, so a reviewer sees it in real
time instead of polling review_ui/.

Runs as a standalone stdio MCP server -- spawned by integrations/notifier.py
as a subprocess, or attachable to any other MCP host the same way:
    python -m integrations.slack_server

Real Slack Web API (chat.postMessage), gated behind SLACK_BOT_TOKEN /
SLACK_CHANNEL in common/config.py. No hidden defaults for secrets -- an
unconfigured call raises rather than silently no-oping.
"""
import httpx
from mcp.server.fastmcp import FastMCP

from common.config import settings

mcp = FastMCP("slack")

SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"


@mcp.tool()
async def post_hitl_alert(text: str, channel: str = "") -> dict:
    """Post a Slack message alerting a reviewer to a new HITL item or high-risk finding.

    Args:
        text: Alert body, e.g. "HITL review: liability_cap_status='uncapped' on contract_0005 (low_confidence)".
        channel: Slack channel ID/name to override the configured default (SLACK_CHANNEL), if set.
    """
    if not settings.slack_bot_token:
        raise RuntimeError("Slack integration not configured -- missing SLACK_BOT_TOKEN")
    target_channel = channel or settings.slack_channel
    if not target_channel:
        raise RuntimeError("No Slack channel configured -- set SLACK_CHANNEL or pass channel explicitly")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            SLACK_POST_MESSAGE_URL,
            headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
            json={"channel": target_channel, "text": text},
        )
        response.raise_for_status()
        data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error')}")
    return {"ts": data["ts"], "channel": data["channel"]}


if __name__ == "__main__":
    mcp.run()
