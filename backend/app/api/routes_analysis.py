from __future__ import annotations

from fastapi import APIRouter

from app.detection.drawing_detector import DrawingDetector

router = APIRouter()


@router.post("/analyze")
async def analyze() -> dict[str, object]:
    sample_entities = [
        {"id": "main_1", "entity_type": "LINE", "bbox": (0, 0, 10, 10), "layer": "0"},
        {"id": "main_2", "entity_type": "LINE", "bbox": (1, 1, 9, 9), "layer": "0"},
        {"id": "stray_1", "entity_type": "LINE", "bbox": (1000, 1000, 1010, 1010), "layer": "0"},
    ]

    result = DrawingDetector().detect(sample_entities)
    return {
        "entities_detected": len(sample_entities),
        "candidate_drawing_clusters": 1,
        "selected_primary_cluster": result["selected_cluster"],
        "drawing_size": {
            "width": result["bbox"][2] - result["bbox"][0],
            "height": result["bbox"][3] - result["bbox"][1],
        },
        "bbox": result["bbox"],
    }
