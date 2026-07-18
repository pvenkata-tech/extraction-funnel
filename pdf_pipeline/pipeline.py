"""
Orchestrates DIVE 2 end to end: ingest -> OCR -> de-identify -> lexical filter
(discard 85-95% here, no LLM cost) -> section chunk -> rule-based
indemnification_present + LLM negation-aware liability_cap_status -> confidence
gate -> HITL or store -> risk-review cohort query.

Run: python -m pdf_pipeline.pipeline sample_data/pdf
Requires ANTHROPIC_API_KEY in .env for the precision layer.
"""
import asyncio
import hashlib
import sys
from pathlib import Path

from common.config import settings
from common.db import get_session, init_db
from common.models import ExtractedField, FileRegistry, HitlReview, SectionChunk
from integrations.notifier import HitlEvent, HitlNotifier
from pdf_pipeline.chunker import chunk_by_section, relevant_chunks
from pdf_pipeline.deid import deidentify
from pdf_pipeline.extractor import NegationAwareExtractor
from pdf_pipeline.lexical_filter import ensure_index, index_document, matches_trigger_vocabulary
from pdf_pipeline.ocr import extract_text

INDEMNIFICATION_TERMS = ["indemnify", "indemnification", "hold harmless"]
INDEMNIFICATION_SECTIONS = {"indemnification", "recitals", "unstructured"}
LIABILITY_SECTIONS = {"limitation_of_liability", "unstructured"}


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _detect_indemnification(chunks) -> tuple[str, float]:
    """Rule-based, no LLM needed: indemnification language has a closed, predictable vocabulary."""
    for chunk in relevant_chunks(chunks, INDEMNIFICATION_SECTIONS):
        lowered = chunk.text.lower()
        if any(term in lowered for term in INDEMNIFICATION_TERMS):
            return "true", 0.95
    return "false", 0.7  # absence of a keyword is weaker evidence than presence


async def _process_file(path: Path, session, extractor: NegationAwareExtractor, notifier: HitlNotifier):
    checksum = _checksum(path)
    if session.query(FileRegistry).filter_by(checksum=checksum).first():
        print(f"[skip] {path.name} already ingested (checksum match)")
        return

    text, ocr_confidence, page_count = extract_text(str(path))
    scrubbed_text, redaction_count = deidentify(text)

    file_row = FileRegistry(
        source_uri=str(path), file_type="pdf", checksum=checksum, page_count=page_count,
    )
    session.add(file_row)
    session.flush()
    print(f"[ingest] {path.name}: {page_count} page(s), OCR confidence {ocr_confidence:.2f}, {redaction_count} sensitive field(s) redacted")

    index_document(str(file_row.id), scrubbed_text)
    if not matches_trigger_vocabulary(str(file_row.id)):
        file_row.ingest_status = "discarded_no_lexical_match"
        print(f"[filter] {path.name}: no trigger terms found -> discarded before any LLM call")
        return
    file_row.lexical_match = True

    chunks = chunk_by_section(scrubbed_text)
    for chunk in chunks:
        session.add(SectionChunk(
            file_id=file_row.id, section_name=chunk.section_name,
            text=chunk.text, full_section_text=chunk.full_section_text,
        ))

    indemnification_value, indemnification_confidence = _detect_indemnification(chunks)
    session.add(ExtractedField(
        file_id=file_row.id, entity_key=path.stem, field_name="indemnification_present",
        value=indemnification_value, confidence=indemnification_confidence, extraction_method="rule",
    ))

    liability_chunks = relevant_chunks(chunks, LIABILITY_SECTIONS)
    target_chunk = liability_chunks[0]
    result = await extractor.extract(target_chunk, session, file_id=file_row.id)

    confidence = float(result["confidence"])
    negation_detected = "uncapped" in result.get("liability_cap_status", "") or "not be limited" in result.get("evidence_span", "").lower()
    extraction_pass = result.get("extraction_pass", 1)

    field = ExtractedField(
        file_id=file_row.id, entity_key=path.stem, field_name="liability_cap_status",
        value=result["liability_cap_status"], confidence=confidence,
        extraction_method="llm", negation_detected=negation_detected, extraction_pass=extraction_pass,
        source_ref={"evidence_span": result.get("evidence_span")},
    )
    session.add(field)
    session.flush()

    if confidence < settings.confidence_threshold:
        reason = "negation_ambiguous" if negation_detected else "low_confidence"
        session.add(HitlReview(extracted_field_id=field.id, reason=reason))
        field.extraction_method = "human_review"
        print(f"[precision] {path.name}: liability_cap_status='{result['liability_cap_status']}' confidence={confidence:.2f} -> HITL queue")
        await notifier.notify(HitlEvent(
            file_name=path.name, entity_key=path.stem, field_name="liability_cap_status",
            value=result["liability_cap_status"], reason=reason,
        ))
    else:
        print(f"[precision] {path.name}: liability_cap_status='{result['liability_cap_status']}' confidence={confidence:.2f} -> stored")


async def run(data_dir: str):
    init_db()
    ensure_index()
    pdf_paths = sorted(Path(data_dir).glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found in {data_dir}")
        return

    extractor = NegationAwareExtractor()
    # One session PER FILE, not one for the whole batch: a single bad file (bad
    # OCR, a malformed LLM response) must not roll back every other file that
    # already succeeded. This is the same "safely re-runnable" property the
    # cheatsheet calls out under idempotency -- one failure shouldn't force
    # reprocessing the whole batch.
    async with HitlNotifier() as notifier:
        for path in pdf_paths:
            try:
                with get_session() as session:
                    await _process_file(path, session, extractor, notifier)
            except Exception as exc:
                print(f"[error] {path.name}: {exc!r} -- skipped, other files unaffected")

    with get_session() as session:
        print("\n--- Risk Review Query: indemnification_present=true AND liability_cap_status=uncapped ---")
        indemnifying_entities = {
            f.entity_key for f in session.query(ExtractedField).filter_by(field_name="indemnification_present", value="true")
        }
        for f in session.query(ExtractedField).filter_by(field_name="liability_cap_status", value="uncapped"):
            if f.entity_key in indemnifying_entities and f.extraction_method != "human_review":
                print(f"  {f.entity_key}  (confidence={f.confidence})")


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else "sample_data/pdf"))
