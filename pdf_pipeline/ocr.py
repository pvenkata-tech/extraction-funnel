"""
Stage 1 (ingest) for PDF: convert raw bytes into uniform text.

Native-text PDFs go through PyMuPDF directly (fast, no OCR needed). Scanned/faxed
PDFs with no text layer fall back to Tesseract over rendered page images — the
Textract-equivalent for a local/portfolio deployment. Every page reports a
confidence so low-quality scans can be routed to a second pass or HITL, exactly
like the cheatsheet's OCR failure mode.
"""
import fitz  # PyMuPDF
import pytesseract
from PIL import Image

MIN_NATIVE_TEXT_CHARS_PER_PAGE = 20  # below this, assume no usable text layer -> OCR


def extract_text(pdf_path: str) -> tuple[str, float, int]:
    """Returns (full_text, mean_confidence, page_count)."""
    doc = fitz.open(pdf_path)
    pages_text = []
    confidences = []

    for page in doc:
        native_text = page.get_text().strip()
        if len(native_text) >= MIN_NATIVE_TEXT_CHARS_PER_PAGE:
            pages_text.append(native_text)
            confidences.append(1.0)  # native text layer: no OCR uncertainty
            continue

        pix = page.get_pixmap(dpi=300)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        ocr_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        words = [w for w in ocr_data["text"] if w.strip()]
        word_confidences = [int(c) for c, w in zip(ocr_data["conf"], ocr_data["text"]) if w.strip() and int(c) >= 0]

        pages_text.append(" ".join(words))
        confidences.append((sum(word_confidences) / len(word_confidences) / 100) if word_confidences else 0.0)

    doc.close()
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return "\n\n".join(pages_text), round(mean_confidence, 3), len(pages_text)
