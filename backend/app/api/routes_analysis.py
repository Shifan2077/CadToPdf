from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.cad.storage import drawings
from app.detection.drawing_detector import DrawingDetector

router = APIRouter()


class AnalysisRequest(BaseModel):
    upload_id: str


@router.post("/analyze")
async def analyze(request: AnalysisRequest) -> dict[str, object]:
    drawing = drawings.get(request.upload_id)
    if drawing is None:
        raise HTTPException(status_code=404, detail="Uploaded drawing not found.")

    result = DrawingDetector().detect(drawing.entities)
    dimensions_detected = sum(entity["entity_type"] == "DIMENSION" for entity in drawing.entities)
    annotations_detected = sum(
        entity["entity_type"] in {"TEXT", "MTEXT", "DIMENSION"}
        for entity in drawing.entities
    )
    detailed_dimensions = [
        entity["measurement"]
        for entity in drawing.entities
        if entity["entity_type"] == "DIMENSION" and "measurement" in entity
    ]
    return {
        "upload_id": request.upload_id,
        "entities_detected": len(drawing.entities),
        "candidate_drawing_clusters": len(result["clusters"]),
        "dimensions_detected": dimensions_detected,
        "detailed_dimensions": detailed_dimensions,
        "annotations_detected": annotations_detected,
        "selected_primary_cluster": result["selected_cluster"],
        "drawing_size": {
            "width": result["bbox"][2] - result["bbox"][0],
            "height": result["bbox"][3] - result["bbox"][1],
        },
        "bbox": result["bbox"],
    }
