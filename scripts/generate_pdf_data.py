"""
Generates synthetic clinical-note PDFs that exercise every branch of DIVE 2:

- 0001: cancer diagnosis + explicit patient negation -> IN the cohort
- 0002: cancer diagnosis + explicit patient smoker -> excluded (wrong status, not missing)
- 0003: no cancer/smoking vocabulary at all -> discarded by the lexical filter, never reaches an LLM
- 0004: cancer diagnosis + family-history smoking only, patient's own status stated separately
        as non-smoker -> tests "distinguish patient from other people"
- 0005: cancer diagnosis + genuinely hedged/ambiguous smoking history -> triggers the verify
        pass and still lands in HITL
- 0006: cancer diagnosis, native text stripped so only a rendered image remains -> exercises
        the Tesseract OCR fallback path (requires the Docker image; no text layer to cheat with)

Run: python scripts/generate_pdf_data.py
"""
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path("sample_data/pdf")


def _write_text_pdf(path: Path, patient_name: str, mrn: str, sections: dict[str, str]):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    y = height - 72

    c.setFont("Helvetica-Bold", 13)
    c.drawString(72, y, f"Clinical Note — {patient_name} (MRN: {mrn})")
    y -= 28

    for heading, body in sections.items():
        c.setFont("Helvetica-Bold", 11)
        c.drawString(72, y, f"{heading}:")
        y -= 16
        c.setFont("Helvetica", 10)
        for line in _wrap(body, 95):
            c.drawString(72, y, line)
            y -= 14
        y -= 10

    c.save()


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def _write_image_only_pdf(path: Path, patient_name: str, mrn: str, sections: dict[str, str]):
    """No text layer at all -- the page is a single rasterized image, forcing
    the OCR fallback path in pdf_pipeline/ocr.py instead of native text extraction."""
    img = Image.new("RGB", (1700, 2200), "white")
    draw = ImageDraw.Draw(img)
    try:
        font_bold = ImageFont.truetype("arialbd.ttf", 34)
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font_bold = font = ImageFont.load_default()

    y = 80
    draw.text((80, y), f"Clinical Note - {patient_name} (MRN: {mrn})", font=font_bold, fill="black")
    y += 70

    for heading, body in sections.items():
        draw.text((80, y), f"{heading}:", font=font_bold, fill="black")
        y += 45
        for line in _wrap(body, 70):
            draw.text((80, y), line, font=font, fill="black")
            y += 38
        y += 25

    img_path = path.with_suffix(".png")
    img.save(img_path)

    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.drawImage(str(img_path), 0, 0, width=LETTER[0], height=LETTER[1])
    c.save()
    img_path.unlink()


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    _write_text_pdf(OUT_DIR / "patient_0001.pdf", "Jordan Ellis", "MRN10023", {
        "Chief Complaint": "Follow-up after abnormal mammogram.",
        "Assessment": "Diagnosis: Stage II invasive ductal carcinoma, left breast. "
                      "Recommend oncology referral for treatment planning.",
        "Social History": "Patient denies any history of smoking or tobacco use. "
                           "Drinks alcohol socially, exercises regularly.",
    })

    _write_text_pdf(OUT_DIR / "patient_0002.pdf", "Sam Whitfield", "MRN10047", {
        "Chief Complaint": "Persistent cough and unintentional weight loss.",
        "Assessment": "Diagnosis: Lung adenocarcinoma, right upper lobe, confirmed on biopsy.",
        "Social History": "Patient reports current smoking, approximately one pack per day "
                           "for the past 20 years. Expressed interest in cessation resources.",
    })

    _write_text_pdf(OUT_DIR / "patient_0003.pdf", "Priya Nair", "MRN10088", {
        "Chief Complaint": "Annual physical examination, no acute concerns.",
        "Assessment": "Routine wellness visit. Cholesterol panel within normal limits. "
                      "Seasonal allergies noted, continue current antihistamine.",
        "Plan": "Return in 12 months for annual physical, or sooner if symptoms arise.",
    })

    _write_text_pdf(OUT_DIR / "patient_0004.pdf", "Marcus Boyd", "MRN10112", {
        "Chief Complaint": "Elevated PSA on routine screening.",
        "Assessment": "Diagnosis: Prostate cancer, localized, Gleason score 6.",
        "Family History": "Notable for father's heavy tobacco use for over 30 years and "
                           "subsequent death from lung cancer at age 68.",
        "Social History": "Patient himself has never smoked and has no personal tobacco history.",
    })

    _write_text_pdf(OUT_DIR / "patient_0005.pdf", "Elena Voss", "MRN10139", {
        "Chief Complaint": "Blood in stool, referred for colonoscopy follow-up.",
        "Assessment": "Diagnosis: Colorectal cancer, stage III, post-resection follow-up.",
        "Social History": "Smoking history unclear from available records; patient may have "
                           "quit at some point but duration and quantity are not documented "
                           "in this chart. History includes possibly intermittent use.",
    })

    _write_image_only_pdf(OUT_DIR / "patient_0006.pdf", "Grace Kim", "MRN10165", {
        "Chief Complaint": "Referred for suspicious thyroid nodule",
        "Assessment": "Diagnosis - papillary thyroid carcinoma confirmed on fine needle aspiration",
        "Social History": "Patient denies ever smoking or using any tobacco products",
    })

    print(f"Wrote {len(list(OUT_DIR.glob('*.pdf')))} PDFs to {OUT_DIR}/")
