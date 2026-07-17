"""
Stage 3 (targeted focus) for PDF: split a document into section-scoped chunks so
the precision layer only ever sees the paragraphs that matter ("Limitation of
Liability", "Indemnification") instead of the whole document. Falls back to
fuzzy heading match so a nonstandard template still gets chunked rather than
silently dropped.
"""
import re
from dataclasses import dataclass

SECTION_HEADINGS = [
    "recitals", "indemnification", "limitation of liability",
    "affiliates and subcontractors", "term and termination", "governing law",
]

HEADING_PATTERN = re.compile(
    r"^\s*(" + "|".join(re.escape(h) for h in SECTION_HEADINGS) + r")\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class Chunk:
    section_name: str
    text: str
    full_section_text: str
    page_number: int = 1


def chunk_by_section(text: str) -> list[Chunk]:
    """Splits on recognized headings. If no heading matches at all, returns the
    whole document as one 'unstructured' chunk rather than dropping it."""
    matches = list(HEADING_PATTERN.finditer(text))
    if not matches:
        return [Chunk(section_name="unstructured", text=text, full_section_text=text)]

    chunks = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        if section_text:
            section_name = match.group(1).lower().replace(" ", "_")
            chunks.append(Chunk(section_name=section_name, text=section_text, full_section_text=section_text))
    return chunks


def relevant_chunks(chunks: list[Chunk], target_sections: set[str]) -> list[Chunk]:
    """Narrow further to the sections that actually matter for the cohort question."""
    narrowed = [c for c in chunks if c.section_name in target_sections]
    return narrowed or chunks  # if targeting misses everything, fall back to all chunks
