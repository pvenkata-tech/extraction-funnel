"""
Thin wrapper around the Anthropic API. Every call is the 'precision layer' — it
should only ever see the narrow slice of text that survived the cheap filter and
targeted-focus stages, never a raw document.
"""
import json
import re

from anthropic import AsyncAnthropic

from common.config import settings

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to .env — the precision layer "
                "cannot run without it."
            )
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _extract_json(text: str) -> dict:
    """Models occasionally wrap JSON in prose or code fences despite instructions; salvage it."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output: {text!r}")
    return json.loads(match.group(0))


async def extract_json(prompt: str, model: str | None = None, max_tokens: int = 512) -> dict:
    """Send a prompt, return the parsed JSON object the model returned. Raises on malformed output
    rather than silently guessing — a broken contract should surface, not get papered over."""
    client = _get_client()
    response = await client.messages.create(
        model=model or settings.extraction_model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return _extract_json(text)
