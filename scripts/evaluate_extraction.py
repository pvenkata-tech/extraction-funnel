"""
Regression eval for the precision layer: runs the real extractor (a live Claude
call, not a mock) against a small hand-labeled gold set and reports per-class
precision/recall/accuracy for liability_cap_status, plus accuracy for the
rule-based indemnification_present field.

This is the answer to "how do you know a prompt change didn't quietly make
extraction worse": change EXTRACTION_PROMPT or VERIFY_PROMPT in
pdf_pipeline/extractor.py, rerun this script, and compare against the
committed baseline below. Exits non-zero if accuracy drops under the
threshold, so it's usable as a CI gate on prompt changes.

Six labeled examples is a floor, not a target -- in production this gold set
should grow with every HITL correction the review queue produces (see
review_ui/), not stay hand-curated forever.

Run: python -m scripts.evaluate_extraction
Requires a real ANTHROPIC_API_KEY -- costs a handful of Haiku/Sonnet calls.
"""
import asyncio
import sys
from pathlib import Path

from pdf_pipeline.chunker import chunk_by_section, relevant_chunks
from pdf_pipeline.deid import deidentify
from pdf_pipeline.extractor import NegationAwareExtractor
from pdf_pipeline.ocr import extract_text
from pdf_pipeline.pipeline import LIABILITY_SECTIONS, _detect_indemnification

ACCURACY_GATE = 0.80  # fail CI if liability_cap_status accuracy drops below this

# Ground truth for sample_data/pdf/*.pdf, established when the fixtures were
# authored (scripts/generate_pdf_data.py). Expand this as new fixtures are added.
GOLD_SET = [
    {"file": "contract_0001.pdf", "liability_cap_status": "uncapped", "indemnification_present": "true"},
    {"file": "contract_0002.pdf", "liability_cap_status": "capped", "indemnification_present": "true"},
    {"file": "contract_0004.pdf", "liability_cap_status": "uncapped", "indemnification_present": "true"},  # subcontractor trap
    {"file": "contract_0005.pdf", "liability_cap_status": "unknown", "indemnification_present": "true"},   # genuinely ambiguous
    {"file": "contract_0006.pdf", "liability_cap_status": "uncapped", "indemnification_present": "true"},  # OCR fallback path
]


class FakeSession:
    """The extractor writes audit-log rows through the caller's session; this
    eval doesn't need a database, so it just swallows them."""
    def add(self, _obj):
        pass


async def evaluate(data_dir: str):
    extractor = NegationAwareExtractor()
    predictions = []

    for example in GOLD_SET:
        path = Path(data_dir) / example["file"]
        text, _, _ = extract_text(str(path))
        scrubbed, _ = deidentify(text)
        chunks = chunk_by_section(scrubbed)

        indemnification_pred, _ = _detect_indemnification(chunks)
        liability_chunk = relevant_chunks(chunks, LIABILITY_SECTIONS)[0]
        result = await extractor.extract(liability_chunk, session=FakeSession())

        predictions.append({
            "file": example["file"],
            "liability_expected": example["liability_cap_status"],
            "liability_predicted": result["liability_cap_status"],
            "indemnification_expected": example["indemnification_present"],
            "indemnification_predicted": indemnification_pred,
        })

    return predictions


def _precision_recall(predictions, label: str) -> tuple[float, float]:
    tp = sum(1 for p in predictions if p["liability_predicted"] == label and p["liability_expected"] == label)
    fp = sum(1 for p in predictions if p["liability_predicted"] == label and p["liability_expected"] != label)
    fn = sum(1 for p in predictions if p["liability_predicted"] != label and p["liability_expected"] == label)
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    return precision, recall


def report(predictions) -> float:
    print(f"{'file':<20} {'liability: expected -> predicted':<38} {'indemnification: exp -> pred':<30} match")
    correct = 0
    for p in predictions:
        liability_match = p["liability_expected"] == p["liability_predicted"]
        indemnification_match = p["indemnification_expected"] == p["indemnification_predicted"]
        correct += int(liability_match)
        flag = "OK" if liability_match and indemnification_match else "MISMATCH"
        print(
            f"{p['file']:<20} "
            f"{p['liability_expected'] + ' -> ' + p['liability_predicted']:<38} "
            f"{p['indemnification_expected'] + ' -> ' + p['indemnification_predicted']:<30} {flag}"
        )

    accuracy = correct / len(predictions)
    print(f"\nliability_cap_status accuracy: {accuracy:.1%} ({correct}/{len(predictions)})")

    for label in ("capped", "uncapped", "unknown"):
        precision, recall = _precision_recall(predictions, label)
        print(f"  {label:<12} precision={precision:.2f}  recall={recall:.2f}")

    return accuracy


if __name__ == "__main__":
    predictions = asyncio.run(evaluate(sys.argv[1] if len(sys.argv) > 1 else "sample_data/pdf"))
    accuracy = report(predictions)

    if accuracy < ACCURACY_GATE:
        print(f"\nFAILED: accuracy {accuracy:.1%} is below the {ACCURACY_GATE:.0%} gate.")
        sys.exit(1)
