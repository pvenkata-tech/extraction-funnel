"""
De-identification node: strips obvious PHI/PII before any text reaches an LLM call
or the audit log. This is a regex-based demo scrubber — swap for AWS Comprehend
Medical or an in-house NER model in production; the interface (text in, text out
plus a redaction count) stays the same.
"""
import re

PATTERNS = {
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "PHONE": re.compile(r"\b\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
    "MRN": re.compile(r"\bMRN[:\s]*\d{6,10}\b", re.IGNORECASE),
    "DOB": re.compile(r"\b(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/(19|20)\d{2}\b"),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}


def deidentify(text: str) -> tuple[str, int]:
    """Returns (scrubbed_text, redaction_count)."""
    redactions = 0
    for label, pattern in PATTERNS.items():
        text, count = pattern.subn(f"[REDACTED_{label}]", text)
        redactions += count
    return text, redactions
