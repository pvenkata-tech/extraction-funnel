from pdf_pipeline.chunker import chunk_by_section, relevant_chunks

CONTRACT = """Recitals:
This Agreement is entered into between Acme Industries and Vendor Corp.

Limitation of Liability:
Vendor's liability under this Agreement shall not be limited.

Indemnification:
Vendor shall indemnify Client for third-party claims arising from breach.
"""


def test_chunk_by_section_splits_on_known_headings():
    chunks = chunk_by_section(CONTRACT)
    names = [c.section_name for c in chunks]
    assert names == ["recitals", "limitation_of_liability", "indemnification"]
    liability = next(c for c in chunks if c.section_name == "limitation_of_liability")
    assert "shall not be limited" in liability.text.lower()


def test_no_heading_falls_back_to_unstructured_instead_of_dropping():
    chunks = chunk_by_section("Just a plain paragraph with no section headings at all.")
    assert len(chunks) == 1
    assert chunks[0].section_name == "unstructured"


def test_relevant_chunks_narrows_to_target_sections():
    chunks = chunk_by_section(CONTRACT)
    narrowed = relevant_chunks(chunks, {"limitation_of_liability"})
    assert len(narrowed) == 1
    assert narrowed[0].section_name == "limitation_of_liability"


def test_relevant_chunks_falls_back_to_all_when_target_missing():
    chunks = chunk_by_section(CONTRACT)
    narrowed = relevant_chunks(chunks, {"nonexistent_section"})
    assert narrowed == chunks
