"""Central settings, loaded from environment / .env. No hidden defaults for secrets."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg2://funnel:funnel@localhost:5432/funnel")
    opensearch_url: str = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    extraction_model: str = os.getenv("EXTRACTION_MODEL", "claude-haiku-4-5-20251001")
    verify_model: str = os.getenv("VERIFY_MODEL", "claude-sonnet-5")
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.85"))
    raw_data_dir: str = os.getenv("RAW_DATA_DIR", "sample_data")

    # HITL notification MCP servers (integrations/). Off by default so the
    # pipeline runs end to end without real Jira/Slack credentials -- the same
    # "swap-in, not a rewrite" posture as the redaction/schema-registry stubs.
    enable_mcp_notifications: bool = os.getenv("ENABLE_MCP_NOTIFICATIONS", "false").lower() == "true"
    jira_base_url: str = os.getenv("JIRA_BASE_URL", "")
    jira_email: str = os.getenv("JIRA_EMAIL", "")
    jira_api_token: str = os.getenv("JIRA_API_TOKEN", "")
    jira_project_key: str = os.getenv("JIRA_PROJECT_KEY", "")
    slack_bot_token: str = os.getenv("SLACK_BOT_TOKEN", "")
    slack_channel: str = os.getenv("SLACK_CHANNEL", "")


settings = Settings()
