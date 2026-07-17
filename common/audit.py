from common.models import AuditLog


def log_llm_call(session, file_id, model: str, prompt: str, response: str):
    """Writes into the caller's session/transaction -- file_id may still be
    pending (flushed but uncommitted) in the same transaction, so a separate
    session/connection can't see it yet and would trip the FK constraint."""
    session.add(AuditLog(file_id=file_id, model=model, prompt=prompt, response=response))
