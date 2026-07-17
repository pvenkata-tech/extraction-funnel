from pdf_pipeline.chunker import chunk_by_section, relevant_chunks

NOTE = """Chief Complaint:
Persistent cough for three weeks.

Social History:
Patient denies any history of smoking or tobacco use.

Assessment:
Diagnosis: lung adenocarcinoma, right upper lobe.
"""


def test_chunk_by_section_splits_on_known_headings():
    chunks = chunk_by_section(NOTE)
    names = [c.section_name for c in chunks]
    assert names == ["chief_complaint", "social_history", "assessment"]
    social = next(c for c in chunks if c.section_name == "social_history")
    assert "denies" in social.text.lower()


def test_no_heading_falls_back_to_unstructured_instead_of_dropping():
    chunks = chunk_by_section("Just a plain paragraph with no section headings at all.")
    assert len(chunks) == 1
    assert chunks[0].section_name == "unstructured"


def test_relevant_chunks_narrows_to_target_sections():
    chunks = chunk_by_section(NOTE)
    narrowed = relevant_chunks(chunks, {"social_history"})
    assert len(narrowed) == 1
    assert narrowed[0].section_name == "social_history"


def test_relevant_chunks_falls_back_to_all_when_target_missing():
    chunks = chunk_by_section(NOTE)
    narrowed = relevant_chunks(chunks, {"nonexistent_section"})
    assert narrowed == chunks
