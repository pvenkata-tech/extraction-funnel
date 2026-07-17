from common.models import AuditLog


def log_llm_call(session, file_id, model: str, prompt: str, response: str, telemetry=None):
    """Writes into the caller's session/transaction -- file_id may still be
    pending (flushed but uncommitted) in the same transaction, so a separate
    session/connection can't see it yet and would trip the FK constraint.

    telemetry: an llm.LLMCallTelemetry, if the caller has one -- carries
    latency/token/cost data onto the row for scripts/llm_cost_report.py."""
    session.add(AuditLog(
        file_id=file_id, model=model, prompt=prompt, response=response,
        latency_ms=telemetry.latency_ms if telemetry else None,
        input_tokens=telemetry.input_tokens if telemetry else None,
        output_tokens=telemetry.output_tokens if telemetry else None,
        estimated_cost_usd=telemetry.estimated_cost_usd if telemetry else None,
    ))
