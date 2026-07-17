from unittest.mock import AsyncMock, MagicMock

import pytest

from pdf_pipeline.chunker import Chunk
from pdf_pipeline.extractor import NegationAwareExtractor
from common.llm import LLMCallTelemetry


def _chunk(text="Vendor's liability under this Agreement shall not be limited.") -> Chunk:
    return Chunk(section_name="limitation_of_liability", text=text, full_section_text=text)


def _telemetry(model="claude-haiku-4-5-20251001") -> LLMCallTelemetry:
    return LLMCallTelemetry(model=model, latency_ms=250, input_tokens=120, output_tokens=30, estimated_cost_usd=0.0002)


@pytest.mark.asyncio
async def test_high_confidence_unambiguous_skips_verify_pass(monkeypatch):
    parsed = {"liability_cap_status": "uncapped", "confidence": 0.97, "evidence_span": "shall not be limited"}
    mock_extract = AsyncMock(return_value=(parsed, _telemetry()))
    monkeypatch.setattr("pdf_pipeline.extractor.extract_json", mock_extract)

    result = await NegationAwareExtractor().extract(_chunk(), session=MagicMock())

    assert result["liability_cap_status"] == "uncapped"
    assert result["extraction_pass"] == 1
    assert mock_extract.await_count == 1  # no verify pass needed


@pytest.mark.asyncio
async def test_low_confidence_triggers_verify_pass(monkeypatch):
    first_pass = {"liability_cap_status": "unknown", "confidence": 0.5, "evidence_span": "subcontractor's liability is limited"}
    verify_pass = {"liability_cap_status": "uncapped", "confidence": 0.9, "evidence_span": "vendor's own liability shall not be limited"}
    mock_extract = AsyncMock(side_effect=[(first_pass, _telemetry()), (verify_pass, _telemetry("claude-sonnet-5"))])
    monkeypatch.setattr("pdf_pipeline.extractor.extract_json", mock_extract)

    result = await NegationAwareExtractor().extract(_chunk(), session=MagicMock())

    assert mock_extract.await_count == 2
    assert result["liability_cap_status"] == "uncapped"
    assert result["extraction_pass"] == 2


@pytest.mark.asyncio
async def test_hedge_language_triggers_verify_pass_even_if_confident(monkeypatch):
    first_pass = {"liability_cap_status": "unknown", "confidence": 0.95, "evidence_span": "subject to further negotiation"}
    verify_pass = {"liability_cap_status": "unknown", "confidence": 0.95, "evidence_span": "no cap amount stated for the vendor"}
    mock_extract = AsyncMock(side_effect=[(first_pass, _telemetry()), (verify_pass, _telemetry("claude-sonnet-5"))])
    monkeypatch.setattr("pdf_pipeline.extractor.extract_json", mock_extract)

    result = await NegationAwareExtractor().extract(_chunk(), session=MagicMock())

    assert mock_extract.await_count == 2
    assert result["extraction_pass"] == 2


@pytest.mark.asyncio
async def test_telemetry_is_forwarded_to_audit_log(monkeypatch):
    parsed = {"liability_cap_status": "capped", "confidence": 0.99, "evidence_span": "limited to fees paid in the preceding 12 months"}
    telemetry = _telemetry()
    mock_extract = AsyncMock(return_value=(parsed, telemetry))
    monkeypatch.setattr("pdf_pipeline.extractor.extract_json", mock_extract)

    mock_log = MagicMock()
    monkeypatch.setattr("pdf_pipeline.extractor.log_llm_call", mock_log)

    await NegationAwareExtractor().extract(_chunk(), session=MagicMock(), file_id="f1")

    _, kwargs = mock_log.call_args
    assert kwargs["telemetry"] is telemetry
