"""
MCP server wrapping Jira Service Management as a tool: file a ticket when a
field lands in the HITL queue or a high-risk finding is flagged, instead of
relying on a reviewer to notice it in review_ui/.

Runs as a standalone stdio MCP server -- spawned by integrations/notifier.py
as a subprocess, or attachable to any other MCP host (e.g. Claude Desktop)
the same way:
    python -m integrations.jira_server

Real Jira Cloud REST API v3, gated behind the JIRA_* env vars in
common/config.py. No hidden defaults for secrets -- an unconfigured call
raises rather than silently no-oping (the pipeline-side caller in
integrations/notifier.py is what decides whether to call this at all).
"""
import httpx
from mcp.server.fastmcp import FastMCP

from common.config import settings

mcp = FastMCP("jira-service-management")


def _require_config() -> None:
    missing = [
        name for name, value in [
            ("JIRA_BASE_URL", settings.jira_base_url),
            ("JIRA_EMAIL", settings.jira_email),
            ("JIRA_API_TOKEN", settings.jira_api_token),
            ("JIRA_PROJECT_KEY", settings.jira_project_key),
        ] if not value
    ]
    if missing:
        raise RuntimeError(f"Jira integration not configured -- missing {', '.join(missing)}")


@mcp.tool()
async def create_hitl_ticket(summary: str, description: str, priority: str = "Medium") -> dict:
    """File a Jira Service Management ticket for a HITL review item or a flagged high-risk finding.

    Args:
        summary: One-line issue summary, e.g. "HITL review: liability_cap_status on contract_0005".
        description: Full context -- source file, field, value, reason, entity key.
        priority: Jira priority name ("Highest" | "High" | "Medium" | "Low" | "Lowest").
    """
    _require_config()
    payload = {
        "fields": {
            "project": {"key": settings.jira_project_key},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
            },
            "issuetype": {"name": "Task"},
            "priority": {"name": priority},
        }
    }
    async with httpx.AsyncClient(
        base_url=settings.jira_base_url, auth=(settings.jira_email, settings.jira_api_token), timeout=10.0
    ) as client:
        response = await client.post("/rest/api/3/issue", json=payload)
        response.raise_for_status()
        data = response.json()
    return {"key": data["key"], "url": f"{settings.jira_base_url}/browse/{data['key']}"}


if __name__ == "__main__":
    mcp.run()
