"""
Stage 4 (precision layer) for PDF: the only place an LLM is called, and only on
chunks that survived the lexical filter + section chunker. Negation and subject
attribution are the failure modes that actually matter clinically — missing
"denies smoking" would wrongly include a non-smoker in a smoker cohort.
"""
from common.audit import log_llm_call
from common.config import settings
from common.llm import extract_json

HEDGE_WORDS = ["may", "possibly", "unclear", "history includes", "unsure"]

EXTRACTION_PROMPT = """Extract the patient's smoking status from the clinical note excerpt below.
Return ONLY valid JSON: {{"smoking_status": "smoker" | "non_smoker" | "unknown", "confidence": 0.0-1.0, "evidence_span": "<exact quote>"}}

Rules:
- Pay careful attention to negation: "denies smoking", "non-smoker", "never smoked" -> non_smoker
- Distinguish the PATIENT from other people: "father smoked 2 packs/day" is about the father, not the patient -> unknown (unless patient status is also stated)
- Distinguish current from historical: "quit smoking in 2019" -> non_smoker (current status), but note it in evidence_span
- If the excerpt does not mention the patient's own smoking status, return "unknown" with confidence 1.0 -- do not guess

Excerpt:
{chunk_text}
"""

VERIFY_PROMPT = """A first pass extracted: {first_pass}

Re-examine the full section below and confirm or correct this extraction.
Focus specifically on negation and whose smoking status is being described.

Full section:
{full_section_text}

Return the same JSON schema: {{"smoking_status": "smoker" | "non_smoker" | "unknown", "confidence": 0.0-1.0, "evidence_span": "<exact quote>"}}
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
