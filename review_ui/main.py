"""
Minimal HITL review queue: lists every extracted_field that a HitlReview row
points to and is still unresolved, lets a reviewer accept/correct/reject it.
Run: uvicorn review_ui.main:app --reload --port 8080
"""
from datetime import datetime

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from common.db import get_session
from common.models import ExtractedField, FileRegistry, HitlReview

app = FastAPI(title="Extraction Funnel — HITL Review Queue")
templates = Jinja2Templates(directory="review_ui/templates")


@app.get("/")
def queue(request: Request):
    with get_session() as session:
        pending = (
            session.query(HitlReview, ExtractedField, FileRegistry)
            .join(ExtractedField, HitlReview.extracted_field_id == ExtractedField.id)
            .join(FileRegistry, ExtractedField.file_id == FileRegistry.id)
            .filter(HitlReview.resolution.is_(None))
            .all()
        )
        rows = [
            {
                "review_id": review.id, "reason": review.reason,
                "source_uri": file.source_uri, "entity_key": field.entity_key,
                "field_name": field.field_name, "value": field.value,
                "confidence": field.confidence, "negation_detected": field.negation_detected,
            }
            for review, field, file in pending
        ]
    return templates.TemplateResponse("queue.html", {"request": request, "rows": rows})


@app.post("/review/{review_id}")
def resolve(review_id: str, resolution: str = Form(...), corrected_value: str = Form("")):
    with get_session() as session:
        review = session.get(HitlReview, review_id)
        review.resolution = resolution
        review.reviewed_at = datetime.utcnow()

        field = session.get(ExtractedField, review.extracted_field_id)
        if resolution == "corrected" and corrected_value:
            field.value = corrected_value
            field.confidence = 1.0
        elif resolution == "accepted":
            field.confidence = 1.0
        field.extraction_method = "human_review"

    return RedirectResponse("/", status_code=303)
