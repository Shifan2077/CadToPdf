from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.cad.storage import drawings
from app.detection.drawing_detector import DrawingDetector

router = APIRouter()


@router.get("/preview/{drawing_id}")
async def preview(drawing_id: str) -> dict[str, object]:
    drawing = drawings.get(drawing_id)
    if drawing is None:
        raise HTTPException(status_code=404, detail="Uploaded drawing not found.")
    result = DrawingDetector().detect(drawing.entities)
    entities = result["clusters"][0]["entities"] if result["clusters"] else []
    return {"bbox": result["bbox"], "entities": entities}