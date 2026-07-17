"""
De-identification node: strips sensitive identifiers (signer PII, tax IDs) before
any text reaches an LLM call or the audit log. This is a regex-based demo
scrubber — swap for AWS Comprehend or an in-house NER/DLP model in production;
the interface (text in, text out plus a redaction count) stays the same.
"""
import re

PATTERNS = {
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "PHONE": re.compile(r"\b\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
    "EIN": re.compile(r"\bEIN[:\s]*\d{2}-\d{7}\b", re.IGNORECASE),
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}


def deidentify(text: str) -> tuple[str, int]:
    """Returns (scrubbed_text, redaction_count)."""
    redactions = 0
    for label, pattern in PATTERNS.items():
        text, count = pattern.subn(f"[REDACTED_{label}]", text)
        redactions += count
    return text, redactions
