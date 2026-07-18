"""
MCP client wiring for the HITL boundary: when a field lands in the HITL
queue, call the Jira Service Management and Slack MCP servers (jira_server.py,
slack_server.py) instead of relying on a reviewer to notice it in review_ui/.

This is the tool-calling layer both pipelines call into at Stage 5 -- the
same shape as an agent calling a tool through MCP, just triggered
deterministically by a confidence/MNAR gate instead of an LLM's tool-choice
decision.

Disabled by default (ENABLE_MCP_NOTIFICATIONS=false) so the pipeline runs
end to end on Docker Compose without real Jira/Slack credentials -- the same
"swap-in, not a rewrite" posture as the redaction/schema-registry stubs
called out in the README.
"""
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from common.config import settings

_JIRA_SERVER = StdioServerParameters(command=sys.executable, args=["-m", "integrations.jira_server"])
_SLACK_SERVER = StdioServerParameters(command=sys.executable, args=["-m", "integrations.slack_server"])


@dataclass
class HitlEvent:
    file_name: str
    entity_key: str
    field_name: str
    value: str | None
    reason: str


class HitlNotifier:
    """One pair of long-lived MCP client sessions per pipeline run, not one
    subprocess spawn per HITL event. A notification failure is logged and
    swallowed -- it must never fail the extraction run itself."""

    def __init__(self):
        self._stack = AsyncExitStack()
        self.jira: ClientSession | None = None
        self.slack: ClientSession | None = None

    async def __aenter__(self) -> "HitlNotifier":
        if not settings.enable_mcp_notifications:
            return self
        self.jira = await self._connect(_JIRA_SERVER)
        self.slack = await self._connect(_SLACK_SERVER)
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._stack.aclose()

    async def _connect(self, params: StdioServerParameters) -> ClientSession:
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return session

    async def notify(self, event: HitlEvent) -> None:
        if not settings.enable_mcp_notifications:
            return

        summary = f"HITL review: {event.field_name}={event.value!r} on {event.entity_key} ({event.reason})"
        description = (
            f"File: {event.file_name}\nEntity: {event.entity_key}\n"
            f"Field: {event.field_name}\nValue: {event.value}\nReason: {event.reason}"
        )

        if self.jira is not None:
            await self._call_tool(
                self.jira, "create_hitl_ticket", {"summary": summary, "description": description}, label="Jira ticket"
            )
        if self.slack is not None:
            await self._call_tool(self.slack, "post_hitl_alert", {"text": summary}, label="Slack alert")

    @staticmethod
    async def _call_tool(session: ClientSession, tool_name: str, arguments: dict, *, label: str) -> None:
        try:
            result = await session.call_tool(tool_name, arguments)
            if result.isError:
                print(f"[notify] {label} failed (non-fatal): {result.content}")
            else:
                print(f"[notify] {label} sent")
        except Exception as exc:  # noqa: BLE001 -- notification failures must not fail the extraction run
            print(f"[notify] {label} failed (non-fatal): {exc!r}")
