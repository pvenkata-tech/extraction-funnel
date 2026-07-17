"""
Generates synthetic vendor-contract PDFs that exercise every branch of DIVE 2:

- 0001: indemnification + explicit "shall not be limited" -> IN the risk-review cohort
- 0002: indemnification + explicit dollar-figure liability cap -> excluded (capped, not missing)
- 0003: no liability/indemnification language at all -> discarded by the lexical filter, never reaches an LLM
- 0004: indemnification + a subcontractor's liability is capped, but the vendor's own liability is
        stated separately as uncapped -> tests "distinguish the vendor from other parties"
- 0005: indemnification + genuinely deferred/hedged liability language -> triggers the verify
        pass and still lands in HITL
- 0006: indemnification, native text stripped so only a rendered image remains -> exercises
        the Tesseract OCR fallback path (requires the Docker image; no text layer to cheat with)

Run: python scripts/generate_pdf_data.py
"""
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path("sample_data/pdf")


def _write_text_pdf(path: Path, title: str, contract_id: str, sections: dict[str, str]):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    y = height - 72

    c.setFont("Helvetica-Bold", 13)
    c.drawString(72, y, f"{title} (Contract ID: {contract_id})")
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


def _write_image_only_pdf(path: Path, title: str, contract_id: str, sections: dict[str, str]):
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
    draw.text((80, y), f"{title} (Contract ID: {contract_id})", font=font_bold, fill="black")
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

    _write_text_pdf(OUT_DIR / "contract_0001.pdf", "Master Services Agreement - TechSupply Corp", "CTR-10023", {
        "Recitals": "This Master Services Agreement is entered into between Acme Industries ('Client') and "
                    "TechSupply Corp ('Vendor') for the provision of cloud infrastructure monitoring services.",
        "Indemnification": "Vendor agrees to indemnify, defend, and hold harmless Client from any third-party "
                            "claims arising out of Vendor's breach of this Agreement or negligent acts.",
        "Limitation of Liability": "Vendor's liability under this Agreement shall not be limited, and Vendor "
                                    "shall be fully liable for all direct and consequential damages arising from "
                                    "a breach of the Indemnification provisions above.",
    })

    _write_text_pdf(OUT_DIR / "contract_0002.pdf", "Master Services Agreement - DataFlow Systems", "CTR-10047", {
        "Recitals": "This Master Services Agreement is entered into between Acme Industries ('Client') and "
                    "DataFlow Systems ('Vendor') for the provision of data pipeline engineering services.",
        "Indemnification": "Vendor shall indemnify and hold harmless Client against losses resulting from "
                            "Vendor's gross negligence or willful misconduct.",
        "Limitation of Liability": "Except for indemnification obligations, Vendor's total liability under this "
                                    "Agreement is limited to the fees paid by Client in the twelve (12) months "
                                    "preceding the claim.",
    })

    _write_text_pdf(OUT_DIR / "contract_0003.pdf", "Equipment Rental Order Form", "ORD-10088", {
        "Order Details": "Rental of one (1) commercial generator, Model GX-400, for the period June 1 through "
                          "June 30, 2026. Delivery to 1200 Industrial Pkwy.",
        "Payment Terms": "Rate: $450 per week. Payment due net 30 from invoice date. No additional terms apply.",
    })

    _write_text_pdf(OUT_DIR / "contract_0004.pdf", "Master Services Agreement - BuildRight Construction", "CTR-10112", {
        "Recitals": "This Master Services Agreement is entered into between Acme Industries ('Client') and "
                    "BuildRight Construction ('Vendor') for general contracting services on the Northgate site.",
        "Indemnification": "Vendor shall indemnify Client for claims arising from work performed under this Agreement.",
        "Affiliates and Subcontractors": "Any subcontractor engaged by Vendor shall carry its own liability "
                                          "insurance, and such subcontractor's liability to Client shall be "
                                          "limited to the value of the subcontract.",
        "Limitation of Liability": "Notwithstanding the subcontractor provisions above, Vendor's own liability "
                                    "under this Agreement shall not be limited, and Vendor remains fully liable "
                                    "for all damages arising from its own performance.",
    })

    _write_text_pdf(OUT_DIR / "contract_0005.pdf", "Master Services Agreement - Meridian Analytics", "CTR-10139", {
        "Recitals": "This Master Services Agreement is entered into between Acme Industries ('Client') and "
                    "Meridian Analytics ('Vendor') for business intelligence consulting services.",
        "Indemnification": "Vendor shall indemnify Client under terms to be finalized in a forthcoming amendment.",
        "Limitation of Liability": "The parties acknowledge that liability cap provisions are subject to further "
                                    "negotiation and are not yet finalized as of the Effective Date. A specific "
                                    "cap amount is to be determined and will be documented in Exhibit B once agreed.",
    })

    _write_image_only_pdf(OUT_DIR / "contract_0006.pdf", "Master Services Agreement - Ironclad Logistics", "CTR-10165", {
        "Recitals": "This Master Services Agreement is entered into between Acme Industries and Ironclad "
                    "Logistics for third-party warehouse fulfillment services",
        "Indemnification": "Vendor agrees to indemnify and hold harmless Client for third-party claims",
        "Limitation of Liability": "Vendor's liability shall not be limited under this Agreement",
    })

    print(f"Wrote {len(list(OUT_DIR.glob('*.pdf')))} PDFs to {OUT_DIR}/")
