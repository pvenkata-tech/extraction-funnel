"""
Stage 4 (precision layer) for PDF: the only place an LLM is called, and only on
chunks that survived the lexical filter + section chunker. Negation and subject
attribution are the failure modes that actually matter here — missing "shall
not be limited" would wrongly treat an uncapped-liability contract as capped,
and conflating a subcontractor's liability cap with the vendor's own would
wrongly clear a contract that's actually high-risk.
"""
from common.audit import log_llm_call
from common.config import settings
from common.llm import extract_json

HEDGE_WORDS = ["may", "possibly", "unclear", "subject to further negotiation", "to be determined", "tbd"]

EXTRACTION_PROMPT = """Extract the vendor's liability cap status from the contract excerpt below.
Return ONLY valid JSON: {{"liability_cap_status": "capped" | "uncapped" | "unknown", "confidence": 0.0-1.0, "evidence_span": "<exact quote>"}}

Rules:
- Pay careful attention to negation: "liability shall not be limited", "no cap on liability" -> uncapped
- Distinguish the VENDOR from other parties: a subcontractor's or affiliate's liability cap is about them, not the vendor -> unknown (unless the vendor's own status is also stated)
- If a specific dollar figure or formula caps the vendor's liability (e.g. "limited to fees paid in the preceding 12 months") -> capped
- If the excerpt does not state the vendor's own liability cap status, or explicitly defers it to future negotiation, return "unknown" with confidence 1.0 -- do not guess

Excerpt:
{chunk_text}
"""

VERIFY_PROMPT = """A first pass extracted: {first_pass}

Re-examine the full section below and confirm or correct this extraction.
Focus specifically on negation and whose liability is being described.

Full section:
{full_section_text}

Return the same JSON schema: {{"liability_cap_status": "capped" | "uncapped" | "unknown", "confidence": 0.0-1.0, "evidence_span": "<exact quote>"}}
"""


class NegationAwareExtractor:
    def __init__(self, confidence_threshold: float = None):
        self.confidence_threshold = confidence_threshold or settings.confidence_threshold

    async def extract(self, chunk, session, file_id=None) -> dict:
        prompt = EXTRACTION_PROMPT.format(chunk_text=chunk.text)
        parsed, telemetry = await extract_json(prompt, model=settings.extraction_model)
        log_llm_call(session, file_id, settings.extraction_model, prompt, str(parsed), telemetry=telemetry)
        parsed["extraction_pass"] = 1

        if parsed["confidence"] < self.confidence_threshold or self._looks_ambiguous(parsed):
            parsed = await self._verify_pass(chunk, parsed, session, file_id)

        return parsed

    def _looks_ambiguous(self, parsed: dict) -> bool:
        span = parsed.get("evidence_span", "").lower()
        return any(word in span for word in HEDGE_WORDS)

    async def _verify_pass(self, chunk, first_pass: dict, session, file_id) -> dict:
        prompt = VERIFY_PROMPT.format(first_pass=first_pass, full_section_text=chunk.full_section_text)
        parsed, telemetry = await extract_json(prompt, model=settings.verify_model)
        log_llm_call(session, file_id, settings.verify_model, prompt, str(parsed), telemetry=telemetry)
        parsed["extraction_pass"] = 2
        return parsed
