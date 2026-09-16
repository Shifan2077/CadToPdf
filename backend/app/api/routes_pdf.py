from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.cad.pdf_renderer import render_drawing_pdf
from app.cad.storage import drawings
from app.detection.drawing_detector import DrawingDetector

router = APIRouter()


class PdfRequest(BaseModel):
    upload_id: str


@router.post("/generate-pdf")
async def generate_pdf(request: PdfRequest) -> Response:
    drawing = drawings.get(request.upload_id)
    if drawing is None:
        raise HTTPException(status_code=404, detail="Uploaded drawing not found.")

    result = DrawingDetector().detect(drawing.entities)
    entities = result["clusters"][0]["entities"] if result["clusters"] else []
    pdf_content = render_drawing_pdf(entities, result["bbox"])
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="drawing.pdf"'},
    )
