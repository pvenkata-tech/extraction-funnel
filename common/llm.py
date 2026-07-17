"""
Thin wrapper around the Anthropic API. Every call is the 'precision layer' — it
should only ever see the narrow slice of text that survived the cheap filter and
targeted-focus stages, never a raw document.

Every call also returns telemetry (latency, token counts, estimated cost) so the
caller can log it to the audit trail. This is the minimum an LLM-calling system
needs before you can answer "did the last prompt change make this slower or
more expensive" -- observability isn't a bolt-on here, the same way it isn't
in `common/audit.py`.
"""
import json
import re
import time
from dataclasses import dataclass

from anthropic import AsyncAnthropic

from common.config import settings

_client: AsyncAnthropic | None = None

# $ per million tokens. Approximate list pricing -- check console.anthropic.com/settings/billing
# for current rates before using this for real cost accounting; this is enough precision to spot
# a 10x regression from a prompt change, not to reconcile an invoice.
PRICE_PER_MTOK_USD = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
}
DEFAULT_PRICE = {"input": 3.00, "output": 15.00}


@dataclass
class LLMCallTelemetry:
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


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


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price = PRICE_PER_MTOK_USD.get(model, DEFAULT_PRICE)
    return round((input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000, 6)


async def extract_json(prompt: str, model: str | None = None, max_tokens: int = 512) -> tuple[dict, LLMCallTelemetry]:
    """Send a prompt, return (parsed_json, telemetry). Raises on malformed output rather than
    silently guessing -- a broken contract should surface, not get papered over."""
    resolved_model = model or settings.extraction_model
    client = _get_client()

    started = time.perf_counter()
    response = await client.messages.create(
        model=resolved_model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    text = "".join(block.text for block in response.content if block.type == "text")
    parsed = _extract_json(text)

    telemetry = LLMCallTelemetry(
        model=resolved_model,
        latency_ms=latency_ms,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        estimated_cost_usd=_estimate_cost(resolved_model, response.usage.input_tokens, response.usage.output_tokens),
    )
    return parsed, telemetry
